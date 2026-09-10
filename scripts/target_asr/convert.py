#!/usr/bin/env python3
"""Convert the registered TS-ASR source snapshots to portable AudioRecords.

Requires audio-data-contract and its existing [duration] extras. Audio files are
only inspected; no waveform is copied, cropped, concatenated, or resampled.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

import orjson

from audio_data_contract import AudioRecord, load_catalog, load_view_catalog

LANGUAGES = {"English": "en", "Chinese": "zh"}
LABEL_KEYS = (
    "n_spk", "sample_type", "target_spk", "enroll_spk", "mix_speakers",
)
CONVERTER_VERSION = "1"


def encode(value):
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def location(path, roots):
    """Retain the logical spelling; physical() checks resolved containment."""
    path = str(path)
    for alias, root in sorted(roots.items(), key=lambda x: -len(str(x[1]))):
        prefix = str(root).rstrip("/") + "/"
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        if ".." in relative.split("/"):
            raise ValueError(f"unsafe source path: {path}")
        return {"root_alias": alias, "relative_path": relative}
    raise ValueError(f"source path has no configured root: {path}")


def physical(ref, roots):
    root = Path(roots[ref["root_alias"]]).resolve()
    path = root / ref["relative_path"]
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"path escapes configured root: {ref}")
    return path


def audio_id(ref):
    key = ref["root_alias"] + ":" + ref["relative_path"]
    return hashlib.sha256(key.encode()).hexdigest()


def normalize(row, language):
    """Remove known model framing without editing the actual transcript."""
    if "messages" in row:
        replies = [m["content"] for m in row["messages"] if m["role"] == "assistant"]
        if len(replies) != 1 or len(row["audios"]) != 1:
            raise ValueError("expected one assistant target and one enrollment")
        text = replies[0]
        data = dict(row["chat_template_kwargs"])
        data["enroll_wav"] = row["audios"][0]
    else:
        data = dict(row)
        text = data.pop("text")
    if not isinstance(text, str):
        raise TypeError("target must be a string")
    negative = str(data.get("sample_type", "")).startswith("negative")
    match = re.fullmatch(r"language (English|Chinese|None)<asr_text>(.*)", text, re.DOTALL)
    if match:
        tag, text = match.groups()
        if tag == "None":
            if not negative:
                raise ValueError("language None on a non-negative sample")
        elif LANGUAGES[tag] != language:
            raise ValueError("language tag disagrees with dataset language")
    if any(tag in text for tag in ("<asr_text>", "<think>", "<answer>", "<|")):
        raise ValueError("unrecognized model framing in target")
    if negative != (text == ""):
        raise ValueError("empty target and negative sample label disagree")
    if data.get("n_spk") not in (1, 2, 3):
        raise ValueError("expected n_spk in 1, 2, 3")
    if not isinstance(data.get("id"), str) or not data["id"]:
        raise ValueError("missing source record ID")
    for name in ("enroll_wav", "mix_wav"):
        if not isinstance(data.get(name), str) or not data[name]:
            raise ValueError(f"missing {name}")
    return data, text, negative


def core_signature(data, text, negative):
    return hashlib.sha256(encode([
        data["id"], data["enroll_wav"], data["mix_wav"],
        data["n_spk"], text, negative,
    ])).digest()


def inspect_audio(item):
    import soundfile

    path, ref, roots = item
    info = soundfile.info(physical(ref, roots))
    if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
        raise ValueError(f"invalid audio header: {path}")
    return str(path), {
        "cut_id": audio_id(ref), **ref, "sample_rate": info.samplerate,
        "channels": info.channels, "num_frames": info.frames,
        "duration": info.frames / info.samplerate,
    }


def batches(path, size=4096):
    with path.open("rb") as stream:
        batch = []
        for number, line in enumerate(stream, 1):
            try:
                row = orjson.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON") from exc
            batch.append((number, row))
            if len(batch) == size:
                yield batch
                batch = []
        if batch:
            yield batch


def make_record(data, text, negative, job, split, source_name, line, index):
    slots = []
    for name, field in (("enrollment", "enroll_wav"), ("mixture", "mix_wav")):
        slots.append({"name": name, "purpose": name, "ref": {
            "dataset_id": job["dataset_id"], "version": job["version"],
            "split": split, "cut_id": index[data[field]]["cut_id"],
        }})
    omitted = {"id", "enroll_wav", "mix_wav", "split", "language", *LABEL_KEYS}
    record = {
        "schema_version": "audio-record/1.0", "id": split + ":" + data["id"],
        "task": "ts_asr", "audio_slots": slots, "target": text,
        "language": job["language"], "labels": {
            **{k: data[k] for k in LABEL_KEYS if k in data},
            "target_present": not negative,
        }, "metadata": {
            "source_record_id": data["id"], "source_artifact": source_name,
            "source_line": line,
            "source_dataset_version": job["source_version"],
            **{k: v for k, v in data.items() if k not in omitted},
        },
    }
    AudioRecord.from_dict(record)
    return record


def artifact(name, kind, path, roots, count):
    return {
        "name": name, "kind": kind, **location(path, roots),
        "expected_bytes": path.stat().st_size, "sha256": sha256_file(path),
        "metadata": {"record_count": count},
    }


def gzip_writer(stack, path):
    raw = stack.enter_context(path.open("xb"))
    return stack.enter_context(gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=1,
    ))


def convert_job(job, roots, workers, audio_cache):
    project = Path(roots["amphion_asr_project"])
    final = project / "data/audio-records" / job["dataset_id"] / job["version"]
    if final.exists():
        raise FileExistsError(f"published version already exists: {final}")
    work = project / "data/audio-records/work" / job["dataset_id"] / job["version"]
    work.mkdir(parents=True, exist_ok=False)
    index = {}
    seen = defaultdict(dict)
    mixture_ids = defaultdict(set)
    seconds = defaultdict(float)
    negative_counts = defaultdict(int)
    input_artifacts = []
    output_files = {}
    equivalences = []
    with ExitStack() as stack:
        executor = ThreadPoolExecutor if workers == 1 else ProcessPoolExecutor
        pool = stack.enter_context(executor(max_workers=workers))
        outputs = {}
        for source in job["sources"]:
            path = physical(source, roots)
            before = path.stat()
            count = 0
            source_seen = set()
            for batch in batches(path):
                normalized = []
                missing = {}
                for line, row in batch:
                    try:
                        data, text, negative = normalize(row, job["language"])
                    except (ValueError, TypeError, KeyError) as exc:
                        raise ValueError(f"{path}:{line}: {exc}") from exc
                    split = source.get("split") or (
                        "train_neg" if negative else f"train_{data['n_spk']}spk"
                    )
                    normalized.append((line, data, text, negative, split))
                    if "equivalent_to" not in source:
                        for field in ("enroll_wav", "mix_wav"):
                            audio_path = data[field]
                            if audio_path not in audio_cache:
                                ref = location(audio_path, roots)
                                missing[audio_path] = (Path(audio_path), ref, roots)
                audio_cache.update(pool.map(inspect_audio, missing.values(), chunksize=16))
                for line, data, text, negative, split in normalized:
                    key = (split, data["id"])
                    if key in source_seen:
                        raise ValueError(f"{path}:{line}: duplicate source ID {key}")
                    source_seen.add(key)
                    signature = core_signature(data, text, negative)
                    if "equivalent_to" in source:
                        if split not in source["equivalent_to"]:
                            raise ValueError(f"{path}:{line}: unexpected split {split}")
                        if seen[split].get(data["id"]) != signature:
                            raise ValueError(f"{path}:{line}: aggregate/equivalent mismatch")
                        count += 1
                        continue
                    if data["id"] in seen[split]:
                        raise ValueError(f"duplicate converted ID in {split}: {data['id']}")
                    seen[split][data["id"]] = signature
                    for field in ("enroll_wav", "mix_wav"):
                        index[data[field]] = audio_cache[data[field]]
                    if split not in outputs:
                        output_files[split] = work / (split + ".jsonl.gz")
                        outputs[split] = gzip_writer(stack, output_files[split])
                    record = make_record(
                        data, text, negative, job, split, source["name"], line, index,
                    )
                    outputs[split].write(encode(record) + b"\n")
                    mix = index[data["mix_wav"]]
                    seconds[split] += mix["duration"]
                    mixture_ids[split].add(mix["cut_id"])
                    negative_counts[split] += negative
                    count += 1
                if count % 100000 < len(batch):
                    print(job["version"], source["name"], count, flush=True)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError(f"source changed during conversion: {path}")
            if "equivalent_to" in source:
                expected = sum(len(seen[s]) for s in source["equivalent_to"])
                if count != expected:
                    raise ValueError(f"{path}: incomplete aggregate: {count} != {expected}")
                equivalences.append({"source_artifact": source["name"],
                                     "splits": source["equivalent_to"], "records": count})
            input_artifacts.append(artifact(
                source["name"], source["kind"], path, roots, count,
            ))
            print(job["version"], source["name"], "done", count, flush=True)
    by_id = {row["cut_id"]: row for row in index.values()}
    if len(by_id) != len(index):
        raise ValueError("audio ID collision")
    with ExitStack() as stack:
        writer = gzip_writer(stack, work / "audio-index.jsonl.gz")
        for cut_id in sorted(by_id):
            writer.write(encode(by_id[cut_id]) + b"\n")
    publish_job(job, roots, work, index, {s: len(ids) for s, ids in seen.items()},
                seconds, mixture_ids, negative_counts, input_artifacts, equivalences)


def publish_job(job, roots, work, index, counts, seconds, mixture_ids,
                negative_counts, input_artifacts, equivalences):
    """Publish completed, validated records and index without rereading audio."""
    project = Path(roots["amphion_asr_project"])
    final = project / "data/audio-records" / job["dataset_id"] / job["version"]
    if final.exists():
        raise FileExistsError(f"published version already exists: {final}")
    by_id = {row["cut_id"]: row for row in index.values()}
    source_splits = {
        a["name"]: {"source_artifact": a["name"],
                    "statistics": {"records": a["metadata"]["record_count"]}}
        for a in input_artifacts
    }
    splits = {}
    artifacts = []
    basis = "sum of mixture duration per target example; excludes enrollment/silence; repeated mixtures count once per example"
    for split, count in counts.items():
        path = work / (split + ".jsonl.gz")
        artifacts.append(artifact(split, "audio-records", path, roots, count))
        splits[split] = {
            "group": split.split("_", 1)[0], "records_artifact": split,
            "audio_index_artifact": "audio_index", "statistics": {
                "records": count, "negative_records": negative_counts[split],
                "duration_hours": seconds[split] / 3600, "duration_basis": basis,
                "unique_mixture_count": len(mixture_ids[split]),
                "unique_mixture_duration_hours": sum(
                    by_id[k]["duration"] for k in mixture_ids[split]
                ) / 3600,
            },
        }
    for group in sorted({s["group"] for s in splits.values()}):
        children = [s for s in splits if splits[s].get("group") == group]
        unique = set().union(*(mixture_ids[s] for s in children))
        splits[group] = {
            "records_artifacts": children, "audio_index_artifact": "audio_index",
            "statistics": {
                "records": sum(counts[s] for s in children),
                "duration_hours": sum(seconds[s] for s in children) / 3600,
                "duration_basis": basis, "unique_mixture_count": len(unique),
                "unique_mixture_duration_hours": sum(
                    by_id[k]["duration"] for k in unique
                ) / 3600,
            },
        }
    artifacts.append(artifact(
        "audio_index", "audio-index", work / "audio-index.jsonl.gz", roots, len(index),
    ))
    for item in artifacts:
        item["relative_path"] = str(
            final.relative_to(project) / Path(item["relative_path"]).name
        )
    common = {
        "schema_version": "dataset-catalog/1.0", "dataset_id": job["dataset_id"],
        "languages": [job["language"]], "tasks": ["ts_asr"], "aliases": [],
    }
    source_spec = {
        **common, "version": job["source_version"], "artifacts": input_artifacts,
        "splits": source_splits, "provenance": {
            "description": job["description"] + "；转换输入快照，时长见通用版本。",
            "upstream_lineage_status": "inferred", "snapshot_date": job["date"],
            "historical_path_note": "历史路径按登记时现存字节取快照，不能证明与过去运行时逐字节一致。",
        },
    }
    result_spec = {
        **common, "version": job["version"], "artifacts": artifacts, "splits": splits,
        "recipe_parameters": {
            "converter": "scripts/target_asr/convert.py", "converter_version": CONVERTER_VERSION,
            "converter_sha256": sha256_file(Path(__file__)),
            "source_version": job["source_version"], "equivalent_sources": equivalences,
            "audio_index_fields": ["cut_id", "root_alias", "relative_path", "sample_rate",
                                   "channels", "num_frames", "duration"],
            "original_consumer": {"enrollment_seconds": 3, "enrollment_start": 0,
                                  "silence_seconds": 3, "sample_rate": 16000},
        },
        "provenance": {
            "description": job["description"] + "；纯转写、独立 enrollment/mixture、空转写负样本。",
            "snapshot_date": job["date"], "source_version": job["source_version"],
            "integrity": "verified", "quality_status": "source_annotations_preserved_not_reaudited",
            "duration_label": "按目标样本累计混合音频，非去重语料时长",
            "validation": {"audio_headers_checked": len(index),
                           "all_records_validated": True, "duplicate_record_ids": 0},
        },
    }
    view = {
        "schema_version": "dataset-view/1.0", "view_id": job["view_id"],
        "version": job["version"],
        "source": {"dataset_id": job["dataset_id"], "version": job["source_version"]},
        "result": {"dataset_id": job["dataset_id"], "version": job["version"]},
        "transforms": [{"name": "portable-target-asr", "version": CONVERTER_VERSION,
                        "kind": "representation-conversion",
                        "writes": ["audio_slots", "target", "language", "labels", "metadata"],
                        "parameters": {"source_records_preserved": True,
                                       "aggregate_files_materialized_once": True}}],
        "materialization": "full", "lineage_status": "exact",
    }
    report = {"datasets": [source_spec, result_spec], "view": view}
    (work / "registration.json").write_bytes(encode(report) + b"\n")
    final.parent.mkdir(parents=True, exist_ok=True)
    work.rename(final)
    print("PUBLISHED", final, flush=True)


def register(recipe, roots, repository):
    """Publish declarations only after every recipe job has completed."""
    by_dataset = defaultdict(list)
    views = []
    for job in recipe["jobs"]:
        directory = (Path(roots["amphion_asr_project"]) / "data/audio-records"
                     / job["dataset_id"] / job["version"])
        report = json.loads((directory / "registration.json").read_text())
        by_dataset[job["dataset_id"]].extend(report["datasets"])
        views.append(report["view"])
    # Validate all new declarations together with the existing catalog before writing.
    from audio_data_contract.catalog import validate_catalog
    from audio_data_contract.types import DatasetSpec, DatasetViewSpec
    from audio_data_contract.views import validate_view_catalog

    current = load_catalog(repository / "catalog")
    combined = validate_catalog([
        *current, *(DatasetSpec.from_dict(d) for ds in by_dataset.values() for d in ds),
    ])
    validate_view_catalog([
        *load_view_catalog(repository / "views", current),
        *(DatasetViewSpec.from_dict(v) for v in views),
    ], combined)
    destinations = {repository / "catalog" / (ds + ".jsonl"): rows
                    for ds, rows in by_dataset.items()}
    destinations[repository / "views/target_asr.jsonl"] = views
    for path in destinations:
        if path.exists():
            raise FileExistsError(f"refusing to replace existing declarations: {path}")
    for path, rows in destinations.items():
        path.write_bytes(b"".join(encode(row) + b"\n" for row in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["convert", "register"])
    parser.add_argument("--recipe", type=Path, default=Path(__file__).with_name("sources.json"))
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--job", action="append", help="convert only this version")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    recipe = json.loads(args.recipe.read_text())
    if args.command == "register":
        register(recipe, roots, Path(__file__).resolve().parents[2])
    else:
        jobs = [j for j in recipe["jobs"] if not args.job or j["version"] in args.job]
        if not jobs or (args.job and set(args.job) != {j["version"] for j in jobs}):
            parser.error("unknown job version")
        if args.workers < 1:
            parser.error("workers must be positive")
        audio_cache = {}
        for job in jobs:
            convert_job(job, roots, args.workers, audio_cache)


if __name__ == "__main__":
    main()
