#!/usr/bin/env python3
"""Speaker-embedding worker for ``voice_check.py`` (WeSpeaker ECAPA-TDNN512-LM, ONNX, CPU).

Runs in an environment with ``onnxruntime`` and ``torchaudio`` (not dependencies of this repository), as a
separate process: it writes the embedding size as one little-endian uint32, then answers each request (uint64
sample count, then that many float32 samples at 16 kHz) with that many float32 values of a unit-norm
embedding. Features as in ``scripts/ts_benchmark/speaker_embeddings.py``.

    <python with onnxruntime> scripts/ts_real/embed_worker.py --model voxceleb_ECAPA512_LM.onnx
"""

import argparse
import struct
import sys

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    import onnxruntime as ort
    import torch
    from torchaudio.compliance import kaldi

    torch.set_num_threads(1)
    options = ort.SessionOptions()
    options.intra_op_num_threads = args.threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(args.model, options, providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name

    def embed(w):
        feats = kaldi.fbank(torch.from_numpy(w).unsqueeze(0) * 32768, num_mel_bins=80, frame_length=25,
                            frame_shift=10, dither=0, sample_frequency=16000, window_type="hamming",
                            use_energy=False)
        feats = feats - feats.mean(0, keepdim=True)
        e = session.run(None, {name: feats.unsqueeze(0).numpy()})[0].reshape(-1).astype(np.float32)
        return e / np.linalg.norm(e)

    source, sink = sys.stdin.buffer, sys.stdout.buffer
    dim = len(embed(np.zeros(16000, dtype=np.float32)))
    sink.write(struct.pack("<I", dim))
    sink.flush()
    while True:
        header = source.read(8)
        if len(header) < 8:
            return
        (count,) = struct.unpack("<Q", header)
        w = np.frombuffer(source.read(4 * count), dtype="<f4").copy()
        sink.write(embed(w).astype("<f4").tobytes())
        sink.flush()


if __name__ == "__main__":
    main()
