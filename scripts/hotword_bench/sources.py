#!/usr/bin/env python3
"""Collect benchmark items from the upstream sources (no LLM calls).

Writes ``<source>/items/<split>.jsonl`` with one item per utterance::

    {split, id, language, text, gold, labels, audio: {path, start, duration},
     quarantine (reason or null), lists (precomputed official lists, optional)}

``gold`` holds the hotwords spoken in the utterance (found in the normalized
reference, longest match first). The real_zh candidates (no gold yet) go to
``<source>/candidates/real_zh.jsonl``; mine.py labels them.

    python scripts/hotword_bench/sources.py --source <source dir> [--only aishell1_ne ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    DATASETS,
    iter_manifest,
    normalize,
    occurrences,
    order_key,
    read_jsonl,
    write_jsonl,
)

HERE = Path(__file__).resolve().parent


def recordings(pattern: str) -> dict[str, dict]:
    return {row["id"]: row for row in iter_manifest(pattern)}


def audio_of(recording: dict, supervision: dict) -> dict:
    (source,) = recording["sources"]
    return {"path": source["source"], "start": supervision.get("start", 0.0),
            "duration": supervision["duration"], "recording_duration": recording["duration"],
            "sample_rate": recording["sampling_rate"]}


def unique(words):
    return list(dict.fromkeys(words))


def check(item: dict, recipe: dict) -> dict:
    duration = item["audio"]["duration"]
    if duration < recipe["min_seconds"]:
        item["quarantine"] = f"duration {duration:.3f} s < {recipe['min_seconds']} s"
    elif duration > recipe["max_seconds"]:
        item["quarantine"] = f"duration {duration:.1f} s > {recipe['max_seconds']} s"
    return item


def aishell1_ne(recipe, source):
    spec = recipe["sources"]["aishell1_ne"]
    upstream = source / "upstream" / "seaco-paraformer"
    out = {}
    for split, part in spec["splits"].items():
        listed = [w.strip() for w in (upstream / part / "hotword.txt").read_text().splitlines() if w.strip()]
        r1 = {w.strip() for w in (upstream / part / "r1-hotword.txt").read_text().splitlines() if w.strip()}
        recs = recordings(f"{spec['audio']['dataset']}/versions/{spec['audio']['version']}/{part}_rec_0")
        sups = {s["id"]: s for s in iter_manifest(f"{spec['audio']['dataset']}/versions/{spec['audio']['version']}/{part}_sup_0")}
        items = []
        for line in (upstream / part / "text").read_text().splitlines():
            uttid, text = line.strip().split(maxsplit=1)
            gold = unique(occurrences(text, listed, "zh"))
            sup = sups[uttid]
            item = {
                "split": split, "id": uttid, "language": "zh",
                # the upstream SeACo text is the AISHELL-1 transcript without spaces
                "text": text, "gold": gold,
                "labels": {"source": "aishell1_ne", "r1": sorted(set(gold) & r1)},
                "audio": audio_of(recs[sup["recording_id"]], sup), "quarantine": None,
                "lists": {"official": listed},
            }
            if not gold:
                item["quarantine"] = "no listed hotword in the reference"
            items.append(check(item, recipe))
        out[split] = items
    return out


def contextasr(recipe, source):
    upstream = source / "upstream" / "contextasr-bench"
    audio_root = upstream / "audio" / "extracted"
    items = []
    for row in read_jsonl(upstream / "ContextASR-Speech_Mandarin.jsonl"):
        entities = unique(e for e in row["entity_list"] if normalize(e))
        gold = unique(occurrences(row["text"], entities, "zh"))
        item = {
            "split": "contextasr_speech_zh", "id": row["uniq_id"], "language": "zh", "text": row["text"],
            "gold": gold,
            "labels": {"source": "contextasr_speech_zh", "domain": row["domain_label"],
                       "seed_corpus": row["uniq_id"].rsplit("-", 1)[0]},
            "audio": {"path": str(audio_root / row["audio"]), "start": 0.0, "duration": row["duration"],
                      "recording_duration": row["duration"], "sample_rate": None},
            "quarantine": None,
            # entities the upstream lists but the normalized reference does not contain
            "upstream_entities_not_in_text": [e for e in entities if e not in gold],
        }
        if not gold:
            item["quarantine"] = "no upstream entity in the reference"
        items.append(check(item, recipe))
    return {"contextasr_speech_zh": items}


def local(recipe, source):
    out = {}
    cap = recipe["local_positive_cap"]
    for name, spec in recipe["sources"]["local"].items():
        recs = recordings(spec["recordings"])
        language = spec["language"]
        positives = []
        for sup in iter_manifest(spec["supervisions"]):
            custom = sup.get("custom") or {}
            listed = [h for h in custom.get("hotwords") or [] if normalize(h)]
            gold = unique(occurrences(sup["text"], listed, language))
            if not gold:
                continue
            labels = {"source": name}
            if name == "kespeech":
                labels["dialect"] = sup.get("language")
            item = {
                "split": name, "id": sup["id"], "language": language, "text": sup["text"], "gold": gold,
                "labels": labels, "audio": audio_of(recs[sup["recording_id"]], sup), "quarantine": None,
                "upstream_hotwords_not_in_text": [h for h in listed if h not in gold],
            }
            clean = custom.get("clean")
            if clean is not None and not clean.get("pass"):
                item["quarantine"] = f"upstream clean.pass false: {clean.get('reason', '')}".strip()
            positives.append(check(item, recipe))
        positives.sort(key=lambda it: order_key(recipe["seed"], name, it["id"]))
        scored = [it for it in positives if not it["quarantine"]][:cap]
        kept = {it["id"] for it in scored}
        # quarantined positives inside the capped prefix stay visible (not scored)
        horizon = positives.index(scored[-1]) + 1 if scored else len(positives)
        out[name] = scored + [it for it in positives[:horizon] if it["quarantine"] and it["id"] not in kept]
        print(f"{name}: {len(positives)} positives, kept {len(scored)}", file=sys.stderr)
    return out


def librispeech(recipe, source):
    spec = recipe["sources"]["librispeech"]
    upstream = source / "upstream" / "fbai-is21-deep-bias" / "ref"
    out = {}
    for split, part in spec["splits"].items():
        tag = part.replace("-", "_")
        recs = recordings(f"{spec['audio']['dataset']}/versions/{spec['audio']['version']}/{tag}_rec_0")
        sups = {s["id"]: s for s in iter_manifest(f"{spec['audio']['dataset']}/versions/{spec['audio']['version']}/{tag}_sup_0")}
        lists, refs, golds = {}, {}, {}
        for size in spec["list_sizes"]:
            for line in (upstream / f"{part}.biasing_{size}.tsv").read_text().splitlines():
                uttid, ref, gold, biasing = line.split("\t")
                refs[uttid], golds[uttid] = ref, json.loads(gold)
                lists.setdefault(uttid, {})[f"n{size}"] = json.loads(biasing)
        items = []
        for uttid, ref in refs.items():
            sup = sups[uttid]
            item = {
                "split": split, "id": uttid, "language": "en", "text": ref, "gold": unique(golds[uttid]),
                "labels": {"source": "librispeech"},
                "audio": audio_of(recs[sup["recording_id"]], sup), "quarantine": None,
                "lists": lists[uttid],
            }
            items.append(check(item, recipe))
        out[split] = items
    return out


def real_zh_candidates(recipe, source):
    spec = recipe["sources"]["real_zh"]
    rows = []
    for corpus, paths in spec["corpora"].items():
        recs = recordings(paths["recordings"])
        for sup in iter_manifest(paths["supervisions"]):
            subset = (sup.get("custom") or {}).get(paths["subset_field"]) if paths.get("subset_field") else None
            subset = f"{corpus}:{subset}" if subset else corpus
            item = {"split": "real_zh", "id": sup["id"], "language": "zh", "text": sup["text"], "gold": [],
                    "labels": {"source": corpus, "subset": subset},
                    "audio": audio_of(recs[sup["recording_id"]], sup), "quarantine": None,
                    "order": order_key(recipe["seed"], "real_zh", subset, sup["id"])}
            if normalize(item["text"]):
                rows.append(check(item, recipe))
    rows.sort(key=lambda it: (it["labels"]["subset"], it["order"]))
    write_jsonl(source / "candidates" / "real_zh.jsonl", rows)
    print(f"real_zh candidates: {len(rows)}", file=sys.stderr)


BUILDERS = {"aishell1_ne": aishell1_ne, "contextasr": contextasr, "local": local, "librispeech": librispeech}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--only", nargs="*", choices=[*BUILDERS, "real_zh"])
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    for name in args.only or [*BUILDERS, "real_zh"]:
        if name == "real_zh":
            real_zh_candidates(recipe, args.source)
            continue
        for split, items in BUILDERS[name](recipe, args.source).items():
            write_jsonl(args.source / "items" / f"{split}.jsonl", items)
            bad = sum(1 for it in items if it["quarantine"])
            print(f"{split}: {len(items)} items, {bad} quarantined", file=sys.stderr)


if __name__ == "__main__":
    assert DATASETS.exists()
    main()
