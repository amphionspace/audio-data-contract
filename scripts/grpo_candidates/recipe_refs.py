#!/usr/bin/env python3
"""Collect the Chinese text and audio a training recipe has shown the model.

Reads a data config (the SFT recipe's data-effective.yaml) and writes, like eval_refs.py,
``texts`` (references and every utterance named in a record, e.g. a scene's targets) and
``audio`` (files from audio indexes and recordings). English-only sources are skipped:
candidates are Mandarin and those sources neither share their text nor their audio.

    python scripts/grpo_candidates/recipe_refs.py --data data-effective.yaml --output recipe-refs.json.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_refs import lines, walk

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.roots import load_roots

ENGLISH_ONLY = {"librimix", "gigaspeech", "common_voice_en", "librispeech", "fleurs_en", "ami_sdm", "chime6"}
SECTIONS = ("train", "interference_sources")


def collect(job):
    catalog_path, roots_path, dataset_id, version, split = job
    roots = load_roots(roots_path)
    catalog = load_catalog(catalog_path)
    out = {"texts": set(), "utterances": set(), "audio": set()}
    for role in ("records", "supervisions", "recordings", "audio_index"):
        for artifact in resolve_split(catalog, dataset_id, version, split, role, roots):
            for file in (sorted(artifact.glob("*.jsonl.gz")) if artifact.is_dir() else [artifact]):
                for row in lines(file):
                    if role == "audio_index":
                        out["audio"].add(str(Path(roots[row["root_alias"]]) / row["relative_path"]))
                    else:
                        walk(row, None, out)
    print(f"{dataset_id}@{version}:{split} texts {len(out['texts'])} audio {len(out['audio'])}", flush=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", default="/workspace/data/registry/catalog")
    parser.add_argument("--roots", default="/workspace/data/registry/roots.json")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    config = yaml.safe_load(args.data.read_text())
    sources = sorted({(s["dataset_id"], s["version"], s["split"]) for section in SECTIONS for s in config.get(section) or []
                      if s["dataset_id"] not in ENGLISH_ONLY})
    merged = {"texts": set(), "audio": set()}
    with ProcessPoolExecutor(args.workers) as pool:
        for out in pool.map(collect, [(args.catalog, args.roots, *s) for s in sources]):
            merged["texts"] |= out["texts"]
            merged["audio"] |= {os.path.normpath(p) for p in out["audio"]}
    with gzip.open(args.output, "wt", encoding="utf-8") as stream:
        json.dump({"sources": [f"{d}@{v}:{s}" for d, v, s in sources], **{k: sorted(v) for k, v in merged.items()}},
                  stream, ensure_ascii=False)
    print({k: len(v) for k, v in merged.items()}, len(sources))


if __name__ == "__main__":
    main()
