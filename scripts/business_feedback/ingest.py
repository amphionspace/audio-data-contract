#!/usr/bin/env python3
"""Register a business-feedback target-speaker bad case batch as AudioRecords.

Input is a directory of debug packages unpacked as ``cases/<case>/`` (each with
``registration-reference.wav``, ``source-audio.wav``, ``manifest.json`` and
``attempt-1/response.json``) plus a labels file under ``batches/``. Every batch
becomes a new immutable ``business_feedback@<version>``; later batches are new
versions of the same dataset, never edits of an existing one.

    python scripts/business_feedback/ingest.py --source <badcase dir> \
        --labels scripts/business_feedback/batches/ts-20261010.yaml \
        --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import soundfile as sf
import yaml

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

DATASET_ID = "business_feedback"
ROOT_ALIAS = DATASET_ID
SAMPLE_RATE = 16000
SPLIT_DESCRIPTIONS = {
    "target_speaker": "目标说话人未在场、期望输出为空的反馈（已由反馈人确认）。",
    "target_present": "目标说话人在场、参考文本已由复核人听音确认的反馈。",
    "pending_labels": "现象已记录但参考文本未确认，不参与打分。",
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


def read_response(path):
    """(text, finish_reason, streamed) of a recorded response, plain JSON or an SSE stream.

    A cancelled stream may have no finish reason; the text is then whatever arrived.
    """
    raw = path.read_text()
    if raw.lstrip().startswith("data:"):
        parts, finish = [], None
        for line in raw.splitlines():
            if not line.startswith("data: {"):
                continue
            for choice in json.loads(line[6:]).get("choices") or []:
                parts.append((choice.get("delta") or {}).get("content") or "")
                finish = choice.get("finish_reason") or finish
        return "".join(parts), finish, True
    choice = json.loads(raw)["choices"][0]
    return choice["message"].get("content") or "", choice.get("finish_reason"), False


def package_names(source):
    names = {}
    for item in sorted((source / "packages").glob("*--*.zip")):
        names[item.name.split("--", 1)[0]] = item.name.split("--", 1)[1]
    return names


def build(source, labels, data_root):
    version = labels["version"]
    audio_dir = data_root / "source" / version / "audio"
    version_dir = data_root / "versions" / version
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace registered version: {version_dir}")
    packages = package_names(source)
    index, by_split = {}, {}

    def add_audio(src, name):
        destination = audio_dir / name
        audio_dir.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(src, destination)
        relative = f"source/{version}/audio/{name}"
        cut_id = name.removesuffix(".wav")
        index.setdefault(cut_id, index_entry(destination, relative, cut_id))
        return index[cut_id]

    for case, label in labels["cases"].items():
        directory = source / "cases" / case
        manifest = json.loads((directory / "manifest.json").read_text())
        output, finish, streamed = read_response(directory / "attempt-1" / "response.json")
        request = json.loads((directory / "attempt-1" / "request.json").read_text())
        case_id = case.replace("/", "-")
        enrollment_hash = sha256_file(directory / "registration-reference.wav")[:12]
        enrollment = add_audio(directory / "registration-reference.wav", f"enrollment-{enrollment_hash}.wav")
        mixture = add_audio(directory / "source-audio.wav", f"{case_id}-mixture.wav")
        split = label["split"]
        record_labels = {"issue": label["issue"]}
        if "target_present" in label:
            record_labels["target_present"] = label["target_present"]
        else:
            record_labels["label_status"] = "unlabeled"
        if "label_source" in label:
            record_labels["label_source"] = label["label_source"]

        def ref(entry, split=split):
            return {"dataset_id": DATASET_ID, "version": version, "split": split,
                    "cut_id": entry["cut_id"], "duration": entry["duration"]}

        record = AudioRecord.from_dict({
            "schema_version": "audio-record/1.0",
            "id": f"{version}:{case_id}",
            "task": "ts_asr",
            "audio_slots": [
                {"name": "enrollment", "purpose": "enrollment", "ref": ref(enrollment)},
                {"name": "mixture", "purpose": "mixture", "ref": ref(mixture)},
            ],
            "target": label.get("target", ""),
            "language": labels["language"],
            "labels": record_labels,
            "metadata": {
                "batch": version,
                "case": case,
                "package": packages.get(case.split("/")[0]),
                "trace_id": manifest.get("trace_id"),
                "segment_id": manifest.get("segment_id"),
                "reported_model": manifest.get("model"),
                "reported_source_revision": manifest.get("source_revision"),
                "reported_output": output,
                "reported_finish_reason": finish,
                "reported_streamed": streamed,
                "reported_error": manifest.get("error") or None,
                "request_params": {k: request[k] for k in ("max_tokens", "stream", "mm_processor_kwargs")
                                   if k in request},
            },
        }).to_dict()
        by_split.setdefault(split, []).append(record)

    for split, rows in by_split.items():
        write_jsonl_gz(version_dir / "records" / f"{split}.jsonl.gz", rows)
    write_jsonl_gz(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    return by_split, index


def declaration(labels, by_split, index, data_root):
    version = labels["version"]

    def relative(*parts):
        return "/".join(("versions", version, *parts))

    artifacts = [{
        "name": "audio-index", "kind": "audio-index", "root_alias": ROOT_ALIAS,
        "relative_path": relative("audio-index.jsonl.gz"),
        "sha256": sha256_file(data_root / relative("audio-index.jsonl.gz")),
        "metadata": {"record_count": len(index)},
    }]
    splits = {}
    for split, rows in sorted(by_split.items()):
        path = relative("records", f"{split}.jsonl.gz")
        artifacts.append({
            "name": f"{split}-records", "kind": "audio-records", "root_alias": ROOT_ALIAS,
            "relative_path": path, "sha256": sha256_file(data_root / path),
            "metadata": {"record_count": len(rows)},
        })
        seconds = sum(r["audio_slots"][1]["ref"]["duration"] for r in rows)
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "task": "ts_asr",
            "statistics": {"records": len(rows), "duration_hours": round(seconds / 3600, 4),
                           "duration_basis": "Mixture (recognition segment) duration"},
            # A batch whose labels came another way (e.g. automatic review) says so for that split.
            "provenance": {"description": labels.get("split_descriptions", {}).get(split, SPLIT_DESCRIPTIONS[split])},
        }
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": version,
        "languages": [labels["language"]],
        "tasks": ["ts_asr"],
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "status": "complete",
            "synthetic": "none",
            "description": "业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。"
                           + " ".join(labels["description"].split()),
            "sources": [f"business feedback debug packages: {labels['source']}"],
        },
    }


def register(repository, spec):
    path = repository / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    current = load_catalog(repository / "catalog")
    validate_catalog([*current, DatasetSpec.from_dict(spec)])
    # Plain block YAML, matching the hand-maintained catalog files.
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512),
                    encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    args = parser.parse_args()
    labels = yaml.safe_load(args.labels.read_text())
    roots = json.loads(args.roots.read_text())
    data_root = Path(roots[ROOT_ALIAS])
    by_split, index = build(args.source, labels, data_root)
    register(Path(__file__).resolve().parents[2], declaration(labels, by_split, index, data_root))
    print({s: len(r) for s, r in by_split.items()}, f"audio files: {len(index)}")


if __name__ == "__main__":
    main()
