#!/usr/bin/env python3
"""Speaker check of the Emilia2 single-speaker pairs of ts_real_train v3 (see build_ts_real_train_v3.py).

For every pair: the ERes2NetV2 cosine of the positive's enrollment with the window, and of the negative's
enrollment with the window (L2-normalized embeddings, the model of speaker_neighbors.py). The builder turns
these into keep / drop decisions with thresholds taken from the pairs themselves.

    python qc_ts_real_train_v3.py --records DIR/emilia2_1spk-unchecked.jsonl.gz \
        --index DIR/emilia2_1spk-unchecked-index.jsonl.gz --output DIR/qc.json --workers 16
"""

import argparse
import gzip
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

DATA = Path("/workspace/data")
MODEL = "/workspace/model/modelscope/models/iic--speech_eres2netv2_sv_zh-cn_16k-common/snapshots/master"
SR = 16000
_MODEL = None


def _init(threads):
    global _MODEL
    import torch
    from modelscope.pipelines import pipeline

    torch.set_num_threads(threads)
    _MODEL = pipeline(task="speaker-verification", model=MODEL, device="cpu")


def _read(path, ref):
    first = round(ref["start"] * SR)
    w, sr = sf.read(path, start=first, stop=first + round(ref["duration"] * SR), dtype="float32", always_2d=True)
    assert sr == SR, (path, sr)
    return w[:, 0]


def _embed(w):
    e = np.asarray(_MODEL([w], output_emb=True)["embs"])[0]
    return e / np.linalg.norm(e)


def _pair(job):
    number, window, pos, neg = job
    vectors = [_embed(_read(*item)) for item in (window, pos, neg)]
    return number, float(vectors[1] @ vectors[0]), float(vectors[2] @ vectors[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    with gzip.open(args.index, "rt") as stream:
        paths = {row["cut_id"]: str(DATA / row["relative_path"]) for row in map(json.loads, stream)}
    pairs = {}
    with gzip.open(args.records, "rt", encoding="utf-8") as stream:
        for r in map(json.loads, stream):
            enroll, mix = (s["ref"] for s in r["audio_slots"])
            slot = pairs.setdefault(r["labels"]["pair"], {})
            slot["window"] = (paths[mix["cut_id"]], mix)
            slot["pos" if r["labels"]["target_present"] else "neg"] = (paths[enroll["cut_id"]], enroll)
    jobs = [(n, p["window"], p["pos"], p["neg"]) for n, p in sorted(pairs.items())][: args.limit]
    out = {}
    with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(args.threads,)) as pool:
        for i, (number, pos, neg) in enumerate(pool.map(_pair, jobs, chunksize=8)):
            out[str(number)] = [round(pos, 4), round(neg, 4)]
            if i % 1000 == 0:
                print(i, len(jobs), flush=True)
    args.output.write_text(json.dumps(out) + "\n")
    print("pairs", len(out))


if __name__ == "__main__":
    main()
