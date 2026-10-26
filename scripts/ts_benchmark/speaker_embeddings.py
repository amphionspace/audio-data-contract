#!/usr/bin/env python3
"""Speaker embeddings for choosing hard negatives (WeSpeaker ECAPA-TDNN512-LM, ONNX).

Writes an ``.npz`` with ``keys`` (speaker ids as used by the recipe pools) and
``vectors`` (unit-norm, mean of up to three utterances). The recipe's recorded
registrations (``enrollment_files``) are added as ``file:<name>``, one vector per
recording. Needs ``onnxruntime`` and
``torchaudio``, which are not dependencies of this repository.

    python scripts/ts_benchmark/speaker_embeddings.py --roots roots.json --output embeddings.npz
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

from audio_data_contract import load_catalog

MODEL = "/workspace/model/wespeaker-ecapa-tdnn512-LM/voxceleb_ECAPA512_LM.onnx"
UTTERANCES_PER_SPEAKER = 3


def main():
    import onnxruntime as ort
    import torch
    from torchaudio.compliance import kaldi

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=Path(__file__).with_name("recipe.yaml"))
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    roots = json.loads(args.roots.read_text())
    pools = build.build_pools(recipe, load_catalog(args.catalog), roots)
    session = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name

    def embed(w):
        feats = kaldi.fbank(torch.from_numpy(w).unsqueeze(0) * 32768, num_mel_bins=80, frame_length=25,
                            frame_shift=10, dither=0, sample_frequency=16000, window_type="hamming",
                            use_energy=False)
        feats = feats - feats.mean(0, keepdim=True)
        e = session.run(None, {name: feats.unsqueeze(0).numpy()})[0].reshape(-1)
        return e / np.linalg.norm(e)

    rng = random.Random(recipe["seed"])
    keys, vectors = [], []
    for speaker, utts in sorted(pools["mixed"]["speakers"].items()):
        chosen = rng.sample(utts, min(UTTERANCES_PER_SPEAKER, len(utts)))
        mean = np.mean([embed(build.read_audio(u.path)) for u in chosen], axis=0)
        keys.append(speaker)
        vectors.append(mean / np.linalg.norm(mean))
    for recording, path in sorted(build.enrollment_files(recipe, roots).items()):
        keys.append(f"file:{recording}")
        vectors.append(embed(build.read_audio(path)))
    np.savez(args.output, keys=np.array(keys), vectors=np.stack(vectors).astype(np.float32))
    print(f"{len(keys)} speakers -> {args.output}")


if __name__ == "__main__":
    main()
