#!/usr/bin/env python3
"""Voice check of the TTS training enrollments (tts_training_enrollments.py): keep clips that sound like the speaker.

As enrollments only the voice matters (the transcript is never used), so the check is the ECAPA (WeSpeaker
ECAPA-TDNN512-LM) cosine between each clip and the real enrollment it was cloned from, against the cosine between
clips of different speakers. Clips below ``--min-cos`` are dropped; the kept list is ``utterances-qc.jsonl.gz`` and
the statistics ``qc.json`` (per kind and language). Needs ``onnxruntime``, ``torchaudio``.

The check fails (exit 3, ``qc.json`` written, kept list not written) when the data as a whole is unreliable rather than a few
clips being bad: ``--min-cos`` below the 99th percentile of the different-speaker cosine (the threshold would keep
clips that sound like someone else), or a kind/language group keeping less than ``--min-kept-ratio`` of its clips
(the synthesis for that group does not reproduce the voice; on v1-20261110 cross-zh kept 69%, mean cosine 0.49
against 0.673 for real Common Voice speakers across languages, and training on it went ahead unnoticed).

    python scripts/ts_benchmark/qc_tts_enrollments.py --root <version dir> --workers 32
"""

import argparse
import gzip
import json
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ECAPA = "/workspace/model/wespeaker-ecapa-tdnn512-LM/voxceleb_ECAPA512_LM.onnx"
DATA = Path("/workspace/data")
_session = None


def _embed(path):
    global _session
    import onnxruntime as ort
    import soundfile as sf
    import torch
    from torchaudio.compliance import kaldi

    if _session is None:
        torch.set_num_threads(1)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        _session = ort.InferenceSession(ECAPA, sess_options=options, providers=["CPUExecutionProvider"])
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    wav = wav.mean(axis=-1) if wav.ndim > 1 else wav
    if sr != 16000:
        from math import gcd

        from scipy.signal import resample_poly
        g = gcd(16000, sr)
        wav = resample_poly(wav, 16000 // g, sr // g).astype(np.float32)
    f = kaldi.fbank(torch.from_numpy(wav[: 16000 * 12]).unsqueeze(0) * 32768, num_mel_bins=80, frame_length=25,
                    frame_shift=10, dither=0.0, sample_frequency=16000, window_type="hamming", use_energy=False)
    f = f - f.mean(0, keepdim=True)
    e = _session.run(None, {_session.get_inputs()[0].name: f.unsqueeze(0).numpy()})[0].reshape(-1)
    return e / np.linalg.norm(e)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--min-cos", type=float, default=0.5,
                        help="drop clips below this cosine; must not be below the different-speaker p99 (0.475 on v1)")
    parser.add_argument("--min-kept-ratio", type=float, default=0.9,
                        help="fail when a kind/language group keeps less than this share of its clips")
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    with gzip.open(args.root / "utterances.jsonl.gz", "rt") as handle:
        rows = [json.loads(line) for line in handle]
    if not rows:
        raise SystemExit(f"no clips in {args.root / 'utterances.jsonl.gz'}")
    refs = sorted({r["ref_path"] for r in rows})
    with ProcessPoolExecutor(args.workers) as pool:
        ref_vec = dict(zip(refs, pool.map(_embed, [str(DATA / r) for r in refs], chunksize=16)))
        clip_vec = list(pool.map(_embed, [str(args.root / r["path"]) for r in rows], chunksize=16))
    for row, vector in zip(rows, clip_vec):
        row["voice_cos"] = round(float(vector @ ref_vec[row["ref_path"]]), 3)
    rng = random.Random(0)
    other = [float(clip_vec[i] @ ref_vec[rows[j]["ref_path"]]) for i, j in
             ((rng.randrange(len(rows)), rng.randrange(len(rows))) for _ in range(5000))
             if rows[i]["speaker"] != rows[j]["speaker"]]
    kept = [r for r in rows if r["voice_cos"] >= args.min_cos]
    stats = {"clips": len(rows), "kept": len(kept), "min_cos": args.min_cos,
             "different_speaker_cos": {"mean": round(float(np.mean(other)), 3), "p99": round(float(np.percentile(other, 99)), 3)},
             "by_kind_language": {}}
    for kind in ("cross", "same"):
        for lang in ("zh", "en"):
            part = [r["voice_cos"] for r in rows if r["kind"] == kind and r["language"] == lang]
            if part:
                stats["by_kind_language"][f"{kind}-{lang}"] = {
                    "clips": len(part), "mean_cos": round(float(np.mean(part)), 3),
                    "kept": sum(c >= args.min_cos for c in part)}
    stats["speakers_kept"] = len({r["speaker"] for r in kept})
    failures = []
    if args.min_cos < stats["different_speaker_cos"]["p99"]:
        failures.append(f"--min-cos {args.min_cos} is below the different-speaker p99 "
                        f"{stats['different_speaker_cos']['p99']}")
    for group, part in stats["by_kind_language"].items():
        if part["kept"] < args.min_kept_ratio * part["clips"]:
            failures.append(f"{group} keeps {part['kept']}/{part['clips']} (mean cosine {part['mean_cos']}), "
                            f"below --min-kept-ratio {args.min_kept_ratio}")
    stats["failures"] = failures
    (args.root / "qc.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))
    if failures:
        raise SystemExit(3)
    with gzip.open(args.root / "utterances-qc.jsonl.gz", "wt") as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
