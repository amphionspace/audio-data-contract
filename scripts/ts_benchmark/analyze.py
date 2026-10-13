#!/usr/bin/env python3
"""Diagnostics for a model run on ts_asr_benchmark, beyond what the AmphionEval table reports.

Per scenario: CER and miss rate (target present), wrong-speaker rate (the output is closer to an
interferer's text than to the target's), false alarm rate and leak rate (the output is an
interferer's speech, target absent), and loop rate (repetition). Slices by overlap, interferer count
and length. Needs ``rapidfuzz``; reads the ``predictions.jsonl`` of an ``ae open-audio-llm ts-asr`` run.

    python scripts/ts_benchmark/analyze.py --run <ae output dir> --roots roots.json [--json out.json]
"""

import argparse
import gzip
import json
import math
import random
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from rapidfuzz.distance import Levenshtein

LEAK_CER = 0.5  # output within this CER of an interferer's text counts as that speaker's speech
REPEAT = re.compile(r"(.{1,10}?)\1{7,}")


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\W_]+", "", text)


def looped(hyp, ref):
    return bool(REPEAT.search(hyp)) or len(hyp) > 3 * len(ref) + 30


def cer(a, b):
    return Levenshtein.distance(list(a), list(b)) / max(len(b), 1)


def wilson(k, n, z=1.96):
    if not n:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def bootstrap_cer(errors, lengths, rng, rounds=500):
    n = len(errors)
    out = []
    for _ in range(rounds):
        idx = [rng.randrange(n) for _ in range(n)]
        out.append(sum(errors[i] for i in idx) / max(sum(lengths[i] for i in idx), 1))
    out.sort()
    return out[int(0.025 * rounds)], out[int(0.975 * rounds)]


def load_records(root, roots, version):
    base = Path(roots["ts_asr_benchmark"]) / "versions" / version / "records"
    records = {}
    for path in sorted(base.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                r = json.loads(line)
                records[r["id"]] = r
    return records


def prediction_text(row):
    for key in ("prediction", "hyp", "hypothesis", "text"):
        if key in row:
            return row[key] or ""
    raise KeyError(f"no prediction field in {sorted(row)}")


def score(record, hyp):
    """Per-sample facts used by every table."""
    labels, meta = record["labels"], record["metadata"]
    ref, hyp = normalize(record["target"]), normalize(hyp)
    others = [normalize("".join(u["text"] for u in t["utts"])) for t in meta["interferers"]]
    other_utts = [normalize(u["text"]) for t in meta["interferers"] for u in t["utts"]]
    out = {"present": labels["target_present"], "empty": not hyp, "looped": bool(hyp) and looped(hyp, ref)}
    if labels["target_present"]:
        out["errors"] = Levenshtein.distance(list(ref), list(hyp))
        out["length"] = len(ref)
        if hyp and others:
            out["wrong_speaker"] = min(cer(hyp, o) for o in others + other_utts) < cer(hyp, ref)
    elif hyp:
        out["leak"] = bool(other_utts) and min(cer(hyp, u) for u in other_utts + others) < LEAK_CER
    return out


def summarize(rows, rng):
    pos = [r for r in rows if r["present"]]
    neg = [r for r in rows if not r["present"]]
    out = {"n": len(rows)}
    if pos:
        errors, lengths = [r["errors"] for r in pos], [r["length"] for r in pos]
        out["cer"] = sum(errors) / max(sum(lengths), 1)
        out["cer_ci"] = bootstrap_cer(errors, lengths, rng)
        out["miss"] = sum(r["empty"] for r in pos) / len(pos)
        speaking = [r for r in pos if "wrong_speaker" in r]
        if speaking:
            out["wrong_speaker"] = sum(r["wrong_speaker"] for r in speaking) / len(speaking)
        out["loop"] = sum(r["looped"] for r in pos) / len(pos)
    if neg:
        alarms = sum(not r["empty"] for r in neg)
        out["false_alarm"] = alarms / len(neg)
        out["fa_ci"] = wilson(alarms, len(neg))
        raised = [r for r in neg if not r["empty"]]
        if raised and any("leak" in r for r in raised):
            out["leak_share"] = sum(r.get("leak", False) for r in raised) / len(raised)
        out["loop"] = sum(r["looped"] for r in neg) / len(neg)
    return out


def bucket(value, edges, names):
    for edge, name in zip(edges, names):
        if value < edge:
            return name
    return names[-1]


def slices(records, scored):
    """Rows grouped by (slice kind, bucket) across all splits of one polarity."""
    out = defaultdict(list)
    for rid, row in scored.items():
        labels = records[rid]["labels"]
        kind = "pos" if labels["target_present"] else "neg"
        if labels["kind"] == "nonspeech":
            continue
        if "target_overlap_ratio" in labels and kind == "pos":
            out[(kind, "overlap", bucket(labels["target_overlap_ratio"], [0.2, 0.6], ["<0.2", "0.2-0.6", ">=0.6"]))].append(row)
        out[(kind, "interferers", str(labels["n_interferers"]))].append(row)
        out[(kind, "duration", bucket(labels["duration_s"], [3, 8, 15], ["<3s", "3-8s", "8-15s", ">=15s"]))].append(row)
    return out


BASELINES = {"enroll-pos": "enroll-clean-pos", "enroll-neg": "enroll-clean-neg",
             "dom-pos": "dom-clean-pos", "dom-neg": "dom-clean-neg", "abs2": "abs-k2"}


def _ratio(pairs, idx):
    return sum(pairs[i][0] for i in idx) / max(sum(pairs[i][1] for i in idx), 1)


def paired(records, scored, rng, rounds=1000):
    """Per-scenario change against its paired baseline, on the same scenes, with bootstrap 95% intervals."""
    by_pair = defaultdict(lambda: defaultdict(dict))
    for rid, row in scored.items():
        labels, meta = records[rid]["labels"], records[rid]["metadata"]
        if "pair" in labels:
            by_pair[labels["pair"]][labels["scenario"]][meta["index"]] = row
    out = {}
    for pair, scenarios in by_pair.items():
        base = scenarios.get(BASELINES[pair])
        for name, rows in scenarios.items():
            if rows is base or base is None:
                continue
            ids = sorted(set(rows) & set(base))
            if not ids:
                continue
            if rows[ids[0]]["present"]:
                pairs = [(rows[i]["errors"] - base[i]["errors"], base[i]["length"]) for i in ids]
                metric = "dCER"
            else:
                pairs = [(int(not rows[i]["empty"]) - int(not base[i]["empty"]), 1) for i in ids]
                metric = "dFA"
            full = list(range(len(ids)))
            boot = sorted(_ratio(pairs, [rng.randrange(len(ids)) for _ in full]) for _ in range(rounds))
            out[name] = {"baseline": BASELINES[pair], "metric": metric, "n": len(ids), "delta": _ratio(pairs, full),
                         "ci": (boot[int(0.025 * rounds)], boot[int(0.975 * rounds)])}
    return out


def paired_table(deltas):
    lines = ["| 场景 | 相对 | 指标 | n | 变化（百分点） | 95% 区间 |", "| --- | --- | --- | ---: | ---: | --- |"]
    for name, d in sorted(deltas.items()):
        lines.append(f"| {name} | {d['baseline']} | {d['metric']} | {d['n']} | {100 * d['delta']:+.1f} | [{100 * d['ci'][0]:+.1f}, {100 * d['ci'][1]:+.1f}] |")
    return "\n".join(lines)


def pct(x):
    return "" if x is None else f"{100 * x:.1f}"


def table(summary):
    lines = ["| 场景 | n | CER | 漏识 | 转写了别人 | 误输出 | 误输出中是干扰人的话 | 复读 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, s in summary.items():
        cer_text = pct(s.get("cer")) + (f" [{100 * s['cer_ci'][0]:.1f}, {100 * s['cer_ci'][1]:.1f}]" if "cer_ci" in s else "")
        fa_text = pct(s.get("false_alarm")) + (f" [{100 * s['fa_ci'][0]:.1f}, {100 * s['fa_ci'][1]:.1f}]" if "fa_ci" in s else "")
        lines.append(f"| {name} | {s['n']} | {cer_text} | {pct(s.get('miss'))} | {pct(s.get('wrong_speaker'))} | {fa_text} | {pct(s.get('leak_share'))} | {pct(s.get('loop'))} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--version", default="v1-20261013")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    records = load_records(None, roots, args.version)
    scored = {}
    with (args.run / "predictions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["id"] in records:
                scored[row["id"]] = score(records[row["id"]], prediction_text(row))
    missing = len({r["labels"]["scenario"] for r in records.values()}) - len({records[i]["labels"]["scenario"] for i in scored})
    rng = random.Random(0)
    by_split = defaultdict(list)
    for rid, row in scored.items():
        by_split[records[rid]["labels"]["scenario"]].append(row)
    summary = {name: summarize(rows, rng) for name, rows in sorted(by_split.items())}
    cuts = {f"{k[0]}:{k[1]}={k[2]}": summarize(v, rng) for k, v in sorted(slices(records, scored).items())}
    print(f"scored {len(scored)} of {len(records)} records; scenarios without predictions: {missing}\n")
    print("## 场景\n")
    print(table(summary))
    print("\n## 切片（目标在场 pos / 目标缺席 neg）\n")
    print(table(cuts))
    deltas = paired(records, scored, rng)
    print("\n## 配对差值（同一批场景，相对干净对照）\n")
    print(paired_table(deltas))
    if args.json:
        args.json.write_text(json.dumps({"scenarios": summary, "slices": cuts, "paired": deltas}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
