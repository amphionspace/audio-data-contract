#!/usr/bin/env python3
"""Record IDs of a training split that come from the recordings held out by ``ts_asr_real``.

``source/<version>/excluded-recordings.txt`` lists Emilia2 recording IDs (``<hash>_dlg_<n>``). Training
configs exclude by record ID (``exclude_records``: a file with one record ID per line), and an Emilia2
record ID contains its recording ID, so this lists every record of a split whose recording is held out.

    python scripts/ts_real/exclusion_records.py --roots roots.json --catalog catalog \
        --dataset emilia2_zh_dialogue_diarize --version moss-transcribe-diarize-0.9B --split train_120s \
        --output excluded-records.txt
"""

import argparse
import gzip
import json
import re
from pathlib import Path

from audio_data_contract import load_catalog, resolve_split

RECORDING = re.compile(r"[0-9a-f]{16}_dlg_\d{5}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--excluded", type=Path, default=None, help="excluded-recordings.txt (default: the ts_asr_real v2 list)")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    excluded_file = args.excluded or Path(roots["ts_asr_real"]) / "source" / "v2-20261013" / "excluded-recordings.txt"
    held_out = set(excluded_file.read_text().split())
    (path,) = resolve_split(load_catalog(args.catalog), args.dataset, args.version, args.split, "records", roots)
    ids = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            record_id = json.loads(line)["id"]
            match = RECORDING.search(record_id)
            if match and match.group(0) in held_out:
                ids.append(record_id)
    args.output.write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8")
    print(f"{len(ids)} records of {args.dataset}@{args.version}:{args.split} -> {args.output}")


if __name__ == "__main__":
    main()
