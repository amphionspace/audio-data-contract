#!/usr/bin/env python3
"""Extract real noise recordings and room impulse responses for the target-speaker benchmark.

Noise pools (16 kHz mono, RMS-normalized to -30 dBFS; the renderer rescales them):

* ``wham``            WHAM! noise test split (real cafe, restaurant, bar, park and street ambience)
* ``dns5_audioset``   a deterministic sample of the DNS5 AudioSet noise archives
* ``dns5_freesound``  a deterministic sample of the DNS5 Freesound noise archives
* ``device``          ambient recordings from business feedback segments without speech

Every clip is flagged ``stationary`` when its level is steady (usable as a noise floor).
Room impulse responses: ``real`` (SLR28 real RIRs), ``sim_small`` / ``sim_medium`` /
``sim_large`` (SLR28 simulated, by room size). Archives are streamed, never extracted whole.

    python scripts/ts_benchmark/prepare_noise.py --output <dir> --roots roots.json
"""

import argparse
import gzip
import hashlib
import io
import json
import math
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000
NOISE_DBFS = -30.0
CLIP_SECONDS = 30.0
DNS5 = Path("/workspace/data/DATA-TTS/dns5")
WHAM = Path("/workspace/data/datasets/noise_open/wham_noise/extracted/wham_noise/tt")
DNS5_AUDIOSET = [f"datasets_fullband.noise_fullband.audioset_{i:03d}.tar.bz2" for i in range(7)]
DNS5_FREESOUND = [f"datasets_fullband.noise_fullband.freesound_{i:03d}.tar.bz2" for i in range(2)]
PER_ARCHIVE = 80
WHAM_COUNT = 300
RIR_PER_SIM_SIZE = 100
# Steady means short-term level varies by less than this many dB and has no loud event.
STATIONARY_STD_DB = 3.0
STATIONARY_PEAK_DB = 10.0


def to_16k_mono(w, sr):
    if w.ndim > 1:
        w = w.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly

        g = math.gcd(sr, SR)
        w = resample_poly(w, SR // g, sr // g)
    return w.astype(np.float32)


def stationarity(w):
    """(std, peak-over-median) of the 0.5 s frame levels in dB."""
    step = SR // 2
    frames = [w[i:i + step] for i in range(0, len(w) - step + 1, step)] or [w]
    levels = np.array([20 * math.log10(np.sqrt(np.mean(f.astype(np.float64) ** 2)) + 1e-9) for f in frames])
    return float(levels.std()), float(levels.max() - np.median(levels))


def save(directory, pool, key, w, source, extra=None):
    w = w[: int(CLIP_SECONDS * SR)]
    rms = float(np.sqrt(np.mean(w.astype(np.float64) ** 2)))
    if rms < 1e-6:
        return None
    std, peak = stationarity(w)
    clip_id = f"{pool}-{hashlib.sha256(key.encode()).hexdigest()[:12]}"
    scaled = w * (10 ** (NOISE_DBFS / 20) / rms)
    path = directory / pool / f"{clip_id}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.clip(scaled, -1, 1), SR, subtype="PCM_16")
    return {"id": clip_id, "pool": pool, "path": f"{pool}/{clip_id}.wav", "source": source,
            "seconds": round(len(w) / SR, 2), "stationary": std < STATIONARY_STD_DB and peak < STATIONARY_PEAK_DB,
            "level_std_db": round(std, 2), "peak_over_median_db": round(peak, 2), **(extra or {})}


def dns5_job(job):
    directory, pool, archive = job
    out = []
    with tarfile.open(DNS5 / archive, "r|bz2") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".wav"):
                continue
            w, sr = sf.read(io.BytesIO(tar.extractfile(member).read()), dtype="float32")
            entry = save(directory, pool, f"{archive}/{member.name}", to_16k_mono(w, sr),
                         f"dns5:{archive}:{Path(member.name).name}")
            if entry:
                out.append(entry)
            if len(out) >= PER_ARCHIVE:
                break
    return out


def wham_entries(directory):
    files = sorted(WHAM.glob("*.wav"), key=lambda p: hashlib.sha256(p.name.encode()).hexdigest())[:WHAM_COUNT]
    out = []
    for path in files:
        w, sr = sf.read(path, dtype="float32")
        entry = save(directory, "wham", path.name, to_16k_mono(w, sr), f"wham:tt:{path.name}")
        if entry:
            out.append(entry)
    return out


def device_entries(directory, roots):
    """Steady ambient segments of the business feedback recordings (the device's own noise).

    Only segments with a steady level qualify; segments with a voice or a song are not noise.
    """
    base = Path(roots["business_feedback"])
    out = []
    for path in sorted(base.glob("source/*/audio/*-mixture.wav")):
        w, sr = sf.read(path, dtype="float32")
        w = to_16k_mono(w, sr)
        if len(w) >= 4 * SR and stationarity(w)[0] < STATIONARY_STD_DB:
            entry = save(directory, "device", str(path), w, f"business_feedback:{path.name}")
            if entry:
                out.append(entry)
    return out


def rir_entries(directory, catalog_root):
    def rows(path):
        with gzip.open(path, "rt") as stream:
            return [json.loads(line) for line in stream]

    out = []
    real = rows(catalog_root / "real_rir_slr28/versions/prepared-20260908/recordings/real_rir_slr28_recordings_all.jsonl.gz")
    sim = rows(catalog_root / "sim_rir_slr28/versions/legacy-20260804/recordings/sim_rir_slr28_recordings_all.jsonl.gz")
    pools = {"real": [(r["sources"][0]["source"], "real") for r in real]}
    for size in ("small", "medium", "large"):
        picked = [r for r in sim if f"/{size}room/" in r["sources"][0]["source"]]
        picked.sort(key=lambda r: hashlib.sha256(r["id"].encode()).hexdigest())
        pools[f"sim_{size}"] = [(r["sources"][0]["source"], size) for r in picked[:RIR_PER_SIM_SIZE]]
    for pool, items in pools.items():
        for source, _ in items:
            w, sr = sf.read(source, dtype="float32")
            w = to_16k_mono(w, sr)
            name = hashlib.sha256(source.encode()).hexdigest()[:12]
            path = directory / "rir" / pool / f"{name}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, w, SR, subtype="FLOAT")
            out.append({"id": name, "pool": pool, "path": f"rir/{pool}/{name}.wav", "source": source,
                        "seconds": round(len(w) / SR, 3)})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog-data", type=Path, default=Path("/workspace/data/datasets"))
    parser.add_argument("--workers", type=int, default=9)
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = [(args.output, "dns5_audioset", a) for a in DNS5_AUDIOSET] + [(args.output, "dns5_freesound", a) for a in DNS5_FREESOUND]
    manifest = []
    with ProcessPoolExecutor(args.workers) as pool:
        futures = [pool.submit(dns5_job, job) for job in jobs]
        manifest += wham_entries(args.output)
        manifest += device_entries(args.output, roots)
        manifest += rir_entries(args.output, args.catalog_data)
        for future in futures:
            manifest += future.result()
    (args.output / "manifest.json").write_text(json.dumps(sorted(manifest, key=lambda e: e["id"]), ensure_ascii=False, indent=1))
    counts = {}
    for e in manifest:
        key = e["pool"] + (":stationary" if e.get("stationary") else "")
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
