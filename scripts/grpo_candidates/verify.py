#!/usr/bin/env python3
"""Independent checks on a built candidate version, from its files only.

Texts and audio against eval_refs.py / recipe_refs.py output; every audio slot inside its file;
the start of a sample of files decoded. For hotword records also the list contract: the list is the
record's ``hotwords``, no gold first, no gold in a no_gold list, distractors absent from the
reference, and the GRPO hotword reward (loaded from --reward-module) scoring the reference itself 1.0.

    python scripts/grpo_candidates/verify.py --version-dir DIR --split zh --eval-refs E --recipe-refs R \\
        [--reward-module .../rewards/qwen3_asr.py] --output verify.json
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hotword_bench"))
from common import compact

ROOT = Path("/workspace/data")
DECODE_SAMPLE = 500


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def refs(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version-dir", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--eval-refs", type=Path, required=True)
    parser.add_argument("--recipe-refs", type=Path)
    parser.add_argument("--reward-module", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = list(lines(args.version_dir / f"records_{args.split}.jsonl.gz"))
    index = {r["cut_id"]: r for r in lines(args.version_dir / f"audio_index_{args.split}.jsonl.gz")}
    evals = refs(args.eval_refs)
    eval_texts, eval_utts, eval_audio = set(evals["texts"]), set(evals["utterances"]), set(evals["audio"])
    trained = refs(args.recipe_refs) if args.recipe_refs else {"texts": [], "audio": []}
    train_texts, train_audio = set(trained["texts"]), set(trained["audio"])
    report = Counter()
    report["records"] = len(records)
    report["unique_ids"] = len({r["id"] for r in records})
    reward = None
    if args.reward_module:
        spec = importlib.util.spec_from_file_location("grpo_rewards", args.reward_module)
        reward = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reward)
    paths = set()
    for record in records:
        (slot,) = record["audio_slots"]
        ref = slot["ref"]
        row = index[ref["cut_id"]]
        path = os.path.normpath(str(ROOT / row["relative_path"]))
        paths.add(path)
        start = ref.get("start", 0.0)
        if start + ref["duration"] > row["duration"] + 0.01:
            report["span_outside_file"] += 1
        report["audio_in_eval"] += path in eval_audio
        report["audio_in_recipe"] += path in train_audio
        key = compact(record["target"], "zh")
        if key:
            report["text_in_eval"] += key in eval_texts
            report["text_in_recipe"] += key in train_texts
        source_id = record["metadata"].get("source_id")
        if source_id:
            report["utterance_in_eval"] += f"{record['metadata']['source_corpus']}:{source_id}" in eval_utts or source_id in eval_utts
        if not record["target"]:
            report["empty_target"] += 1
            continue
        meta = record["metadata"]
        words, golds = record["hotwords"], set(meta["golds"])
        kind = meta["kind"]
        report[f"kind_{kind}"] += 1
        report["list_under_30"] += len(words) < 30
        report["duplicate_word"] += len(set(words)) != len(words)
        report["comma_in_word"] += any("," in w for w in words)
        report["gold_first"] += words[0] in golds
        report["gold_in_no_gold_list"] += kind == "no_gold" and bool(golds & set(words))
        report["gold_missing_from_gold_list"] += kind == "gold" and not golds <= set(words)
        report["prompt_differs"] += meta["hotword_prompt"] != ",".join(words)
        if reward:
            distractors = [w for w in words if w not in golds]
            ref_units = reward.units(record["target"])
            report["distractor_in_reference"] += any(reward._contains(ref_units, reward.units(w)) for w in distractors)
            answer = f"language Chinese<asr_text>{record['target']}"
            report["reference_reward_not_1"] += reward.hotword(answer, answer, ",".join(words)) != 1.0
    rng = random.Random(1)
    sample = rng.sample(sorted(paths), min(DECODE_SAMPLE, len(paths)))
    for path in sample:
        try:
            sf.read(path, frames=1600)
            report["decode_ok"] += 1
        except Exception:  # noqa: BLE001 - counted, the report shows it
            report["decode_failed"] += 1
    out = {"version_dir": str(args.version_dir), "files": len(paths), "checks": dict(sorted(report.items())),
           "eval_refs": evals["report"], "recipe_sources": trained.get("sources")}
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out["checks"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
