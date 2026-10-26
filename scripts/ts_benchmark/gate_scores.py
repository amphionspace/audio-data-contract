#!/usr/bin/env python3
"""Speaker-verification scores for every benchmark record, for judging an external gate.

Writes ``{record id: cosine}`` between the 3-second enrollment the model receives and the whole
mixture (WeSpeaker ECAPA-TDNN512-LM, ONNX). Needs ``onnxruntime`` and ``torchaudio``.

    python scripts/ts_benchmark/gate_scores.py --roots roots.json --output scores.json --workers 16
"""

import argparse
import gzip
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL = "/workspace/model/wespeaker-ecapa-tdnn512-LM/voxceleb_ECAPA512_LM.onnx"
SR = 16000
ENROLL = 3 * SR
_SESSION = {}


def session():
    if not _SESSION:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        _SESSION["s"] = ort.InferenceSession(MODEL, options, providers=["CPUExecutionProvider"])
    return _SESSION["s"]


def embed(w):
    import torch
    from torchaudio.compliance import kaldi

    feats = kaldi.fbank(torch.from_numpy(w).unsqueeze(0) * 32768, num_mel_bins=80, frame_length=25,
                        frame_shift=10, dither=0, sample_frequency=16000, window_type="hamming", use_energy=False)
    feats = feats - feats.mean(0, keepdim=True)
    s = session()
    e = s.run(None, {s.get_inputs()[0].name: feats.unsqueeze(0).numpy()})[0].reshape(-1)
    return e / np.linalg.norm(e)


NOISE_FLOOR_DBFS = None  # set from --noise-floor; digital silence distorts the embedding


def with_floor(w, seed):
    if NOISE_FLOOR_DBFS is None:
        return w
    noise = np.random.default_rng(seed).standard_normal(len(w)).astype(np.float32)
    return w + noise * 10.0 ** (NOISE_FLOOR_DBFS / 20.0)


def score(job):
    rid, enroll_path, mix_path = job
    enroll, _ = sf.read(enroll_path, dtype="float32", frames=ENROLL)
    enroll = np.pad(enroll, (0, ENROLL - len(enroll)))
    mix, _ = sf.read(mix_path, dtype="float32")
    return rid, float(embed(with_floor(enroll, 1)) @ embed(with_floor(mix, 2)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--version", default="v2-20261013")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--noise-floor", type=float, help="add white noise at this dBFS before embedding")
    args = parser.parse_args()
    global NOISE_FLOOR_DBFS
    NOISE_FLOOR_DBFS = args.noise_floor
    root = Path(json.loads(args.roots.read_text())["ts_asr_benchmark"])
    index = {}
    with gzip.open(root / "versions" / args.version / "audio-index.jsonl.gz", "rt") as stream:
        for line in stream:
            r = json.loads(line)
            index[r["cut_id"]] = root / r["relative_path"]
    jobs = []
    for path in sorted((root / "versions" / args.version / "records").glob("*.jsonl.gz")):
        with gzip.open(path, "rt") as stream:
            for line in stream:
                r = json.loads(line)
                enroll, mix = (index[s["ref"]["cut_id"]] for s in r["audio_slots"])
                jobs.append((r["id"], str(enroll), str(mix)))
    os.environ["OMP_NUM_THREADS"] = "1"
    with ProcessPoolExecutor(args.workers) as pool:
        scores = dict(pool.map(score, jobs, chunksize=16))
    args.output.write_text(json.dumps(scores))
    print(f"{len(scores)} scores -> {args.output}")


if __name__ == "__main__":
    main()
