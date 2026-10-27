#!/usr/bin/env python3
"""Mirror the datasets that eval sets use to COS with `ab`, and pull them back.

A dataset directory is mirrored as is, so `ab pull` gives a complete copy: audio
indexes hold paths relative to that directory. Only datasets whose root alias is
their own directory are mirrored; datasets inside a shared root are listed as
skipped. `catalog/backups/ab-datasets.json` records what is mirrored and must be
committed. `pending --check` exits 1 while an eval set uses a dataset that is not
recorded there. `run` needs `roots.json` on the machine that holds the audio;
`pull` needs only `ab`.
"""

import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

REPOSITORY = Path(__file__).resolve().parent.parent
LEDGER = REPOSITORY / "catalog" / "backups" / "ab-datasets.json"
BUCKET = "amphion-audio-backup-1373259071"
PREFIX = "audio-data-contract/datasets/"
YAML_LOADER = YAML(typ="safe")


def eval_set_datasets(root):
    keys = set()
    for path in sorted(Path(root).glob("*/*/eval-set.yaml")):
        config = YAML_LOADER.load(path.read_text()) or {}
        for section in ("validation", "evaluation"):
            for entry in config.get(section) or []:
                keys.add(f"{entry['dataset_id']}@{entry['version']}")
    return keys


def load_ledger():
    if not LEDGER.exists():
        return {"bucket": BUCKET, "prefix": PREFIX, "datasets": {}}
    return json.loads(LEDGER.read_text())


def pending(keys, ledger, root_aliases):
    """Split unrecorded keys into {key: alias} to mirror and keys in a shared root.

    `root_aliases(key)` returns the set of root aliases the dataset's artifacts use.
    """
    aliases, shared = {}, []
    for key in sorted(keys - set(ledger["datasets"])):
        roots = root_aliases(key)
        if roots == {key.rsplit("@", 1)[0]}:
            aliases[key] = key.rsplit("@", 1)[0]
        else:
            shared.append(key)
    return aliases, shared


def catalog_aliases(catalog):
    def aliases(key):
        try:
            return {a.root_alias for a in catalog.get(*key.rsplit("@", 1)).artifacts}
        except Exception:  # noqa: BLE001 - unknown datasets are reported as skipped
            return set()

    return aliases


def ab(*arguments, capture=False):
    command = shutil.which("ab") or str(Path.home() / ".local" / "bin" / "ab")
    return subprocess.run(
        [command, *map(str, arguments)], check=True, text=True, capture_output=capture
    )


def remote(alias):
    return f"{BUCKET}:{PREFIX}{alias}/"


def verified(source, alias):
    """A dry run after the push must find nothing left to transfer."""
    out = ab("--json", "push", source, remote(alias), "--dry-run", capture=True).stdout
    summary = json.loads(out.strip().splitlines()[-1])["summary"]
    return summary["preview"] == summary["conflict"] == summary["failed"] == 0


def run(args, aliases):
    roots = json.loads(args.roots.read_text())
    ledger = load_ledger()
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    for alias in sorted(set(aliases.values())):
        source = roots[alias].rstrip("/") + "/"
        ab("push", source, remote(alias))
        if not verified(source, alias):
            raise SystemExit(f"{alias}: files still differ after the push")
        for key, name in aliases.items():
            if name == alias:
                ledger["datasets"][key] = {"alias": alias, "synced": today}
        LEDGER.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        print(f"mirrored {alias}", flush=True)


def pull(args):
    mirrored = {v["alias"] for v in load_ledger()["datasets"].values()}
    wanted = set(args.alias) or mirrored
    if wanted - mirrored:
        raise SystemExit("not mirrored: " + ", ".join(sorted(wanted - mirrored)))
    roots = {}
    for alias in sorted(wanted):
        ab("pull", remote(alias), args.dest / alias)
        roots[alias] = str((args.dest / alias).resolve())
    listing = args.dest / "roots.pulled.json"
    listing.write_text(json.dumps(roots, indent=2) + "\n")
    print(f"export AUDIO_DATA_ROOTS_FILE={listing.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pending", "run", "pull"])
    parser.add_argument("--eval-sets", type=Path, help="amphion-eval's defaults/eval-sets")
    parser.add_argument("--catalog", type=Path, default=REPOSITORY / "catalog")
    parser.add_argument("--roots", type=Path, default=REPOSITORY / "roots.json")
    parser.add_argument("--check", action="store_true", help="pending: exit 1 if any")
    parser.add_argument("--dest", type=Path, help="pull: directory for the datasets")
    parser.add_argument("--alias", action="append", default=[], help="pull: one dataset")
    args = parser.parse_args()
    if args.command == "pull":
        if not args.dest:
            parser.error("pull requires --dest")
        return pull(args)
    if not args.eval_sets:
        parser.error(f"{args.command} requires --eval-sets")
    from audio_data_contract import load_catalog

    aliases, shared = pending(
        eval_set_datasets(args.eval_sets),
        load_ledger(),
        catalog_aliases(load_catalog(args.catalog)),
    )
    if args.command == "run":
        return run(args, aliases)
    print("\n".join(aliases))
    if shared:
        print("skipped (shared root): " + ", ".join(shared), file=sys.stderr)
    if args.check and aliases:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
