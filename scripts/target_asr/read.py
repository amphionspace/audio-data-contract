#!/usr/bin/env python3
"""Print one portable TS-ASR record and resolve both audio slots locally."""

import argparse
import gzip
import json
from pathlib import Path

from audio_data_contract import load_catalog, load_records, resolve_artifact


def resolve_audio(record, catalog, roots):
    # One shared audio index per version. Read only the wanted IDs into memory.
    wanted = {slot.ref.cut_id for slot in record.audio_slots}
    indexes = {}
    for slot in record.audio_slots:
        ref = slot.ref
        spec = catalog.get(ref.dataset_id, ref.version)
        name = spec.splits[ref.split]["audio_index_artifact"]
        path = resolve_artifact(catalog, ref.dataset_id, ref.version, name, roots)
        indexes[path] = None
    found = {}
    for path in indexes:
        with gzip.open(path, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                if row["cut_id"] in wanted:
                    found[(path, row["cut_id"])] = row
    result = {}
    for slot in record.audio_slots:
        ref = slot.ref
        spec = catalog.get(ref.dataset_id, ref.version)
        index = resolve_artifact(catalog, ref.dataset_id, ref.version,
                                 spec.splits[ref.split]["audio_index_artifact"], roots)
        row = found[(index, ref.cut_id)]
        root = Path(roots[row["root_alias"]]).resolve()
        audio = (root / row["relative_path"]).resolve()
        if not audio.is_relative_to(root) or not audio.is_file():
            raise ValueError(f"audio reference is missing or escapes root: {row['cut_id']}")
        result[slot.name] = {"path": str(audio), "sample_rate": row["sample_rate"],
                             "channels": row["channels"], "duration": row["duration"]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id")
    parser.add_argument("version")
    parser.add_argument("split")
    parser.add_argument("--catalog", default="catalog")
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--id", help="default: first record")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    catalog = load_catalog(args.catalog)
    spec = catalog.get(args.dataset_id, args.version)
    split = spec.splits[args.split]
    names = split.get("records_artifacts") or [split["records_artifact"]]
    for name in names:
        path = resolve_artifact(catalog, spec.dataset_id, spec.version, name, roots)
        for record in load_records(path):
            if args.id is None or args.id == record.id:
                print(json.dumps({"record": record.to_dict(),
                                  "audio": resolve_audio(record, catalog, roots)},
                                 ensure_ascii=False, indent=2))
                return
    raise ValueError(f"record not found: {args.id}")


if __name__ == "__main__":
    main()
