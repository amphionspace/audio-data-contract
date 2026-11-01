#!/usr/bin/env python3
"""ts_real_train en-v1-20261101: English real-meeting target-speaker windows from splits the benchmark does not use.

The English counterpart of v1 (``build_ts_real_train.py``). The English benchmark (``ts_real/build.py --recipe en``)
cuts its windows from the test / eval splits of AMI (single distant mic Array1-01), NOTSOFAR-1 (one single-channel
device per meeting), CHiME-6, DiPCo (far-field device channel 1, timeline moved onto the far-field file) and ICSI
(official headset mix); this script cuts the same windows, with the same corpus readers (``ts_real/english.py``), from
the other splits and writes them as records over spans of the long recordings: nothing is copied, mixed or re-encoded
(except the ICSI headset mixes, which the mirror stores inside parquet shards; they are written once as WAV to
``--audio-dir``).

Windows are v1's: 8-22 s runs of whole utterances, every usable one (no quota), speaker-count buckets 1spk / 2spk /
3plus (``labels.bucket``). Each window is a pair on the same audio: a positive (a speaker with >= 1 s in the window
whose utterances there are all transcribed and hold a word beyond fillers, enrolled with one other utterance of theirs
from outside the window: 3-6 s, others overlap <= 20% of it and talk < 0.3 s in its first 5 s) and a negative (a
speaker of the same recording who does not speak in the window; when there is none, a speaker of another recording
who does not speak in it either - the English corpora reuse speaker IDs across meetings; ``labels.absent_source``).
Every slot names ``channel: 0`` of a single-channel file. Records carry ``metadata.window_utts`` (every annotated
utterance of the window relative to its start, including speech without a transcript, marked ``excluded``) and
``metadata.target_speaker``, as v2 does, so ``add_window_utts.py`` derives ``-utts`` with the ``keep`` family.

Sources (one split per corpus) and what stays out:

* ``ami``: ami_sdm train. The dev and test meetings stay out (the benchmark uses test).
* ``notsofar``: notsofar_sdm train and dev (240825.1_train, 240825.1_dev1). The eval set (the benchmark) stays out.
* ``dipco``: dev sessions (S02, S04, S05, S09, S10). Eval (the benchmark) stays out.
* ``icsi``: lhotse train meetings. The test (Bmr013, Bmr018, Bro021: the benchmark) and dev (Bmr021, Bns001) meetings
  stay out.

CHiME-6 is not among them: the benchmark cuts each window from the reference array of the room everyone in it talks in,
and only the dev / eval transcripts name the room (``location``, ``ref``); the train transcripts do not, so a train
window cannot be tied to the array that hears its speakers (``chime6@turn-taking-20261014`` already trains on CHiME-6
train through its first far-field channel).

A recording with a speaker of a held-out split is dropped (ICSI keeps only the Bed meetings this way), and the build
stops when a held-out meeting is among the sources; ``report.json`` (``heldout``) lists both checks.

Every enrollment passes the English benchmark's voice check (``ts_real/voice_check.py``, WeSpeaker ECAPA-TDNN512-LM
through ``embed_worker.py``): its embedding is closer to its speaker's profile in that recording (their other clean
utterances) than to every other speaker's, on the close-talk sum where the corpus has headsets (NOTSOFAR, DiPCo),
else on the channel the records read. A failing utterance is replaced by another eligible one (``enrollment_replaced``);
a pair whose positive or negative finds none is dropped. The v3 rule (drop pairs by percentiles of window-vs-enrollment
cosines) does not fit here: on far-field multi-speaker windows the two cosine distributions overlap (AMI smoke: positive
10th percentile 0.28, negative 90th percentile 0.31), and it would drop 27% (AMI) and 46% (NOTSOFAR) of the pairs, far
more than the label errors of human-annotated meetings, taking hard (close-sounding) negatives with them.

    python build_ts_real_train_en.py --output-dir O --embed-python <python with onnxruntime> [--limit N]
    python build_ts_real_train_en.py --output-dir O --stats-only
"""

import argparse
import gzip
import hashlib
import importlib.util
import json
import random
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf

from audio_data_contract import load_catalog, resolve_split

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ts_real_build_en", HERE.parent / "ts_real/build.py")
real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real)  # ts_real/build.py: loaders, windows, enrollment rules, voice-check views
english = real._english()  # ts_real/english.py

DATA = Path("/workspace/data")
ROOT_ALIAS = "aidc_data"
DATASET_ID = "ts_real_train"
VERSION = "en-v1-20261101"
SEED = 20261101
UNLIMITED = 10 ** 9  # plan_samples takes a window quota; v1 keeps every usable window
ICSI_TEST = ("Bmr013", "Bmr018", "Bro021")  # lhotse test partition, the benchmark's ICSI meetings
ICSI_DEV = ("Bmr021", "Bns001")  # lhotse dev partition
CORPORA = {
    "ami": {"dataset": "ami_sdm", "version": "icefall-20260908", "splits": ["train"], "heldout": ["dev", "test"]},
    "notsofar": {"kind": "notsofar", "dataset": "notsofar_sdm", "version": "icefall-20260908", "splits": ["train", "dev"],
                 "heldout": ["test"]},
    "dipco": {"kind": "dipco", "dataset": "dipco", "version": "zenodo-8122551-20261023", "splits": ["dev"],
              "heldout": ["eval"]},
    # The mirror has one split ("test") holding all 75 meetings; the recipe picks meetings.
    "icsi": {"kind": "icsi", "dataset": "icsi", "version": "modelscope-argmaxinc-20261025", "splits": ["test"],
             "heldout_meetings": [*ICSI_TEST, *ICSI_DEV]},
}
# The benchmark's meetings and the dev meetings named in the data plan; a source recording of one stops the build.
EVAL_MEETINGS = {
    "ami": ("ES2004", "IS1009", "TS3003", "EN2002"),
    "dipco": ("S01", "S03", "S06", "S07", "S08"),
    "icsi": (*ICSI_TEST, *ICSI_DEV),
}


def meeting_of(name, recording):
    """Meeting of a recording ID (NOTSOFAR names a recording ``MTG_<n>_<device>``)."""
    return "_".join(recording.split("_")[:2]) if name == "notsofar" else recording


# --- sources --------------------------------------------------------------------------------------------


def icsi_participants(catalog, roots, split):
    """{meeting: {participant}} from the MRT transcripts."""
    transcripts = next(p for p in resolve_split(catalog, "icsi", CORPORA["icsi"]["version"], split, "transcriptions", roots)
                       if (p / "transcripts").is_dir())
    out = {}
    for path in sorted((transcripts / "transcripts").glob("B*.mrt")):
        root = ET.parse(path).getroot()
        out[path.stem] = {s.get("Participant") for s in root.iter("Segment") if s.get("Participant")}
    return out


def disjoint_meetings(participants, heldout):
    """(kept, dropped) meetings: neither held out nor sharing a participant with a held-out meeting."""
    held = set().union(*(participants[m] for m in heldout))
    candidates = sorted(m for m in participants if m not in heldout)
    kept = [m for m in candidates if not participants[m] & held]
    return kept, sorted(set(candidates) - set(kept))


def heldout_sets(name, corpus, catalog, roots):
    """(meetings, speakers) of the corpus's held-out splits, read with the benchmark's readers."""
    kind = corpus.get("kind")
    meetings, speakers = set(), set()
    if kind == "icsi":
        participants = icsi_participants(catalog, roots, corpus["splits"][0])
        for m in corpus["heldout_meetings"]:
            meetings.add(m)
            speakers |= participants[m]
        return meetings, speakers
    for split in corpus["heldout"]:
        spec = {**corpus, "split": split, "language": "en"}
        if kind is None:
            entries = real.load_corpus(spec, catalog, roots)
        elif kind == "notsofar":
            entries = english.load_notsofar(spec, catalog, roots, random.Random(0))
        else:
            entries = english.load_dipco(spec, catalog, roots, random.Random(0))
        for rid, entry in entries.items():
            meetings.add(meeting_of(name, rid))
            speakers |= {u[2] for u in entry["sups"]}
    return meetings, speakers


def write_icsi_audio(recordings, directory):
    """Write each ICSI headset mix (decoded by ``english.load_icsi``) as 16-bit WAV once; entries then point at it.
    A later run with the same ``--audio-dir`` reads the WAVs instead of decoding the parquet shards again."""
    directory.mkdir(parents=True, exist_ok=True)
    for meeting, entry in recordings.items():
        path = directory / f"{meeting}.interaction.wav"
        samples = entry.pop("samples")
        if not path.exists() or sf.info(str(path)).frames != len(samples):
            partial = path.with_suffix(".partial.wav")
            sf.write(str(partial), samples, english.SR, subtype="PCM_16")
            partial.rename(path)
        entry["path"] = str(path)


def load_source(name, corpus, catalog, roots, audio_dir, report):
    """{recording: entry} over the corpus's source splits, recordings with held-out speakers dropped."""
    meetings, held_speakers = heldout_sets(name, corpus, catalog, roots)
    check = {"heldout_meetings": len(meetings), "heldout_speakers": len(held_speakers)}
    recordings = {}
    for split in corpus["splits"]:
        spec = {**corpus, "split": split, "language": "en", "enrollmix": False}
        if corpus.get("kind") == "icsi":
            spec["meetings"], check["dropped_meetings_sharing_speakers"] = disjoint_meetings(
                icsi_participants(catalog, roots, split), corpus["heldout_meetings"])
        written = audio_dir and spec.get("meetings") and [audio_dir / f"{m}.interaction.wav" for m in spec["meetings"]]
        if written and all(path.exists() for path in written):  # an earlier run wrote the headset mixes
            loaded = english.load_icsi(spec, catalog, roots, {
                path.name.removesuffix(".interaction.wav"): sf.read(str(path), dtype="float32")[0] for path in written})
            for entry in loaded.values():  # as real.load_recordings does
                entry.update(language="en", enrollmix=False)
                real.finish_entry(entry)
        else:
            loaded = real.load_recordings(name, spec, catalog, roots, f"{SEED}:{split}", report)
        if overlap := set(loaded) & set(recordings):
            raise ValueError(f"{name}: recordings in two splits {sorted(overlap)[:5]}")
        recordings.update(loaded)
    if corpus.get("kind") == "icsi" and audio_dir is not None:  # None: --stats-only, nothing is written
        write_icsi_audio(recordings, audio_dir)
    named = EVAL_MEETINGS.get(name, ())
    leaked = sorted(r for r in recordings
                    if meeting_of(name, r) in meetings or any(meeting_of(name, r).startswith(m) for m in named))
    if leaked:
        raise ValueError(f"{name}: held-out meetings among the sources: {leaked}")
    dropped = sorted(r for r, e in recordings.items() if {u[2] for u in e["sups"]} & held_speakers)
    for rid in dropped:
        del recordings[rid]
    check.update(
        source_recordings=len(recordings), dropped_recordings_with_heldout_speakers=dropped,
        meeting_overlap=sorted({meeting_of(name, r) for r in recordings} & meetings),
        speaker_overlap=sorted({u[2] for e in recordings.values() for u in e["sups"]} & held_speakers),
        source_speakers=len({u[2] for e in recordings.values() for u in e["sups"]}))
    report.setdefault("heldout", {})[name] = check
    return recordings


# --- records --------------------------------------------------------------------------------------------

_ROWS = {}


def file_row(path):
    """Audio index row of a file under /workspace/data (cut ID as in v1 / v3)."""
    path = Path(path)
    if path not in _ROWS:
        relative = path.relative_to(DATA).as_posix()
        info = sf.info(str(path))
        if info.channels != 1 or info.samplerate != english.SR:
            raise ValueError(f"{path}: expected 16 kHz mono, got {info.samplerate} Hz x {info.channels}")
        _ROWS[path] = {"cut_id": hashlib.sha256(f"{ROOT_ALIAS}:{relative}".encode()).hexdigest(),
                       "root_alias": ROOT_ALIAS, "relative_path": relative, "sample_rate": info.samplerate,
                       "channels": info.channels, "num_frames": info.frames,
                       "duration": round(info.frames / info.samplerate, 3)}
    return _ROWS[path]


def window_utterances(name, entry, window):
    excluded = entry.get("excluded", {})
    return [{"speaker": f"{name}:{spk}", "start": round(s - window["lo"], 3), "duration": round(e - s, 3), "text": text,
             **({"excluded": excluded[(s, e, spk)]} if (s, e, spk) in excluded else {})}
            for s, e, spk, text in sorted(window["utts"])]


def checked_enrollment(checker, recordings, recording, speaker, lo, hi, rng, key):
    """(span, verdict, failed verdict or None) of an enrollment utterance of ``speaker`` outside [lo, hi] that passes
    the voice check: v1's random pick, else up to ``VOICE_ATTEMPTS`` other eligible utterances; (None, None, first
    failed verdict) if none passes."""
    candidates = real.eligible_enrollments(recordings[recording], speaker, lo, hi)
    first = rng.choice(candidates)
    others = [c for c in candidates if c != first]
    random.Random(f"{key}:voice-check").shuffle(others)
    failed = None
    for s, e, _ in [first, *others[:real.VOICE_ATTEMPTS]]:
        span = (s, min(e, s + real.ENROLL_MAX))
        verdict = checker.check(recordings, recording, speaker, [span])
        if verdict["passed"]:
            return span, verdict, failed
        failed = failed or verdict
    return None, None, failed


def make_records(split, plans, recordings, rng, audio, checker, stats):
    """Paired records (positive at even lines), as v1's ``make_records`` with English text and voice-checked
    enrollments; a pair whose positive or negative has no enrollment that passes is dropped."""
    records, number = [], 0
    for bucket, items in sorted(plans.items()):
        for item in items:
            window, target = item["window"], item["target"]
            rid, lo, hi = window["recording"], window["lo"], window["hi"]
            rec = recordings[rid]

            def ref(recording, start, end):
                row = file_row(recordings[recording]["path"])
                audio.setdefault(row["cut_id"], row)
                if end > row["duration"] or start < 0:
                    raise ValueError(f"{recording}: span {start}-{end} outside {row['relative_path']}")
                return {"dataset_id": DATASET_ID, "version": VERSION, "split": split, "cut_id": row["cut_id"],
                        "channel": 0, "start": round(start, 3), "duration": round(end - start, 3)}

            other, speaker, source = item["absent"]
            bounds = (-1e9, -1e9) if source == "other_recording" else (lo, hi)
            key = f"{split}:{rid}:{lo:.3f}"
            picked = {"pos": checked_enrollment(checker, recordings, rid, target, lo, hi, rng, f"{key}:pos"),
                      "neg": checked_enrollment(checker, recordings, other, speaker, *bounds, rng, f"{key}:neg")}
            for kind, (span, _, failed) in picked.items():
                if span is None:  # reason "no_profile": no clean >= 2 s utterance of the speaker to compare with
                    stats[f"{kind}/dropped/{failed.get('reason', 'closer_to_another_speaker')}"] += 1
                else:
                    stats[f"{kind}/{'replaced' if failed else 'passed'}"] += 1
            if any(span is None for span, _, _ in picked.values()):
                stats["pairs_dropped"] += 1
                continue
            target_utts = sorted(u for u in window["utts"] if u[2] == target)
            span = ref(rid, lo, hi)
            utts = window_utterances(split, rec, window)
            common = {"corpus": split, "recording": rid, "bucket": bucket, "speakers_in_window": window["speakers"],
                      "duration_s": round(hi - lo, 3), "annotation": "human", "pair": number}
            for kind, who, recording in (("pos", target, rid), ("neg", speaker, other)):
                (start, end), verdict, failed = picked[kind]
                present = kind == "pos"
                labels = {**common, "target_present": present,
                          "n_interferers": window["speakers"] - (1 if present else 0)}
                if present:
                    labels["target_overlap_ratio"] = round(real.overlap_ratio(target_utts, window["utts"]), 3)
                    labels["target_seconds"] = round(sum(e - s for s, e, _, _ in target_utts), 2)
                else:
                    labels["absent_source"] = source
                metadata = {"source_group": f"{split}:{rid}:{who}", "target_speaker": f"{split}:{who}",
                            "window_start_s": round(lo, 3), "mixture_source": rec["source"],
                            "enrollment_recording": recording, "enroll_voice_check": verdict}
                if failed:  # as ts_asr_real: the first utterance drawn sounded like someone else
                    metadata["enrollment_replaced"] = {"voice_check": failed}
                if "offset_s" in rec:
                    metadata["timeline_offset_s"] = rec["offset_s"]
                metadata["window_utts"] = utts
                records.append({
                    "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{split}:{kind}:{number:07d}",
                    "task": "ts_asr", "target": " ".join(u[3] for u in target_utts) if present else "",
                    "language": "en", "labels": labels, "hotwords": [],
                    "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": ref(recording, start, end)},
                                    {"name": "mixture", "purpose": "mixture", "ref": span}],
                    "metadata": metadata})
            number += 1
    return records


def summary(records):
    """Records and mixture hours per bucket and pos / neg."""
    out = defaultdict(lambda: {"records": 0, "hours": 0.0})
    for r in records:
        key = f"{r['labels']['bucket']}/{'pos' if r['labels']['target_present'] else 'neg'}"
        out[key]["records"] += 1
        out[key]["hours"] += r["audio_slots"][1]["ref"]["duration"] / 3600
    return {k: {"records": v["records"], "hours": round(v["hours"], 2)} for k, v in sorted(out.items())}


def write_jsonl(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def build(args):
    roots = {k: Path(v) for k, v in json.loads((DATA / "registry/roots.json").read_text()).items()}
    catalog = load_catalog(DATA / "registry/catalog")
    if not args.stats_only:
        if (args.output_dir / "report.json").exists():
            raise FileExistsError(f"{args.output_dir} already holds a version")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        voice = real._sibling("voice_check")
        checker = voice.VoiceCheck(voice.Embedder(args.embed_python, args.speaker_model, args.embed_threads),
                                   real.check_cut, real.ENROLL_CROP, real.ENROLL_MAX, real.check_view)
    report = {"version": VERSION, "limit_per_bucket": args.limit}
    for name in args.corpora:
        corpus = CORPORA[name]
        recordings = load_source(name, corpus, catalog, roots, None if args.stats_only else args.audio_dir, report)
        plans = real.plan_samples(name, {"windows": UNLIMITED, "language": "en"}, recordings,
                                  random.Random(f"{SEED}:{name}"))
        available = {key.rsplit("-", 1)[1]: len(items) for key, items in sorted(plans.items())}
        plans = {key.rsplit("-", 1)[1]: items[: args.limit] if args.limit else items for key, items in plans.items()}
        if args.stats_only:
            report.setdefault("corpora", {})[name] = {
                "recordings": len(recordings), "windows": {b: len(v) for b, v in sorted(plans.items())},
                "records": 2 * sum(len(v) for v in plans.values()),
                "window_hours": {b: round(sum(p["window"]["hi"] - p["window"]["lo"] for p in v) / 3600, 2)
                                 for b, v in sorted(plans.items())},
                "absent_source": dict(Counter(p["absent"][2] for v in plans.values() for p in v))}
            print(name, json.dumps(report["corpora"][name]), flush=True)
            continue
        audio, stats = {}, Counter()
        records = make_records(name, plans, recordings, random.Random(f"{SEED}:{name}:records"), audio, checker, stats)
        write_jsonl(args.output_dir / f"records_{name}.jsonl.gz", records)
        write_jsonl(args.output_dir / f"audio_index_{name}.jsonl.gz", sorted(audio.values(), key=lambda r: r["cut_id"]))
        report.setdefault("corpora", {})[name] = {
            "recordings": len(recordings), "windows_available": available,
            "windows_planned": {b: len(v) for b, v in sorted(plans.items())},
            "records": len(records), "by_bucket": summary(records), "voice_check": dict(sorted(stats.items())),
            "voice_check_audio": dict(Counter(r["metadata"]["enroll_voice_check"]["audio"] for r in records)),
            "absent_source": dict(Counter(r["labels"]["absent_source"] for r in records if not r["labels"]["target_present"])),
            "mixture_sources": dict(Counter(r["metadata"]["mixture_source"] for r in records[::2]))}
        print(name, json.dumps(report["corpora"][name], ensure_ascii=False), flush=True)
    if args.stats_only:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    else:
        checker.embed.close()
    (args.output_dir / ("stats-report.json" if args.stats_only else "report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True, help="the version directory (--stats-only: any)")
    parser.add_argument("--audio-dir", type=Path, default=DATA / f"datasets/{DATASET_ID}/source/{VERSION}/icsi",
                        help="where the ICSI headset mixes are written as WAV")
    parser.add_argument("--embed-python", type=Path, help="Python with onnxruntime and torchaudio (embed_worker.py)")
    parser.add_argument("--speaker-model", type=Path, default=Path(real.SPEAKER_MODEL))
    parser.add_argument("--embed-threads", type=int, default=8)
    parser.add_argument("--limit", type=int, help="windows per bucket and corpus (smoke runs)")
    parser.add_argument("--stats-only", action="store_true", help="plan every corpus and report counts; write no records")
    parser.add_argument("--corpora", nargs="+", choices=sorted(CORPORA), default=list(CORPORA))
    args = parser.parse_args()
    if not args.stats_only and not args.embed_python:
        parser.error("the voice check needs --embed-python")
    build(args)


if __name__ == "__main__":
    main()
