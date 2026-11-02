#!/usr/bin/env python3
"""Pick references for the td-tech customer recordings where two independent transcripts agree.

EvalHub's machine references for the general recognition recordings come from Qwen-audio-3.1
(two from MOSS). Two more systems transcribe the same audio: FireRedASR2-AED and MiMo-V2.5-ASR,
neither of them Qwen-based. A general recording gets a reference when any two of the three give
the same scoring tokens under amphion-eval's native scoring (``tokens``), i.e. agree at CER 0
after the board's own normalization; the reference is EvalHub's text when it is one of the two,
otherwise FireRedASR2-AED's. Recordings where no two agree are left out.

The police command recordings keep EvalHub's reference (the term the speaker read, from the
recording group, partly confirmed by listening, not an ASR output); FireRedASR2-AED is compared
with it for information only.

Run in the amphion-eval environment with an amphion-eval source checkout that has native scoring
version 3 or later (it imports that scoring):

    PYTHONPATH=<amphion-eval>/src python scripts/tdtech_customer_bench/agree.py \
        --source /workspace/data/datasets/tdtech_customer_bench/source
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from amphion_eval.integrations.open_audio_llm.scoring import VERSION, tokens
from rapidfuzz.distance import Levenshtein

GENERAL = "asr_dingqiao-asr-quality@20261016-machine01"
POLICE = "asr_dingqiao-asr-police-cmd@20261020-jyjy-v6-human04"
SYSTEMS = {"firered": "FireRedASR2-AED", "mimo": "MiMo-V2.5-ASR"}
PREDICTIONS = {"firered": "firered-aed/predictions.jsonl", "mimo": "mimo-asr/predictions.jsonl"}


def reference(row):
    """The reference EvalHub scores with: the verified text, else the machine candidate."""
    annotation = row.get("annotation") or {}
    if annotation.get("status") == "verified" and (row.get("text") or "").strip():
        return row["text"]
    return annotation.get("reference_candidate") or row.get("text") or ""


def read_predictions(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("status") != "success":
            raise ValueError(f"{path}: {row['id']} did not finish ({row.get('status')})")
        rows[row["id"]] = row
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    predictions = {name: read_predictions(args.source / path) for name, path in PREDICTIONS.items()}
    result = {"scoring_version": VERSION, "systems": {"evalhub": "EvalHub reference", **SYSTEMS},
              "samples": {}}
    for name in (GENERAL, POLICE):
        manifest = args.source / "evalhub" / name / "manifest.jsonl"
        for line in manifest.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            texts = {"evalhub": reference(row)}
            texts.update({s: p[row["id"]]["text"] for s, p in predictions.items() if row["id"] in p})
            toks = {s: tokens(t, "zh") for s, t in texts.items()}
            errors = {f"{a}-{b}": Levenshtein.distance(toks[a], toks[b]) for a, b in combinations(toks, 2)}
            if name == GENERAL:
                agreed_by = next(([a, b] for a, b in combinations(toks, 2)
                                  if toks[a] and toks[a] == toks[b]), None)
                chosen = texts[agreed_by[0]] if agreed_by else None
            else:
                agreed_by = ["evalhub", "firered"] if toks["evalhub"] == toks["firered"] else None
                chosen = texts["evalhub"]
            result["samples"][row["id"]] = {
                "dataset": name,
                "reference": chosen,
                "agreed_by": agreed_by,
                "texts": texts,
                "notes": {s: p[row["id"]].get("note") for s, p in predictions.items()
                          if row["id"] in p and p[row["id"]].get("note")},
                "reference_tokens": len(toks["evalhub"]),
                "errors": errors,
            }
    output = args.source / "agreement.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name in (GENERAL, POLICE):
        rows = [s for s in result["samples"].values() if s["dataset"] == name]
        pairs = [" + ".join(s["agreed_by"]) for s in rows if s["agreed_by"]]
        print(name, f"agreed {len(pairs)}/{len(rows)}", {p: pairs.count(p) for p in sorted(set(pairs))})


if __name__ == "__main__":
    main()
