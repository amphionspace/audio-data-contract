#!/usr/bin/env python3
"""16 kHz training version of the MIT environmental impulse response survey.

mit_ir_survey@modelscope-benjamin-paine-20261025 stores the 270 RIRs as 32 kHz 24-bit WAV bytes inside a parquet, which
the training loader's RIR pool (lhotse recordings) cannot read. This decodes each RIR, resamples it 2:1 to 16 kHz
(polyphase, scipy.signal.resample_poly), writes it as 24-bit FLAC, and appends mit_ir_survey@flac16k-20261026 (split
all, lhotse recordings) to catalog/mit_ir_survey.yaml. Files are named by survey id (mit-ir-NNN.flac): the far-field
RIR selection keys on "far" in the file name, and these 1.5 m recordings belong to the ordinary RIR pool.

    python build_mit_ir_survey_16k.py --catalog catalog
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
import yaml
from scipy.signal import resample_poly

ROOT = Path("/workspace/data/datasets/mit_ir_survey")
SOURCE = ROOT / "source/modelscope-benjamin-paine-20261025/data/train-00000-of-00001.parquet"
VERSION = "flac16k-20261026"
OUT = ROOT / "versions" / VERSION
RATE = 16000


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    target = args.catalog / "mit_ir_survey.yaml"
    if any(e["version"] == VERSION for e in yaml.safe_load(target.read_text())):
        raise SystemExit(f"mit_ir_survey@{VERSION} is already in {target}")
    (OUT / "audio").mkdir(parents=True, exist_ok=True)
    (OUT / "manifests").mkdir(exist_ok=True)
    recordings, seconds = [], 0.0
    for row in sorted(pq.read_table(SOURCE).to_pylist(), key=lambda r: r["id"]):
        audio, rate = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float64", always_2d=True)
        assert rate == 32000 and audio.shape[1] == 1, (row["id"], rate, audio.shape)
        rir = resample_poly(audio[:, 0], 1, 2)
        rir = rir / max(1.0, float(np.max(np.abs(rir))))  # keep 24-bit FLAC from clipping; the training loaders divide each RIR by its energy
        path = OUT / "audio" / f"mit-ir-{row['id']:03d}.flac"
        sf.write(path, rir.astype(np.float32), RATE, subtype="PCM_24")
        frames = sf.info(path).frames
        seconds += frames / RATE
        recordings.append({"id": f"mit-ir-{row['id']:03d}", "sources": [{"type": "file", "channels": [0], "source": str(path)}],
                           "sampling_rate": RATE, "num_samples": frames, "duration": frames / RATE, "channel_ids": [0],
                           "custom": {"location": row["location"], "detail": row["detail"], "source_file": row["audio"]["path"]}})
    manifest = OUT / "manifests/mit_ir_survey_recordings_all.jsonl.gz"
    with gzip.open(manifest, "wt", encoding="utf-8") as stream:
        for row in recordings:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": "mit_ir_survey", "version": VERSION, "languages": ["und"],
             "tasks": ["rir"], "aliases": [],
             "artifacts": [{"name": "recordings", "kind": "lhotse-recordings", "root_alias": "mit_ir_survey",
                            "relative_path": manifest.relative_to(ROOT).as_posix(), "expected_bytes": manifest.stat().st_size,
                            "sha256": sha256(manifest), "metadata": {"record_count": len(recordings)}}],
             "splits": {"all": {"artifacts": {"recordings": ["recordings"]},
                                "statistics": {"num_rirs": len(recordings), "duration_hours": round(seconds / 3600, 4),
                                               "duration_basis": "sum of impulse response lengths"}}},
             "provenance": {"source": "mit_ir_survey@modelscope-benjamin-paine-20261025", "derived_from": "mit_ir_survey@modelscope-benjamin-paine-20261025",
                            "snapshot_date": "2026-10-26", "license": "CC BY 4.0",
                            "description": "MIT 真实环境冲激响应的 16 kHz 训练版：270 条 RIR 从 32 kHz 按 2:1 多相滤波降采样到 16 kHz，存成 24 位单声道 FLAC，"
                                           "带 lhotse 录音清单，可直接放进训练的 rir_sources。文件按调查编号命名（mit-ir-NNN），custom 里保留场所类别、说明与原文件名。",
                            "integrity": "local_sha256_recorded"}}
    with open(target, "a", encoding="utf-8") as stream:
        if not target.read_text().endswith("\n"):
            stream.write("\n")
        stream.write(yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=120))
    print(f"{len(recordings)} RIRs, {seconds / 60:.1f} min, appended mit_ir_survey@{VERSION} to {target}")


if __name__ == "__main__":
    main()
