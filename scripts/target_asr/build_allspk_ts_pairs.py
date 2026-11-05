#!/usr/bin/env python3
"""Target-speaker records on the same windows as ``<dataset>@allspk-asr-v1-20261103``, so each window is seen both ways.

The all-speaker windows teach plain ASR to transcribe every party of a multi-party recording. Trained alone, that
habit leaks into TS mode: on multi-speaker turn-taking audio the model also writes the other parties' turns (more
insertions on the TS benchmark's 3+ speaker and alternating-turn sets). This script writes
``<dataset>@allspk-ts-v1-20261104``: for every window of the all-speaker version, the same audio as a TS record, so
the model learns from identical audio that the prompt decides whose words to write.

* ``train``: one target speaker per window (uniform over the window's speakers that have an enrollment); the target
  is the punctuated text (``punc-written-v1-20261029``) of that speaker's utterances in the window, in start order.
* ``train_neg``: per window, one speaker of the same recording who does not speak in the window (when there is one
  with an enrollment); the target is empty.
* Enrollment: an utterance of that speaker in the same recording, outside the window, 3-10 s long (2-15 s when there
  is none), that no other utterance overlaps, and (MagicData-RAMC) that passed ``clean-dual-qwen-moss-v1-20261008``.
* Audio: both slots refer to the corpus's ``asr-20261014`` train audio (the window's own reference and channel);
  nothing is copied. Utterances come from ``icefall-20260908`` train supervisions, as in the all-speaker version.

    python build_allspk_ts_pairs.py --dataset alimeeting_sdm
"""

import argparse
import gzip
import hashlib
import json
import random
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

from audio_data_contract import load_catalog, resolve_split

DATA = Path("/workspace/data")
VERSION = "allspk-ts-v1-20261104"
WINDOWS = "allspk-asr-v1-20261103"
ANNOTATION = "icefall-20260908"
PUNC = "punc-written-v1-20261029"
CLEAN = {"magicdata_ramc": "clean-dual-qwen-moss-v1-20261008"}  # as in build_allspk_asr_windows.py
ENROLL_S = (3.0, 10.0)  # preferred enrollment length
ENROLL_FALLBACK_S = (2.0, 15.0)
SEED = 20261104


def read_jsonl(paths):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def clean_enrollments(utts, failed):
    """Utterances (one recording, any order) that no other utterance overlaps and that passed the clean pass."""
    ordered = sorted(utts, key=lambda u: u["start"])
    keep = []
    for i, u in enumerate(ordered):
        if u["id"] in failed:
            continue
        before = any(v["end"] > u["start"] for v in ordered[:i])
        after = i + 1 < len(ordered) and ordered[i + 1]["start"] < u["end"]
        if not before and not after:
            keep.append(u)
    return keep


def pick_enrollment(candidates, window_start, window_end, rng):
    outside = [u for u in candidates if u["end"] <= window_start or u["start"] >= window_end]
    for low, high in (ENROLL_S, ENROLL_FALLBACK_S):
        fit = [u for u in outside if low <= u["end"] - u["start"] <= high]
        if fit:
            return rng.choice(fit)
    return None


def ts_record(dataset, language, window, in_window, window_speakers, target_speaker, enroll, target):
    """One TS record on a window's audio; an empty target makes it a negative (the speaker is absent)."""
    present = bool(target)
    mixture = window["audio_slots"][0]["ref"]
    meta = window["metadata"]
    enroll_ref = {k: mixture[k] for k in ("dataset_id", "version", "split", "cut_id", "channel") if k in mixture}
    enroll_ref.update(start=round(enroll["start"], 3), duration=round(enroll["end"] - enroll["start"], 3))
    labels = {"n_spk": len(window_speakers), "target_present": present, "enroll_spk": target_speaker,
              "mix_speakers": window_speakers}
    labels.update({"target_spk": target_speaker} if present else {"sample_type": "negative_distractor"})
    return {
        "schema_version": "audio-record/1.0",
        "id": f"{dataset}:allspk-ts:{window['id'].split(':allspk:', 1)[1]}:{'pos' if present else 'neg'}",
        "task": "ts_asr",
        "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": enroll_ref},
                        {"name": "mixture", "purpose": "mixture", "ref": dict(mixture)}],
        "target": target, "language": language, "labels": labels, "hotwords": [],
        "metadata": {"source_record_id": window["id"], "recording_id": meta["recording_id"],
                     "window_start": meta["window_start"], "window_end": meta["window_end"],
                     "enroll_utt": enroll["id"], "enroll_recording_id": meta["recording_id"],
                     "target_speaker": f"{dataset}:{target_speaker}",
                     "window_utts": [dict(u, speaker=f"{dataset}:{u['speaker']}") for u in in_window]}}


def build(dataset):
    catalog = load_catalog(DATA / "registry" / "catalog")
    roots = json.loads((DATA / "registry" / "roots.json").read_text())
    language = next(e for e in catalog if e.dataset_id == dataset and e.version == ANNOTATION).languages[0]
    joiner = "" if language == "zh" else " "
    utts_by_rec, speaker_of = {}, {}
    for row in read_jsonl(resolve_split(catalog, dataset, ANNOTATION, "train", "supervisions", roots)):
        if not (row.get("text") or "").strip():
            continue
        start = float(row["start"])
        u = {"id": row["id"], "start": start, "end": start + float(row["duration"]), "speaker": str(row["speaker"])}
        utts_by_rec.setdefault(row["recording_id"], []).append(u)
        speaker_of[row["id"]] = u["speaker"]
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
    enrollable = {}  # recording -> speaker -> clean utterances
    for rid, utts in utts_by_rec.items():
        for u in clean_enrollments(utts, failed):
            enrollable.setdefault(rid, {}).setdefault(u["speaker"], []).append(u)
    windows = list(read_jsonl(resolve_split(catalog, dataset, WINDOWS, "train", "records", roots)))
    out_dir = DATA / "datasets" / dataset / "versions" / VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    stats, speakers = Counter(), Counter()
    paths = {"train": out_dir / "records_train.jsonl.gz", "train_neg": out_dir / "records_train_neg.jsonl.gz"}
    with ExitStack() as stack:
        streams = {k: stack.enter_context(gzip.open(p, "wt", encoding="utf-8")) for k, p in paths.items()}
        for window in windows:
            meta = window["metadata"]
            rid, w_start, w_end = meta["recording_id"], meta["window_start"], meta["window_end"]
            rng = random.Random(f"{SEED}:{window['id']}")
            in_window = [dict(u, speaker=speaker_of[u["id"]]) for u in meta["window_utts"]]
            window_speakers = sorted({u["speaker"] for u in in_window})
            by_speaker = enrollable.get(rid, {})
            stats["windows"] += 1
            positives = [(s, e) for s in window_speakers
                         if (e := pick_enrollment(by_speaker.get(s, []), w_start, w_end, rng))]
            if positives:
                s, enroll = rng.choice(positives)
                target = joiner.join(punc[u["id"]].strip() for u in in_window if u["speaker"] == s)
                row = ts_record(dataset, language, window, in_window, window_speakers, s, enroll, target)
                streams["train"].write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["train"] += 1
                speakers[min(len(window_speakers), 4)] += 1
            else:
                stats["no_target_enrollment"] += 1
            absent = [(s, e) for s in sorted(set(by_speaker) - set(window_speakers))
                      if (e := pick_enrollment(by_speaker[s], w_start, w_end, rng))]
            if absent:
                s, enroll = rng.choice(absent)
                row = ts_record(dataset, language, window, in_window, window_speakers, s, enroll, "")
                streams["train_neg"].write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["train_neg"] += 1
            else:
                stats["no_absent_speaker"] += 1
    report = {"dataset": dataset, "version": VERSION, "windows": f"{dataset}@{WINDOWS}",
              "annotation": f"{dataset}@{ANNOTATION}", "punctuation": f"{dataset}@{PUNC}",
              **({"clean_pass": f"{dataset}@{CLEAN[dataset]}"} if dataset in CLEAN else {}),
              "parameters": {"enroll_s": ENROLL_S, "enroll_fallback_s": ENROLL_FALLBACK_S, "seed": SEED},
              "counts": dict(stats), "positive_window_speakers": {("4+" if k == 4 else str(k)): v for k, v in sorted(speakers.items())},
              "records_sha256": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()}}
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, choices=("alimeeting_sdm", "aishell4", "magicdata_ramc"))
    build(parser.parse_args().dataset)


if __name__ == "__main__":
    main()
