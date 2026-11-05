#!/usr/bin/env python3
"""Cut plain-ASR windows from real multi-party recordings whose transcript is every speaker's words in time order.

Plain-ASR training data of the TS-robust recipe has one transcribed speaker per sample: meeting ASR versions
(``asr-20261014``) hold one supervision each, and the turn-taking windows where several people take turns are
TS records (an enrollment and only the target's words). A model trained on them drops the other parties' turns
of a multi-party recording in plain-ASR mode, and stops early in recordings longer than about 30 s. This script
writes ``<dataset>@allspk-asr-v1-20261103``: windows of 10-90 s over the train recordings, cut where nobody
speaks, whose target is the punctuated text of every utterance in the window, ordered by start time.

* Utterances: the corpus's ``icefall-20260908`` train supervisions (complete annotation, short backchannels
  included), so a window's target covers all annotated speech in it.
* Text: ``punc-written-v1-20261029`` (the punctuated, written form of each supervision, same IDs). A window
  with any utterance that lacks it is dropped: every training target is punctuated.
* Audio: the corpus's ``asr-20261014`` train audio index (one row per recording, channel 0 as in its records);
  records refer to that version, nothing is copied.
* Clean pass: for MagicData-RAMC, a window with an utterance that failed ``clean-dual-qwen-moss-v1-20261008``
  (``custom.clean.pass`` false) is dropped, matching ``require_clean_pass`` on its per-utterance training version.
* Windows: per recording, consecutive and disjoint; each draws its length uniformly from [10, 90] s (seeded by
  the recording ID), then ends at the last utterance end that leaves a pause of at least 0.2 s before the next
  utterance. Windows whose overlapped speech exceeds 10% of their length are dropped (their word order is
  ambiguous for a plain transcript). Only the train split is read.

    python build_allspk_asr_windows.py --dataset alimeeting_sdm [--limit N]
"""

import argparse
import gzip
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from audio_data_contract import load_catalog, resolve_split

DATA = Path("/workspace/data")
VERSION = "allspk-asr-v1-20261103"
ANNOTATION = "icefall-20260908"
PUNC = "punc-written-v1-20261029"
AUDIO = "asr-20261014"
# Corpora with a clean pass: a window with any utterance that failed it is dropped, as require_clean_pass does
# for the corpus's per-utterance training version (the pass marks are custom.clean.pass of these supervisions).
CLEAN = {"magicdata_ramc": "clean-dual-qwen-moss-v1-20261008"}
LENGTH_S = (10.0, 90.0)
MIN_PAUSE_S = 0.2  # silence required on both sides of a window
EDGE_S = 0.1  # audio kept before the first and after the last utterance (within the pauses)
MIN_WINDOW_S = 5.0
MAX_OVERLAP = 0.10
SEED = 20261103


def read_jsonl(paths):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def overlap_seconds(utts):
    """Seconds where two or more utterances are active."""
    events = sorted([(u["start"], 1) for u in utts] + [(u["end"], -1) for u in utts])
    active, last, total = 0, None, 0.0
    for time, step in events:
        if active >= 2 and last is not None:
            total += time - last
        active += step
        last = time
    return total


def windows(utts, rng):
    """Disjoint windows over one recording's utterances (sorted by start), cut at pauses of MIN_PAUSE_S."""
    n = len(utts)
    # reach[i]: latest end among utterances 0..i; a cut after i is clean when the next one starts a pause later.
    reach, latest = [], float("-inf")
    for u in utts:
        latest = max(latest, u["end"])
        reach.append(latest)
    clean_after = [i + 1 == n or utts[i + 1]["start"] - reach[i] >= MIN_PAUSE_S for i in range(n)]
    i = 0
    while i < n:
        if i and not clean_after[i - 1]:
            i += 1
            continue
        length = rng.uniform(*LENGTH_S)
        j, best = i, None
        while j < n and reach[j] - utts[i]["start"] <= length:
            if clean_after[j]:
                best = j
            j += 1
        if best is None:  # no clean cut within the drawn length: skip to the next clean start
            i += 1
            continue
        yield utts[i:best + 1]
        i = best + 1


def build(dataset, limit=None):
    catalog = load_catalog(DATA / "registry" / "catalog")
    roots = json.loads((DATA / "registry" / "roots.json").read_text())
    entry = next(e for e in catalog if e.dataset_id == dataset and e.version == ANNOTATION)
    sups = list(read_jsonl(resolve_split(catalog, dataset, ANNOTATION, "train", "supervisions", roots)))
    punc_entry = next(e for e in catalog if e.dataset_id == dataset and e.version == PUNC)
    punc = {}
    for split in punc_entry.splits:
        for row in read_jsonl(resolve_split(catalog, dataset, PUNC, split, "punctuated_supervisions", roots)):
            punc[row["id"]] = row["text"]
    failed = set()
    if dataset in CLEAN:
        for row in read_jsonl(resolve_split(catalog, dataset, CLEAN[dataset], "train", "supervisions", roots)):
            if not row["custom"]["clean"]["pass"]:
                failed.add(row["id"])
        if not failed:
            raise SystemExit(f"{dataset}@{CLEAN[dataset]}: no clean marks read")
    # recording ID -> (audio cut ID, channel) of the asr-20261014 train records
    cuts = {}
    for row in read_jsonl(resolve_split(catalog, dataset, AUDIO, "train", "records", roots)):
        ref = row["audio_slots"][0]["ref"]
        cuts.setdefault(row["metadata"]["recording_id"], (ref["cut_id"], ref.get("channel")))
    by_recording = {}
    for row in sups:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        by_recording.setdefault(row["recording_id"], []).append(
            {"id": row["id"], "start": float(row["start"]), "end": float(row["start"]) + float(row["duration"]),
             "speaker": str(row["speaker"])})
    language = (entry.languages or ["zh"])[0]
    joiner = "" if language == "zh" else " "
    out_dir = DATA / "datasets" / dataset / "versions" / VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    speakers = Counter()
    seconds = Counter()
    records_path = out_dir / "records_train.jsonl.gz"
    with gzip.open(records_path, "wt", encoding="utf-8") as stream:
        for rid in sorted(by_recording):
            if limit is not None and stats["recordings"] >= limit:
                break
            if rid not in cuts:
                stats["recordings_without_audio"] += 1
                continue
            stats["recordings"] += 1
            cut_id, channel = cuts[rid]
            utts = sorted(by_recording[rid], key=lambda u: (u["start"], u["end"]))
            rng = random.Random(f"{SEED}:{dataset}:{rid}")
            previous_end = 0.0
            for k, group in enumerate(windows(utts, rng)):
                first, last_end = group[0]["start"], max(u["end"] for u in group)
                start = max(previous_end, first - EDGE_S, 0.0)
                end = last_end + EDGE_S
                previous_end = last_end
                duration = end - start
                stats["windows"] += 1
                if duration < MIN_WINDOW_S:
                    stats["drop_short"] += 1
                    continue
                if overlap_seconds(group) > MAX_OVERLAP * duration:
                    stats["drop_overlap"] += 1
                    continue
                if any(u["id"] not in punc for u in group):
                    stats["drop_unpunctuated"] += 1
                    continue
                if any(u["id"] in failed for u in group):
                    stats["drop_clean_reject"] += 1
                    continue
                target = joiner.join(punc[u["id"]].strip() for u in group)
                n_spk = len({u["speaker"] for u in group})
                ref = {"dataset_id": dataset, "version": AUDIO, "split": "train", "cut_id": cut_id,
                       **({"channel": channel} if channel is not None else {}),
                       "start": round(start, 3), "duration": round(duration, 3)}
                record = {
                    "schema_version": "audio-record/1.0", "id": f"{dataset}:allspk:{rid}:{k:04d}", "task": "asr",
                    "target": target, "language": language, "labels": {"speakers": n_spk}, "hotwords": [],
                    "audio_slots": [{"name": "primary", "purpose": "primary", "ref": ref}],
                    "metadata": {
                        "recording_id": rid, "window_start": round(start, 3), "window_end": round(end, 3),
                        "overlap_seconds": round(overlap_seconds(group), 3),
                        "window_utts": [{"id": u["id"], "speaker": f"{dataset}:{u['speaker']}",
                                         "start": round(u["start"] - start, 3),
                                         "duration": round(u["end"] - u["start"], 3)} for u in group]}}
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stats["kept"] += 1
                speakers[min(n_spk, 4)] += 1
                seconds[int(min(duration, 89.999) // 10) * 10] += duration
    report = {"dataset": dataset, "version": VERSION, "annotation": f"{dataset}@{ANNOTATION}",
              "punctuation": f"{dataset}@{PUNC}", "audio": f"{dataset}@{AUDIO}",
              **({"clean_pass": f"{dataset}@{CLEAN[dataset]}", "clean_rejected_utterances": len(failed)}
                 if dataset in CLEAN else {}),
              "parameters": {"length_s": LENGTH_S, "min_pause_s": MIN_PAUSE_S, "edge_s": EDGE_S,
                             "min_window_s": MIN_WINDOW_S, "max_overlap": MAX_OVERLAP, "seed": SEED},
              "counts": dict(stats), "speakers": {("4+" if k == 4 else str(k)): v for k, v in sorted(speakers.items())},
              "hours_by_length": {f"{k}-{k + 10}s": round(v / 3600, 2) for k, v in sorted(seconds.items())},
              "hours": round(sum(seconds.values()) / 3600, 2),
              "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest()}
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, choices=("alimeeting_sdm", "aishell4", "magicdata_ramc"))
    parser.add_argument("--limit", type=int, help="first N recordings only (a trial run)")
    args = parser.parse_args()
    build(args.dataset, args.limit)


if __name__ == "__main__":
    main()
