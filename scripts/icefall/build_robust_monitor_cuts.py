#!/usr/bin/env python3
"""Build a small deterministic eval set matching the robust train augmentations."""

from __future__ import annotations

import argparse
import hashlib
import logging
import math
from pathlib import Path

from consumer import icefall_root

icefall_root()


import numpy as np
import soundfile as sf
from diagnose_absolute_level import iter_testsets, stable_sample
from diagnose_foreground_snr import (
    build_variants,
    make_noise_window,
    pair_noise,
    stable_noise_pool,
)
from lhotse import CutSet, Recording, SupervisionSegment
from lhotse.utils import fastcopy
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

logger = logging.getLogger(__name__)


CONDITIONS = (
    "clean",
    "foreground_snr5",
    "foreground_snr0",
    "local_gain_snr5",
    "narrowband",
    "eq_bandpass",
    "rir",
    "clipping",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成与 robust augmentation 一一对应的固定 police 监控集。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE/eval_robust_monitor"),
    )
    parser.add_argument(
        "--noise-manifest",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE/traffic_noise_cuts.jsonl.gz"),
    )
    parser.add_argument("--max-cuts-per-split", type=int, default=20)
    parser.add_argument("--lhotse-root", default="/ai_sds_wuzz/DATA_ASR/LHOTSE")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _safe_peak(samples: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(samples)))
    limit = 10.0 ** (-1.0 / 20.0)
    if peak > limit:
        samples = samples * np.float32(limit / peak)
    return np.asarray(samples, dtype=np.float32)


def _narrowband(samples: np.ndarray) -> np.ndarray:
    down = resample_poly(samples, 1, 2).astype(np.float32)
    mu = 255.0
    compressed = np.sign(down) * np.log1p(mu * np.abs(down)) / math.log1p(mu)
    codes = np.rint((compressed + 1.0) * 0.5 * mu)
    quantized = codes * (2.0 / mu) - 1.0
    decoded = np.sign(quantized) * np.expm1(np.abs(quantized) * math.log1p(mu)) / mu
    restored = resample_poly(decoded, 2, 1)[: len(samples)]
    return np.asarray(restored, dtype=np.float32)


def _bandpass(samples: np.ndarray) -> np.ndarray:
    sos = butter(2, (350.0, 3400.0), btype="bandpass", fs=16000, output="sos")
    return np.asarray(sosfilt(sos, samples), dtype=np.float32)


def _reverb(samples: np.ndarray, source_id: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(source_id.encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    impulse = np.zeros(6400, dtype=np.float32)
    impulse[0] = 1.0
    impulse[800] = 0.35
    impulse[1920] = 0.2
    tail = rng.standard_normal(len(impulse) - 320).astype(np.float32)
    tail *= np.exp(-np.arange(len(tail), dtype=np.float32) / 1500.0) * 0.012
    impulse[320:] += tail
    impulse /= max(float(np.sum(np.abs(impulse))), 1.0)
    return np.asarray(
        fftconvolve(samples, impulse, mode="full")[: len(samples)], dtype=np.float32
    )


def build_conditions(
    speech: np.ndarray, noise: np.ndarray, source_id: str
) -> dict[str, np.ndarray]:
    mixtures, _, _ = build_variants(speech, noise, [5.0, 0.0], 20.0)
    speech_scale_5 = np.float32(10.0 ** ((5.0 - 20.0) / 20.0))
    noise_at_anchor = mixtures["snr5"] - speech * speech_scale_5
    envelope = np.ones(len(speech), dtype=np.float32)
    start, end = round(0.3 * len(speech)), round(0.7 * len(speech))
    envelope[start:end] = np.float32(10.0 ** (-9.0 / 20.0))
    variants = {
        "clean": speech.copy(),
        "foreground_snr5": mixtures["snr5"],
        "foreground_snr0": mixtures["snr0"],
        "local_gain_snr5": speech * speech_scale_5 * envelope + noise_at_anchor,
        "narrowband": _narrowband(speech),
        "eq_bandpass": _bandpass(speech),
        "rir": _reverb(speech, source_id),
        "clipping": np.clip(speech * np.float32(10.0 ** (9.0 / 20.0)), -0.95, 0.95),
    }
    return {name: _safe_peak(variants[name]) for name in CONDITIONS}


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.max_cuts_per_split <= 0:
        raise SystemExit("--max-cuts-per-split must be positive")
    manifests = {
        name: args.output_dir / f"police_robust_monitor_{name}_cuts.jsonl.gz"
        for name in CONDITIONS
    }
    if not args.force and all(path.is_file() for path in manifests.values()):
        logger.info("Robust monitor manifests already exist; use --force to rebuild.")
        return

    noise_pool = stable_noise_pool(args.noise_manifest, 256)
    output = {name: [] for name in CONDITIONS}
    audio_root = args.output_dir / "audio"
    audio_root.mkdir(parents=True, exist_ok=True)
    for testset, cuts in iter_testsets(
        ["police_synthetic_zh_accent"], args.lhotse_root
    ):
        for cut in stable_sample(cuts, args.max_cuts_per_split):
            audio = cut.load_audio()
            speech = np.asarray(
                audio[0] if audio.ndim == 2 else audio, dtype=np.float32
            )
            noise = make_noise_window(pair_noise(cut.id, noise_pool), len(speech))
            variants = build_conditions(speech, noise, cut.id)
            source_supervision = cut.supervisions[0]
            for condition, samples in variants.items():
                recording_id = f"{condition}-{cut.id}"
                path = audio_root / condition / testset / f"{cut.id}.wav"
                path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(path, samples, 16000, subtype="PCM_16")
                recording = Recording.from_file(path, recording_id=recording_id)
                supervision = SupervisionSegment(
                    id=f"{condition}-{source_supervision.id}",
                    recording_id=recording_id,
                    start=0.0,
                    duration=recording.duration,
                    text=source_supervision.text,
                    language=source_supervision.language,
                    speaker=source_supervision.speaker,
                    custom={"source_cut_id": cut.id, "condition": condition},
                )
                output[condition].append(
                    fastcopy(
                        recording.to_cut(), id=recording_id, supervisions=[supervision]
                    )
                )

    for condition, cuts in output.items():
        CutSet.from_cuts(cuts).to_file(manifests[condition])
        logger.info("Wrote %s (%d cuts)", manifests[condition], len(cuts))


if __name__ == "__main__":
    main()
