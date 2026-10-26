#!/usr/bin/env python3
"""Lhotse manifests for the CHiME-4 real 1-channel track (dt05_real, et05_real) and their catalog entry.

chime4@hf-prummn-20261023 registers the extracted package as source directories only, which AmphionEval and the
training loader cannot read. This writes one recording and one supervision per isolated_1ch_track utterance of the
real dev and eval sets (the track the challenge scores single-channel WER on), with the transcript from the
utterance's .trn file (the challenge's normalised reference, upper case, spelled acronyms like "N. E. C."), and
appends chime4@isolated-1ch-20261026 to catalog/chime4.yaml. Audio stays where it is; nothing is copied.

    python build_chime4_1ch_manifests.py --catalog catalog
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import soundfile as sf
import yaml

ROOT = Path("/workspace/data/datasets/chime4")
SOURCE = ROOT / "source/hf-prummn-20261023/extracted/CHiME4/data"
VERSION = "isolated-1ch-20261026"
OUT = ROOT / "versions" / VERSION / "manifests"
SPLITS = ("dt05_real", "et05_real")
ENVIRONMENTS = ("bus", "caf", "ped", "str")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build(split):
    stage, kind = split.split("_")
    recordings, supervisions = [], []
    for environment in ENVIRONMENTS:
        name = f"{stage}_{environment}_{kind}"
        for wav in sorted((SOURCE / "audio/16kHz/isolated_1ch_track" / name).glob("*.wav")):
            utterance = wav.stem
            line = (SOURCE / "transcriptions" / name / f"{utterance}.trn").read_text().strip()
            label, text = line.split(" ", 1)
            assert label == utterance, (wav, label)
            info = sf.info(str(wav))
            assert info.samplerate == 16000 and info.channels == 1, wav
            recordings.append({"id": utterance, "sources": [{"type": "file", "channels": [0], "source": str(wav)}],
                               "sampling_rate": 16000, "num_samples": info.frames, "duration": info.frames / 16000,
                               "channel_ids": [0]})
            supervisions.append({"id": utterance, "recording_id": utterance, "start": 0.0,
                                 "duration": info.frames / 16000, "channel": 0, "text": text, "language": "en",
                                 "speaker": utterance.split("_")[0],
                                 "custom": {"environment": environment.upper(), "track": "isolated_1ch_track"}})
    return recordings, supervisions


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    target = args.catalog / "chime4.yaml"
    if any(e["version"] == VERSION for e in yaml.safe_load(target.read_text())):
        raise SystemExit(f"chime4@{VERSION} is already in {target}")
    OUT.mkdir(parents=True, exist_ok=True)
    artifacts, splits = [], {}
    for split in SPLITS:
        recordings, supervisions = build(split)
        for role, rows in (("recordings", recordings), ("supervisions", supervisions)):
            path = OUT / f"chime4_{role}_{split}.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            artifacts.append({"name": f"{split}_{role}", "kind": f"lhotse-{role}", "root_alias": "chime4",
                              "relative_path": path.relative_to(ROOT).as_posix(), "expected_bytes": path.stat().st_size,
                              "sha256": sha256(path), "metadata": {"record_count": len(rows)}})
        splits[split] = {"artifacts": {"recordings": [f"{split}_recordings"], "supervisions": [f"{split}_supervisions"]},
                         "task": "asr",
                         "statistics": {"utterances": len(supervisions),
                                        "speakers": len({s["speaker"] for s in supervisions}),
                                        "duration_hours": round(sum(r["duration"] for r in recordings) / 3600, 4),
                                        "duration_basis": "sum of utterance audio lengths"}}
        print(split, splits[split]["statistics"])
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": "chime4", "version": VERSION, "languages": ["en"],
             "tasks": ["asr"], "aliases": [], "artifacts": artifacts, "splits": splits,
             "provenance": {
                 "source": "chime4@hf-prummn-20261023 (CHiME-4 challenge package, community mirror Prummn/chime4)",
                 "snapshot_date": "2026-10-26",
                 "license": "Real CHiME data CC BY-NC-SA 2.0 UK (non-commercial); WSJ0 prompts LDC93S6A.",
                 "description": "CHiME-4 真实录音 1 通道 track 的评测清单：dev（dt05_real，1,640 条）和 eval（et05_real，1,320 条），"
                                "公交 / 咖啡馆 / 步行街 / 街道四种环境，每组 4 个说话人，英文 16 kHz。音频是 hf-prummn-20261023 解包目录里的"
                                " isolated_1ch_track 原文件（不复制），参考文本取每条的 .trn（挑战赛官方规范化文本：大写，缩写拼成 N. E. C.）。"
                                "只能评测：训练音频 tr05 属于完整 CHiME-3（LDC），公开渠道没有；常用 et05_real 报单通道 WER。",
                 "derived_from": "chime4@hf-prummn-20261023",
                 "integrity": "local_sha256_recorded"}}
    text = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=120)
    with open(target, "a", encoding="utf-8") as stream:
        if not target.read_text().endswith("\n"):
            stream.write("\n")
        stream.write(text)
    print(f"appended chime4@{VERSION} to {target}")


if __name__ == "__main__":
    main()
