#!/usr/bin/env python3
"""Register ``<dataset>@allspk-asr-v1-20261103`` (build_allspk_asr_windows.py) in catalog/ and views/.

Appends one catalog entry per dataset to ``catalog/allspk_asr_v1.yaml`` (records, plus the ``asr-20261014`` audio
index the records refer to, copied from the registry's declaration of that version) and writes the Views
``views/allspk_asr_v1.yaml``. Build the Lance record index afterwards with ``build-record-index --register``.

    python register_allspk_asr_windows.py --repo . [--registry /workspace/data/registry/catalog]
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import yaml

from audio_data_contract import load_catalog

DATA = Path("/workspace/data")
VERSION = "allspk-asr-v1-20261103"
DATASETS = ("magicdata_ramc", "aishell4", "alimeeting_sdm")
NAMES = {"magicdata_ramc": "MagicData-RAMC", "aishell4": "AISHELL-4", "alimeeting_sdm": "AliMeeting"}
TOOL = "scripts/target_asr/build_allspk_asr_windows.py"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hours(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return sum(json.loads(line)["audio_slots"][0]["ref"]["duration"] for line in stream) / 3600


def catalog_entry(dataset, registry):
    directory = DATA / "datasets" / dataset / "versions" / VERSION
    records = directory / "records_train.jsonl.gz"
    report = json.loads((directory / "report.json").read_text())
    if report["records_sha256"] != sha256(records):
        raise SystemExit(f"{records} changed after its report was written")
    audio = next(e for e in registry if e.dataset_id == dataset and e.version == report["audio"].split("@")[1])
    index = next(a for a in audio.artifacts if a.kind == "audio-index")
    counts = report["counts"]
    description = (
        f"{NAMES[dataset]} 训练集的普通 ASR 多人窗口：按 {report['annotation']} 训练集标注，在每段录音上依次切出不重叠的窗口，"
        "每个窗口长度在 10–90 秒间均匀抽取，只在没人说话（前后静音至少 0.2 秒）处下刀；目标文本是窗口内所有说话人每句话的书面化"
        f"标点文本（{report['punctuation']}，同一 ID）按开始时间顺序拼接，不区分说话人。重叠语音超过窗口时长 10% 的窗口丢弃"
        "（普通转写的字序不确定），有任一句缺标点文本的窗口丢弃"
        + (f"，有任一句未通过 {report['clean_pass']} 清洗（custom.clean.pass 为 false）的窗口丢弃"
           if report.get("clean_pass") else "")
        + "。音频引用 "
        f"{report['audio']} 训练集（只取第 0 路），不复制。用途：普通 ASR 模式下多人轮流说话时转写每个人、长录音不提前结束"
        "（此前普通 ASR 训练数据每条只转写一个说话人）。"
        f"保留 {counts['kept']} 个窗口，丢弃：重叠 {counts.get('drop_overlap', 0)}、缺标点 {counts.get('drop_unpunctuated', 0)}、"
        f"短于 5 秒 {counts.get('drop_short', 0)}"
        + (f"、未过清洗 {counts['drop_clean_reject']}" if "drop_clean_reject" in counts else "")
        + f"；说话人数分布 {report['speakers']}。")
    entry = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": VERSION,
        "languages": ["zh"], "tasks": ["asr"], "aliases": [],
        "artifacts": [
            {"name": "train_records", "kind": "audio-records", "root_alias": "aidc_data",
             "relative_path": records.relative_to(DATA).as_posix(), "expected_bytes": records.stat().st_size,
             "sha256": report["records_sha256"], "metadata": {"record_count": counts["kept"], "punctuated": True}},
            {"name": "audio_index", "kind": "audio-index", "root_alias": index.root_alias,
             "relative_path": index.relative_path,
             **({"expected_bytes": index.expected_bytes} if getattr(index, "expected_bytes", None) else {}),
             "sha256": index.sha256, "metadata": dict(index.metadata or {})},
        ],
        "splits": {"train": {
            "group": "train",
            "artifacts": {"records": ["train_records"], "audio_index": ["audio_index"]},
            "task": "asr",
            "statistics": {"records": counts["kept"], "duration_hours": round(hours(records), 2),
                           "duration_basis": "window duration (ref.duration)"}}},
        "provenance": {
            "status": "complete", "synthetic": "none", "snapshot_date": "2026-11-03", "description": description,
            "sources": [report["annotation"], report["punctuation"], report["audio"],
                        *([report["clean_pass"]] if report.get("clean_pass") else [])],
            "audit": (directory / "report.json").relative_to(DATA).as_posix()},
    }
    return entry, report


def view_entry(dataset, report):
    parameters = dict(report["parameters"])
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/allspk-asr", "version": VERSION,
        "source": {"dataset_id": dataset, "version": report["punctuation"].split("@")[1]},
        "result": {"dataset_id": dataset, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "allspk-asr-windows", "version": VERSION, "kind": "representation-conversion",
            "writes": ["$membership", "target", "audio_slots", "labels.speakers", "metadata.window_utts",
                       "metadata.recording_id", "metadata.window_start", "metadata.window_end",
                       "metadata.overlap_seconds"],
            "parameters": {
                **parameters, "tool": TOOL, "split": "train",
                "utterances": f"{report['annotation']} train supervisions with non-empty text",
                "text": f"{report['punctuation']} (same supervision IDs), joined in start order",
                "audio": f"{report['audio']} train audio index, channel of its records",
                **({"clean_pass": f"{report['clean_pass']} custom.clean.pass; windows with a rejected utterance dropped"}
                   if report.get("clean_pass") else {}),
                "records_sha256": report["records_sha256"], "counts": report["counts"]}}],
        "provenance": {"registered_at": "2026-11-03"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DATA / "registry" / "catalog")
    args = parser.parse_args()
    registry = load_catalog(args.registry)
    catalog_path, views_path = args.repo / "catalog" / "allspk_asr_v1.yaml", args.repo / "views" / "allspk_asr_v1.yaml"
    for path in (catalog_path, views_path):
        if path.exists():
            raise SystemExit(f"{path} exists")
    entries, views = [], []
    for dataset in DATASETS:
        entry, report = catalog_entry(dataset, registry)
        entries.append(entry)
        views.append(view_entry(dataset, report))
    catalog_path.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=120))
    views_path.write_text(yaml.safe_dump(views, sort_keys=False, allow_unicode=True, width=120))
    print(f"wrote {catalog_path} and {views_path}")


if __name__ == "__main__":
    main()
