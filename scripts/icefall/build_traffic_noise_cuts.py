#!/usr/bin/env python3
# Copyright    2026  Amphion Project
#
# See ../../../LICENSE for clarification regarding multiple authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0


"""为 lhotse 直读训练生成 traffic_noise_cuts.jsonl.gz（不带 fbank）。

本文件位于 egs/amphion/shared_amphion/build_traffic_noise_cuts.py（amphion 私
有共享层），被 zh_en / yue_en 等 amphion recipe 通过 ASR/build_traffic_noise_cuts.py
软链复用。设计动机与 build_musan_cuts.py 完全一致，参见该文件文档；这里只补
充 traffic-noise 特有的处理。

数据来源：AudioSet RoadTraffic 子集
    /ai_sds_wuzz/MULTILINGUAL_DATA/noise/AudioSet_RoadTraffic/data/manifests/
        audioset_road_traffic_recordings_noise.jsonl.gz
        audioset_road_traffic_supervisions_noise.jsonl.gz   ← 不需要

录音特点：
- 已经统一切成 10 秒整段（0..10s），无需 cut_into_windows。
- 48 kHz / stereo (channels: [0, 1])。MUSAN 是 16 kHz / mono；为了让 lhotse
  CutMix 与 mono 训练 cut 混合时行为与 MUSAN 完全一致，本脚本在 build 阶段
  做两件事：
    1) .with_channels(0) 取第一个声道，输出 MonoCut；
    2) .resample(_TARGET_SAMPLING_RATE=16000) 把采样率与 16 kHz 训练 cut 对齐。

  关于 (2)，lhotse Cut.resample 是 lazy 的：只更新 metadata 把 sampling_rate
  字段改写成 16000，并把 resample 操作挂到 recording 的 transform 链上，实际
  重采样发生在 dataloader worker 调 cut.load_audio() 时，磁盘零开销，cuts 文件
  依旧只是几 MB 元数据。这一步不能省——lhotse/cut/set.py 的 mix() 在
  reference_cut.sampling_rate != mixed_in_cut.sampling_rate 时会硬性 assert
  失败（"Cannot mix cuts with different sampling rates"），CutMix 不会自动
  按目标 cut SR 重采样。

amphion/{zh_en,yue_en}/ASR/zipformer/asr_datamodule.py 在
enable_traffic_noise=True 时按下面的逻辑装载 traffic noise（与 MUSAN 并行）。
load 完后还会做一次防御性 .resample(16000)，兼容旧的 48 kHz cuts 文件，对
新生成的 16 kHz cuts 是 no-op：

    cuts_traffic = load_manifest(<manifest_dir>/traffic_noise_cuts.jsonl.gz)
    cuts_traffic = cuts_traffic.resample(16000)  # 防御性兜底
    transforms.append(
        CutMix(cuts=cuts_traffic, p=traffic_noise_prob,
               snr=traffic_noise_snr, preserve_id=True))

用法：
    # 默认输入 / 输出
    python3 ./build_traffic_noise_cuts.py \\
        --lhotse-root /ai_sds_wuzz/DATA_ASR/LHOTSE

    # 自定义输入 / 输出
    python3 ./build_traffic_noise_cuts.py \\
        --recordings-jsonl /path/to/audioset_road_traffic_recordings_noise.jsonl.gz \\
        --output /path/to/traffic_noise_cuts.jsonl.gz

输出：
    <output> 默认是 <lhotse-root>/traffic_noise_cuts.jsonl.gz；这是
    train.py（lhotse 模式）兜底搜索 traffic noise 的位置（见
    shared_amphion/zipformer/train.py 中紧跟 musan 兜底之后的 traffic-noise
    分支）。
"""

import argparse
import dataclasses
import logging
from pathlib import Path

from lhotse import CutSet, RecordingSet

logger = logging.getLogger(__name__)


_DEFAULT_RECORDINGS = Path(
    "/ai_sds_wuzz/MULTILINGUAL_DATA/noise/AudioSet_RoadTraffic/data/manifests/"
    "audioset_road_traffic_recordings_noise.jsonl.gz"
)

# 与 16 kHz 训练 cut（librispeech / cumix2017 / wenetspeech_yue / ...）以及
# MUSAN 对齐。CutMix 的 mix() 实现强制 reference 与 mixed-in 两侧 SR 完全相同。
_TARGET_SAMPLING_RATE = 16000


def _to_mono_first_channel(cut):
    # AudioSet RoadTraffic 录音都是 stereo (channels: [0, 1])，from_manifests
    # 出来是 MultiCut；with_channels(0) 取第一个声道转成 MonoCut。
    # 已经是 mono 时（防御性兜底）原样返回。
    if (
        hasattr(cut, "channel")
        and isinstance(cut.channel, list)
        and len(cut.channel) > 1
    ):
        return cut.with_channels(0)
    return cut


def _snap_to_integer_samples(c):
    """Snap ``cut.duration`` to ``round(d * sr) / sr``.

    Why: 48 kHz -> 16 kHz resample is lazy in lhotse (only metadata is
    updated, real resampling happens on load_audio). However, if the
    source ``recording.duration`` happens to be non-integer at either
    sample rate, the cut's ``duration`` may carry float precision past
    lhotse's 8-digit ``MixedCut.duration`` rounding. lhotse CutMix's
    ``mixed_in_duration`` tracker accumulates the *unrounded* value, so
    the next ``mix(offset_other_by=mixed_in_duration)`` call can fail
    the ``offset <= reference_cut.duration`` assert by ~1e-9 s. Snapping
    here makes ``duration == num_samples / sr`` bit-identically, killing
    the drift at the source.

    Idempotent and metadata-only. AudioSet RoadTraffic recordings are
    already at 10.0 s exactly, so this is a no-op in practice; we keep
    it as a defensive guard in case upstream ever produces non-round
    durations (e.g. clip-by-event with non-integer offsets).
    """
    sr = c.sampling_rate
    n_samples = round(c.duration * sr)
    snapped = n_samples / sr
    if abs(snapped - c.duration) < 1e-12:
        return c
    return dataclasses.replace(c, duration=snapped)


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--lhotse-root",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE"),
        help="LHOTSE root directory; used to compute the default --output "
        "if it is not provided.",
    )
    parser.add_argument(
        "--recordings-jsonl",
        type=Path,
        default=_DEFAULT_RECORDINGS,
        help="Path to AudioSet RoadTraffic recordings manifest "
        "(audioset_road_traffic_recordings_noise.jsonl.gz).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output traffic_noise_cuts.jsonl.gz path. "
        "Defaults to <lhotse-root>/traffic_noise_cuts.jsonl.gz, which is the "
        "path that the amphion lhotse-direct training pipeline searches for.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing output file. Without --force we skip "
        "if the output file already exists.",
    )
    return parser.parse_args()


def main():
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)

    args = get_args()

    output = args.output or (args.lhotse_root / "traffic_noise_cuts.jsonl.gz")

    if output.is_file() and not args.force:
        logger.info(f"{output} already exists - skipping (pass --force to overwrite).")
        return

    if not args.recordings_jsonl.is_file():
        raise FileNotFoundError(
            f"AudioSet RoadTraffic recordings manifest not found: "
            f"{args.recordings_jsonl}. Pass --recordings-jsonl explicitly."
        )

    logger.info(f"Reading recordings from {args.recordings_jsonl}")
    recordings = RecordingSet.from_jsonl_lazy(str(args.recordings_jsonl))

    cuts = (
        CutSet.from_manifests(recordings=recordings)
        .map(_to_mono_first_channel)
        .resample(_TARGET_SAMPLING_RATE)
        # Defensive: snap to integer-sample boundary post-resample so
        # downstream CutMix's mixed_in_duration tracker doesn't drift
        # past lhotse's MixedCut.duration 8-digit rounding (see docstring
        # of _snap_to_integer_samples and docs/training_lessons.md §1.7).
        .map(_snap_to_integer_samples)
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    cuts.to_file(output)

    eager = CutSet.from_file(output)
    n = len(eager)
    total_dur = sum(c.duration for c in eager)
    sample_cut = eager[0] if n > 0 else None
    sample_sr = sample_cut.sampling_rate if sample_cut else "n/a"
    logger.info(
        f"Wrote {output} ({n} cuts, total duration ≈ {total_dur / 3600:.2f} h, "
        f"sample sr={sample_sr})"
    )
    if sample_cut is not None and sample_cut.sampling_rate != _TARGET_SAMPLING_RATE:
        # 几乎不可能进来；放着是为了让未来 lhotse 改 resample 语义时第一时间
        # 暴露问题，而不是在训练 dataloader 里以 AssertionError 形式炸出。
        raise RuntimeError(
            f"Expected sampling_rate={_TARGET_SAMPLING_RATE} after lazy resample, "
            f"got {sample_cut.sampling_rate}. CutMix would assert-fail at train time."
        )
    logger.info(
        "Note: this manifest carries only recording metadata (no fbank). "
        "Cuts are lazily resampled to %d Hz so they can be mixed into "
        "%d Hz training cuts via lhotse CutMix (which requires identical "
        "sampling rates on both sides). Real resampling happens in the "
        "dataloader worker on cut.load_audio(); fbank is computed after "
        "mixing by OnTheFlyFeatures, so precomputing fbank is unnecessary "
        "in the lhotse-direct training mode.",
        _TARGET_SAMPLING_RATE,
        _TARGET_SAMPLING_RATE,
    )


if __name__ == "__main__":
    main()
