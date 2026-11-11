#!/usr/bin/env python3
"""Per-split quality gate of a built benchmark version against a reference version of the same dataset.

Run by ``build.py --reference-version`` before the catalog is written, or on its own for an already built version:

    python scripts/ts_benchmark/qc_gate.py --data-root /workspace/data/datasets/ts_asr_noise \
        --version es-v1-20261111 --reference-version en-v1-20261031

Every split must have records, all audio must decode with the indexed length, mixtures must not be digital
silence, references must be empty exactly when the target is absent, and the record count, target-present ratio
and mean mixture length must match the reference split of the same name. A split the reference does not have
fails. Results are printed per group; any failing split exits non-zero.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

# Scenes of a split draw their length from the same recipe range in both languages; only the speakers differ, so
# the mean mixture length moves a little with the utterance lengths. Outside this ratio the scene plan changed.
DURATION_RATIO = (0.8, 1.25)
# Kinds are fixed per split (pos / neg / nonspeech), so the target-present ratio matches exactly unless broken.
PRESENT_RATIO_TOLERANCE = 0.05
# The noise floor (-65 dBFS at its quietest) is in every mixture; anything below this is an empty render.
SILENCE_DBFS = -90.0


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def split_stats(records, index, data_root):
    """Counts, lengths and audio problems of one split's records."""
    problems = []
    durations, present = [], 0
    for record in records:
        target_present = record["labels"]["target_present"]
        present += target_present
        if bool(record["target"].strip()) != target_present:
            problems.append(f"{record['id']}: reference text does not match target_present={target_present}")
        for slot in record["audio_slots"]:
            entry = index.get(slot["ref"]["cut_id"])
            if entry is None:
                problems.append(f"{record['id']}: {slot['name']} not in the audio index")
                continue
            try:
                wave, sr = sf.read(data_root / entry["relative_path"], dtype="float32")
            except Exception as error:  # noqa: BLE001 - any decode failure fails the gate
                problems.append(f"{record['id']}: {slot['name']} does not decode ({error})")
                continue
            if len(wave) != entry["num_frames"] or sr != entry["sample_rate"]:
                problems.append(f"{record['id']}: {slot['name']} length or rate differs from the index")
            if slot["name"] == "mixture":
                durations.append(len(wave) / sr)
                rms = float(np.sqrt(np.mean(np.square(wave, dtype=np.float64)))) if len(wave) else 0.0
                if 20 * np.log10(max(rms, 1e-12)) < SILENCE_DBFS:
                    problems.append(f"{record['id']}: mixture is silent")
    n = len(records)
    return {"records": n, "present": present / n if n else 0.0,
            "mean_s": float(np.mean(durations)) if durations else 0.0,
            "hours": sum(durations) / 3600, "problems": problems}


def reference_stats(path):
    records = _rows(path)
    n = len(records)
    return {"records": n, "present": sum(r["labels"]["target_present"] for r in records) / n if n else 0.0,
            "mean_s": sum(r["audio_slots"][1]["ref"]["duration"] for r in records) / n if n else 0.0}


def check(data_root, version, reference_version, expected_counts=None):
    """{group: [(split, stats, reference, failures)]}; a split fails when its failure list is non-empty."""
    data_root = Path(data_root)
    base, ref_base = data_root / "versions" / version, data_root / "versions" / reference_version
    index = {e["cut_id"]: e for e in _rows(base / "audio-index.jsonl.gz")}
    groups = defaultdict(list)
    for path in sorted((base / "records").glob("*.jsonl.gz")):
        name = path.name.removesuffix(".jsonl.gz")
        records = _rows(path)
        stats = split_stats(records, index, data_root)
        failures = list(stats["problems"][:5])
        if len(stats["problems"]) > 5:
            failures.append(f"... {len(stats['problems']) - 5} more")
        if stats["records"] == 0:
            failures.append("no records")
        if expected_counts and stats["records"] != expected_counts.get(name):
            failures.append(f"{stats['records']} records, the recipe asks for {expected_counts.get(name)}")
        ref_path = ref_base / "records" / path.name
        reference = reference_stats(ref_path) if ref_path.is_file() else None
        if reference is None:
            failures.append(f"no split {name} in {reference_version}")
        else:
            if stats["records"] != reference["records"]:
                failures.append(f"{stats['records']} records vs {reference['records']} in the reference")
            if abs(stats["present"] - reference["present"]) > PRESENT_RATIO_TOLERANCE:
                failures.append(f"target present {stats['present']:.2f} vs {reference['present']:.2f}")
            ratio = stats["mean_s"] / reference["mean_s"] if reference["mean_s"] else 0.0
            if not DURATION_RATIO[0] <= ratio <= DURATION_RATIO[1]:
                failures.append(f"mean length {stats['mean_s']:.2f} s vs {reference['mean_s']:.2f} s")
        group = records[0]["labels"]["group"] if records else "?"
        groups[group].append((name, stats, reference, failures))
    return groups


def report(groups):
    """Print the per-group table; True when every split passed."""
    ok = True
    for group, rows in sorted(groups.items()):
        failed = [name for name, *_, failures in rows if failures]
        ok &= not failed
        print(f"[{'FAIL' if failed else 'PASS'}] group {group}: {len(rows)} splits, "
              f"{sum(s['records'] for _, s, _, _ in rows)} records, {sum(s['hours'] for _, s, _, _ in rows):.2f} h")
        for name, stats, reference, failures in rows:
            ref = (f" | ref {reference['records']} rec, present {reference['present']:.2f}, "
                   f"mean {reference['mean_s']:.2f} s") if reference else ""
            print(f"  {name}: {stats['records']} rec, present {stats['present']:.2f}, "
                  f"mean {stats['mean_s']:.2f} s{ref}")
            for failure in failures:
                print(f"    - {failure}")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--reference-version", required=True)
    args = parser.parse_args()
    if not report(check(args.data_root, args.version, args.reference_version)):
        sys.exit(1)


if __name__ == "__main__":
    main()
