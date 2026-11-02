#!/usr/bin/env python3
"""Speech-free clips outside the recipe's empty-target pools, as GRPO mining candidates.

Same records as ``scripts/ts_robust/build_nonspeech_pool.py`` (one span of a source file,
empty target, level drawn at training time), from the sources in
``recipe-nonspeech.yaml``. Every span is decoded, dropped when silent, and run through
Silero VAD (default parameters) after an RMS normalization; a span with any detected
speech segment is not used. Silero misses speech under music and in noisy rooms
(trailer narration in DNS5 AudioSet, talk on a bus in RealMAN), so spans that pass also go
through SenseVoiceSmall, and a span it writes more than ``asr_max_units`` units on is
quarantined. Spans whose file an eval set reads (``eval_refs.py`` output) are dropped too.

Stages (``spans`` writes the plan, ``vad`` and ``asr`` resume, ``build`` writes the version):

    python scripts/grpo_candidates/nonspeech.py spans --work DIR
    PYTHONPATH=<silero-vad 6.2.3> python scripts/grpo_candidates/nonspeech.py vad --work DIR [--workers 32]
    <funasr env>/python scripts/grpo_candidates/nonspeech.py asr --work DIR [--workers 6]
    python scripts/grpo_candidates/nonspeech.py build --work DIR --eval-refs eval-refs.json.gz --version-dir DIR
"""

from __future__ import annotations

import argparse
import csv
import glob
import gzip
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
DATA_ROOT = Path("/workspace/data")
DATASETS = DATA_ROOT / "datasets"
CATALOG = "/workspace/data/registry/catalog"
ROOTS = "/workspace/data/registry/roots.json"
ROOT_ALIAS = "aidc_data"
VAD_RATE = 16000
SENSEVOICE = "/workspace/model/SenseVoiceSmall"
ASR_THREADS = 8
ASR_BATCH = 16
_UNITS = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]|[a-z0-9]+(?:'[a-z0-9]+)*")


def lines(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def source_files(name, spec):
    """[{path, sample_rate, num_frames, duration, channels, labels}] of one source."""
    import soundfile as sf

    if "catalog" in spec:
        from audio_data_contract import load_catalog, resolve_split
        from audio_data_contract.roots import load_roots

        ref = spec["catalog"]
        out = []
        for path in resolve_split(load_catalog(CATALOG), ref["dataset"], ref["version"], ref["split"],
                                  "recordings", load_roots(ROOTS)):
            for rec in lines(path):
                (audio,) = rec["sources"]
                out.append({"path": os.path.normpath(audio["source"]), "sample_rate": rec["sampling_rate"],
                            "num_frames": rec["num_samples"], "duration": rec["duration"],
                            "channels": len(rec["channel_ids"]), "labels": None})
        return out
    if name == "fsd50k":
        excluded = set(spec["exclude_labels"])
        out = []
        with (DATASETS / spec["ground_truth"]).open(newline="") as stream:
            for row in csv.DictReader(stream):
                labels = row["labels"].split(",")
                if row["split"] != spec["dev_split"] or excluded & set(labels):
                    continue
                out.append({"path": str(DATASETS / spec["audio_dir"] / f"{row['fname']}.wav"), "labels": labels})
    else:
        out = [{"path": path, "labels": None} for path in sorted(glob.glob(str(DATASETS / spec["glob"])))]
    for item in out:  # files without a manifest: read the header
        info = sf.info(item["path"])
        item.update(sample_rate=info.samplerate, num_frames=info.frames, duration=info.frames / info.samplerate,
                    channels=info.channels)
    return out


def spans(recipe, work):
    plan = []
    report = {}
    for name, spec in recipe["sources"].items():
        rng = random.Random(f"{recipe['seed']}:{name}")
        files = [f for f in source_files(name, spec) if f["duration"] >= recipe["min_seconds"]]
        rng.shuffle(files)
        wanted = int(spec["count"] * recipe["oversample"])
        for number in range(wanted):
            item = files[number % len(files)] if number < len(files) * spec["per_file"] else rng.choice(files)
            span = min(item["duration"], math.exp(rng.uniform(math.log(recipe["min_seconds"]),
                                                              math.log(recipe["max_seconds"]))))
            start = rng.uniform(0, item["duration"] - span)
            plan.append({"key": f"{name}:{number:06d}", "source": name, "file": item,
                         "start": round(start, 3), "duration": round(span, 3)})
        report[name] = {"files": len(files), "spans": wanted}
        print(name, report[name], flush=True)
    write_jsonl(work / "spans.jsonl.gz", plan)
    (work / "spans-report.json").write_text(json.dumps(report, indent=1) + "\n")


_VAD = {}


def _vad_model():
    if "model" not in _VAD:
        import torch
        from silero_vad import load_silero_vad

        torch.set_num_threads(1)
        _VAD["model"] = load_silero_vad()
    return _VAD["model"]


def check_span(job):
    """(key, result): decode, RMS, Silero VAD speech seconds on the RMS-normalized 16 kHz mono span."""
    import soundfile as sf
    import soxr
    import torch
    from silero_vad import get_speech_timestamps

    span, min_rms, vad_rms_dbfs = job
    item = span["file"]
    try:
        start = round(span["start"] * item["sample_rate"])
        frames = max(1, round(span["duration"] * item["sample_rate"]))
        audio, rate = sf.read(item["path"], start=start, frames=frames, dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
    except Exception as error:  # noqa: BLE001 - a damaged span costs only its own clip
        return span["key"], {"error": f"decode_failed: {repr(error)[:80]}"}
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
    if rms < min_rms:
        return span["key"], {"error": "silent", "rms": rms}
    if rate != VAD_RATE:
        audio = soxr.resample(audio, rate, VAD_RATE)
    audio = np.clip(audio * (10 ** (vad_rms_dbfs / 20) / rms), -1.0, 1.0).astype(np.float32)
    stamps = get_speech_timestamps(torch.from_numpy(audio), _vad_model(), sampling_rate=VAD_RATE)
    speech = sum(s["end"] - s["start"] for s in stamps) / VAD_RATE
    return span["key"], {"rms": round(rms, 6), "speech_seconds": round(speech, 3), "segments": len(stamps)}


def vad(recipe, work, workers):
    path = work / "vad.jsonl"
    done = {row["key"] for row in lines(path)} if path.exists() else set()
    todo = [s for s in lines(work / "spans.jsonl.gz") if s["key"] not in done]
    print(f"vad: {len(todo)} spans to do ({len(done)} done)", flush=True)
    with path.open("a", encoding="utf-8") as stream, ProcessPoolExecutor(workers) as pool:
        jobs = ((s, recipe["min_rms"], recipe["vad_rms_dbfs"]) for s in todo)
        for number, (key, result) in enumerate(pool.map(check_span, jobs, chunksize=16), 1):
            stream.write(json.dumps({"key": key, **result}) + "\n")
            if number % 2000 == 0:
                stream.flush()
                print(f"vad: {number}/{len(todo)}", flush=True)


def asr_batch(job):
    """SenseVoice transcripts of RMS-normalized spans; each worker process keeps its own model."""
    import soundfile as sf
    import torch
    from funasr import AutoModel
    from scipy.signal import resample_poly

    batch, vad_rms_dbfs = job
    if "asr" not in _VAD:
        torch.set_num_threads(ASR_THREADS)
        _VAD["asr"] = AutoModel(model=SENSEVOICE, device="cpu", disable_update=True, log_level="ERROR")
    waves = []
    for span in batch:
        item = span["file"]
        audio, rate = sf.read(item["path"], start=round(span["start"] * item["sample_rate"]),
                              frames=max(1, round(span["duration"] * item["sample_rate"])),
                              dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if rate != VAD_RATE:
            audio = resample_poly(audio, VAD_RATE, rate).astype(np.float32)
        gain = 10 ** (vad_rms_dbfs / 20) / max(1e-6, float(np.sqrt(np.mean(audio ** 2))))
        waves.append(np.clip(audio * gain, -1.0, 1.0).astype(np.float32))
    results = _VAD["asr"].generate(input=waves, batch_size=len(waves), language="auto", use_itn=False, disable_pbar=True)
    return [{"key": span["key"], "source": span["source"], "raw": result["text"],
             "text": re.sub(r"<\|[^|]*\|>", "", result["text"]).strip()} for span, result in zip(batch, results)]


def vad_passed(recipe, work):
    """VAD-clean spans of each source, in plan order, up to the share the ASR check looks at."""
    checked = {row["key"]: row for row in lines(work / "vad.jsonl")}
    by_source = defaultdict(list)
    for span in lines(work / "spans.jsonl.gz"):
        result = checked.get(span["key"])
        if result and "error" not in result and not result["segments"]:
            by_source[span["source"]].append(span)
    return {name: rows[:int(recipe["sources"][name]["count"] * recipe["asr_share"])] for name, rows in by_source.items()}


def asr(recipe, work, workers):
    path = work / "asr.jsonl"
    done = {row["key"] for row in lines(path)} if path.exists() else set()
    todo = [s for rows in vad_passed(recipe, work).values() for s in rows if s["key"] not in done]
    print(f"asr: {len(todo)} spans to do ({len(done)} done)", flush=True)
    batches = [(todo[i:i + ASR_BATCH], recipe["vad_rms_dbfs"]) for i in range(0, len(todo), ASR_BATCH)]
    with path.open("a", encoding="utf-8") as stream, ProcessPoolExecutor(workers) as pool:
        for number, rows in enumerate(pool.map(asr_batch, batches), 1):
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            if number % 50 == 0:
                print(f"asr: {number}/{len(batches)} batches", flush=True)


def build(recipe, work, eval_refs, version_dir):
    with gzip.open(eval_refs, "rt", encoding="utf-8") as stream:
        refs = json.load(stream)
    eval_audio = set(refs["audio"])
    checked = {row["key"]: row for row in lines(work / "vad.jsonl")}
    transcripts = {row["key"]: row["text"] for row in lines(work / "asr.jsonl")}
    by_source = defaultdict(list)
    for span in lines(work / "spans.jsonl.gz"):
        by_source[span["source"]].append(span)
    records, index_rows, report = [], {}, {"eval_refs": refs["report"] | {"file": str(eval_refs)}}
    quarantine = []
    for name, spec in recipe["sources"].items():
        rng = random.Random(f"{recipe['seed']}:{name}:language")
        dropped, kept = Counter(), []
        looked_at = 0
        for span in by_source[name]:
            if len(kept) >= spec["count"]:
                break
            looked_at += 1
            result = checked.get(span["key"])
            text = transcripts.get(span["key"])
            reason = ("unchecked" if result is None
                      else result["error"].split(":")[0] if "error" in result
                      else "vad_speech" if result["segments"]
                      else "eval_audio" if span["file"]["path"] in eval_audio
                      else "asr_unchecked" if text is None
                      else "asr_text" if len(_UNITS.findall(text.lower())) > recipe["asr_max_units"]
                      else None)
            if reason:
                dropped[reason] += 1
                if reason in ("vad_speech", "asr_text"):
                    quarantine.append({"key": span["key"], "reason": reason, "path": span["file"]["path"],
                                       "start": span["start"], "duration": span["duration"], "text": text})
            else:
                kept.append(span)
        if len(kept) < spec["count"]:
            print(f"warning: {name}: wanted {spec['count']}, only {len(kept)} usable", file=sys.stderr)
        for span in kept:
            item = span["file"]
            relative = Path(item["path"]).relative_to(DATA_ROOT).as_posix()
            file_id = f"{name}:{relative}"
            metadata = {"source_dataset": name, "source_group": file_id}
            if item.get("labels"):
                metadata["fsd50k_labels"] = item["labels"]
            if name == "realman":
                metadata["scene"] = Path(item["path"]).parent.name
            records.append({
                "schema_version": "audio-record/1.0", "id": f"{recipe['dataset_id']}:{span['key']}",
                "task": "asr", "target": "", "language": rng.choice(("zh", "en")),
                "labels": {"target_present": False}, "hotwords": [],
                "audio_slots": [{"name": "primary", "ref": {
                    "dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": recipe["split"],
                    "cut_id": file_id, "start": span["start"], "duration": span["duration"]}}],
                "metadata": metadata})
            index_rows.setdefault(file_id, {
                "cut_id": file_id, "root_alias": ROOT_ALIAS, "relative_path": relative,
                "sample_rate": item["sample_rate"], "channels": item["channels"],
                "num_frames": item["num_frames"], "duration": item["duration"]})
        seconds = [s["duration"] for s in kept]
        report[name] = {"clips": len(kept), "files": len({s["file"]["path"] for s in kept}),
                        "hours": round(sum(seconds) / 3600, 2),
                        "seconds_median": round(float(np.median(seconds)), 2) if seconds else None,
                        "looked_at": looked_at, "dropped": dict(dropped)}
        print(name, report[name], flush=True)
    records.sort(key=lambda r: r["id"])
    split = recipe["split"]
    write_jsonl(version_dir / f"records_{split}.jsonl.gz", records)
    write_jsonl(version_dir / f"audio_index_{split}.jsonl.gz", sorted(index_rows.values(), key=lambda r: r["cut_id"]))
    write_jsonl(version_dir / "quarantine.jsonl.gz", quarantine)
    report["total"] = {"clips": len(records), "files": len(index_rows),
                       "hours": round(sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600, 2)}
    (version_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("total", report["total"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("spans", "vad", "asr", "build"))
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-nonspeech.yaml")
    parser.add_argument("--work", type=Path, required=True, help="work directory (span plan, VAD results)")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--eval-refs", type=Path)
    parser.add_argument("--version-dir", type=Path)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    args.work.mkdir(parents=True, exist_ok=True)
    if args.stage == "spans":
        spans(recipe, args.work)
    elif args.stage == "vad":
        vad(recipe, args.work, args.workers)
    elif args.stage == "asr":
        asr(recipe, args.work, args.workers)
    else:
        build(recipe, args.work, args.eval_refs, args.version_dir)


if __name__ == "__main__":
    main()
