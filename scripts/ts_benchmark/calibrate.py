#!/usr/bin/env python3
"""Check that the simulated far-field conditions move the metrics the way real far-field recordings do.

Part 1 (near/far 2x2). Enrollment and mixture are each near-field (n) or far-field (f). Simulated
(``ts_asr_farfield``): n/n is the panel baseline, n/f ``rirdiff``, f/f ``mmfarfar``, f/n ``mmfarnear``.
Real (``ts_asr_nearfar``, AliMeeting headsets vs. the far-field array): the same four cells of the same windows.
Contrasts are paired differences on the same scenes with bootstrap 95% intervals.

Part 2 (covariates). Number of interferers and target overlap in the simulated benchmark against the real
AliMeeting and AISHELL-4 windows (``ts_asr_real``): is the direction of the effect the same?

    python scripts/ts_benchmark/calibrate.py --roots roots.json \
        --farfield RUN... --nearfar RUN... --benchmark RUN... --real RUN... --output calibration.md
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze

CELLS_SIM = {"panel-base": "nn", "rirdiff": "nf", "mmfarfar": "ff", "mmfarnear": "fn"}
CELLS_REAL = {"en-mn": "nn", "en-mf": "nf", "ef-mf": "ff", "ef-mn": "fn"}
# (name, A, B): the effect is metric(A) - metric(B)
CONTRASTS = [
    ("混合近场 → 远场（注册近场）", "nf", "nn"),
    ("注册近场 → 远场（混合近场）", "fn", "nn"),
    ("远场混合：近场注册相对远场注册（失配代价）", "nf", "ff"),
    ("注册和混合都从近场到远场", "ff", "nn"),
]
METRICS = {"pos": [("CER", "cer"), ("漏识", "miss"), ("转写了别人", "wrong")], "neg": [("误输出", "fa")]}


def load_scored(dataset, version, roots, runs):
    records = analyze.load_records(dataset, roots, version)
    scored = {}
    for run in runs:
        with (Path(run) / "predictions.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["id"] in records:
                    scored[row["id"]] = analyze.score(records[row["id"]], analyze.prediction_text(row))
    return records, scored


def cell_rows(records, scored, kind):
    """{cell: {key: row}} where key identifies the same scene in every cell."""
    out = defaultdict(dict)
    for rid, row in scored.items():
        labels, meta = records[rid]["labels"], records[rid]["metadata"]
        if labels["kind"] != kind:
            continue
        name = labels["scenario"]
        if "window_id" in labels:  # real: nearfar-<bucket>-<cell>-<kind>
            _, _, *cell, _ = name.split("-")
            cell, key = CELLS_REAL["-".join(cell)], (labels["window_id"], kind)
        else:  # simulated: <cond>-<kind>
            cond = name.rsplit("-", 1)[0]
            if cond not in CELLS_SIM:
                continue
            cell, key = CELLS_SIM[cond], (meta["index"], kind)
        out[cell][key] = row
    return out


def contrast(a, b, metric, rng, rounds=1000):
    keys = sorted(set(a) & set(b), key=str)
    if metric == "cer":
        pairs = [(a[k]["errors"] - b[k]["errors"], b[k]["length"]) for k in keys]
    elif metric == "miss":
        pairs = [(int(a[k]["empty"]) - int(b[k]["empty"]), 1) for k in keys]
    elif metric == "wrong":
        keys = [k for k in keys if "wrong_speaker" in a[k] and "wrong_speaker" in b[k]]
        pairs = [(int(a[k]["wrong_speaker"]) - int(b[k]["wrong_speaker"]), 1) for k in keys]
    else:
        pairs = [(int(not a[k]["empty"]) - int(not b[k]["empty"]), 1) for k in keys]
    if len(pairs) < 10:
        return None
    full = list(range(len(pairs)))
    point = analyze._ratio(pairs, full)
    boot = sorted(analyze._ratio(pairs, [rng.randrange(len(pairs)) for _ in full]) for _ in range(rounds))
    return {"n": len(pairs), "delta": point, "ci": (boot[int(0.025 * rounds)], boot[int(0.975 * rounds)])}


def verdict(sim, real):
    if not sim or not real:
        return "-"
    sig = lambda c: c["ci"][0] > 0 or c["ci"][1] < 0
    if sim["delta"] * real["delta"] <= 0 and (sig(sim) or sig(real)):
        return "相反"
    if sig(sim) and sig(real):
        return "一致"
    if sig(sim) or sig(real):
        return "同向，只有一边显著"
    return "都不显著"


def fmt(c):
    return "-" if not c else f"{100 * c['delta']:+.1f} [{100 * c['ci'][0]:+.1f}, {100 * c['ci'][1]:+.1f}] (n={c['n']})"


def part1(args, roots, rng):
    sim_records, sim_scored = load_scored("ts_asr_farfield", args.farfield_version, roots, args.farfield)
    real_records, real_scored = load_scored("ts_asr_nearfar", args.nearfar_version, roots, args.nearfar)
    # panel-base is shared with the benchmark: pair on scene index, the baselines have the same indices
    groups = {
        "合成（k=1–2 个干扰人）": (sim_records, sim_scored, None),
        "真实 AliMeeting 2 人窗口": (real_records, real_scored, "2spk"),
        "真实 AliMeeting 3 人及以上窗口": (real_records, real_scored, "3plus"),
        "真实 AliMeeting 1 人窗口（没有干扰人）": (real_records, real_scored, "1spk"),
    }
    lines = ["## 1. 近场/远场 2×2：合成与真实的配对差值（百分点）", ""]
    result = {}
    for kind in ("pos", "neg"):
        for metric_name, metric in METRICS[kind]:
            lines += [f"### {metric_name}（目标{'在场' if kind == 'pos' else '缺席'}）", "",
                      "| 对比 | " + " | ".join(groups) + " | 合成 vs 真实 2 人 |", "| --- | " + " | ".join("---" for _ in groups) + " | --- |"]
            for name, a, b in CONTRASTS:
                cells = []
                for label, (records, scored, bucket) in groups.items():
                    subset = {r: s for r, s in scored.items() if bucket is None or f"-{bucket}-" in records[r]["labels"]["scenario"]}
                    rows = cell_rows(records, subset, kind)
                    cells.append(contrast(rows[a], rows[b], metric, rng))
                    result[(kind, metric, name, label)] = cells[-1]
                lines.append(f"| {name} | " + " | ".join(fmt(c) for c in cells) + f" | {verdict(cells[0], cells[1])} |")
            lines.append("")
    return lines, result


def covariate_rows(records, scored, corpus=None):
    out = defaultdict(list)
    for rid, row in scored.items():
        labels = records[rid]["labels"]
        if corpus and labels.get("corpus") != corpus:
            continue
        # Simulated: undegraded scenes only (dynamics, absence, the panel baseline); real: every window.
        if labels["kind"] == "nonspeech" or (labels["group"] != "real" and not (
                labels["group"] in ("dynamics", "absent") or labels["scenario"].startswith("panel-base"))):
            continue
        k = labels["n_interferers"]
        if row["present"]:
            out[("pos", "interferers", "1" if k == 1 else ">=2" if k >= 2 else "0")].append(row)
            if "target_overlap_ratio" in labels:
                out[("pos", "overlap", analyze.bucket(labels["target_overlap_ratio"], [0.2, 0.6], ["<0.2", "0.2-0.6", ">=0.6"]))].append(row)
        else:
            out[("neg", "interferers", "1" if k == 1 else ">=2" if k >= 2 else "0")].append(row)
    return out


def part2(args, roots, rng):
    sources = {"合成评测集 v3": ("ts_asr_benchmark", args.benchmark_version, args.benchmark, None),
               "真实 AliMeeting": ("ts_asr_real", args.real_version, args.real, "alimeeting"),
               "真实 AISHELL-4": ("ts_asr_real", args.real_version, args.real, "aishell4")}
    tables = {}
    for label, (dataset, version, runs, corpus) in sources.items():
        records, scored = load_scored(dataset, version, roots, runs)
        tables[label] = {k: analyze.summarize(v, rng) for k, v in covariate_rows(records, scored, corpus).items()}
    lines = ["## 2. 协变量：干扰人数与重叠，方向是否一致", "",
             "| 切片 | 指标 | " + " | ".join(tables) + " |", "| --- | --- | " + " | ".join("---" for _ in tables) + " |"]
    for kind, covariate, bins, metrics in (("pos", "interferers", ["1", ">=2"], ["cer", "wrong_speaker", "miss"]),
                                           ("pos", "overlap", ["<0.2", "0.2-0.6", ">=0.6"], ["cer", "wrong_speaker"]),
                                           ("neg", "interferers", ["1", ">=2"], ["false_alarm"])):
        for metric in metrics:
            for b in bins:
                cells = []
                for table in tables.values():
                    s = table.get((kind, covariate, b), {})
                    cells.append("-" if metric not in s else f"{100 * s[metric]:.1f} (n={s['n']})")
                lines.append(f"| {covariate} {b} | {metric} | " + " | ".join(cells) + " |")
    return lines, tables


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--farfield", nargs="+", required=True)
    parser.add_argument("--nearfar", nargs="+", required=True)
    parser.add_argument("--benchmark", nargs="+", required=True)
    parser.add_argument("--real", nargs="+", required=True)
    parser.add_argument("--farfield-version", default="v1-20261014")
    parser.add_argument("--nearfar-version", default="v1-20261014")
    parser.add_argument("--benchmark-version", default="v3-20261013")
    parser.add_argument("--real-version", default="v2-20261013")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    rng = random.Random(20261014)
    lines1, _ = part1(args, roots, rng)
    lines2, _ = part2(args, roots, rng)
    args.output.write_text("\n".join(lines1 + [""] + lines2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
