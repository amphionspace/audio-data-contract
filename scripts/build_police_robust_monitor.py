#!/usr/bin/env python3
"""Rebuild police_robust_monitor as AudioRecords whose IDs name the subset.

``police_robust_monitor@icefall-20260908`` has eight conditions (clean and seven degradations) of the
same 60 synthetic police utterances: 20 from each of the ``test``, ``test_qwen3_tts`` and
``test_cosyvoice3`` splits of ``police_synthetic_zh_accent@icefall-20260908``. Its cut ID
``<condition>-audio-<hash>`` drops the subset, and 20 hashes occur in two subsets with the same text
and speaker but different audio, so each condition has 60 cuts and only 40 distinct IDs.

This version keeps all 480 cuts with their text, speaker, duration and audio file, and names every
record and audio-index entry ``<condition>-<subset>-audio-<hash>``; the old cut ID stays in
``metadata.icefall_cut_id``. No audio is copied: the audio index points at the existing files under
``source/`` of the dataset directory, so the directory alone is a complete copy for ``ab`` mirroring.

    PYTHONPATH=src python scripts/build_police_robust_monitor.py

reads the old cuts through the local registry, writes ``versions/<VERSION>/`` under the dataset's root
alias, adds the version to ``catalog/police_robust_monitor.yaml`` and copies that file into the
registry. It refuses to replace an existing version.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
from pathlib import Path

import soundfile as sf
import yaml

from audio_data_contract import (
    AudioRecord,
    DatasetSpec,
    load_catalog,
    load_roots,
    resolve_split,
    validate_catalog,
)

DATASET_ID = "police_robust_monitor"
SOURCE_VERSION = "icefall-20260908"
VERSION = "eval-20261113"
CONDITIONS = ("clean", "foreground_snr5", "foreground_snr0", "local_gain_snr5",
              "narrowband", "eq_bandpass", "rir", "clipping")
SUBSET_PREFIX = "police_synthetic_zh_accent_"
SUBSETS = ("test", "test_qwen3_tts", "test_cosyvoice3")
REPO = Path(__file__).resolve().parents[1]
CATALOG_FILE = REPO / "catalog" / f"{DATASET_ID}.yaml"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl_gz(path, rows):
    """Write deterministic gzip JSONL (no file name or time stamp in the gzip header)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
        for row in rows:
            stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    path.write_bytes(buffer.getvalue())


def convert(cut, condition, root):
    """One old cut -> (record, audio-index row); every assumption about the old cut is checked."""
    (sup,) = cut["supervisions"]
    recording = cut["recording"]
    (source,) = recording["sources"]
    audio = Path(source["source"]).resolve()
    relative = audio.relative_to(root)
    folder_condition, folder = relative.parts[-3], relative.parts[-2]
    subset = folder.removeprefix(SUBSET_PREFIX)
    if (folder_condition, sup["custom"]) != (condition, {"source_cut_id": audio.stem, "condition": condition}):
        raise ValueError(f"{cut['id']}: audio {relative} is not of condition {condition}")
    if subset not in SUBSETS or not folder.startswith(SUBSET_PREFIX):
        raise ValueError(f"{cut['id']}: unknown subset folder {folder}")
    if not cut["id"] == sup["id"] == recording["id"] == f"{condition}-{audio.stem}":
        raise ValueError(f"{cut['id']}: unexpected cut, supervision or recording ID")
    if not (cut["start"] == sup["start"] == 0 and cut["duration"] == sup["duration"] == recording["duration"]):
        raise ValueError(f"{cut['id']}: supervision does not span the whole recording")
    info = sf.info(str(audio))
    if (info.samplerate, info.frames, info.channels) != (recording["sampling_rate"], recording["num_samples"], 1):
        raise ValueError(f"{cut['id']}: {relative} header differs from the old recording")
    cut_id = f"{condition}-{subset}-{audio.stem}"
    record = AudioRecord.from_dict({
        "schema_version": "audio-record/1.0",
        "id": cut_id,
        "task": "asr",
        "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
            "dataset_id": DATASET_ID, "version": VERSION, "split": condition,
            "cut_id": cut_id, "duration": recording["duration"]}}],
        "target": sup["text"],
        "language": sup["language"],
        "labels": {"condition": condition, "subset": subset},
        "metadata": {"icefall_cut_id": cut["id"], "source_cut_id": audio.stem, "speaker": sup["speaker"]},
    }).to_dict()
    row = {
        "cut_id": cut_id, "root_alias": DATASET_ID, "relative_path": relative.as_posix(),
        "sample_rate": recording["sampling_rate"], "channels": 1,
        "num_frames": recording["num_samples"], "duration": recording["duration"], "sha256": sha256_file(audio),
    }
    return record, row


def declaration(records_by_split, index, version_dir, root):
    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": DATASET_ID,
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path), "metadata": {"record_count": count}}

    artifacts = [artifact("audio-index", "audio-index", version_dir / "audio-index.jsonl.gz", len(index))]
    splits = {}
    for condition, records in records_by_split.items():
        artifacts.append(artifact(f"{condition}-records", "audio-records",
                                  version_dir / "records" / f"{condition}.jsonl.gz", len(records)))
        hours = sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600
        splits[condition] = {
            "artifacts": {"records": [f"{condition}-records"], "audio_index": ["audio-index"]},
            "group": "test",
            "task": "asr",
            "statistics": {"records": len(records), "duration_hours": round(hours, 4),
                           "duration_basis": "sum of recording durations"},
        }
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "languages": ["zh"],
        "tasks": ["asr"],
        "aliases": [],
        "derived_from": f"{DATASET_ID}@{SOURCE_VERSION}",
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "summary": "警务合成测试语音的干净及 7 种退化版本，只用于评测",
            "description": (
                "警务合成语音鲁棒性监控集：60 条测试语音（police_synthetic_zh_accent@icefall-20260908 的 test、"
                "test_qwen3_tts、test_cosyvoice3 各 20 条）的干净版和 7 种退化版（foreground_snr5、foreground_snr0、"
                "local_gain_snr5、narrowband、eq_bandpass、rir、clipping），每个划分 60 条，共 480 条。"
                f"内容与 {SOURCE_VERSION} 逐条相同（文本、说话人、时长和音频文件都不变，音频不复制，"
                "索引指向数据集目录 source/ 下的原文件），只是改成 AudioRecord 并给每条换了不重复的 ID："
                "<条件>-<子集>-audio-<hash>，子集为 test / test_qwen3_tts / test_cosyvoice3；"
                f"原 cut ID 保留在 metadata.icefall_cut_id。{SOURCE_VERSION} 的 cut ID 不含子集，"
                "每个划分 60 条只有 40 个不同 ID，按 ID 读取的评测器会报重复或丢样本。只用于评测，不进训练。"
            ),
            "known_issues": [
                ("同一 hash 在 test 与 test_qwen3_tts（11 对）、test 与 test_cosyvoice3（9 对）中各出现一次："
                 "文本和说话人相同，音频不同。两条都保留，不要按 hash 或 metadata.icefall_cut_id 去重。"),
                "全部为合成语音，只经过自动质检，没有人工听审。",
            ],
            "build_script": "scripts/build_police_robust_monitor.py",
        },
    }


def register(entry, registry):
    rows = list(yaml.safe_load(CATALOG_FILE.read_text(encoding="utf-8")) or []) if CATALOG_FILE.exists() else []
    if any(r["version"] == VERSION for r in rows):
        raise FileExistsError(f"version already registered: {VERSION}")
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(entry)])
    CATALOG_FILE.write_text(yaml.safe_dump([*rows, entry], allow_unicode=True, sort_keys=False, width=512),
                            encoding="utf-8")
    if registry:
        shutil.copy(CATALOG_FILE, registry / CATALOG_FILE.name)
        validate_catalog(load_catalog(registry))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"),
                        help="catalog that holds the old version (and receives the new catalog file)")
    parser.add_argument("--roots", type=Path, default=Path("/workspace/data/registry/roots.json"))
    parser.add_argument("--no-registry-copy", action="store_true", help="do not copy the catalog file to --catalog")
    args = parser.parse_args()

    catalog, roots = load_catalog(args.catalog), load_roots(args.roots)
    root = Path(roots[DATASET_ID]).resolve()
    version_dir = root / "versions" / VERSION
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace {version_dir}")
    if set(catalog.get(DATASET_ID, SOURCE_VERSION).splits) != set(CONDITIONS):
        raise ValueError(f"{DATASET_ID}@{SOURCE_VERSION} splits differ from {CONDITIONS}")

    records_by_split, index = {}, []
    for condition in CONDITIONS:
        records = []
        for path in resolve_split(catalog, DATASET_ID, SOURCE_VERSION, condition, "cuts", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    record, row = convert(json.loads(line), condition, root)
                    records.append(record)
                    index.append(row)
        records_by_split[condition] = records
        print(json.dumps({"split": condition, "records": len(records)}), flush=True)
    if len({row["cut_id"] for row in index}) != len(index):
        raise ValueError("cut IDs are still not unique")
    if len({row["relative_path"] for row in index}) != len(index):
        raise ValueError("two records share one audio file")

    partial = version_dir.with_name(VERSION + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    for condition, records in records_by_split.items():
        write_jsonl_gz(partial / "records" / f"{condition}.jsonl.gz", records)
    write_jsonl_gz(partial / "audio-index.jsonl.gz", sorted(index, key=lambda row: row["cut_id"]))
    partial.rename(version_dir)
    entry = declaration(records_by_split, index, version_dir, root)
    register(entry, None if args.no_registry_copy else args.catalog)
    print(json.dumps({"version": f"{DATASET_ID}@{VERSION}", "index": len(index), "catalog": str(CATALOG_FILE)}))


if __name__ == "__main__":
    main()
