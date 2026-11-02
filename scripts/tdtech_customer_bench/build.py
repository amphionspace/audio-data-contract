#!/usr/bin/env python3
"""Register the td-tech (鼎桥) customer recordings from EvalHub as an ASR evaluation dataset.

The recordings are the customer's own audio (mail/Wiki baseline 2026-09-30) that EvalHub published
as ``asr/dingqiao-asr-quality@20261016-machine01`` (general recognition) and
``asr/dingqiao-asr-police-cmd@20261020-jyjy-v6-human04`` (police PTT commands). Their copies sit
unchanged under ``source/evalhub/<category>_<id>@<version>/`` (``files.json`` checked on build), and
the records point at those wavs.

- ``general``: only recordings where two of three transcripts agree at CER 0 under amphion-eval's
  native scoring: EvalHub's machine reference (Qwen-audio-3.1 or MOSS), FireRedASR2-AED and
  MiMo-V2.5-ASR (``agree.py`` writes ``source/agreement.json``). Machine references, not human gold.
- ``police-cmd``: all 137 recordings. The reference is the term the speaker read (recording group,
  aligned to 警言警语 V6.0); 39 of them were confirmed by listening (``reference_kind: human``).

    python scripts/tdtech_customer_bench/build.py --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import soundfile as sf
import yaml

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

DATASET_ID = "tdtech_customer_bench"
ROOT_ALIAS = DATASET_ID
VERSION = "v1-20261102"
SAMPLE_RATE = 16000
GENERAL = "asr_dingqiao-asr-quality@20261016-machine01"
POLICE = "asr_dingqiao-asr-police-cmd@20261020-jyjy-v6-human04"
SPLITS = {
    "general": (
        GENERAL,
        (
            "通用识别（远场、长语音、PTT、警务 badcase 等客户录音）：EvalHub 机器参考（Qwen-audio-3.1 / MOSS）、"
            "FireRedASR2-AED、MiMo-V2.5-ASR 三份转写中有两份在原生打分口径下逐字一致才保留，参考取一致的那份"
            "（含 EvalHub 参考时取 EvalHub 的文本），未经人工听审。"
        ),
    ),
    "police-cmd": (
        POLICE,
        (
            "警务指令（PTT 短句）客户录音：参考为录音分组对应的指令词（按《警言警语 V6.0》对齐），"
            "其中 39 条经人工听原音确认（reference_kind: human），其余为按术语表对齐的机器参考。"
        ),
    ),
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl_gz(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def check_files(directory):
    """Every file EvalHub listed in files.json is present with its sha256."""
    listed = json.loads((directory / "files.json").read_text(encoding="utf-8"))
    files = listed.get("files", listed)
    entries = files.items() if isinstance(files, dict) else ((f["path"], f["sha256"]) for f in files)
    for relative, digest in entries:
        digest = digest["sha256"] if isinstance(digest, dict) else digest
        if sha256_file(directory / relative) != digest:
            raise ValueError(f"{directory / relative}: sha256 differs from files.json")


def index_entry(path, relative_path, cut_id):
    info = sf.info(path)
    if info.samplerate != SAMPLE_RATE or info.channels != 1:
        raise ValueError(f"{path}: expected 16 kHz mono, got {info.samplerate} Hz x{info.channels}")
    return {
        "cut_id": cut_id,
        "root_alias": ROOT_ALIAS,
        "relative_path": relative_path,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "num_frames": info.frames,
        "duration": round(info.frames / info.samplerate, 4),
        "sha256": sha256_file(path),
    }


def evalhub_ref(directory_name):
    category, rest = directory_name.split("_", 1)
    return f"{category}/{rest}"


def build(data_root, agreement):
    version_dir = data_root / "versions" / VERSION
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace registered version: {version_dir}")
    index, by_split, dropped = {}, {}, []
    for split, (directory_name, _) in SPLITS.items():
        directory = data_root / "source" / "evalhub" / directory_name
        check_files(directory)
        for line in (directory / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            check = agreement[row["id"]]
            if check["dataset"] != directory_name:
                raise ValueError(f"{row['id']}: agreement entry is for {check['dataset']}")
            if split == "general" and not check["agreed_by"]:
                dropped.append({"id": row["id"], "duration": row.get("duration"),
                                "errors": check["errors"], "reference_tokens": check["reference_tokens"]})
                continue
            relative = f"source/evalhub/{directory_name}/{row['audio']}"
            entry = index.setdefault(row["id"], index_entry(data_root / relative, relative, row["id"]))
            labels = row.get("labels") or {}
            record_labels = {
                "scenario": labels.get("scenario"),
                "display_name": labels.get("display_name"),
                "reference_kind": labels.get("reference_kind"),
                "reference_source": labels.get("reference_source"),
                "agreed_by": check["agreed_by"],
            }
            if split == "police-cmd":
                record_labels["term"] = labels.get("term")
                record_labels["reference_audit_status"] = labels.get("reference_audit_status")
            if split == "general":
                # One general sample is marked verified in EvalHub although its text is the
                # Qwen pre-annotation; here every general reference counts as machine-agreed.
                record_labels["reference_kind"] = "machine_two_of_three"
            record = AudioRecord.from_dict({
                "schema_version": "audio-record/1.0",
                "id": f"{split}:{row['id']}",
                "task": "asr",
                "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                    "dataset_id": DATASET_ID, "version": VERSION, "split": split,
                    "cut_id": entry["cut_id"], "duration": entry["duration"]}}],
                "target": " ".join(check["reference"].split()),
                "language": "zh",
                "labels": {k: v for k, v in record_labels.items() if v is not None},
                "metadata": {
                    "evalhub": {"ref": evalhub_ref(directory_name), "sample_id": row["id"],
                                "annotation_status": (row.get("annotation") or {}).get("status")},
                    "transcripts": check["texts"],
                    "transcript_errors": check["errors"],
                    "source_audio_sha256": labels.get("source_audio_sha256"),
                },
            }).to_dict()
            by_split.setdefault(split, []).append(record)
    for split, rows in by_split.items():
        write_jsonl_gz(version_dir / "records" / f"{split}.jsonl.gz", rows)
    write_jsonl_gz(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    (version_dir / "general-dropped.json").write_text(
        json.dumps(dropped, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return by_split, index


def declaration(by_split, index, data_root):
    def relative(*parts):
        return "/".join(("versions", VERSION, *parts))

    artifacts = [{
        "name": "audio-index", "kind": "audio-index", "root_alias": ROOT_ALIAS,
        "relative_path": relative("audio-index.jsonl.gz"),
        "sha256": sha256_file(data_root / relative("audio-index.jsonl.gz")),
        "metadata": {"record_count": len(index)},
    }]
    splits = {}
    for split, rows in by_split.items():
        path = relative("records", f"{split}.jsonl.gz")
        artifacts.append({
            "name": f"{split}-records", "kind": "audio-records", "root_alias": ROOT_ALIAS,
            "relative_path": path, "sha256": sha256_file(data_root / path),
            "metadata": {"record_count": len(rows)},
        })
        seconds = sum(r["audio_slots"][0]["ref"]["duration"] for r in rows)
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "task": "asr",
            "statistics": {"records": len(rows), "duration_hours": round(seconds / 3600, 4),
                           "duration_basis": "recording duration"},
            "provenance": {"description": SPLITS[split][1]},
        }
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "languages": ["zh"],
        "tasks": ["asr"],
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "status": "complete",
            "synthetic": "none",
            "summary": "鼎桥客户真实录音的语音识别评测，仅评测",
            "description": "鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），"
                           "只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，"
                           "难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认。",
            "sources": [f"EvalHub {evalhub_ref(name)}" for name, _ in SPLITS.values()],
        },
    }


def register(repository, spec):
    path = repository / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    current = load_catalog(repository / "catalog")
    validate_catalog([*current, DatasetSpec.from_dict(spec)])
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512),
                    encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roots", type=Path, required=True)
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[ROOT_ALIAS])
    agreement = json.loads((data_root / "source" / "agreement.json").read_text())["samples"]
    by_split, index = build(data_root, agreement)
    register(Path(__file__).resolve().parents[2], declaration(by_split, index, data_root))
    print({s: len(r) for s, r in by_split.items()}, f"audio files: {len(index)}")


if __name__ == "__main__":
    main()
