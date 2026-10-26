#!/usr/bin/env python3
"""Append a records + audio_index dataset version to a catalog YAML file.

The new entry is appended as text, so earlier versions in the file keep their exact bytes.

    python register_pool.py --catalog DIR --yaml ts_interference_pool.yaml --dataset-id ts_interference_pool \\
        --version v2-20261016 --task ts_asr_interference --splits zh en --languages zh en --description TEXT
"""

import argparse
import datetime
import gzip
import hashlib
import json
from pathlib import Path

import yaml

ROOT_ALIAS = "aidc_data"
DATA_ROOT = Path("/workspace/data")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def count(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return sum(1 for line in stream if line.strip())


def hours(path, indexes):
    total = 0.0
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            ref = record["audio_slots"][0]["ref"]
            # A clip read from a Lance release is not in the pool's audio index.
            total += ref.get("duration") or indexes.get(ref["cut_id"]) or record["metadata"]["duration"]
    return total / 3600


def durations(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return {row["cut_id"]: row["duration"] for row in map(json.loads, stream)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--yaml", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--splits", nargs="+", required=True)
    parser.add_argument("--languages", nargs="+", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--sources", nargs="*", default=[])
    parser.add_argument("--snapshot-date", default=datetime.datetime.now(tz=datetime.UTC).date().isoformat())
    args = parser.parse_args()
    directory = DATA_ROOT / "datasets" / args.dataset_id / "versions" / args.version
    relative = directory.relative_to(DATA_ROOT).as_posix()
    artifacts, splits = [], {}
    for split in args.splits:
        records, index = directory / f"records_{split}.jsonl.gz", directory / f"audio_index_{split}.jsonl.gz"
        for name, kind, path in ((f"{split}-records", "audio-records", records), (f"{split}-audio-index", "audio-index", index)):
            artifacts.append({"name": name, "kind": kind, "root_alias": ROOT_ALIAS,
                              "relative_path": f"{relative}/{path.name}", "sha256": sha256(path),
                              "metadata": {"record_count": count(path)}})
        splits[split] = {"artifacts": {"records": [f"{split}-records"], "audio_index": [f"{split}-audio-index"]},
                         "task": args.task,
                         "statistics": {"records": count(records), "duration_hours": round(hours(records, durations(index)), 2),
                                        "duration_basis": "clip duration (segment span, or the whole file)"}}
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": args.dataset_id, "version": args.version,
             "languages": args.languages, "tasks": [args.task], "aliases": [], "artifacts": artifacts, "splits": splits,
             "provenance": {"status": "complete", "synthetic": "none", "snapshot_date": args.snapshot_date,
                            "description": args.description, "sources": args.sources}}
    target = args.catalog / args.yaml
    existing = yaml.safe_load(target.read_text()) if target.exists() else []
    if any(row["version"] == args.version for row in existing or []):
        raise SystemExit(f"{args.dataset_id}@{args.version} is already in {target}")
    text = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=120)
    with open(target, "a", encoding="utf-8") as stream:
        if target.stat().st_size and not target.read_text().endswith("\n"):
            stream.write("\n")
        stream.write(text)
    print(f"appended {args.dataset_id}@{args.version} to {target}")


if __name__ == "__main__":
    main()
