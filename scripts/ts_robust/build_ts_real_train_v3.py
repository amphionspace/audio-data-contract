#!/usr/bin/env python3
"""ts_real_train v3-20261020: real windows where one person talks alone, and AliMeeting near-field views.

Two gaps of v1 / v2 that the benchmark exposes, both filled with records over spans of the original
recordings (nothing is copied, mixed or re-encoded):

* ``emilia2_1spk`` - crawled web conversations (``emilia2_zh_dialogue_diarize``, MOSS pseudo labels whose
  windows already passed the Qwen3-ASR text check and the Emilia2 speaker check) cut into 8-22 s runs of whole
  utterances in which exactly one person talks. Each window is a pair on the same audio: the target is that
  person (enrolled with another utterance of theirs outside the window) or absent (another speaker of the same
  diarization window is enrolled). This is the "only somebody else is talking" case (benchmark
  real-emilia2-1spk-neg). Speaker labels of web audio can be wrong (one voice actor split into roles, two
  people merged), so every pair is checked with ERes2NetV2 speaker embeddings and dropped when the enrolled
  voice of the negative sounds like the window's speaker or the positive's does not (``--qc``).
  Recordings of the benchmark's held-out Emilia2 videos and the speaker-merge windows are left out.
* ``alimeeting_en_mn`` / ``alimeeting_en_mf`` - AliMeeting train windows (same windowing as v1, far-field
  human annotation) seen through the headsets: the enrollment is always cut from the enrolled speaker's
  headset; the mixture is the headset of one speaker of the window (``en_mn``: the device is near somebody
  talking) or far-field channel 0 (``en_mf``: a phone registration used in the meeting room). In ``en_mn`` the
  target of the positive is the headset's wearer. Near and far files of AliMeeting train are aligned to within
  0.07 s (cross-correlation spot check), below what the windows or the 3-6 s enrollments can see.

    python build_ts_real_train_v3.py --output-dir DIR [--stats-only] [--qc QC.json]
"""

import argparse
import gzip
import hashlib
import importlib.util
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf

from audio_data_contract import load_catalog, resolve_artifact, resolve_split

_spec = importlib.util.spec_from_file_location("ts_real_train_build", Path(__file__).with_name("build_ts_real_train.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
real = base.real

DATA = Path("/workspace/data")
ROOT_ALIAS = "aidc_data"
DATASET_ID = "ts_real_train"
VERSION = "v3-20261020"
SEED = 20261020
EMILIA2 = ("emilia2_zh_dialogue_diarize", "moss-transcribe-diarize-0.9B", "train_120s")
# Videos whose windows are in the benchmark (ts_asr_real v2); a video's dialogue files share speakers, so the
# whole video is left out, not only the listed dialogue file.
HELDOUT = DATA / "datasets/ts_asr_real/source/v2-20261013/excluded-recordings.txt"
EMILIA2_WINDOWS = 15000  # pairs; one per diarization window at most
ALIMEETING = ("alimeeting_sdm", "icefall-20260908")
NEAR_DIR = DATA / "datasets/alimeeting/source/openslr-119-local-20260826/Train_Ali_near/audio_dir"
END_MARGIN = 0.05  # seconds kept clear of a file's end (headsets end a little before the far-field array)


def file_row(relative, sample_rate, channels, num_frames):
    cut = hashlib.sha256(f"{ROOT_ALIAS}:{relative}".encode()).hexdigest()
    return {"cut_id": cut, "root_alias": ROOT_ALIAS, "relative_path": relative, "sample_rate": sample_rate,
            "channels": channels, "num_frames": num_frames, "duration": round(num_frames / sample_rate, 3)}


# --- Emilia2 ------------------------------------------------------------------------------------------


def load_emilia2(catalog, roots):
    """{window_id: entry} of the diarization windows, times relative to the window start."""
    (records,) = resolve_split(catalog, *EMILIA2, "records", roots)
    files = {}
    with gzip.open(resolve_artifact(catalog, EMILIA2[0], EMILIA2[1], "train-audio-index", roots), "rt") as stream:
        for row in map(json.loads, stream):
            files[row["cut_id"]] = row
    merged = set(resolve_artifact(catalog, EMILIA2[0], EMILIA2[1], "train_120s-speaker-merge-excluded-records",
                                  roots).read_text().split())
    held = {line.split("_dlg_")[0] for line in HELDOUT.read_text().split()}
    entries, dropped = {}, Counter()
    with gzip.open(records, "rt", encoding="utf-8") as stream:
        for r in map(json.loads, stream):
            ref = r["audio_slots"][0]["ref"]
            if r["id"] in merged:
                dropped["speaker_merge"] += 1
                continue
            if ref["cut_id"].split("_dlg_")[0] in held:
                dropped["heldout_video"] += 1
                continue
            row = files[ref["cut_id"]]
            # MOSS end times may run past the audio; the window ends where the file does.
            duration = min(ref["duration"], row["duration"] - ref["start"] - END_MARGIN)
            entry = {"cut_id": ref["cut_id"], "offset": ref["start"], "duration": duration, "file": row,
                     "sups": [(t["start"], t["end"], f"{r['id']}:{t['speaker']}", "".join(t["text"].split()))
                              for t in r["metadata"]["turns"] if t["text"].strip() and t["end"] > t["start"]]}
            if entry["sups"]:
                real.finish_entry(entry)
                entries[r["id"]] = entry
    return entries, dropped


def plan_emilia2(entries, rng, quota):
    """At most one single-speaker window per diarization window, paired with an absent speaker of it."""
    plans, why = [], Counter()
    ids = sorted(entries)
    rng.shuffle(ids)
    for wid in ids:
        if len(plans) >= quota:
            break
        rec = entries[wid]
        windows = []
        for window in real.candidate_windows(rec, rng):
            present = real.speaker_seconds(window["utts"])
            if len(present) == 1:
                windows.append((window, next(iter(present))))
        if not windows:
            why["no_single_speaker_window"] += 1
            continue
        rng.shuffle(windows)
        for window, target in windows:
            if real.speaker_seconds(window["utts"])[target] < real.MIN_TARGET_SECONDS:
                continue
            if not real.eligible_enrollments(rec, target, window["lo"], window["hi"]):
                continue
            others = [s for s in sorted({u[2] for u in rec["sups"]} - {target})
                      if real.eligible_enrollments(rec, s, window["lo"], window["hi"])]
            if not others:
                continue
            plans.append({"entry": wid, "window": window, "target": target, "absent": rng.choice(others)})
            break
        else:
            why["no_enrollment"] += 1
    return plans, why


def emilia2_records(plans, entries, rng, audio):
    split, records = "emilia2_1spk", []
    for number, plan in enumerate(plans):
        rec, window, target = entries[plan["entry"]], plan["window"], plan["target"]
        row = file_row(rec["file"]["relative_path"], rec["file"]["sample_rate"], rec["file"]["channels"],
                       rec["file"]["num_frames"])
        row = audio.setdefault(row["cut_id"], row)  # keyed like the refs, as write() looks them up

        def ref(start, end, row=row, rec=rec):
            return {"dataset_id": DATASET_ID, "version": VERSION, "split": split, "cut_id": row["cut_id"],
                    "channel": 0, "start": round(rec["offset"] + start, 3), "duration": round(end - start, 3)}

        target_utts = sorted(u for u in window["utts"] if u[2] == target)
        span = ref(window["lo"], window["hi"])
        common = {"corpus": "emilia2", "recording": rec["cut_id"], "bucket": "1spk", "speakers_in_window": 1,
                  "duration_s": round(window["hi"] - window["lo"], 3), "annotation": "moss", "pair": number}
        for kind, who in (("pos", target), ("neg", plan["absent"])):
            s, e, _ = rng.choice(real.eligible_enrollments(rec, who, window["lo"], window["hi"]))
            present = kind == "pos"
            labels = {**common, "target_present": present, "n_interferers": 0 if present else 1}
            if present:
                labels["target_seconds"] = round(sum(b - a for a, b, _, _ in target_utts), 2)
            else:
                labels["absent_source"] = "same_recording"
            records.append({
                "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{split}:{kind}:{number:07d}",
                "task": "ts_asr", "target": "".join(u[3] for u in target_utts) if present else "", "language": "zh",
                "labels": labels, "hotwords": [],
                "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": ref(s, min(e, s + real.ENROLL_MAX))},
                                {"name": "mixture", "purpose": "mixture", "ref": span}],
                "metadata": {"source_group": f"emilia2:{rec['cut_id']}:{who}", "target_speaker": f"emilia2:{who}",
                             "window_start_s": round(rec["offset"] + window["lo"], 3), "source_record": plan["entry"]}})
    return records


# --- AliMeeting headsets ------------------------------------------------------------------------------


def headsets():
    """{(recording, speaker): (row, duration)} of the AliMeeting train headset files."""
    out = {}
    for path in sorted(NEAR_DIR.glob("*.wav")):
        parts = path.stem.split("_")  # R0003_M0046_F_SPK0093
        info = sf.info(str(path))
        row = file_row(path.relative_to(DATA).as_posix(), info.samplerate, info.channels, info.frames)
        out[(f"{parts[0]}_{parts[1]}", parts[3].removeprefix("SPK"))] = row
    return out


def fits(row, start, end):
    return end <= row["duration"] - END_MARGIN and start >= 0


def plan_alimeeting(recordings, near, rng, mixture):
    """Paired plans per speaker-count bucket; ``mixture`` is "near" (a headset of the window) or "far"."""
    plans, why = defaultdict(list), Counter()

    def enrollable(r, speaker, w_lo, w_hi):
        """Enrollment utterances of ``speaker`` outside the window that their headset file covers."""
        row = near.get((r, speaker))
        return row is not None and [c for c in real.eligible_enrollments(recordings[r], speaker, w_lo, w_hi)
                                    if fits(row, c[0], min(c[1], c[0] + real.ENROLL_MAX))]

    anywhere = [(r, s) for r, o in sorted(recordings.items()) for s in sorted({u[2] for u in o["sups"]})
                if enrollable(r, s, -1e9, -1e9)]
    for rid, rec in sorted(recordings.items()):
        for window in real.candidate_windows(rec, rng):
            present = real.speaker_seconds(window["utts"])
            bucket = next(b for b, (lo, hi) in base.BUCKETS.items() if lo <= len(present) <= hi)
            lo, hi = window["lo"], window["hi"]
            usable = [s for s, sec in present.items() if sec >= real.MIN_TARGET_SECONDS and enrollable(rid, s, lo, hi)]
            if mixture == "near":
                usable = [s for s in usable if fits(near[(rid, s)], lo, hi)]
            if not usable:
                why["no_target"] += 1
                continue
            target = rng.choice(sorted(usable))
            absent = [s for s in sorted({u[2] for u in rec["sups"]} - set(present)) if enrollable(rid, s, lo, hi)]
            if absent:
                other = (rid, rng.choice(absent), "same_recording")
            else:  # another meeting, as in v1 and the benchmark
                r, s = rng.choice([p for p in anywhere if p[0] != rid])
                other = (r, s, "other_recording")
            window.update(recording=rid, present=present, speakers=len(present))
            plans[bucket].append({"window": window, "target": target, "absent": other, "enrollable": enrollable})
    return plans, why


def alimeeting_records(split, plans, recordings, near, rng, audio, mixture):
    records, number = [], 0
    for bucket, items in sorted(plans.items()):
        for item in items:
            window, target = item["window"], item["target"]
            rid = window["recording"]
            mix_row = near[(rid, target)] if mixture == "near" else base.index_row(recordings, rid)
            audio.setdefault(mix_row["cut_id"], mix_row)

            def ref(row, start, end):
                audio.setdefault(row["cut_id"], row)
                return {"dataset_id": DATASET_ID, "version": VERSION, "split": split, "cut_id": row["cut_id"],
                        "channel": 0, "start": round(start, 3), "duration": round(end - start, 3)}

            span = ref(mix_row, window["lo"], window["hi"])
            target_utts = sorted(u for u in window["utts"] if u[2] == target)
            other, speaker, source = item["absent"]
            common = {"corpus": "alimeeting", "recording": rid, "bucket": bucket,
                      "speakers_in_window": window["speakers"], "duration_s": round(window["hi"] - window["lo"], 3),
                      "annotation": "human", "pair": number, "enroll_domain": "near", "mix_domain": mixture}
            for kind, who, r, w_lo, w_hi in (("pos", target, rid, window["lo"], window["hi"]),
                                              ("neg", speaker, other, *((-1e9, -1e9) if source == "other_recording"
                                                                        else (window["lo"], window["hi"])))):
                s, e, _ = rng.choice(item["enrollable"](r, who, w_lo, w_hi))
                present = kind == "pos"
                labels = {**common, "target_present": present,
                          "n_interferers": window["speakers"] - (1 if present else 0)}
                if present:
                    labels["target_overlap_ratio"] = round(real.overlap_ratio(target_utts, window["utts"]), 3)
                    labels["target_seconds"] = round(sum(b - a for a, b, _, _ in target_utts), 2)
                else:
                    labels["absent_source"] = source
                records.append({
                    "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{split}:{kind}:{number:07d}",
                    "task": "ts_asr", "target": "".join(u[3] for u in target_utts) if present else "",
                    "language": "zh", "labels": labels, "hotwords": [],
                    "audio_slots": [{"name": "enrollment", "purpose": "enrollment",
                                     "ref": ref(near[(r, who)], s, min(e, s + real.ENROLL_MAX))},
                                    {"name": "mixture", "purpose": "mixture", "ref": span}],
                    "metadata": {"source_group": f"alimeeting:{rid}:{who}", "target_speaker": f"alimeeting:{who}",
                                 "window_start_s": round(window["lo"], 3),
                                 **({"mixture_headset": f"alimeeting:{target}"} if mixture == "near" else {})}})
            number += 1
    return records


# --- speaker check of the Emilia2 pairs ---------------------------------------------------------------


def qc_filter(records, qc):
    """Drop Emilia2 pairs whose embeddings contradict the labels; thresholds come from the pairs themselves.

    ``qc`` maps a pair number to (cosine of the positive's enrollment with the window, same for the
    negative). A negative as similar as a typical same-speaker pair (at or above the 10th percentile of the
    positives) is likely the window's own speaker under another label; a positive no more similar than a
    typical different-speaker pair (at or below the 90th percentile of the negatives) is likely mislabeled.
    """
    pos = sorted(v[0] for v in qc.values())
    neg = sorted(v[1] for v in qc.values())
    same_floor, diff_ceiling = pos[len(pos) // 10], neg[len(neg) * 9 // 10]
    bad = {int(k) for k, (p, n) in qc.items() if n >= same_floor or p <= diff_ceiling}
    kept = [r for r in records if r["labels"]["pair"] not in bad]
    for r in kept:
        p, n = qc[str(r["labels"]["pair"])]
        r["labels"]["speaker_cosine"] = round(p if r["labels"]["target_present"] else n, 3)
    return kept, {"pairs": len(qc), "dropped_pairs": len(bad), "negative_too_similar": sum(n >= same_floor for _, n in qc.values()),
                  "positive_too_different": sum(p <= diff_ceiling for p, _ in qc.values()),
                  "same_floor": round(same_floor, 3), "diff_ceiling": round(diff_ceiling, 3)}


def write(directory, split, records, audio):
    with gzip.open(directory / f"records_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in records:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    used = {s["ref"]["cut_id"] for r in records for s in r["audio_slots"]}
    with gzip.open(directory / f"audio_index_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in sorted((audio[c] for c in used), key=lambda r: r["cut_id"]):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stats-only", action="store_true")
    parser.add_argument("--qc", type=Path, help="pair cosines from qc_ts_real_train_v3.py for the Emilia2 split")
    args = parser.parse_args()
    roots = {k: Path(v) for k, v in json.loads(Path("/workspace/data/registry/roots.json").read_text()).items()}
    catalog = load_catalog("/workspace/data/registry/catalog")
    report = {}

    entries, dropped = load_emilia2(catalog, roots)
    plans, why = plan_emilia2(entries, random.Random(f"{SEED}:emilia2"), EMILIA2_WINDOWS)
    report["emilia2_1spk"] = {"diarization_windows": len(entries), "left_out": dict(dropped), "pairs": len(plans),
                              "skipped": dict(why)}
    print("emilia2_1spk", report["emilia2_1spk"], flush=True)

    recordings = base.load_corpus(*ALIMEETING, catalog, roots)
    near = headsets()
    alimeeting = {}
    for split, mixture in (("alimeeting_en_mn", "near"), ("alimeeting_en_mf", "far")):
        rng = random.Random(f"{SEED}:{split}")
        alimeeting[split] = (plan_alimeeting(recordings, near, rng, mixture), rng, mixture)
        (split_plans, skipped) = alimeeting[split][0]
        report[split] = {"windows": {b: len(v) for b, v in sorted(split_plans.items())}, "skipped": dict(skipped),
                         "other_recording_negatives": sum(p["absent"][2] == "other_recording"
                                                          for v in split_plans.values() for p in v)}
        print(split, report[split], flush=True)
    if args.stats_only:
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audio = {}
    records = emilia2_records(plans, entries, random.Random(f"{SEED}:emilia2:records"), audio)
    if args.qc:
        records, report["emilia2_1spk"]["speaker_check"] = qc_filter(records, json.loads(args.qc.read_text()))
    else:  # the plan the speaker check embeds
        (args.output_dir / "emilia2_1spk-unchecked.jsonl.gz").unlink(missing_ok=True)
        with gzip.open(args.output_dir / "emilia2_1spk-unchecked.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        with gzip.open(args.output_dir / "emilia2_1spk-unchecked-index.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in audio.values():
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("wrote the unchecked Emilia2 pairs; run qc_ts_real_train_v3.py, then pass --qc")
        return
    write(args.output_dir, "emilia2_1spk", records, audio)
    report["emilia2_1spk"]["records"] = len(records)
    for split, ((split_plans, _), _, mixture) in alimeeting.items():
        rows = alimeeting_records(split, split_plans, recordings, near, random.Random(f"{SEED}:{split}:records"),
                                  audio, mixture)
        write(args.output_dir, split, rows, audio)
        report[split]["records"] = len(rows)
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
