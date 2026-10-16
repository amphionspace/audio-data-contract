#!/usr/bin/env python3
"""Write the catalog declaration of the dns5_noise_train recordings made by prepare_training_noise.py.

    python scripts/ts_robust/register_training_noise.py --catalog catalog --version v1-20261016
"""

import argparse
import hashlib
import json
from pathlib import Path

from ruamel.yaml import YAML

DATA = Path("/workspace/data")
ROOT_ALIAS = "aidc_data"
SPLITS = {"audioset": "noise", "freesound": "noise", "stationary": "noise", "rir": "rir"}
DESCRIPTION = (
    "训练用 DNS5 噪声与模拟房间响应：AudioSet 与 Freesound 噪声（16 kHz 单声道 FLAC，≤30 s，RMS 归一到 −30 dBFS），"
    "stationary 为电平稳定、适合做噪声底的片段；rir 为 impulse_responses_000 的模拟房间响应。"
    "已跳过 ts_asr_benchmark v3 用到的片段与哈希最小的 300 个响应，训练与评测互不重叠。"
    "提取脚本 scripts/ts_robust/prepare_training_noise.py。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    source = DATA / "datasets/dns5_noise_train/source" / args.version
    report = json.loads((source / "report.json").read_text())
    artifacts, splits = [], {}
    for split, task in SPLITS.items():
        path = source / "recordings" / f"dns5_{split}_recordings.jsonl.gz"
        artifacts.append({"name": f"{split}-recordings", "kind": "lhotse-recordings", "root_alias": ROOT_ALIAS,
                          "relative_path": path.relative_to(DATA).as_posix(),
                          "expected_bytes": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "metadata": {"record_count": report[split]["recordings"]}})
        splits[split] = {"artifacts": {"recordings": [f"{split}-recordings"]}, "task": task,
                         "statistics": {"records": report[split]["recordings"], "duration_hours": report[split]["hours"]}}
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": "dns5_noise_train", "version": args.version,
             "languages": ["und"], "tasks": ["noise", "rir"], "aliases": [], "artifacts": artifacts, "splits": splits,
             "provenance": {"status": "complete", "synthetic": "none", "snapshot_date": "2026-10-16",
                            "source": "dns5_noise_rir@official-noise-rir-20260924", "description": DESCRIPTION}}
    yaml = YAML()
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=2, offset=0)
    with open(args.catalog / "dns5_noise_train.yaml", "w", encoding="utf-8") as stream:
        yaml.dump([entry], stream)


if __name__ == "__main__":
    main()
