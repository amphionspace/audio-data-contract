#!/usr/bin/env python3
"""Read one registered speaker record and resolve its audio and segment bounds."""

import argparse
import gzip
import json
from pathlib import Path

from audio_data_contract import load_catalog, load_records, resolve_artifact


def resolve_audio(record, catalog, roots):
    wanted = {}
    for slot in record.audio_slots:
        ref = slot.ref
        spec = catalog.get(ref.dataset_id, ref.version)
        index = resolve_artifact(catalog, ref.dataset_id, ref.version,
                                 spec.splits[ref.split]["audio_index_artifact"], roots)
        wanted.setdefault(index, set()).add(ref.cut_id)
    found = {}
    for index, ids in wanted.items():
        with gzip.open(index, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                if row["cut_id"] in ids:
                    found[row["cut_id"]] = row
    result = {}
    for slot in record.audio_slots:
        ref = slot.ref
        row = found[ref.cut_id]
        root = Path(roots[row["root_alias"]]).resolve()
        path = (root / row["relative_path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"invalid audio path: {row['relative_path']}")
        start = ref.start or 0
        duration = ref.duration if ref.duration is not None else row["duration"] - start
        if start < 0 or duration <= 0 or start + duration > row["duration"] + 1e-6:
            raise ValueError(f"invalid segment bounds: {record.id}")
        result[slot.name] = {"path": str(path), "sample_rate": row["sample_rate"],
                             "channels": row["channels"], "channel": ref.channel,
                             "start": start, "duration": duration}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("split")
    parser.add_argument("--version", default="speaker-records-v1-20260912")
    parser.add_argument("--catalog", default="catalog")
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--id")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    catalog = load_catalog(args.catalog)
    spec = catalog.get(args.dataset, args.version)
    path = resolve_artifact(catalog, args.dataset, args.version,
                            spec.splits[args.split]["records_artifact"], roots)
    for record in load_records(path):
        if args.id is None or record.id == args.id:
            print(json.dumps({"record": record.to_dict(),
                              "audio": resolve_audio(record, catalog, roots)},
                             ensure_ascii=False, indent=2))
            return
    raise ValueError("requested record was not found")


if __name__ == "__main__":
    main()
