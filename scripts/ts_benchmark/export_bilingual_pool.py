#!/usr/bin/env python3
"""Export Common Voice utterance lists for the cross-lingual TS benchmark (ts_asr_crosslingual).

Bilingual targets are the Common Voice accounts (``client_id``, the ``speaker`` of the Lhotse supervisions) that
recorded both languages of ``--languages`` (default zh-CN and en); speakers already used as TS training targets
(``--exclude-speakers``) are dropped. Their utterances go to one list per language under one dataset name, so a
speaker has the same id in both pools and a recipe can draw the enrollment from the other language
(``enroll_pool``). Interferer lists are the other speakers of the given splits, bilingual ones removed so a target
never appears as an interferer.

A ``--held-out`` language (es: its train split is a training set) only contributes dev/test utterances, and the
export fails if a target also appears in that language's train split.

Each list is ``utterances.jsonl.gz`` (``id``, ``speaker``, ``text``, ``duration``, ``path``), read by a recipe pool
source ``{manifest: {alias, path}, dataset, version, split}``; ``path`` is the Common Voice clip (absolute).

    python scripts/ts_benchmark/export_bilingual_pool.py --exclude-speakers used.json \
        --output /workspace/data/datasets/ts_asr_crosslingual/source/pools
    python scripts/ts_benchmark/export_bilingual_pool.py --languages es en --held-out es \
        --exclude-speakers ts-training-targets.json \
        --output /workspace/data/datasets/ts_asr_crosslingual/source/pools/es-v1-20261111
"""

import argparse
import glob
import gzip
import json
from collections import defaultdict
from pathlib import Path

LEGACY = "/workspace/data/datasets/common_voice_{lang}/versions/legacy-20260804/{split}_{kind}_*"
# Lhotse manifest globs per language; {kind} is sup or rec. Common Voice es keeps all splits in one directory.
MANIFESTS = {
    "zh": LEGACY.format(lang="zh", split="{split}", kind="{kind}") + "/cv-zh-CN_{name}_{split}*.jsonl.gz",
    "en": LEGACY.format(lang="en", split="{split}", kind="{kind}") + "/cv-en_{name}_{split}*.jsonl.gz",
    "es": "/workspace/data/datasets/common_voice_es/versions/legacy/manifests/cv-es_{name}_{split}.jsonl.gz",
}
INTERFERER_SPLITS = {"zh": ("dev", "test"), "en": ("test",), "es": ("dev", "test")}


def rows(lang, split, kind):
    name = "supervisions" if kind == "sup" else "recordings"
    for path in sorted(glob.glob(MANIFESTS[lang].format(split=split, kind=kind, name=name))):
        with gzip.open(path, "rt") as handle:
            for line in handle:
                yield json.loads(line)


def utterances(lang, splits, seconds):
    audio = {r["id"]: r["sources"][0]["source"] for split in splits for r in rows(lang, split, "rec")}
    out = defaultdict(list)
    for split in splits:
        for s in rows(lang, split, "sup"):
            if s["recording_id"] in audio and seconds[0] <= s["duration"] <= seconds[1] and s.get("text"):
                out[s["speaker"]].append({"id": s["id"], "speaker": s["speaker"], "text": s["text"],
                                          "duration": round(s["duration"], 3), "path": audio[s["recording_id"]],
                                          "split": split})
    return out


def write(path, by_speaker, keep):
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt") as handle:
        for speaker in sorted(keep):
            for row in by_speaker[speaker]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--languages", nargs=2, default=("zh", "en"), choices=sorted(MANIFESTS))
    parser.add_argument("--held-out", choices=sorted(MANIFESTS),
                        help="language whose train split is a training set: only its dev/test utterances are used")
    parser.add_argument("--exclude-speakers", type=Path, help="JSON list of client_ids used as TS training targets")
    parser.add_argument("--min-utterances", type=int, default=5, help="per language, for scenes and enrollments")
    parser.add_argument("--seconds", type=float, nargs=2, default=(1.5, 12.0))
    args = parser.parse_args()
    excluded = set(json.loads(args.exclude_speakers.read_text())) if args.exclude_speakers else set()
    a, b = args.languages
    by_lang = {lang: utterances(lang, ("dev", "test") if lang == args.held_out else ("train", "dev", "test"),
                                args.seconds) for lang in (a, b)}
    both = set(by_lang[a]) & set(by_lang[b])
    bilingual = {s for s in both if min(len(by_lang[lang][s]) for lang in (a, b)) >= args.min_utterances}
    targets = bilingual - excluded
    stats = {"languages": [a, b], "held_out": args.held_out, "bilingual": len(bilingual),
             "excluded_ts_targets": len(bilingual & excluded), "targets": len(targets)}
    if args.held_out:
        trained = {r["speaker"] for r in rows(args.held_out, "train", "sup")}
        if targets & trained:
            raise SystemExit(f"{len(targets & trained)} targets also speak in {args.held_out} train")
        stats[f"targets_in_{args.held_out}_train"] = 0
    for lang in (a, b):
        stats[f"target_{lang}_utterances"] = write(args.output / f"cv-bilingual-{lang}/utterances.jsonl.gz",
                                                   by_lang[lang], targets)
    every = set(by_lang[a]) | set(by_lang[b])
    for lang, by_speaker in by_lang.items():
        held = {s: [u for u in us if u["split"] in INTERFERER_SPLITS[lang]] for s, us in by_speaker.items()}
        keep = {s for s, us in held.items() if len(us) >= 2 and s not in both}
        stats[f"interferer_{lang}_speakers"] = len(keep)
        stats[f"interferer_{lang}_utterances"] = write(args.output / f"cv-interferer-{lang}/utterances.jsonl.gz", held, keep)
    stats["all_speakers_seen"] = len(every)
    (args.output / "cv-pools.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
