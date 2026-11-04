#!/usr/bin/env python3
"""Register ``<dataset>@allspk-ts-v1-20261104`` (build_allspk_ts_pairs.py) in catalog/ and views/.

Writes one catalog entry per dataset to ``catalog/allspk_ts_v1.yaml`` (records of the ``train`` and ``train_neg``
splits, plus the ``asr-20261014`` audio index both slots refer to, copied from the registry's declaration of that
version) and the Views ``views/allspk_ts_v1.yaml``. Build the Lance record index afterwards with
``build-record-index --register``.

    python register_allspk_ts_pairs.py --repo . [--registry /workspace/data/registry/catalog]
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import yaml

from audio_data_contract import load_catalog

DATA = Path("/workspace/data")
VERSION = "allspk-ts-v1-20261104"
AUDIO = "asr-20261014"
DATASETS = ("magicdata_ramc", "aishell4", "alimeeting_sdm")
NAMES = {"magicdata_ramc": "MagicData-RAMC", "aishell4": "AISHELL-4", "alimeeting_sdm": "AliMeeting"}
SPLITS = ("train", "train_neg")
TOOL = "scripts/target_asr/build_allspk_ts_pairs.py"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hours(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return sum(next(s for s in json.loads(line)["audio_slots"] if s["purpose"] == "mixture")["ref"]["duration"]
                   for line in stream) / 3600


def catalog_entry(dataset, registry):
    directory = DATA / "datasets" / dataset / "versions" / VERSION
    report = json.loads((directory / "report.json").read_text())
    records = {split: directory / f"records_{split}.jsonl.gz" for split in SPLITS}
    for split, path in records.items():
        if report["records_sha256"][split] != sha256(path):
            raise SystemExit(f"{path} changed after its report was written")
    audio = next(e for e in registry if e.dataset_id == dataset and e.version == AUDIO)
    index = next(a for a in audio.artifacts if a.kind == "audio-index")
    counts = report["counts"]
    description = (
        f"{NAMES[dataset]} 训练集的目标说话人（TS）多人窗口，与 {report['windows']} 用同一批窗口、同一段音频：普通 ASR 版本转写窗口里所有人，"
        "这里只转写注册的那个人，让模型在同一段音频上靠提示区分两种任务（只训普通 ASR 版本时，TS 模式在多人轮流说话的音频上会把别人的话也写进来）。"
        f"train：每个窗口选一个在窗口里说话的人作目标（在有注册音的说话人里均匀抽），目标文本是此人在窗口内各句的书面化标点文本（{report['punctuation']}）"
        "按开始时间顺序拼接；train_neg：每个窗口选一个同一录音里、窗口内没说话的人（有的话），目标为空。"
        "注册音取同一录音里此人在窗口外的一句话，长 3–10 秒（没有则放宽到 2–15 秒），且没有其他句子与之重叠"
        + (f"、通过 {report['clean_pass']} 清洗" if report.get("clean_pass") else "")
        + f"。两个音频位都引用 {dataset}@{AUDIO} 训练集（与窗口同一路），不复制。"
        f"正样本 {counts.get('train', 0)} 条（{counts.get('no_target_enrollment', 0)} 个窗口没有可用注册音），"
        f"负样本 {counts.get('train_neg', 0)} 条（{counts.get('no_absent_speaker', 0)} 个窗口没有不在场的说话人）；"
        f"正样本窗口的说话人数分布 {report['positive_window_speakers']}。")
    artifacts, splits = [], {}
    for split, path in records.items():
        name = f"{split}_records"
        artifacts.append({"name": name, "kind": "audio-records", "root_alias": "aidc_data",
                          "relative_path": path.relative_to(DATA).as_posix(), "expected_bytes": path.stat().st_size,
                          "sha256": report["records_sha256"][split],
                          "metadata": {"record_count": counts[split], "punctuated": True}})
        splits[split] = {"group": "train", "artifacts": {"records": [name], "audio_index": ["audio_index"]},
                         "task": "ts_asr",
                         "statistics": {"records": counts[split], "duration_hours": round(hours(path), 2),
                                        "duration_basis": "mixture duration (ref.duration)"}}
    artifacts.append({"name": "audio_index", "kind": "audio-index", "root_alias": index.root_alias,
                      "relative_path": index.relative_path,
                      **({"expected_bytes": index.expected_bytes} if getattr(index, "expected_bytes", None) else {}),
                      "sha256": index.sha256, "metadata": dict(index.metadata or {})})
    entry = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": VERSION,
        "languages": ["zh"], "tasks": ["ts_asr"], "aliases": [], "artifacts": artifacts, "splits": splits,
        "provenance": {
            "status": "complete", "synthetic": "none", "snapshot_date": "2026-11-04", "description": description,
            "sources": [report["windows"], report["annotation"], report["punctuation"], f"{dataset}@{AUDIO}",
                        *([report["clean_pass"]] if report.get("clean_pass") else [])],
            "audit": (directory / "report.json").relative_to(DATA).as_posix()},
    }
    return entry, report


def view_entry(dataset, report):
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/allspk-ts", "version": VERSION,
        "source": {"dataset_id": dataset, "version": report["windows"].split("@")[1]},
        "result": {"dataset_id": dataset, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "allspk-ts-pairs", "version": VERSION, "kind": "representation-conversion",
            "writes": ["$membership", "task", "target", "audio_slots", "labels", "metadata.enroll_utt",
                       "metadata.target_speaker", "metadata.window_utts"],
            "parameters": {
                **report["parameters"], "tool": TOOL, "splits": list(SPLITS),
                "windows": f"{report['windows']} train records (same windows, mixture = the window's audio reference)",
                "utterances": f"{report['annotation']} train supervisions with non-empty text",
                "text": f"{report['punctuation']} (same supervision IDs), the target speaker's utterances in start order",
                **({"clean_pass": f"{report['clean_pass']} custom.clean.pass; enrollments must pass"}
                   if report.get("clean_pass") else {}),
                "records_sha256": report["records_sha256"], "counts": report["counts"]}}],
        "provenance": {"registered_at": "2026-11-04"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DATA / "registry" / "catalog")
    args = parser.parse_args()
    registry = load_catalog(args.registry)
    catalog_path, views_path = args.repo / "catalog" / "allspk_ts_v1.yaml", args.repo / "views" / "allspk_ts_v1.yaml"
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
