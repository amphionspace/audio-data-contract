#!/usr/bin/env python3
"""Lance production acceptance at scale; writes only into a new output directory.

Every operation runs in its own subprocess and reports its own peak RSS. Cold
measurements first drop the table's pages with posix_fadvise(DONTNEED).
"""

import argparse
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

from audio_data_contract import TransformStep, load_roots
from audio_data_contract.lance import (
    LanceArtifact,
    RecordQuery,
    cleanup_artifact,
    compact_artifact,
    import_jsonl,
    materialize_layer,
    mirror_artifact,
    read_lance,
    verify_equivalence,
)
from audio_data_contract.lance_stream import iter_records
from audio_data_contract.layers import write_layer


def size(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def drop_cache(path):
    for file in Path(path).rglob("*"):
        if file.is_file():
            descriptor = os.open(file, os.O_RDONLY)
            try:
                os.posix_fadvise(descriptor, 0, 0, os.POSIX_FADV_DONTNEED)
            finally:
                os.close(descriptor)


def sample_ids(artifact, count, seed=0):
    """Reservoir-sample IDs from the snapshot (one pass over the id column)."""
    from audio_data_contract.lance import _open_artifact

    rng, sample, seen = random.Random(seed), [], 0
    dataset = _open_artifact(artifact)
    for batch in dataset.to_batches(columns=["id"], filter="retained = true"):
        for value in batch.column(0).to_pylist():
            seen += 1
            if len(sample) < count:
                sample.append(value)
            elif (index := rng.randrange(seen)) < count:
                sample[index] = value
    return sample


def operation(name, args):
    """Run inside a subprocess; returns this operation's measurements."""
    from audio_data_contract.lance import _dependencies

    _dependencies()  # library import time is not part of any measurement
    started = time.perf_counter()
    if name == "import":
        artifact = import_jsonl(
            args["source"],
            args["destination"],
            source_view=args["source_view"],
            workers=args["workers"],
            roots=load_roots(),
        )
        table = Path(artifact.table_uri)
        result = {
            "records": artifact.record_count,
            "table_bytes": size(table),
            "index_bytes": size(table / "_indices"),
        }
    elif name == "query":
        artifact = LanceArtifact.read(args["artifact"])
        query = dict(args["query"])
        if "id_count" in query:
            ids = json.loads(Path(args["ids"]).read_text())
            query = {"ids": tuple(ids[: query.pop("id_count")])}
        query = RecordQuery(**query)
        timings = []
        for repeat in range(args["repeats"]):
            if repeat == 0:
                drop_cache(artifact.table_uri)
            begin = time.perf_counter()
            matches = sum(1 for _ in read_lance(artifact, query))
            timings.append(time.perf_counter() - begin)
        warm = timings[1:] or timings
        result = {
            "matches": matches,
            "cold_s": timings[0],
            "warm_p50_s": statistics.median(warm),
            "warm_max_s": max(warm),
        }
    elif name == "layer":
        parent = LanceArtifact.read(args["artifact"])
        ids = json.loads(Path(args["ids"]).read_text())[: args["patches"]]
        step = TransformStep(
            "acceptance-quality",
            str(args["patches"]),
            "annotate",
            ("metadata.acceptance_quality",),
            ("metadata.acceptance_quality",),
        )
        patches = (
            {
                "id": i,
                "changes": {"metadata.acceptance_quality": args["patches"]},
                "status": "keep",
            }
            for i in ids
        )
        begin = time.perf_counter()
        layer = write_layer(
            args["destination"], patches, parent=parent, step=step, tool="acceptance"
        )
        written = time.perf_counter() - begin
        artifact = materialize_layer(layer, source_view=args["source_view"])
        result = {
            "patches": len(ids),
            "write_layer_s": written,
            "materialize_s": time.perf_counter() - begin - written,
            "artifact": str(Path(layer) / "artifact.json"),
            "snapshot_version": artifact.snapshot_version,
        }
    elif name == "compact":
        artifact = compact_artifact(
            LanceArtifact.read(args["artifact"]), args["destination"]
        )
        result = {"snapshot_version": artifact.snapshot_version}
    elif name == "cleanup":
        result = cleanup_artifact(
            LanceArtifact.read(args["artifact"]), older_than_days=0
        )
    elif name == "mirror":
        result = mirror_artifact(LanceArtifact.read(args["artifact"]), args["target"])
    elif name == "stream":
        artifact = LanceArtifact.read(args["artifact"])
        drop_cache(artifact.table_uri)
        count = sum(
            1
            for _ in iter_records(
                artifact, shard=args["shard"], num_shards=args["shards"], seed=0
            )
        )
        result = {"records": count}
    elif name == "verify":
        result = verify_equivalence(
            LanceArtifact.read(args["artifact"]), args["source"]
        )
    else:
        raise ValueError(name)
    result["seconds"] = time.perf_counter() - started
    result["peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    return result


def run(name, **args):
    command = [sys.executable, __file__, "--operation", name, json.dumps(args)]
    output = subprocess.run(command, check=True, capture_output=True, text=True)
    result = json.loads(output.stdout.strip().splitlines()[-1])
    print(name, json.dumps(result), file=sys.stderr, flush=True)
    return result


def accept(source, output, *, source_view, workers, roots, layer_sizes, shards):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["AUDIO_DATA_ROOTS_FILE"] = str(output / "roots.json")
    (output / "roots.json").write_text(json.dumps({"acceptance": str(output), **roots}))
    report = {"source": str(source), "workers": workers}
    report["import"] = run(
        "import",
        source=str(source),
        destination=str(output / "raw"),
        source_view=source_view,
        workers=workers,
    )
    report["import"]["rows_per_s"] = (
        report["import"]["records"] / report["import"]["seconds"]
    )
    raw = str(output / "raw/artifact.json")
    ids = sample_ids(LanceArtifact.read(raw), max([65536, *layer_sizes]))
    (output / "ids.json").write_text(json.dumps(ids))
    first = next(read_lance(LanceArtifact.read(raw), RecordQuery(ids=(ids[0],))))
    queries = {
        "single_id": {"id_count": 1},
        "64_ids": {"id_count": 64},
        "65536_ids": {"id_count": 65536},
        "language_split": {
            "language": first.language,
            "split": first.audio_slots[0].ref.split,
        },
        "clean_pass_false": {"clean_pass": False},
    }
    report["queries"] = {
        name: run(
            "query", artifact=raw, query=query, ids=str(output / "ids.json"), repeats=4
        )
        for name, query in queries.items()
    }
    report["verify_import"] = run("verify", artifact=raw, source=str(source))
    report["layers"], parent = [], raw
    for count in layer_sizes:
        result = run(
            "layer",
            artifact=parent,
            ids=str(output / "ids.json"),
            patches=count,
            destination=str(output / f"layer-{count}"),
            source_view=f"acceptance/layer-{count}@v1",
        )
        report["layers"].append(result)
        parent = result["artifact"]
    compacted = str(output / "compacted.json")
    report["compact"] = run("compact", artifact=parent, destination=compacted)
    report["cleanup"] = run("cleanup", artifact=compacted)
    report["mirror"] = run(
        "mirror", artifact=compacted, target=(output / "mirror").as_uri()
    )
    started = time.perf_counter()
    streams = []
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--operation",
                "stream",
                json.dumps({"artifact": compacted, "shard": i, "shards": shards}),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        for i in range(shards)
    ]
    for process in processes:
        stdout, _ = process.communicate()
        if process.returncode:
            raise RuntimeError("stream shard failed")
        streams.append(json.loads(stdout.strip().splitlines()[-1]))
    elapsed = time.perf_counter() - started
    report["stream"] = {
        "shards": shards,
        "records": sum(s["records"] for s in streams),
        "seconds": elapsed,
        "records_per_s": sum(s["records"] for s in streams) / elapsed,
        "max_shard_records": max(s["records"] for s in streams),
        "min_shard_records": min(s["records"] for s in streams),
        "max_shard_rss_mib": max(s["peak_rss_mib"] for s in streams),
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--operation":
        print(json.dumps(operation(sys.argv[2], json.loads(sys.argv[3]))))
        raise SystemExit(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="AudioRecord JSONL(.gz) under a configured root")
    parser.add_argument("output", help="new directory")
    parser.add_argument("--source-view", required=True)
    parser.add_argument("--source-root", required=True, help="root containing source")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--shards", type=int, default=8)
    parser.add_argument(
        "--layer-sizes", type=int, nargs="+", default=[1, 64, 100000, 1000000]
    )
    args = parser.parse_args()
    result = accept(
        Path(args.source).resolve(),
        args.output,
        source_view=args.source_view,
        workers=args.workers,
        roots={"acceptance_source": str(Path(args.source_root).resolve())},
        layer_sizes=args.layer_sizes,
        shards=args.shards,
    )
    print(json.dumps({"results": str(Path(args.output) / "results.json")}))
