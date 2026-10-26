#!/usr/bin/env python3
"""GigaSpeech test biasing lists, rebuilt with the protocol of SALMONN-2 (arXiv 2607.17079).

SALMONN-2 follows the LibriSpeech rare-word protocol (Le et al. 2021) on the
GigaSpeech test set, with lists of 20 / 50 / 100 words; its lists are not
public. Here a word is rare when it is not among the K most frequent words of
the GigaSpeech XL training transcripts; the gold words of an utterance are its
rare words, distractors are drawn from the rare training vocabulary. K is the
candidate whose test statistics are closest to the ones SALMONN-2 reports (37%
of utterances with a biasing word, 1.5 on average among those).

Writes ``<source>/items/gigaspeech_test.jsonl`` and ``<source>/gigaspeech-vocab.json``.

    python scripts/hotword_bench/gigaspeech.py --source <source dir>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import contains, iter_manifest, normalize, order_key, write_jsonl
from sources import audio_of, check, recordings, unique

HERE = Path(__file__).resolve().parent


def lists_for(gold, text, pool, sizes, rng_of):
    """Gold + random rare words; a distractor never matches the reference after normalization
    (``that'`` normalizes to ``that``)."""
    def usable(word, taken):
        return word not in taken and not contains(text, word, "en")

    lists = {}
    for size in sizes:
        rng = rng_of(f"l{size}")
        fill = max(0, size - len(gold))
        distractors = []
        while len(distractors) < fill:
            word = pool[rng.randrange(len(pool))]
            if usable(word, distractors):
                distractors.append(word)
        entries = [*gold, *distractors]
        rng.shuffle(entries)
        lists[f"l{size}"] = entries
        if gold and size == 50:
            rng = rng_of("l50_no_gold")
            kept = list(distractors)
            while len(kept) < size:
                word = pool[rng.randrange(len(pool))]
                if usable(word, kept):
                    kept.append(word)
            rng.shuffle(kept)
            lists["l50_no_gold"] = kept
    return lists


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    spec = recipe["sources"]["gigaspeech"]

    counts = Counter()
    for sup in iter_manifest(spec["train_supervisions"]):
        counts.update(sup["text"].split())
    ranked = [w for w, _ in counts.most_common()]
    tests = list(iter_manifest(spec["supervisions"]))

    stats = {}
    for k in spec["common_k_candidates"]:
        common = set(ranked[:k])
        golds = [[w for w in unique(s["text"].split()) if w not in common] for s in tests]
        positives = [g for g in golds if g]
        stats[k] = {"positive_fraction": len(positives) / len(tests),
                    "words_per_positive": sum(map(len, positives)) / max(1, len(positives))}
    target = (spec["target_positive_fraction"], spec["target_words_per_positive"])
    k = min(stats, key=lambda c: abs(stats[c]["positive_fraction"] - target[0]) / target[0]
            + abs(stats[c]["words_per_positive"] - target[1]) / target[1])
    common = set(ranked[:k])
    pool = [w for w in ranked[k:] if normalize(w)]
    (args.source / "gigaspeech-vocab.json").write_text(json.dumps(
        {"train_words": len(ranked), "train_tokens": sum(counts.values()), "candidates": stats,
         "chosen_common_k": k, "target": dict(zip(("positive_fraction", "words_per_positive"), target)),
         "distractor_pool": len(pool)}, indent=2))
    print(json.dumps(stats), f"chosen K={k}", file=sys.stderr)

    recs = recordings(spec["recordings"])
    items = []
    for sup in tests:
        words = sup["text"].split()
        gold = [w for w in unique(words) if w not in common]
        item = {
            "split": "gigaspeech_test", "id": sup["id"], "language": "en", "text": sup["text"], "gold": gold,
            "labels": {"source": "gigaspeech", "domain": sup["id"][:3]},  # POD / YOU / AUD
            "audio": audio_of(recs[sup["recording_id"]], sup), "quarantine": None,
            "lists": lists_for(gold, sup["text"], pool, spec["list_sizes"],
                               lambda cond, sid=sup["id"]: random.Random(order_key(recipe["seed"], "gigaspeech_test", sid, cond))),
        }
        items.append(check(item, recipe))
    write_jsonl(args.source / "items" / "gigaspeech_test.jsonl", items)
    print(f"gigaspeech_test: {len(items)} items, {sum(1 for it in items if it['quarantine'])} quarantined",
          file=sys.stderr)


if __name__ == "__main__":
    main()
