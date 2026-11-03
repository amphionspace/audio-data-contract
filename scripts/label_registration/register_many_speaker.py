"""Register the 6-12 speaker word-level synthetic mixtures as sot_many_speaker_word_zh_en@word-v1-20261008.

The data was generated on 2026-10-08 by amphiondata feat/many-speaker-word-level-synthesis (docs/many-speaker-word-
synthesis.md): 180 s mixtures of 6-12 speakers built from word-level forced alignments of clean zh / en utterances,
simulated rooms and noise; 42,000 train / 280 dev / 280 test records (zh and en). The generator's own catalog entry
(catalog.jsonl in the run directory) is the declaration; this script
- hard-links (no copy, no deletion at the source) audio/, shards/ and the evidence files into
  <root>/datasets/sot_many_speaker_word_zh_en/versions/word-v1-20261008/,
- rewrites audio-index.jsonl.gz with root_alias aidc_data and the new relative paths (cut ids unchanged),
- checks every shard against the digest declared by the generator, and
- writes the YAML declaration with root_alias aidc_data for every artifact.
The word pool (word-pool.jsonl.gz, per-utterance word times joined with the clean verdicts), the acoustic pool and
the source audit are kept as evidence artifacts. Built data, not a label layer: no view.

    python scripts/label_registration/register_many_speaker.py --root /workspace/data --run DIR/many-speaker-v2-20261008 --pilot DIR/many-speaker-v2-pilot-20261008 \
        --output catalog/sot_many_speaker_word_zh_en.yaml
"""

import argparse
import gzip
import json
import os
from pathlib import Path

from common import (
    artifact,
    new_version_dir,
    sha256,
    write_declaration_file,
    write_jsonl_gz,
)

DATASET = "sot_many_speaker_word_zh_en"
VERSION = "word-v1-20261008"
EVIDENCE = [  # (name, kind, file in data/, description)
    ("word_pool", "word-pool", "word-pool.jsonl.gz"),
    ("acoustic_pool", "json-metadata", "acoustic-pool.json"),
    ("source_audit", "json-metadata", "sources.json"),
    ("recipe", "json-metadata", "recipe.json"),
    ("generation_plan", "json-metadata", "generation-plan.json"),
    ("generation_progress", "json-metadata", "progress.json"),
    ("acceptance_audit", "quality-report", "many-speaker-audit.json"),
]


def link(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        os.link(source, destination)


def register_tree(data, run_logs, out, prefix, subdir="", name_prefix=""):
    """Link one generator `data/` tree into the version directory; return (entry, artifacts, audio files)."""
    entry = json.loads((data / "catalog.jsonl").read_text().splitlines()[0])
    base = f"{prefix}/{subdir}" if subdir else prefix
    target = out / subdir if subdir else out
    artifacts = []
    for item in entry["artifacts"]:
        source = data / item["relative_path"]
        name = name_prefix + item["name"]
        if item["kind"] == "audio-index":
            def rows(path=source):
                with gzip.open(path, "rt", encoding="utf-8") as stream:
                    for line in stream:
                        row = json.loads(line)
                        link(data / row["relative_path"], target / row["relative_path"])
                        row["root_alias"] = "aidc_data"
                        row["relative_path"] = f"{base}/{row['relative_path']}"
                        yield row
            count, size, digest = write_jsonl_gz(target / "audio-index.jsonl.gz", rows())
            artifacts.append({**artifact(name, "audio-index", DATASET, "", "x", size, digest, record_count=count),
                              "relative_path": f"{base}/audio-index.jsonl.gz"})
            continue
        if sha256(source) != item["sha256"]:
            raise SystemExit(f"{source}: digest differs from the generator's declaration")
        link(source, target / item["relative_path"])
        artifacts.append({**artifact(name, item["kind"], DATASET, "", "x", source.stat().st_size,
                                     item["sha256"], **item.get("metadata", {})),
                          "relative_path": f"{base}/{item['relative_path']}"})
    for name, kind, relative in EVIDENCE:
        link(data / relative, target / relative)
        artifacts.append({**artifact(name_prefix + name, kind, DATASET, "", "x", (target / relative).stat().st_size,
                                     sha256(target / relative)), "relative_path": f"{base}/{relative}"})
    for log in sorted(run_logs.iterdir()):
        if log.is_file():
            link(log, target / "build_logs" / log.name)
    audio_files = sum(1 for path in (target / "audio").rglob("*") if path.is_file())
    return entry, artifacts, audio_files


def describe(entry, name_prefix, artifacts):
    names = [a["name"] for a in artifacts]
    for split in entry["splits"].values():
        split["artifacts"] = {role: [name_prefix + n for n in v] for role, v in split["artifacts"].items()}
        split["artifacts"]["evidence"] = [name_prefix + n for n, _, _ in EVIDENCE if name_prefix + n in names]
    return entry["splits"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True, help="generator run directory (README.md, data/, logs/)")
    parser.add_argument("--pilot", type=Path, required=True,
                        help="pilot run directory (data/ = r1, data-r2/, data-control-noclean/, logs/)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    declarations = []

    out = new_version_dir(args.root, DATASET, VERSION)
    prefix = f"datasets/{DATASET}/versions/{VERSION}"
    entry, artifacts, audio_files = register_tree(args.run / "data", args.run / "logs", out, prefix)
    splits = describe(entry, "", artifacts)
    records = {s: v["statistics"]["records"] for s, v in splits.items()}
    if audio_files != sum(records.values()):
        raise SystemExit(f"{audio_files} audio files for {sum(records.values())} records")
    entry["artifacts"], entry["splits"] = artifacts, splits
    entry["version"] = VERSION
    entry["provenance"] = {
        **entry["provenance"],
        "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
        "source": "synthetic: word-level forced alignments of clean zh / en utterances (zh alignments registered as "
                  "<dataset>@alignment-v1-20261008 for aidatatang, aishell3, magicdata, magicdata_ramc, primewords)",
        "description": (
            "6-12 人词级长混音（2026-10-08，amphiondata feat/many-speaker-word-level-synthesis）：每条 180 秒，由"
            "多个说话人的词段交替、重叠拼成，加模拟房间脉冲响应和噪声；训练 42,000 条、dev 280、test 280"
            "（中文和英文各占一部分），共约 2128 小时（混音时长，不是独立语音时长）。录音是 audio/ 下的 flac，"
            "audio-index 指向它们；records 在 shards/，每条含说话人归属、词级时间戳和声学参数。"
            "中文来源的词级对齐见各来源数据集的 alignment-v1-20261008。自动验收（时间线、分区、token 数、SNR、波形重建）"
            "0 项失败，未经人工听审；词时间是自动强制对齐，说话人身份只在单个语料内成立。"
            "audio 与 shards 由生成目录硬链接而来，没有复制。生成日志和代码快照在 build_logs/。"
            "脚本 scripts/label_registration/register_many_speaker.py。"),
        "facts": {"records": records, "audio_files": audio_files,
                  "shards": sum(1 for a in artifacts if a["kind"] == "audio-records")},
    }
    declarations.append(entry)
    print(json.dumps(entry["provenance"]["facts"]))

    version = "pilot-v1-20261008"
    out = new_version_dir(args.root, DATASET, version)
    prefix = f"datasets/{DATASET}/versions/{version}"
    pilot_artifacts, pilot_splits, facts = [], {}, {}
    for subdir, source_dir, tag in (("r1", "data", "r1-"), ("r2", "data-r2", "r2-"),
                                    ("control-noclean", "data-control-noclean", "control-")):
        piece, found, audio_files = register_tree(
            args.pilot / source_dir, args.pilot / "logs", out, prefix, subdir=subdir, name_prefix=tag)
        splits = describe(piece, tag, found)
        count = sum(v["statistics"]["records"] for v in splits.values())
        if audio_files != count:
            raise SystemExit(f"{subdir}: {audio_files} audio files for {count} records")
        pilot_artifacts += found
        pilot_splits.update({f"{tag}{name}": value for name, value in splits.items()})
        facts[subdir] = {"records": count, "audio_files": audio_files, "generator_version": piece["version"]}
    entry = {
        "schema_version": entry["schema_version"], "dataset_id": DATASET, "version": version,
        "languages": ["zh", "en"], "tasks": ["speaker_attributed_asr"], "aliases": [],
        "artifacts": pilot_artifacts, "splits": pilot_splits,
        "provenance": {
            "preparation_status": "partial", "lineage_status": "exact", "materialization": "full",
            "ready_for_training": False,
            "source": f"{DATASET}@{VERSION} generator, small calibration runs",
            "description": (
                "6-12 人词级长混音的小规模验证（2026-10-08），占位登记，不用于训练：r1（±5 dB 增益、轮次 SINR -8 dB）"
                "strong 档低 SNR 被筛掉过多，只作校准证据；r2（±3 dB、-10 dB）364 条；control-noclean 是不带 clean 过滤"
                "的对照池，196 条。全量数据见 word-v1-20261008，它取代了这三组。三组各在一个子目录里，"
                "records 和 audio 与生成目录硬链接，没有复制。任务和配方不要引用此版本。"
                "脚本 scripts/label_registration/register_many_speaker.py。"),
            "facts": facts,
        },
    }
    declarations.append(entry)
    print(json.dumps(facts))
    write_declaration_file(args.output, declarations, "6-12 人词级长混音数据集及其小规模验证占位版本")


if __name__ == "__main__":
    main()
