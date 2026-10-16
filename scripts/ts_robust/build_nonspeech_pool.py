#!/usr/bin/env python3
"""Build ts_nonspeech_pool: speech-free clips that plain ASR must transcribe as nothing.

Each record is one span (file, start, duration) of MUSAN noise or music with an empty
target. Durations are log-uniform between 0.3 s and 26 s, so very short and very long
clips occur as in the benchmark's nonspeech sets. The level is drawn at training time
(`nonspeech: {level_dbfs: [...]}` on the source). WHAM is not used: it is recorded in cafes
and bars and its babble can hold intelligible words, which a plain-ASR model must not be
taught to ignore.

Output (a registrable dataset version, records + audio_index like the interference pool):
  records_all.jsonl.gz, audio_index_all.jsonl.gz, report.json

    python build_nonspeech_pool.py --output-dir DIR [--workers 16]
"""

import argparse
import gzip
import json
import math
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.roots import load_roots

CATALOG = "/workspace/data/registry/catalog"
ROOTS = "/workspace/data/registry/roots.json"
ROOT_ALIAS = "aidc_data"
DATASET_ID, VERSION, SPLIT = "ts_nonspeech_pool", "v1-20261016", "all"
TASK = "asr"
SEED = 20261016
MIN_SECONDS, MAX_SECONDS = 0.3, 26.0
# After the level is reset at training time, only a clip with no signal at all is useless.
MIN_RMS = 1e-4
SOURCES = [
    # (dataset, version, split, clips, most clips per file)
    ("musan", "legacy-20260804", "noise", 24000, 60),
    ("musan", "legacy-20260804", "music", 24000, 60),
]


def lines(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        yield from (json.loads(line) for line in stream)


def measure_file(job):
    from lhotse import AudioSource, Recording

    path, rate, frames, duration, spans = job
    recording = Recording(id="x", sources=[AudioSource("file", [0], path)], sampling_rate=rate,
                          num_samples=frames, duration=duration)
    out = []
    for index, start, span in spans:
        try:
            clip = recording.load_audio(offset=start, duration=span).mean(axis=0)
        except Exception as error:
            out.append((index, f"decode_failed: {repr(error)[:60]}"))
            continue
        out.append((index, None if float(np.sqrt(np.mean(clip**2))) >= MIN_RMS else "silent"))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    catalog, roots = load_catalog(CATALOG), load_roots(ROOTS)
    root = Path(roots[ROOT_ALIAS])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records, index_rows, report = [], {}, {}
    for dataset, version, split, count, per_file in SOURCES:
        rng = random.Random(f"{SEED}:{dataset}:{split}")
        files = [r for path in resolve_split(catalog, dataset, version, split, "recordings", roots)
                 for r in lines(path) if r["duration"] >= MIN_SECONDS]
        spans = []
        for number in range(int(count * 1.1)):
            rec = files[number % len(files)] if number < len(files) * per_file else rng.choice(files)
            span = min(rec["duration"], math.exp(rng.uniform(math.log(MIN_SECONDS), math.log(MAX_SECONDS))))
            spans.append((rec, rng.uniform(0, rec["duration"] - span), span))
        rng.shuffle(spans)
        by_file = defaultdict(list)
        for number, (rec, start, span) in enumerate(spans):
            by_file[rec["id"]].append((number, start, span))
        jobs = [(spans[items[0][0]][0]["sources"][0]["source"], spans[items[0][0]][0]["sampling_rate"],
                 spans[items[0][0]][0]["num_samples"], spans[items[0][0]][0]["duration"], items)
                for items in by_file.values()]
        dropped = defaultdict(int)
        bad = set()
        with ProcessPoolExecutor(args.workers) as pool:
            for out in pool.map(measure_file, jobs, chunksize=4):
                for number, error in out:
                    if error:
                        bad.add(number)
                        dropped[error.split(":")[0]] += 1
        kept = [(number, item) for number, item in enumerate(spans) if number not in bad][:count]
        if len(kept) < count:
            raise ValueError(f"{dataset}:{split}: wanted {count}, only {len(kept)} usable")
        for number, (rec, start, span) in kept:
            file_id = f"{dataset}:{split}:{rec['id']}"
            language = rng.choice(("zh", "en"))
            records.append({
                "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{dataset}-{split}:{number:06d}",
                "task": TASK, "target": "", "language": language, "labels": {"target_present": False},
                "hotwords": [],
                "audio_slots": [{"name": "primary", "ref": {
                    "dataset_id": DATASET_ID, "version": VERSION, "split": SPLIT, "cut_id": file_id,
                    "start": round(start, 3), "duration": round(span, 3)}}],
                "metadata": {"source_dataset": f"{dataset}:{split}", "source_group": file_id}})
            source_path = Path(rec["sources"][0]["source"])
            index_rows.setdefault(file_id, {
                "cut_id": file_id, "root_alias": ROOT_ALIAS, "relative_path": source_path.relative_to(root).as_posix(),
                "sample_rate": rec["sampling_rate"], "channels": len(rec["channel_ids"]),
                "num_frames": rec["num_samples"], "duration": rec["duration"]})
        seconds = [item[2] for _, item in kept]
        report[f"{dataset}:{split}"] = {"clips": len(kept), "files": len({item[0]["id"] for _, item in kept}),
                                        "hours": round(sum(seconds) / 3600, 2), "dropped": dict(dropped),
                                        "seconds_median": round(float(np.median(seconds)), 2)}
        print(dataset, split, report[f"{dataset}:{split}"], flush=True)
    records.sort(key=lambda r: r["id"])
    for stem, items in (("records", records), ("audio_index", sorted(index_rows.values(), key=lambda r: r["cut_id"]))):
        with gzip.open(args.output_dir / f"{stem}_{SPLIT}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for item in items:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    report["total"] = {"clips": len(records), "files": len(index_rows)}
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("total", report["total"])


if __name__ == "__main__":
    main()
