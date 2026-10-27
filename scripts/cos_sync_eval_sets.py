#!/usr/bin/env python3
"""Back up the datasets that registered eval sets use but no COS binding covers yet.

`pending` lists them; `run` uploads them as one new snapshot through
cos_sync_catalog.py and binds it under catalog/backups/. With nothing pending
`run` exits 0 without touching COS, so it can run from cron. Local state belongs
under state/, and the shell needs COS_SecretID / COS_SecretKey.
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

SCRIPTS = Path(__file__).resolve().parent
REPOSITORY = SCRIPTS.parent
BACKUPS = REPOSITORY / "catalog" / "backups"
YAML_LOADER = YAML(typ="safe")
PREFIX = "audio-data-contract/v1/eval-sets-"


def eval_set_datasets(root):
    keys = set()
    for path in sorted(Path(root).glob("*/*/eval-set.yaml")):
        config = YAML_LOADER.load(path.read_text()) or {}
        for section in ("validation", "evaluation"):
            for entry in config.get(section) or []:
                keys.add(f"{entry['dataset_id']}@{entry['version']}")
    return keys


def bound_datasets(backups):
    keys = set()
    for path in sorted(Path(backups).glob("*.json")):
        keys |= set(json.loads(path.read_text()).get("dataset_bindings", {}))
    return keys


def pending(eval_sets, backups):
    return sorted(eval_set_datasets(eval_sets) - bound_datasets(backups))


def run(args, names):
    day = datetime.datetime.now(datetime.timezone.utc).date().strftime("%Y%m%d")
    work = args.work or REPOSITORY / "state" / f"cos-eval-sets-{day}"
    binding = BACKUPS / f"cos-{day}-eval-sets.json"
    if binding.exists():
        raise SystemExit(f"{binding} exists; bind a new day or move it before running again")
    work.mkdir(parents=True, exist_ok=True)
    listing = work / "datasets.txt"
    if not (work / "config.json").exists():
        listing.write_text("\n".join(names) + "\n")
    common = [sys.executable, SCRIPTS / "cos_sync_catalog.py"]
    shared = ["--work", work, "--catalog", args.catalog, "--roots", args.roots]
    steps = [
        [*common, "scan", *shared],
        [*common, "upload", *shared, "--workers", str(args.workers)],
        [sys.executable, SCRIPTS / "cos_restore.py", "bind", "--work", work, "--binding", binding],
    ]
    if not (work / "config.json").exists():
        steps.insert(0, [
            *common, "init", *shared, "--bucket", args.bucket, "--prefix", PREFIX + day,
            "--dataset-file", listing,
        ])
    for step in steps:
        subprocess.run([str(part) for part in step], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pending", "run"])
    parser.add_argument("--eval-sets", type=Path, required=True,
                        help="amphion-eval's src/amphion_eval/defaults/eval-sets")
    parser.add_argument("--catalog", type=Path, default=REPOSITORY / "catalog")
    parser.add_argument("--roots", type=Path, default=REPOSITORY / "roots.json")
    parser.add_argument("--bucket", default="amphion-audio-backup-1373259071")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    names = pending(args.eval_sets, BACKUPS)
    if args.command == "pending":
        print("\n".join(names))
    elif names:
        run(args, names)


if __name__ == "__main__":
    main()
