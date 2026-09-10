#!/usr/bin/env python3
"""Verify published target-ASR gzip files, references, and duration statistics."""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import orjson

from audio_data_contract import load_catalog, resolve_artifact


def rows(path, artifact):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if path.stat().st_size != artifact.expected_bytes or digest.hexdigest() != artifact.sha256:
        raise ValueError(f"artifact integrity mismatch: {path}")
    count = 0
    with gzip.open(path, "rb") as stream:
        for line in stream:
            count += 1
            yield orjson.loads(line)
    if count != artifact.metadata["record_count"]:
        raise ValueError(f"artifact count mismatch: {path}")


def verify(spec, catalog, roots):
    def path(name):
        return resolve_artifact(catalog, spec.dataset_id, spec.version, name, roots)

    index = {}
    for row in rows(path("audio_index"), spec.artifact("audio_index")):
        key = row["cut_id"]
        if key in index or row["duration"] <= 0:
            raise ValueError("duplicate or invalid audio index entry")
        expected_id = hashlib.sha256(
            (row["root_alias"] + ":" + row["relative_path"]).encode()
        ).hexdigest()
        if key != expected_id or Path(row["relative_path"]).is_absolute():
            raise ValueError("audio index ID/path mismatch")
        if ".." in Path(row["relative_path"]).parts or row["root_alias"] not in roots:
            raise ValueError("unresolvable audio index path")
        if row["duration"] != row["num_frames"] / row["sample_rate"]:
            raise ValueError("audio duration disagrees with header facts")
        index[key] = row
    total = 0
    referenced = set()
    groups = {}
    for split_name, split in spec.splits.items():
        if "records_artifact" not in split:
            continue
        name = split["records_artifact"]
        ids = set()
        unique_mix = set()
        seconds = 0
        negative = 0
        for row in rows(path(name), spec.artifact(name)):
            if row["id"] in ids or not row["id"].startswith(split_name + ":"):
                raise ValueError(f"duplicate/incorrect record ID in {name}")
            ids.add(row["id"])
            if row["schema_version"] != "audio-record/1.0" or row["task"] != "ts_asr":
                raise ValueError("incorrect record schema/task")
            if row["language"] not in spec.languages:
                raise ValueError("incorrect record language")
            if [s["name"] for s in row["audio_slots"]] != ["enrollment", "mixture"]:
                raise ValueError("incorrect audio slot mapping")
            if row["labels"]["target_present"] != (row["target"] != ""):
                raise ValueError("target/negative label mismatch")
            for slot in row["audio_slots"]:
                ref = slot["ref"]
                if (ref["dataset_id"], ref["version"], ref["split"]) != (
                    spec.dataset_id, spec.version, split_name,
                ) or ref["cut_id"] not in index:
                    raise ValueError(f"unresolved audio reference in {name}")
                referenced.add(ref["cut_id"])
            mix = row["audio_slots"][1]["ref"]["cut_id"]
            seconds += index[mix]["duration"]
            unique_mix.add(mix)
            negative += not row["labels"]["target_present"]
        stats = split["statistics"]
        if len(ids) != stats["records"] or negative != stats["negative_records"]:
            raise ValueError(f"record count mismatch in {name}")
        if not math.isclose(seconds / 3600, stats["duration_hours"], abs_tol=1e-9):
            raise ValueError(f"duration mismatch in {name}")
        check_unique(stats, unique_mix, index)
        group = groups.setdefault(split["group"], {"count": 0, "seconds": 0, "mix": set()})
        group["count"] += len(ids)
        group["seconds"] += seconds
        group["mix"].update(unique_mix)
        total += len(ids)
        print(spec.key, name, len(ids), "verified", flush=True)
    for name, group in groups.items():
        stats = spec.splits[name]["statistics"]
        if stats["records"] != group["count"] or not math.isclose(
            stats["duration_hours"], group["seconds"] / 3600, abs_tol=1e-9,
        ):
            raise ValueError(f"parent statistics mismatch: {name}")
        check_unique(stats, group["mix"], index)
    if referenced != set(index):
        raise ValueError("audio index contains unreferenced entries")
    return {"dataset": spec.key, "records": total, "audio_files": len(index)}


def check_unique(stats, mixture_ids, index):
    if stats["unique_mixture_count"] != len(mixture_ids) or not math.isclose(
        stats["unique_mixture_duration_hours"],
        sum(index[k]["duration"] for k in mixture_ids) / 3600, abs_tol=1e-9,
    ):
        raise ValueError("unique mixture statistics mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", default="catalog")
    parser.add_argument("--recipe", type=Path, default=Path(__file__).with_name("sources.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    catalog = load_catalog(args.catalog)
    recipe = json.loads(args.recipe.read_text())
    reports = [verify(catalog.get(j["dataset_id"], j["version"]), catalog, roots)
               for j in recipe["jobs"]]
    if args.output:
        args.output.write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
