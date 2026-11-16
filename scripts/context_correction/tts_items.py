#!/usr/bin/env python3
"""tts-items.jsonl: per subtype, the first ceil(target * MARGIN) accepted pairs in items.jsonl order (generation order),
both items of each pair. build.py takes each subtype's first ``target`` pairs whose audio passes QC, so later pairs
are only needed when QC drops more than the margin; they are synthesized in a top-up round in the same order.

    python scripts/context_correction/tts_items.py <recipe> <source dir>
"""
import json
import math
import sys
from collections import Counter, defaultdict

import yaml

MARGIN = 1.5  # v1 QC passed ~89% of items, so ~79% of pairs (both items must pass): 1.5 x 0.79 ≈ 1.19 x target
recipe = yaml.safe_load(open(sys.argv[1]))
source = sys.argv[2]
targets = {sub: n for entry in recipe["categories"].values() for sub, n in entry["subtypes"].items()}
items = [json.loads(l) for l in open(f"{source}/items.jsonl")]
order, members = [], defaultdict(list)
for item in items:
    if item["pair_id"] not in members:
        order.append(item["pair_id"])
    members[item["pair_id"]].append(item)
taken, out = Counter(), []
for pair_id in order:
    sub = members[pair_id][0]["subtype"]
    if taken[sub] < math.ceil(targets[sub] * MARGIN):
        taken[sub] += 1
        out += members[pair_id]
with open(f"{source}/tts-items.jsonl", "w") as f:
    f.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in out)
print("pairs", dict(taken), "items", len(out))
