#!/usr/bin/env python3
"""Real-meeting target-speaker windows from the TRAIN splits, in the benchmark's shape (ts_real_train).

`scripts/ts_real/build.py` cuts the evaluation windows (ts_asr_real) out of the test splits of
AliMeeting far-field, AISHELL-4 and MagicData-RAMC: 8-22 s runs of whole utterances, 1 / 2 / 3+ speakers
talking, and for every window a pair on the same audio - a positive (a speaker of the window enrolled with
another utterance of theirs from outside it) and a negative (a speaker of the same recording who does not
speak in the window). This script cuts the same windows from the train splits and writes them as records
over spans of the long recordings, so nothing is copied and nothing is mixed.

The offline turn-taking sets used for training so far have only windows with two or three speakers (no
window where a single other speaker talks) and read all eight channels of the far-field arrays as a mean;
the benchmark reads channel 0. Every slot here names ``channel: 0``, which the loader honours by reading
that one microphone, exactly like the benchmark does.

One split per corpus (alimeeting, aishell4, ramc) so the training recipe can weigh them separately.

``--recipe v2`` (v2-20261018) cuts target-anchored windows instead (``ts_real/build.py``
``target_windows``: the target's utterances whole, everyone else's clipped to the window), sampled per
overlap bucket - the share of the target's speech that others talk over - so overlapped stretches are not
dropped, and writes each window's utterances (``metadata.window_utts``, as in ts_asr_real) for frame-level
labels. Recordings with a speaker of the corpus's dev or test splits are left out.

    python build_ts_real_train.py --output-dir DIR [--recipe v1 --per-bucket 10000 | --recipe v2]
"""

import argparse
import gzip
import hashlib
import importlib.util
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from audio_data_contract import load_catalog, resolve_split

# ts_real/build.py: windows, enrollment candidates, overlap. Loaded under its own name because it
# imports the benchmark's build.py as ``build``.
_spec = importlib.util.spec_from_file_location("ts_real_build", Path(__file__).resolve().parents[1] / "ts_real/build.py")
real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real)

DATA = Path("/workspace/data")
ROOT_ALIAS = "aidc_data"
DATASET_ID = "ts_real_train"
RECIPES = {
    "v1": {"version": "v1-20261017", "seed": 20261017},
    # Windows per corpus and overlap bucket (ts_real/build.py OVERLAP_BUCKETS); RAMC transcripts never overlap.
    "v2": {"version": "v2-20261018", "seed": 20261018, "windows": {
        "alimeeting": {"o0": 3000, "o20": 4000, "o50": 6000, "o100": 8000},
        "aishell4": {"o0": 4000, "o20": 4000, "o50": 4000, "o100": 4000},
        "ramc": {"o0": 6000},
    }},
}
CORPORA = {
    "alimeeting": ("alimeeting_sdm", "icefall-20260908"),
    "aishell4": ("aishell4", "icefall-20260908"),
    "ramc": ("magicdata_ramc", "icefall-20260908"),
}
BUCKETS = {"1spk": (1, 1), "2spk": (2, 2), "3plus": (3, 99)}


def load_corpus(dataset, version, catalog, roots, split="train"):
    """{recording_id: entry} like ts_real/build.py, over every file of the split."""
    recordings = {}
    for path in resolve_split(catalog, dataset, version, split, "recordings", roots):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                recordings[row["id"]] = row
    out = {}
    for path in resolve_split(catalog, dataset, version, split, "supervisions", roots):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                rid = row["recording_id"]
                if rid not in recordings or not (row.get("text") or "").strip():
                    continue
                recording = recordings[rid]
                entry = out.setdefault(rid, {
                    "path": recording["sources"][0]["source"], "sups": [], "duration": float(recording["duration"]),
                    "sample_rate": int(recording["sampling_rate"]), "num_samples": int(recording["num_samples"]),
                    "channels": len(recording["sources"][0]["channels"])})
                entry["sups"].append((float(row["start"]), float(row["start"]) + float(row["duration"]),
                                      str(row["speaker"]), "".join(row["text"].split())))
    for entry in out.values():
        real.finish_entry(entry)
    return out


def held_out_speakers(dataset, version, catalog, roots):
    """Speakers of the corpus's splits other than train (dev, test)."""
    entry = next(d for d in catalog if d.dataset_id == dataset and d.version == version)
    return {u[2] for split in entry.splits if split != "train"
            for rec in load_corpus(dataset, version, catalog, roots, split).values() for u in rec["sups"]}


def plan(recordings, rng, per_bucket):
    """Paired positive / negative plans per speaker-count bucket, like ts_real/build.py plan_samples."""
    by_bucket = defaultdict(list)
    for rid, rec in sorted(recordings.items()):
        for window in real.candidate_windows(rec, rng):
            present = real.speaker_seconds(window["utts"])
            window.update(recording=rid, present=present, speakers=len(present))
            for bucket, (low, high) in BUCKETS.items():
                if low <= window["speakers"] <= high:
                    by_bucket[bucket].append(window)
    plans = defaultdict(list)
    for bucket, windows in sorted(by_bucket.items()):
        rng.shuffle(windows)
        for window in windows:
            if len(plans[bucket]) >= per_bucket:
                break
            rec = recordings[window["recording"]]
            usable = [s for s, sec in window["present"].items() if sec >= real.MIN_TARGET_SECONDS]
            rng.shuffle(usable)
            target = next((s for s in usable if real.eligible_enrollments(rec, s, window["lo"], window["hi"])), None)
            if target is None:
                continue
            speakers = {u[2] for u in rec["sups"]}
            absent = [s for s in sorted(speakers - set(window["present"]))
                      if real.eligible_enrollments(rec, s, window["lo"], window["hi"])]
            if absent:
                other, speaker, source = window["recording"], rng.choice(absent), "same_recording"
            else:  # another recording of the corpus, as in the benchmark
                pool = [(r, s) for r, o in sorted(recordings.items()) if r != window["recording"]
                        for s in sorted({u[2] for u in o["sups"]}) if real.eligible_enrollments(o, s, -1e9, -1e9)]
                if not pool:
                    continue
                (other, speaker), source = rng.choice(pool), "other_recording"
            plans[bucket].append({"window": window, "target": target, "absent": (other, speaker, source)})
    return plans


def index_row(recordings, rid):
    entry = recordings[rid]
    relative = Path(entry["path"]).resolve().relative_to(DATA).as_posix()
    cut = hashlib.sha256(f"{ROOT_ALIAS}:{relative}".encode()).hexdigest()
    return {"cut_id": cut, "root_alias": ROOT_ALIAS, "relative_path": relative, "sample_rate": entry["sample_rate"],
            "channels": entry["channels"], "num_frames": entry["num_samples"], "duration": round(entry["num_samples"] / entry["sample_rate"], 3)}


def make_records(split, name, plans, recordings, rng, audio, version, window_utts=False):
    records = []
    base = {"dataset_id": DATASET_ID, "version": version, "split": split}

    def ref(rid, start, end):
        row = audio.setdefault(rid, index_row(recordings, rid))
        # channel 0: the benchmark reads the first microphone of the arrays, not the mean of all eight
        return {**base, "cut_id": row["cut_id"], "channel": 0, "start": round(start, 3), "duration": round(end - start, 3)}

    number = 0
    for bucket, items in sorted(plans.items()):
        for item in items:
            window, target = item["window"], item["target"]
            rec = recordings[window["recording"]]
            span = ref(window["recording"], window["lo"], window["hi"])
            target_utts = sorted(u for u in window["utts"] if u[2] == target)
            pos_s, pos_e, _ = rng.choice(real.eligible_enrollments(rec, target, window["lo"], window["hi"]))
            other, speaker, source = item["absent"]
            other_rec = recordings[other]
            candidates = (real.eligible_enrollments(other_rec, speaker, -1e9, -1e9) if source == "other_recording"
                          else real.eligible_enrollments(other_rec, speaker, window["lo"], window["hi"]))
            neg_s, neg_e, _ = rng.choice(candidates)
            common = {"corpus": name, "recording": window["recording"], "bucket": bucket,
                      "speakers_in_window": window["speakers"], "duration_s": round(window["hi"] - window["lo"], 3),
                      "annotation": "human", "pair": number}
            for kind, who, enroll in (("pos", target, ref(window["recording"], pos_s, min(pos_e, pos_s + real.ENROLL_MAX))),
                                      ("neg", speaker, ref(other, neg_s, min(neg_e, neg_s + real.ENROLL_MAX)))):
                present = kind == "pos"
                labels = {**common, "target_present": present,
                          "n_interferers": window["speakers"] - (1 if present else 0)}
                if window_utts:
                    labels["overlap_bucket"] = bucket
                if present:
                    labels["target_overlap_ratio"] = round(real.overlap_ratio(target_utts, window["utts"]), 3)
                    labels["target_seconds"] = round(sum(e - s for s, e, _, _ in target_utts), 2)
                else:
                    labels["absent_source"] = source
                records.append({
                    "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{split}:{kind}:{number:07d}",
                    "task": "ts_asr", "target": "".join(u[3] for u in target_utts) if present else "", "language": "zh",
                    "labels": labels, "hotwords": [],
                    "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": enroll},
                                    {"name": "mixture", "purpose": "mixture", "ref": span}],
                    "metadata": {"source_group": f"{name}:{window['recording']}:{who}",
                                 "target_speaker": f"{name}:{who}", "window_start_s": round(window["lo"], 3),
                                 **({"window_utts": utterances(name, window)} if window_utts else {})}})
            number += 1
    return records


def utterances(name, window):
    """The window's utterances relative to its start, as ts_real/build.py writes them."""
    return [{"speaker": f"{name}:{spk}", "start": round(s - window["lo"], 3), "duration": round(e - s, 3),
             "text": text, **({"clipped": True} if (s, e, spk, text) in window.get("clipped", ()) else {})}
            for s, e, spk, text in sorted(window["utts"])]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipe", choices=sorted(RECIPES), default="v1")
    parser.add_argument("--per-bucket", type=int, default=10000,
                        help="v1: windows per speaker-count bucket and corpus")
    args = parser.parse_args()
    recipe = RECIPES[args.recipe]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    roots = {k: Path(v) for k, v in json.loads(Path("/workspace/data/registry/roots.json").read_text()).items()}
    catalog = load_catalog("/workspace/data/registry/catalog")
    report = {}
    for split, (dataset, version) in CORPORA.items():
        rng = random.Random(f"{recipe['seed']}:{split}")
        recordings = load_corpus(dataset, version, catalog, roots)
        dropped = []
        if "windows" in recipe:
            held = held_out_speakers(dataset, version, catalog, roots)
            dropped = sorted(r for r, e in recordings.items() if {u[2] for u in e["sups"]} & held)
            for rid in dropped:
                del recordings[rid]
            quotas = {"windows": recipe["windows"][split]}
            plans = {key.rsplit("-", 1)[1]: items
                     for key, items in real.plan_overlap_samples(split, quotas, recordings, rng, "train").items()}
        else:
            plans = plan(recordings, rng, args.per_bucket)
        audio = {}
        records = make_records(split, split, plans, recordings, rng, audio, recipe["version"],
                               window_utts="windows" in recipe)
        with gzip.open(args.output_dir / f"records_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        with gzip.open(args.output_dir / f"audio_index_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in sorted(audio.values(), key=lambda r: r["cut_id"]):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        report[split] = {"records": len(records), "windows": {b: len(v) for b, v in plans.items()},
                         "dropped_recordings": dropped,
                         "recordings": len(audio), "same_recording_negatives": Counter(
                             r["labels"].get("absent_source") for r in records if not r["labels"]["target_present"])}
        print(split, report[split], flush=True)
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
