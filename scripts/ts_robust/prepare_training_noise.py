#!/usr/bin/env python3
"""Extract DNS5 noise and room impulse responses for training, disjoint from the TS benchmark.

The benchmark (scripts/ts_benchmark/prepare_noise.py, build.py) takes the first 80 usable
clips of every DNS5 noise archive and the 300 impulse responses with the smallest name hash.
Training takes every other clip, so no noise or room seen in evaluation is trained on.

Noise is 16 kHz mono FLAC, at most 30 s, RMS-normalized to -30 dBFS like the benchmark's
(the loader rescales by SNR or floor level). Each clip is flagged ``stationary`` when its
level is steady, which is what a noise floor needs. Impulse responses keep their level.

Output (`<output>` = datasets/dns5_noise_train/source/<version>):
  audio/<pool>/<id>.flac, rir/<id>.wav
  recordings/dns5_{audioset,freesound,stationary,rir}_recordings.jsonl.gz   (Lhotse)

`--index-only` rebuilds the recordings from the files already written, without reading DNS5 again.

    python scripts/ts_robust/prepare_training_noise.py --output DIR [--workers 10]
"""

import argparse
import hashlib
import io
import json
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
from lhotse import AudioSource, Recording, RecordingSet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ts_benchmark"))
from prepare_noise import (  # noqa: E402  (reused so both sides cut clips the same way)
    CLIP_SECONDS, DNS5, DNS5_AUDIOSET, DNS5_FREESOUND, NOISE_DBFS, SR,
    STATIONARY_PEAK_DB, STATIONARY_STD_DB, stationarity, to_16k_mono,
)

BENCHMARK = Path("/workspace/data/datasets/ts_asr_benchmark/source/v3-20261013")
RIR_ARCHIVE = "datasets_fullband.impulse_responses_000.tar.bz2"
# The benchmark's impulse responses are the 300 smallest name hashes; training skips them.
BENCHMARK_RIR_COUNT = 300
TRAIN_RIR_COUNT = 5000


def noise_job(job):
    output, pool, archive = job
    used = {e["id"] for e in json.loads((BENCHMARK / "noise/manifest.json").read_text()) if e["pool"] == pool}
    rows, skipped = [], 0
    with tarfile.open(DNS5 / archive, "r|bz2") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".wav"):
                continue
            clip_id = f"{pool}-{hashlib.sha256(f'{archive}/{member.name}'.encode()).hexdigest()[:12]}"
            if clip_id in used:
                skipped += 1
                continue
            w, rate = sf.read(io.BytesIO(tar.extractfile(member).read()), dtype="float32")
            w = to_16k_mono(w, rate)[: int(CLIP_SECONDS * SR)]
            rms = float(np.sqrt(np.mean(w.astype(np.float64) ** 2)))
            if rms < 1e-6:
                continue
            std, peak = stationarity(w)
            path = output / "audio" / pool / f"{clip_id}.flac"
            path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, np.clip(w * (10 ** (NOISE_DBFS / 20) / rms), -1, 1), SR, format="FLAC")
            rows.append({"id": clip_id, "pool": pool, "path": str(path), "samples": len(w),
                         "stationary": bool(std < STATIONARY_STD_DB and peak < STATIONARY_PEAK_DB),
                         "level_std_db": round(std, 2), "peak_over_median_db": round(peak, 2),
                         "archive": archive, "member": member.name})
    return rows, skipped


def rir_job(output):
    seen = []
    with tarfile.open(DNS5 / RIR_ARCHIVE, "r|bz2") as tar:
        for member in tar:
            if member.isfile() and member.name.endswith(".wav"):
                # Same key as scripts/ts_benchmark/build.py prepare_rirs, so the split is exact.
                seen.append((int(hashlib.sha256(member.name.encode()).hexdigest(), 16), member.name,
                             tar.extractfile(member).read()))
    seen.sort()
    rows = []
    for _, name, data in seen[BENCHMARK_RIR_COUNT : BENCHMARK_RIR_COUNT + TRAIN_RIR_COUNT]:
        w, rate = sf.read(io.BytesIO(data), dtype="float32")
        w = to_16k_mono(w[:, 0] if w.ndim > 1 else w, rate)
        clip_id = hashlib.sha256(name.encode()).hexdigest()[:16]
        path = output / "rir" / f"{clip_id}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, w, SR, subtype="FLOAT")
        rows.append({"id": clip_id, "pool": "rir", "path": str(path), "samples": len(w), "member": name})
    return rows, len(seen)


def scan_job(path):
    """A row for a clip already on disk (--index-only): stationarity is measured again."""
    w, _ = sf.read(path, dtype="float32")
    pool = path.parent.name
    row = {"id": path.stem, "pool": "rir" if path.parent.name == "rir" else pool, "path": str(path), "samples": len(w)}
    if row["pool"] != "rir":
        std, peak = stationarity(w)
        row["stationary"] = bool(std < STATIONARY_STD_DB and peak < STATIONARY_PEAK_DB)
    return row


def write_recordings(output, name, rows):
    recordings = [Recording(id=r["id"], sources=[AudioSource("file", [0], r["path"])], sampling_rate=SR,
                            num_samples=r["samples"], duration=r["samples"] / SR)
                  for r in sorted(rows, key=lambda r: r["id"])]
    path = output / "recordings" / f"dns5_{name}_recordings.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    RecordingSet.from_recordings(recordings).to_file(path)
    return path, len(recordings), sum(r.duration for r in recordings) / 3600


def write_index(output, noise, rir_rows, report):
    splits = {"audioset": noise["audioset"], "freesound": noise["freesound"],
              "stationary": [r for r in noise["audioset"] + noise["freesound"] if r["stationary"]], "rir": rir_rows}
    for name, rows in splits.items():
        path, count, hours = write_recordings(output, name, rows)
        report[name] = {"recordings": count, "hours": round(hours, 2), "path": str(path)}
        print(name, report[name], flush=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--index-only", action="store_true")
    args = parser.parse_args()
    if args.index_only:
        with ProcessPoolExecutor(args.workers) as pool:
            rows = list(pool.map(scan_job, sorted(args.output.glob("audio/*/*.flac")) + sorted(args.output.glob("rir/*.wav")), chunksize=64))
        noise = {name: [r for r in rows if r["pool"] == f"dns5_{name}"] for name in ("audioset", "freesound")}
        rir_rows, report = [r for r in rows if r["pool"] == "rir"], {}
        write_index(args.output, noise, rir_rows, report)
        return
    jobs = [(args.output, "dns5_audioset", a) for a in DNS5_AUDIOSET] + [(args.output, "dns5_freesound", a) for a in DNS5_FREESOUND]
    noise = {"audioset": [], "freesound": []}
    report = {}
    with ProcessPoolExecutor(args.workers) as pool:
        rir = pool.submit(rir_job, args.output)
        for job, future in [(j, pool.submit(noise_job, j)) for j in jobs]:
            rows, skipped = future.result()
            noise[job[1].split("_")[1]] += rows
            report[job[2]] = {"clips": len(rows), "benchmark_clips_skipped": skipped}
            print(job[2], report[job[2]], flush=True)
        rir_rows, total = rir.result()
    report["rir"] = {"clips": len(rir_rows), "archive_total": total, "benchmark_count": BENCHMARK_RIR_COUNT}
    write_index(args.output, noise, rir_rows, report)


if __name__ == "__main__":
    main()
