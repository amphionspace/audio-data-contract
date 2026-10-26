#!/usr/bin/env python3
"""Pick the benchmark's reference voices from test splits of registered corpora.

Each voice is one test-split speaker with two different utterances: a prompt for
zero-shot voice cloning (audio + transcript) and an enrollment clip for the TS-ASR
panel. Test speakers are unseen in training, and the benchmark keeps them for
itself: training data built later from the same generator must use other voices.

    python scripts/context_correction/voices.py --roots /workspace/data/registry/roots.json \
        --out <source dir>/voices.jsonl
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import yaml

from audio_data_contract import load_catalog, resolve_split

HERE = Path(__file__).resolve().parent


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def speakers(source, catalog, roots):
    paths = {role: resolve_split(catalog, source["dataset"], source["version"], source["split"], role, roots)
             for role in ("recordings", "supervisions")}
    audio = {r["id"]: r["sources"][0]["source"] for path in paths["recordings"] for r in rows(path)}
    by_speaker = defaultdict(list)
    for row in (row for path in paths["supervisions"] for row in rows(path)):
        text = re.sub(r"\s+", "", row.get("text") or "")
        # whole-file utterances with a transcript only: the prompt transcript must match the audio
        if not text or row.get("start", 0) != 0 or row["recording_id"] not in audio:
            continue
        by_speaker[f"{source['dataset']}:{row['speaker']}"].append({
            "utt_id": f"{source['dataset']}:{row['id']}", "text": text, "duration": float(row["duration"]),
            "path": audio[row["recording_id"]], "gender": row.get("gender") or (row.get("custom") or {}).get("gender"),
            "custom": row.get("custom") or {},
        })
    return by_speaker


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    spec = recipe["voices"]
    roots = json.loads(args.roots.read_text())
    catalog = load_catalog(args.catalog)
    rng = random.Random(f"{recipe['seed']}:voices")
    lo, hi = spec["prompt_seconds"]
    voices = []
    for source in spec["sources"]:
        pool = speakers(source, catalog, roots)
        eligible = []
        for speaker, utts in sorted(pool.items()):
            prompts = [u for u in utts if lo <= u["duration"] <= hi and len(u["text"]) >= spec["prompt_min_chars"]]
            if len(prompts) >= 2:
                eligible.append((speaker, prompts))
        for speaker, prompts in rng.sample(eligible, min(source["n"], len(eligible))):
            prompt, enroll = rng.sample(prompts, 2)
            voices.append({
                "voice_id": f"voice-{len(voices):03d}", "speaker": speaker, "corpus": source["dataset"],
                "gender": prompt["gender"], "custom": prompt["custom"],
                "prompt": {k: prompt[k] for k in ("utt_id", "path", "text", "duration")},
                "enrollment": {k: enroll[k] for k in ("utt_id", "path", "text", "duration")},
            })
        print(f"{source['dataset']}: {len(eligible)} eligible speakers, took {min(source['n'], len(eligible))}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as stream:
        for voice in voices:
            stream.write(json.dumps(voice, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
