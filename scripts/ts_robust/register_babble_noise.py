#!/usr/bin/env python3
"""Make the train split of babble_noise_synth usable as training noise and write its catalog entry.

babble_noise_synth lists its clips as a source directory plus a manifest, which the training loader cannot
read as noise. This writes Lhotse recordings for the zh and en train clips (2,600 each, 30 s, 5-20 speakers
talking at once) as the new dataset ``babble_noise_train``. The benchmark's babble uses the dev/test speakers,
which share no speaker with train.

    python scripts/ts_robust/register_babble_noise.py --catalog catalog --version v1-20261017
"""

import argparse
import hashlib
import json
from pathlib import Path

from lhotse import AudioSource, Recording, RecordingSet
from ruamel.yaml import YAML

DATA = Path("/workspace/data")
SOURCE = DATA / "datasets/noise_open/babble_synth"
ROOT_ALIAS = "aidc_data"
SR = 16000
DESCRIPTION = (
    "训练用合成背景人声（babble）：babble_noise_synth 的 zh、en 训练划分（每种语言 2,600 条，30 秒，5–20 位说话人同时说，"
    "16 kHz 单声道 FLAC），按 Lhotse 录音清单登记，可作为 noise_sources 或空目标的 nonspeech_sources。"
    "评测的 babble 用 dev/test 说话人，与训练说话人互不重叠。脚本 scripts/ts_robust/register_babble_noise.py。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    output = DATA / "datasets/babble_noise_train/source" / args.version / "recordings"
    output.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in (SOURCE / "manifest.jsonl").read_text().splitlines() if line.strip()]
    artifacts, splits = [], {}
    for language in ("zh", "en"):
        clips = sorted((r for r in rows if r["language"] == language and r["split"] == "train"), key=lambda r: r["id"])
        recordings = []
        for row in clips:
            path = SOURCE / row["path"]
            if not path.is_file() or row["sampling_rate"] != SR:
                raise SystemExit(f"{row['id']}: missing file or unexpected sampling rate")
            recordings.append(Recording(id=row["id"], sources=[AudioSource("file", [0], str(path))], sampling_rate=SR,
                                        num_samples=round(row["duration"] * SR), duration=row["duration"]))
        target = output / f"babble_{language}_recordings.jsonl.gz"
        RecordingSet.from_recordings(recordings).to_file(target)
        hours = sum(r.duration for r in recordings) / 3600
        artifacts.append({"name": f"{language}-recordings", "kind": "lhotse-recordings", "root_alias": ROOT_ALIAS,
                          "relative_path": target.relative_to(DATA).as_posix(), "expected_bytes": target.stat().st_size,
                          "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                          "metadata": {"record_count": len(recordings)}})
        splits[language] = {"artifacts": {"recordings": [f"{language}-recordings"]}, "task": "noise",
                            "statistics": {"records": len(recordings), "duration_hours": round(hours, 2)}}
        print(language, len(recordings), round(hours, 2), flush=True)
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": "babble_noise_train", "version": args.version,
             "languages": ["zh", "en"], "tasks": ["noise"], "aliases": [], "artifacts": artifacts, "splits": splits,
             "provenance": {"status": "complete", "synthetic": "none", "snapshot_date": args.version.split("-")[-1],
                            "source": "babble_noise_synth@v1-20261013", "description": DESCRIPTION}}
    yaml = YAML()
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=2, offset=0)
    with open(args.catalog / "babble_noise_train.yaml", "w", encoding="utf-8") as stream:
        yaml.dump([entry], stream)


if __name__ == "__main__":
    main()
