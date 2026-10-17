#!/usr/bin/env python3
"""Build the v2 pool of single-speaker utterances used as online TS-ASR interferers.

v1 held 181 h from four sources and had no cap per speaker. v2 adds speaker-labelled
corpora (KeSpeech, Common Voice), caps the number of utterances per speaker or per
source video, and takes WenetSpeech / GigaSpeech segments straight from their long
recordings by offset (no copies of the audio are written).

Output is a registrable dataset version (audio-data-contract records + audio_index):
  records_{zh,en}.jsonl.gz      one AudioRecord per clip; the primary slot names the source
                                file and, for segments, start and duration. metadata holds
                                the quality columns loudness_dbfs, clip_ratio, voiced_ratio
                                (absent for Emilia2, which is not measured) and, for real
                                speaker labels, a dataset-prefixed speaker.
  audio_index_{zh,en}.jsonl.gz  one row per source file: where it is and how long.
  report.json                   counts, hours, groups and what the quality gates dropped.

Not used on purpose: LibriSpeech and AISHELL-2. The LibriMix targets are LibriSpeech
speakers and the AISHELLMix targets are all AISHELL-2 speakers, so those corpora would
put a target's own voice into the interference.

    python build_interference_pool_v2.py --output-dir DIR [--scale 0.01] [--workers 12]
"""

import argparse
import gzip
import json
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
HELD_OUT_MEDIA = "/workspace/data/datasets/ts_asr_real/source/v2-20261013/excluded-media-emilia2_short.txt"
DATASET_ID, VERSION = "ts_interference_pool", "v2-20261016"
TASK = "ts_asr_interference"
SEED = 20261016
SAMPLE_RATE = 16000
MIN_SECONDS, MAX_SECONDS = 1.0, 15.0
# Segments are cut from podcasts and videos: too short ones are mostly fragments.
SEGMENT_MIN_SECONDS = 2.0
# Quality gates on the decoded clip. Only voiced_ratio matters for an interferer: mixing sets the
# level from the active samples, so a clip that is mostly noise or music would be turned up into a
# wall of noise. Loudness only needs a loose floor, and a clipped voice is still a real voice, so
# clip_ratio is recorded but not gated.
MIN_LOUDNESS_DBFS = -50.0
MIN_VOICED_RATIO = 0.5
VOICED_FRAME_DBFS = -50.0
# Over-draw candidates because the gates drop some.
OVERDRAW = 1.2

# kind: recordings = one file per utterance, speaker from supervisions;
#       audio_index = Emilia2 short files, grouped by source video directory;
#       segments = supervisions taken from long recordings by offset.
# speaker: the group is a real speaker label (not only valid inside one recording).
# measure: decode every clip for the quality columns. Emilia2 is already filtered upstream and is
#          the slowest to decode (44.1 kHz stereo m4a), so its quality columns stay empty.
# cap = most utterances kept per group (speaker, video or recording).
SOURCES = [
    {"language": "zh", "kind": "audio_index", "dataset": "emilia2_short", "version": "short-20261014", "split": "train_zh", "count": 150000, "cap": 15, "speaker": False, "measure": False},
    {"language": "zh", "kind": "recordings", "dataset": "kespeech", "version": "legacy-20260804", "split": "train", "count": 90000, "cap": 40, "speaker": True, "measure": True},
    {"language": "zh", "kind": "segments", "dataset": "wenetspeech_youtube", "version": "l-20261014", "split": "train", "count": 40000, "cap": 10, "speaker": False, "measure": True},
    {"language": "zh", "kind": "segments", "dataset": "wenetspeech_podcast", "version": "l-20261014", "split": "train", "count": 40000, "cap": 10, "speaker": False, "measure": True},
    {"language": "en", "kind": "audio_index", "dataset": "emilia2_short", "version": "short-20261014", "split": "train_en", "count": 100000, "cap": 15, "speaker": False, "measure": False},
    {"language": "en", "kind": "recordings", "dataset": "common_voice_en", "version": "legacy-20260804", "split": "train", "count": 50000, "cap": 20, "speaker": True, "measure": True},
    {"language": "en", "kind": "segments", "dataset": "gigaspeech", "version": "legacy-20260804", "split": "train", "count": 50000, "cap": 10, "speaker": False, "measure": True},
]


def lines(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        yield from (json.loads(line) for line in stream)


def candidate(source, clip_id, file_id, path, rate, frames, duration, channels, group, start=None, span=None):
    """One usable clip: the file it lives in and, for segments, the span inside it."""
    return {"id": f"{source['dataset']}:{clip_id}", "file": f"{source['dataset']}:{file_id}",
            "path": path, "rate": rate, "frames": frames, "duration": duration, "channels": channels,
            "group": group, "start": start, "span": span}


def emilia_candidates(catalog, roots, source, held_out):
    index = resolve_split(catalog, source["dataset"], source["version"], source["split"], "audio_index", roots)
    rows, resolved_dirs = [], {}
    for path in index:
        for row in lines(path):
            if not MIN_SECONDS <= row["duration"] <= MAX_SECONDS:
                continue
            # Resolving each of millions of paths costs ~1 ms on quarkfs; the files of a
            # directory share one resolution.
            location = Path(roots[row["root_alias"]]) / row["relative_path"]
            if location.parent not in resolved_dirs:
                resolved_dirs[location.parent] = location.parent.resolve()
            if str(resolved_dirs[location.parent] / location.name) in held_out:
                continue
            rows.append(candidate(source, row["cut_id"], row["cut_id"], str(location), row["sample_rate"],
                                  row["num_frames"], row["duration"], row["channels"],
                                  f"{source['dataset']}:{location.parent.name}"))
    return rows


def utterance_candidates(catalog, roots, source):
    speakers = {}
    for path in resolve_split(catalog, source["dataset"], source["version"], source["split"], "supervisions", roots):
        for sup in lines(path):
            speaker = sup.get("speaker")
            if speaker and speaker != "N/A":
                speakers[sup["recording_id"]] = speaker
    rows, missing = [], 0
    for path in resolve_split(catalog, source["dataset"], source["version"], source["split"], "recordings", roots):
        for rec in lines(path):
            if not MIN_SECONDS <= rec["duration"] <= MAX_SECONDS:
                continue
            speaker = speakers.get(rec["id"])
            if speaker is None:
                missing += 1
                continue
            rows.append(candidate(source, rec["id"], rec["id"], rec["sources"][0]["source"], rec["sampling_rate"],
                                  rec["num_samples"], rec["duration"], len(rec["channel_ids"]),
                                  f"{source['dataset']}:{speaker}"))
    if missing:
        print(f"  {source['dataset']}: {missing} recordings without a speaker label were skipped", flush=True)
    return rows


def segment_candidates(catalog, roots, source, rng):
    """Per long recording keep a seeded sample of at most ``cap`` usable segments."""
    recordings = {}
    for path in resolve_split(catalog, source["dataset"], source["version"], source["split"], "recordings", roots):
        for rec in lines(path):
            recordings[rec["id"]] = rec
    kept, seen = defaultdict(list), defaultdict(int)
    for path in resolve_split(catalog, source["dataset"], source["version"], source["split"], "supervisions", roots):
        for sup in lines(path):
            text = sup.get("text") or ""
            # GigaSpeech marks music, noise and silence with <TAGS>.
            if not text.strip() or "<" in text:
                continue
            if not SEGMENT_MIN_SECONDS <= sup["duration"] <= MAX_SECONDS or sup["recording_id"] not in recordings:
                continue
            rid = sup["recording_id"]
            seen[rid] += 1
            if len(kept[rid]) < source["cap"]:
                kept[rid].append(sup)
            elif (slot := rng.randrange(seen[rid])) < source["cap"]:
                kept[rid][slot] = sup
    rows = []
    for rid, sups in kept.items():
        rec = recordings[rid]
        for sup in sups:
            rows.append(candidate(source, sup["id"], rid, rec["sources"][0]["source"], rec["sampling_rate"],
                                  rec["num_samples"], rec["duration"], len(rec["channel_ids"]),
                                  f"{source['dataset']}:{rid}", start=sup["start"], span=sup["duration"]))
    return rows


def quality(audio):
    frame = 400
    n = len(audio) // frame
    level = 10 * np.log10(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    return {"loudness_dbfs": round(float(20 * np.log10(np.sqrt(np.mean(audio**2)) + 1e-12)), 2),
            "clip_ratio": round(float(np.mean(np.abs(audio) >= 0.999)), 5),
            "voiced_ratio": round(float(np.mean(level > VOICED_FRAME_DBFS)) if n else 0.0, 3)}


def measure_file(job):
    """Measure every clip of one file. Segments are read by offset, like training reads them."""
    from lhotse import AudioSource, Recording

    path, rate, frames, duration, channels, clips = job
    recording = Recording(id="x", sources=[AudioSource("file", list(range(channels)), path)],
                          sampling_rate=rate, num_samples=frames, duration=duration)
    out = []
    for index, start, span in clips:
        try:
            audio = recording.load_audio() if span is None else recording.load_audio(offset=start, duration=span)
        except Exception as error:  # noqa: BLE001  a damaged file or span costs only its own clip
            out.append((index, None, f"decode_failed: {repr(error)[:80]}"))
            continue
        clip = audio.mean(axis=0).astype(np.float32)
        if len(clip) < MIN_SECONDS * rate:
            out.append((index, None, "too_short"))
            continue
        if rate != SAMPLE_RATE:
            from scipy.signal import resample_poly

            clip = resample_poly(clip, SAMPLE_RATE, rate).astype(np.float32)
        out.append((index, quality(clip), None))
    return out


def gate(stats):
    if stats["loudness_dbfs"] < MIN_LOUDNESS_DBFS:
        return "quiet"
    if stats["voiced_ratio"] < MIN_VOICED_RATIO:
        return "sparse"
    return None


def take_with_cap(rng, rows, count, cap):
    """Shuffle, then keep rows while no group exceeds ``cap``."""
    rng.shuffle(rows)
    used, kept = defaultdict(int), []
    for row in rows:
        if used[row["group"]] >= cap:
            continue
        used[row["group"]] += 1
        kept.append(row)
        if len(kept) == count:
            break
    return kept


def measure(rows, workers):
    by_file = defaultdict(list)
    for index, row in enumerate(rows):
        by_file[row["file"]].append((index, row["start"], row["span"]))
    jobs = []
    for clips in by_file.values():
        first = rows[clips[0][0]]
        jobs.append((first["path"], first["rate"], first["frames"], first["duration"], first["channels"], clips))
    results, dropped = {}, defaultdict(int)
    with ProcessPoolExecutor(workers) as pool:
        for number, out in enumerate(pool.map(measure_file, jobs, chunksize=8), 1):
            for index, stats, error in out:
                if error:
                    dropped[error.split(":")[0]] += 1
                elif (reason := gate(stats)):
                    dropped[reason] += 1
                else:
                    results[index] = stats
            if number % 20000 == 0:
                print(f"    measured {number}/{len(jobs)} files", flush=True)
    return results, dict(dropped)


def relative_to_root(path, root, checked):
    """Path of the file relative to the root; its resolved directory must stay inside the root."""
    location = Path(path)
    relative = location.relative_to(root)
    if location.parent not in checked:
        if not location.parent.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError(f"{location} leaves the root {root}")
        checked.add(location.parent)
    return relative.as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=1.0, help="fraction of each source count (smoke tests)")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    catalog, roots = load_catalog(CATALOG), load_roots(ROOTS)
    root = str(roots[ROOT_ALIAS])
    held_out = set(Path(HELD_OUT_MEDIA).read_text().split())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records, indexes, report = defaultdict(list), defaultdict(dict), {}
    checked_dirs = set()
    for source in SOURCES:
        name = f"{source['dataset']}:{source['split']}"
        count = max(1, int(source["count"] * args.scale))
        rng = random.Random(f"{SEED}:{name}")
        if source["kind"] == "segments":
            rows = segment_candidates(catalog, roots, source, rng)
        elif source["kind"] == "audio_index":
            rows = emilia_candidates(catalog, roots, source, held_out)
        else:
            rows = utterance_candidates(catalog, roots, source)
        if source["measure"]:
            drawn = take_with_cap(rng, rows, int(count * OVERDRAW), source["cap"])
            print(f"{name}: {len(rows)} candidates, measuring {len(drawn)}", flush=True)
            stats, dropped = measure(drawn, args.workers)
            passed = [(row, stats[i]) for i, row in enumerate(drawn) if i in stats][:count]
        else:
            drawn = take_with_cap(rng, rows, count, source["cap"])
            print(f"{name}: {len(rows)} candidates, taking {len(drawn)} unmeasured", flush=True)
            dropped, passed = {}, [(row, {}) for row in drawn]
        if len(passed) < count:
            raise ValueError(f"{name}: wanted {count}, only {len(passed)} passed the gates")
        language = source["language"]
        for row, quality_columns in passed:
            ref = {"dataset_id": DATASET_ID, "version": VERSION, "split": language, "cut_id": row["file"]}
            if row["start"] is not None:
                ref.update(start=row["start"], duration=row["span"])
            metadata = {"source_dataset": source["dataset"], "source_group": row["group"], **quality_columns}
            if source["speaker"]:
                metadata["speaker"] = row["group"]
            records[language].append({
                "schema_version": "audio-record/1.0", "id": row["id"], "task": TASK,
                "audio_slots": [{"name": "primary", "ref": ref}], "target": "", "language": language,
                "labels": {}, "hotwords": [], "metadata": metadata})
            if row["file"] not in indexes[language]:
                indexes[language][row["file"]] = {
                    "cut_id": row["file"], "root_alias": ROOT_ALIAS,
                    "relative_path": relative_to_root(row["path"], root, checked_dirs),
                    "sample_rate": row["rate"], "channels": row["channels"],
                    "num_frames": row["frames"], "duration": row["duration"]}
        seconds = [row["span"] or row["duration"] for row, _ in passed]
        report[name] = {"language": language, "kind": source["kind"], "count": len(passed),
                        "hours": round(sum(seconds) / 3600, 1), "groups": len({row["group"] for row, _ in passed}),
                        "cap_per_group": source["cap"], "dropped_by_gate": dropped,
                        "measured": source["measure"]}
        if source["measure"]:
            report[name]["loudness_dbfs_median"] = float(np.median([q["loudness_dbfs"] for _, q in passed]))
            report[name]["voiced_ratio_median"] = float(np.median([q["voiced_ratio"] for _, q in passed]))
        print(f"  {report[name]}", flush=True)
    for language, rows in records.items():
        rows.sort(key=lambda row: row["id"])
        files = sorted(indexes[language].values(), key=lambda row: row["cut_id"])
        for stem, items in (("records", rows), ("audio_index", files)):
            with gzip.open(args.output_dir / f"{stem}_{language}.jsonl.gz", "wt", encoding="utf-8") as stream:
                for item in items:
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        hours = sum(r["audio_slots"][0]["ref"].get("duration") or indexes[language][r["audio_slots"][0]["ref"]["cut_id"]]["duration"]
                    for r in rows) / 3600
        report[f"total_{language}"] = {"clips": len(rows), "files": len(files), "hours": round(hours, 1)}
        print(f"{language}: {len(rows)} clips in {len(files)} files, {hours:.1f} h", flush=True)
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
