#!/usr/bin/env python3
"""Gate a built cross-lingual TS-ASR version (ts_asr_crosslingual) before it is registered.

Checked per pair group (``-same`` / ``-cross`` splits sharing ``pair``); any failing group fails the version:

- both splits exist and hold the recipe's ``n`` records, and as many as the same group of the reference versions;
- every record of a ``pos`` split has the target present with a non-empty reference, every ``neg`` record has it
  absent with an empty one;
- the enrollment utterances belong to the target speaker in the split's ``enroll_pool`` and are none of the mixture's
  target utterances; target utterances belong to the target speaker in ``target_pool``; interferers are other
  speakers from ``interferer_pool``;
- index i of the two splits has the same target speaker and reference, and the share of byte-identical mixtures
  is at least ``MIN_IDENTICAL_MIXTURES`` (the zh/en v1 versions: 94–100% per group; the rest are scenes one side
  re-drew after a failed attempt).

``build.py`` calls ``check`` before it writes the catalog entry (report in ``versions/<v>/qc.json``); run
standalone to re-check a built version:

    python scripts/ts_benchmark/qc_crosslingual.py --recipe scripts/ts_benchmark/recipe-crosslingual-es.yaml \\
        --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

MIN_IDENTICAL_MIXTURES = 0.90
REFERENCE_VERSIONS = ("zh-v1-20261109", "en-v1-20261109")


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _pool_utterances(recipe, roots):
    """{pool: {utt_id: speaker}} with ids and speakers spelled as build.py writes them into record metadata."""
    out = {}
    for name, spec in recipe["pools"].items():
        out[name] = {}
        for source in spec["sources"]:
            for row in build.manifest_rows(source, roots):
                out[name][f"{source['dataset']}:{row['id']}"] = f"{source['dataset']}:{row['speaker']}"
    return out


def _reference_counts(data_root):
    counts = {}
    for version in REFERENCE_VERSIONS:
        for path in sorted((data_root / "versions" / version / "records").glob("*.jsonl.gz")):
            counts.setdefault(path.name[: -len(".jsonl.gz")], set()).add(len(_rows(path)))
    return counts


def check(recipe, data_root, roots, output=None):
    version = recipe["version"]
    vdir = data_root / "versions" / version
    sha = {row["cut_id"]: row["sha256"] for row in _rows(vdir / "audio-index.jsonl.gz")}
    pools = _pool_utterances(recipe, roots)
    reference = _reference_counts(data_root) if version not in REFERENCE_VERSIONS else {}
    splits = {s["name"]: s for s in build.expand_splits(recipe)}
    groups = {}
    for split in splits.values():
        groups.setdefault(split["params"]["pair"], []).append(split["name"])
    report, failed = {"version": version, "groups": {}}, []
    for pair, names in sorted(groups.items()):
        problems = []
        same, cross = f"{pair}-same", f"{pair}-cross"
        if sorted(names) != sorted([same, cross]):
            problems.append(f"splits {sorted(names)} are not exactly {same} and {cross}")
            report["groups"][pair] = {"problems": problems}
            failed.append(pair)
            continue
        records = {name: _rows(vdir / "records" / f"{name}.jsonl.gz") for name in names}
        for name in names:
            params, rows = splits[name]["params"], records[name]
            if len(rows) != splits[name]["n"]:
                problems.append(f"{name}: {len(rows)} records, recipe asks {splits[name]['n']}")
            if name in reference and reference[name] != {len(rows)}:
                problems.append(f"{name}: {len(rows)} records, reference versions have {sorted(reference[name])}")
            present = params["kind"] == "pos"
            bad = Counter()
            for r in rows:
                meta = r["metadata"]
                speaker = meta["target_speaker"]
                if r["labels"]["target_present"] != present or bool(r["target"]) != present:
                    bad["presence"] += 1
                if r["labels"].get("enroll_pool") != params["enroll_pool"]:
                    bad["enroll_pool label"] += 1
                enroll = [meta["enrollment_utt"], *meta.get("enrollment_extra_utts", [])]
                if any(pools[params["enroll_pool"]].get(u["id"]) != speaker for u in enroll):
                    bad["enrollment not the target speaker in enroll_pool"] += 1
                targets = meta["target_utts"]
                if any(pools[params["target_pool"]].get(u["id"]) != speaker for u in targets):
                    bad["target utterance not the target speaker in target_pool"] += 1
                if present != bool(targets):
                    bad["target utterances vs kind"] += 1
                if {u["id"] for u in enroll} & {u["id"] for u in targets}:
                    bad["enrollment reuses a mixture utterance"] += 1
                for track in meta["interferers"]:
                    owners = {pools[params["interferer_pool"]].get(u["id"]) for u in track["utts"]}
                    if owners != {track["speaker"]} or track["speaker"] == speaker:
                        bad["interferer"] += 1
            problems.extend(f"{name}: {n} records with bad {what}" for what, n in sorted(bad.items()))
        mismatch, identical = 0, 0
        for a, b in zip(records[same], records[cross]):
            if (a["metadata"]["target_speaker"], a["target"]) != (b["metadata"]["target_speaker"], b["target"]):
                mismatch += 1
            identical += sha[a["audio_slots"][1]["ref"]["cut_id"]] == sha[b["audio_slots"][1]["ref"]["cut_id"]]
        n = min(len(records[same]), len(records[cross]))
        share = identical / n if n else 0.0
        # A re-drawn scene may pick another speaker or text; the identical-mixture share bounds how many may differ.
        if mismatch > n - identical:
            problems.append(f"{mismatch} pairs differ in speaker or text, more than the {n - identical} re-drawn ones")
        if share < MIN_IDENTICAL_MIXTURES:
            problems.append(f"identical mixtures {identical}/{n} below {MIN_IDENTICAL_MIXTURES:.0%}")
        report["groups"][pair] = {
            "records": {name: len(records[name]) for name in names}, "identical_mixtures": identical,
            "identical_share": round(share, 4), "target_present": sum(r["labels"]["target_present"]
                                                                     for name in names for r in records[name]),
            "speakers": len({r["metadata"]["target_speaker"] for name in names for r in records[name]}),
            "problems": problems}
        if problems:
            failed.append(pair)
    total = sum(sum(g.get("records", {}).values()) for g in report["groups"].values())
    report["records"] = total
    report["target_present_share"] = round(
        sum(g.get("target_present", 0) for g in report["groups"].values()) / total, 4) if total else 0.0
    report["passed"] = not failed
    if output:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    if failed:
        details = {g: report["groups"][g]["problems"] for g in failed}
        raise SystemExit(f"cross-lingual QC failed for {version}: {json.dumps(details, ensure_ascii=False)}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="write the report here (build.py writes versions/<v>/qc.json)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    roots = json.loads(args.roots.read_text())
    report = check(recipe, Path(roots[recipe["dataset_id"]]), roots, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "groups"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
