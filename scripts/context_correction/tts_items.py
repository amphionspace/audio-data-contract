#!/usr/bin/env python3
"""Pick the synthetic pairs to synthesize: per subtype, the first ceil(target * MARGIN) accepted pairs in
items.jsonl order (generation order), both items of each pair, written to ``<source>/tts-items.jsonl``.

build.py takes each subtype's first ``target`` pairs whose audio passes QC, so later pairs are only needed when
QC drops more than the margin; they are synthesized in a top-up round in the same order.

    python scripts/context_correction/tts_items.py --recipe <recipe> --source <source dir>
"""

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl, write_jsonl

MARGIN = 1.5  # v1 QC passed ~89% of items, so ~79% of pairs (both items must pass): 1.5 x 0.79 ≈ 1.19 x target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    targets = {sub: n for entry in recipe["categories"].values() for sub, n in entry["subtypes"].items()}
    members = defaultdict(list)  # insertion order = items.jsonl order
    for item in read_jsonl(args.source / "items.jsonl"):
        members[item["pair_id"]].append(item)
    taken, chosen = Counter(), []
    for pair in members.values():
        subtype = pair[0]["subtype"]
        if taken[subtype] < math.ceil(targets[subtype] * MARGIN):
            taken[subtype] += 1
            chosen += pair
    write_jsonl(args.source / "tts-items.jsonl", chosen)
    print("pairs", dict(taken), "items", len(chosen))


if __name__ == "__main__":
    main()
