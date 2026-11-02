#!/usr/bin/env python3
"""Collect what the evaluation sets contain, so training candidates can be checked against it.

Reads every ``eval-set.yaml`` under the given AmphionEval checkouts (validation and
evaluation entries, all versions), resolves each dataset split through the catalogs in
order (the shared registry first, then unmerged worktree catalogs) and writes:

``texts``
    Every reference and every utterance text an eval record names (TS mixtures list
    their enrollment and interferer utterances in metadata), compacted with the
    hotword scorer's normalization.
``utterances``
    Component utterance ids an eval record names (``corpus:utt``), e.g. the
    MagicData utterances inside a TS benchmark mixture.
``audio``
    Absolute paths of the audio files eval records read (audio indexes, Lhotse
    recordings and cuts, and any audio path written inside a record).

Splits no catalog declares are listed under ``unresolved``.

    python scripts/grpo_candidates/eval_refs.py --output eval-refs.json.gz \\
        --eval-sets /path/amphion-eval ... --catalogs /workspace/data/registry/catalog ...
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hotword_bench"))
from common import compact

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.roots import load_roots

AUDIO_SUFFIXES = (".wav", ".flac", ".mp3", ".m4a", ".opus", ".ogg", ".sph", ".aac")
TEXT_KEYS = {"text", "target"}


def lines(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def walk(value, key, out):
    """Texts, component ids and audio paths anywhere inside one record."""
    if isinstance(value, dict):
        for name, item in value.items():
            walk(item, name, out)
    elif isinstance(value, list):
        for item in value:
            walk(item, key, out)
    elif isinstance(value, str):
        if key in TEXT_KEYS and value.strip():
            out["texts"].add(compact(value, "zh"))
        elif key == "id" and ":" in value:
            out["utterances"].add(value)
        if value.lower().endswith(AUDIO_SUFFIXES):
            out["audio"].add(value)


def declares(catalog, dataset_id, version, split):
    try:
        catalog.get(dataset_id, version).split(split)
    except Exception:  # noqa: BLE001 - not in this catalog
        return False
    return True


def entries(eval_roots):
    found = {}
    for root in eval_roots:
        for path in sorted(Path(root).glob("src/amphion_eval/defaults/eval-sets/*/*/eval-set.yaml")):
            config = yaml.safe_load(path.read_text()) or {}
            name = "/".join(path.parts[-3:-1])
            for section in ("validation", "evaluation"):
                for entry in config.get(section) or []:
                    found.setdefault((entry["dataset_id"], entry["version"], entry["split"]), set()).add(name)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--eval-sets", nargs="+", required=True, help="AmphionEval checkouts")
    parser.add_argument("--catalogs", nargs="+", required=True, help="catalog directories, first match wins")
    parser.add_argument("--roots", default="/workspace/data/registry/roots.json")
    args = parser.parse_args()
    roots = load_roots(args.roots)
    catalogs = []
    for path in args.catalogs:
        try:
            catalogs.append((path, load_catalog(path)))
        except Exception as error:  # noqa: BLE001 - a worktree catalog that no longer loads is skipped
            print(f"skip catalog {path}: {type(error).__name__}: {error}", file=sys.stderr)
    out = {"texts": set(), "utterances": set(), "audio": set()}
    resolved, unresolved = [], []
    for (dataset_id, version, split), sets in sorted(entries(args.eval_sets).items()):
        match = next((item for item in catalogs if declares(item[1], dataset_id, version, split)), None)
        if match is None:
            unresolved.append({"entry": f"{dataset_id}@{version}:{split}", "eval_sets": sorted(sets)})
            continue
        path, catalog = match
        before = {key: len(value) for key, value in out.items()}
        for role in ("records", "supervisions", "cuts", "recordings", "audio_index"):
            for artifact in resolve_split(catalog, dataset_id, version, split, role, roots):
                files = sorted(artifact.glob("*.jsonl.gz")) if artifact.is_dir() else [artifact]
                for file in files:
                    for row in lines(file):
                        if role == "audio_index":
                            out["audio"].add(str(Path(roots[row["root_alias"]]) / row["relative_path"]))
                        else:
                            walk(row, None, out)
        resolved.append({"entry": f"{dataset_id}@{version}:{split}", "catalog": path,
                         **{f"new_{key}": len(out[key]) - before[key] for key in out}})
    # normpath only: resolving every file on this filesystem costs ~1 ms each
    out["audio"] = {os.path.normpath(p) for p in out["audio"]}
    report = {"resolved": len(resolved), "unresolved": unresolved,
              **{key: len(value) for key, value in out.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as stream:
        json.dump({"report": report, "entries": resolved,
                   **{key: sorted(value) for key, value in out.items()}}, stream, ensure_ascii=False)
    print(json.dumps(report, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
