"""Synthesize babble (background crowd speech) noise from existing speech corpora.

Each clip overlaps N distinct speakers (N uniform in [min_speakers, max_speakers]). Every
speaker track is filled to the clip length with that speaker's utterances separated by short
random gaps, gained by a random offset in dB, then summed and scaled to a target RMS.
Speakers are split into train/dev/test pools so splits never share a speaker.
"""

import argparse
import gzip
import json
import multiprocessing
import os
import random
import re
from collections import defaultdict

import numpy as np
import soundfile as sf

SR = 16000
CORPORA = {
    "en": {
        "manifest": "/workspace/data/datasets/librispeech/versions/legacy-20260804/train_rec_0/librispeech_recordings_train-clean-100.jsonl.gz",
        "speaker": lambda rec_id: rec_id.split("-")[0],
        "dataset": "librispeech@legacy-20260804/train-clean-100",
    },
    "zh": {
        "manifest": "/workspace/data/datasets/aishell/versions/legacy-20260804/train_rec_0/aishell_recordings_train.jsonl.gz",
        "speaker": lambda rec_id: re.match(r"BAC009(S\d+)", rec_id).group(1),
        "dataset": "aishell@legacy-20260804/train",
    },
}


def load_pools(lang, seed):
    cfg = CORPORA[lang]
    by_spk = defaultdict(list)
    with gzip.open(cfg["manifest"], "rt") as stream:
        for line in stream:
            r = json.loads(line)
            by_spk[cfg["speaker"](r["id"])].append((r["id"], r["sources"][0]["source"], r["duration"]))
    spks = sorted(by_spk)
    random.Random(seed).shuffle(spks)
    n = len(spks)
    cut_dev, cut_test = int(n * 0.8), int(n * 0.9)
    pools = {"train": spks[:cut_dev], "dev": spks[cut_dev:cut_test], "test": spks[cut_test:]}
    return by_spk, pools


def speaker_track(utts, length, rng):
    chunks, used, total = [], [], 0
    while total < length:
        uid, path, _ = rng.choice(utts)
        wav, sr = sf.read(path, dtype="float32")
        assert sr == SR
        if wav.ndim > 1:
            wav = wav[:, 0]
        gap = np.zeros(int(rng.uniform(0.0, 1.0) * SR), dtype="float32")
        chunks += [gap, wav]
        used.append(uid)
        total += len(gap) + len(wav)
    track = np.concatenate(chunks)
    start = rng.randint(0, max(0, len(track) - length))
    return track[start : start + length], used


POOLS = {}


def make_clip(job):
    lang, split, idx, seed, out_dir, dur, min_n, max_n, rms_db = job
    by_spk, pools = POOLS[lang]
    pool = pools[split]
    rng = random.Random(f"{seed}-{lang}-{split}-{idx}")
    n = rng.randint(min_n, max_n)
    speakers = rng.sample(pool, n)
    length = int(dur * SR)
    mix = np.zeros(length, dtype="float64")
    meta = []
    for spk in speakers:
        track, used = speaker_track(by_spk[spk], length, rng)
        rms = float(np.sqrt(np.mean(track**2))) + 1e-8
        gain_db = rng.uniform(-6.0, 6.0)
        mix += track / rms * 10 ** (gain_db / 20)
        meta.append({"speaker": spk, "gain_db": round(gain_db, 2), "utterances": used})
    mix *= 10 ** (rms_db / 20) / (float(np.sqrt(np.mean(mix**2))) + 1e-8)
    peak = float(np.abs(mix).max())
    if peak > 0.95:
        mix *= 0.95 / peak
    clip_id = f"babble-{lang}-{split}-{idx:05d}"
    rel = f"{lang}/{split}/{clip_id}.flac"
    path = os.path.join(out_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, mix.astype("float32"), SR, format="FLAC", subtype="PCM_16")
    return {"id": clip_id, "path": rel, "language": lang, "split": split, "duration": dur,
            "sampling_rate": SR, "num_speakers": n, "target_rms_db": rms_db, "speakers": meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--min-speakers", type=int, default=5)
    ap.add_argument("--max-speakers", type=int, default=20)
    ap.add_argument("--rms-db", type=float, default=-25.0)
    ap.add_argument("--clips", default="train=2600,dev=200,test=200", help="clips per split per language")
    ap.add_argument("--langs", default="en,zh")
    ap.add_argument("--workers", type=int, default=48)
    args = ap.parse_args()
    counts = {k: int(v) for k, v in (x.split("=") for x in args.clips.split(","))}
    jobs = []
    for lang in args.langs.split(","):
        POOLS[lang] = load_pools(lang, args.seed)
        for split, pool in POOLS[lang][1].items():
            assert len(pool) >= args.max_speakers, (lang, split, len(pool))
            for i in range(counts[split]):
                jobs.append((lang, split, i, args.seed, args.out, args.duration,
                             args.min_speakers, args.max_speakers, args.rms_db))
    os.makedirs(args.out, exist_ok=True)
    with multiprocessing.get_context("fork").Pool(args.workers) as p, open(os.path.join(args.out, "manifest.jsonl"), "w") as f:
        f.writelines(json.dumps(rec, ensure_ascii=False) + "\n" for rec in p.imap(make_clip, jobs, chunksize=8))


if __name__ == "__main__":
    main()
