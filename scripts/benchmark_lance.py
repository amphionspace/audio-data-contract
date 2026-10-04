#!/usr/bin/env python3
"""Reproducible JSONL/Lance pilot; writes only into a new experiment directory."""

import argparse
import json
import math
import platform
import random
import resource
import statistics
import time
from pathlib import Path

from audio_data_contract import TransformStep, read_artifact, write_records
from audio_data_contract.lance import (
    RecordQuery,
    import_jsonl,
    materialize_layer,
    verify_equivalence,
)
from audio_data_contract.layers import replay_layer, write_layer


def timed(action, *args, **kwargs):
    start = time.perf_counter()
    result = action(*args, **kwargs)
    return result, time.perf_counter() - start


def size(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def summarize(values):
    return {
        "seconds": values,
        "p50_s": statistics.median(values),
        "p95_s": sorted(values)[math.ceil(len(values) * 0.95) - 1],
    }


def benchmark(source, output, *, source_view, repeats=7):
    source, output = Path(source).resolve(), Path(output).resolve()
    if repeats < 1:
        raise ValueError("repeats must be positive")
    output.mkdir(parents=True, exist_ok=False)
    rng, sample, count = random.Random(0), [], 0
    started = time.perf_counter()
    for count, record in enumerate(read_artifact(source), 1):
        if len(sample) < 64:
            sample.append(record)
        else:
            index = rng.randrange(count)
            if index < len(sample):
                sample[index] = record
    if not sample:
        raise ValueError("benchmark requires nonempty JSONL")
    report = {
        "source": str(source),
        "source_view": source_view,
        "records": count,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "first_jsonl_scan_s": time.perf_counter() - started,
        "source_bytes": source.stat().st_size,
        "repeats": repeats,
        "notes": [
            "Warm repeated queries, no OS cache flush; full AudioRecord decoding.",
            "No scalar/vector indexes. ID queries exhaust matching scans.",
            "RSS is this process high-water mark, not per-operation delta.",
            "Patch quality values are benchmark markers, not cleaning results.",
        ],
    }
    baseline = output / "materialized.jsonl"
    _, report["jsonl_materialize_s"] = timed(
        lambda: write_records(read_artifact(source), baseline)
    )
    report["jsonl_materialized_bytes"] = baseline.stat().st_size
    report["jsonl_duplicate_bytes"] = baseline.stat().st_size
    # Persist the baseline before creating any Lance table.
    (output / "baseline.json").write_text(json.dumps(report, indent=2) + "\n")
    artifact, report["lance_import_s"] = timed(
        lambda: import_jsonl(source, output / "initial", source_view=source_view)
    )
    report["lance_initial_bytes"] = size(output / "initial/table.lance")
    first = sample[0]
    queries = {
        "full_scan": RecordQuery(),
        "clean_pass": RecordQuery(clean_pass=True),
        "language_task_split": RecordQuery(
            language=first.language,
            task=first.task,
            split=first.audio_slots[0].ref.split,
        ),
        "single_id": RecordQuery(ids=(first.id,)),
        "batch_id": RecordQuery(ids=tuple(r.id for r in sample)),
    }
    report["queries"] = {}
    for name, query in queries.items():
        comparison = {}
        counts = set()
        for backend, value in [("jsonl", source), ("lance", artifact)]:
            seconds = []
            for _ in range(repeats):
                started = time.perf_counter()
                found = sum(1 for _ in read_artifact(value, query))
                elapsed = time.perf_counter() - started
                counts.add(found)
                seconds.append(elapsed)
            comparison[backend] = {"matches": found, **summarize(seconds)}
        if len(counts) != 1:
            raise AssertionError(f"query result count differs: {name}")
        report["queries"][name] = comparison
    report["initial_equivalence"] = verify_equivalence(artifact, source)
    report["updates"] = {}
    for name, selected in [("single", sample[:1]), ("batch", sample)]:
        timings = {"jsonl": [], "lance": [], "canonical_layer": []}
        for iteration in range(repeats):
            patches = [
                {
                    "id": r.id,
                    "changes": {
                        "metadata.lance_pilot_quality": {
                            "iteration": iteration,
                            "batch": name,
                        }
                    },
                    "status": "keep",
                }
                for r in selected
            ]
            step = TransformStep(
                "benchmark-quality",
                str(iteration),
                "annotate",
                ("metadata.lance_pilot_quality",),
                ("metadata.lance_pilot_quality",),
            )
            layer, elapsed = timed(
                write_layer,
                output / f"{name}-{iteration}",
                patches,
                parent=artifact,
                step=step,
                tool="benchmark_lance.py",
                model=None,
            )
            timings["canonical_layer"].append(elapsed)
            updated = output / f"jsonl-{name}-{iteration}.jsonl"
            _, elapsed = timed(
                write_records, replay_layer(read_artifact(baseline), layer), updated
            )
            timings["jsonl"].append(elapsed)
            baseline = updated
            artifact, elapsed = timed(
                materialize_layer,
                layer,
                source_view=f"{source_view}-quality-{name}-{iteration}",
            )
            timings["lance"].append(elapsed)
        report["updates"][name] = {
            key: summarize(value) for key, value in timings.items()
        }
    report["final_equivalence"] = verify_equivalence(artifact, baseline)
    report["lance_final_bytes"] = size(output / "initial/table.lance")
    report["lance_index_bytes"] = 0
    report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["artifact"] = artifact.to_dict()
    report["decision"] = "experimental; real-scale cleaning acceptance required"
    (output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--source-view", required=True)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    result = benchmark(
        args.source, args.output, source_view=args.source_view, repeats=args.repeats
    )
    print(
        json.dumps(
            {
                "results": str(Path(args.output) / "results.json"),
                "records": result["records"],
                "decision": result["decision"],
            }
        )
    )
