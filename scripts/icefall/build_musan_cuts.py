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


"""为 lhotse 直读训练生成 musan_cuts.jsonl.gz（不带 fbank）。

本文件位于 egs/amphion/shared_amphion/build_musan_cuts.py（amphion 私有共享
层），被 zh_en / yue_en 等多个 amphion recipe 通过 ASR/build_musan_cuts.py
软链复用。注意不能放到各 recipe 的 ASR/local/ 下，因为 ASR/local 整体软链
到 egs/multi_zh_en/ASR/local，写入会污染上游 recipe（违反 AGENTS.md 第 3
节"不要修改 amphion 之外文件"的黄金规则）。

amphion/{zh_en,yue_en}/ASR/zipformer/asr_datamodule.py 在 enable_musan=True
时会按下面的逻辑装载 MUSAN：

    cuts_musan = load_manifest(<manifest_dir>/musan_cuts.jsonl.gz)
    transforms.append(CutMix(cuts=cuts_musan, p=0.5, snr=(10, 20), preserve_id=True))

在 lhotse 直读 + OnTheFlyFeatures 训练流程中：
- CutMix 是 cut 级别的 transform，按音频层混合，无需预先计算 fbank。
- fbank 在 input_strategy（OnTheFlyFeatures）那一层即时计算，输入是混合后
  的音频。因此本脚本产出的 musan_cuts.jsonl.gz 只携带 recording 元数据，不
  调用 compute_and_store_features，磁盘和准备时间都极低（<1 秒，<1 MB）。

行为对齐 librispeech/ASR/local/compute_fbank_musan.py 的切片策略：
- music + noise + speech 三类合并成一个 RecordingSet
- 每条录音 cut_into_windows(10.0) 切成 10 秒一段
- 过滤掉 < min_duration 秒的尾巴（默认 5 秒，跟上游 is_cut_long 一致）

用法：
    # 默认：从 LHOTSE/MUSAN/data/manifests 读，写到 LHOTSE/musan_cuts.jsonl.gz
    python3 ./build_musan_cuts.py \\
        --lhotse-root /ai_sds_wuzz/DATA_ASR/LHOTSE

    # 自定义输入/输出
    python3 ./build_musan_cuts.py \\
        --musan-manifests-dir /path/to/MUSAN/data/manifests \\
        --output /path/to/musan_cuts.jsonl.gz

输出：
    <output> 默认是 <lhotse-root>/musan_cuts.jsonl.gz；这是
    train.py（lhotse 模式）兜底搜索 MUSAN 的位置（见 train.py 1757-1765 行）。
"""

import argparse
import dataclasses
import logging
from pathlib import Path

from lhotse import CutSet, combine
from lhotse.recipes.utils import read_manifests_if_cached

logger = logging.getLogger(__name__)


def _is_long_enough(min_duration: float):
    """Return a top-level filter callable so lhotse doesn't warn about lambdas
    leaking into multiprocessing workers (LazyFilter UserWarning).
    """

    def _f(c):
        return c.duration > min_duration

    return _f


def _snap_to_integer_samples(c):
    """Snap ``cut.duration`` to the nearest integer-sample boundary.

    Why: lhotse's ``CutMix`` (and our ``_CutMixAllowPadding`` wrapper) tracks
    a running ``mixed_in_duration`` from raw ``noise_cut.duration`` while
    ``MixedCut.duration`` is rounded to 8 digits inside lhotse. If
    ``noise.duration`` carries precision past 8 digits (e.g. after a
    sample-rate change that doesn't divide evenly), the two diverge by
    ~1e-9 s and the next ``mix(..., offset_other_by=mixed_in_duration)``
    fails the ``offset <= reference_cut.duration`` assert. Snapping the
    duration at build time keeps it bit-identical to ``num_samples / sr``
    so the tracker never accumulates float drift.

    Idempotent and metadata-only: no audio is re-decoded; on cuts already
    at integer-sample boundaries (the common case post cut_into_windows)
    this returns the input unchanged.
    """
    sr = c.sampling_rate
    n_samples = round(c.duration * sr)
    snapped = n_samples / sr
    if abs(snapped - c.duration) < 1e-12:
        return c
    return dataclasses.replace(c, duration=snapped)


def _make_cuts(recordings, window: float, min_duration: float) -> CutSet:
    return (
        CutSet.from_manifests(recordings=recordings)
        .cut_into_windows(window)
        .filter(_is_long_enough(min_duration))
        .map(_snap_to_integer_samples)
    )


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--lhotse-root",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE"),
        help="LHOTSE root directory; used to compute defaults for "
        "--musan-manifests-dir and --output if those are not provided.",
    )
    parser.add_argument(
        "--musan-manifests-dir",
        type=Path,
        default=None,
        help="Directory containing musan_recordings_{music,noise,speech}.jsonl.gz. "
        "Defaults to <lhotse-root>/MUSAN/data/manifests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output musan_cuts.jsonl.gz path. "
        "Defaults to <lhotse-root>/musan_cuts.jsonl.gz, which is exactly the "
        "path that the amphion lhotse-direct training pipeline searches for.",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=10.0,
        help="Window size (seconds) for cut_into_windows.",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=5.0,
        help="Drop cuts shorter than this many seconds (the trailing window).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing output file. Without --force we skip "
        "if the output file already exists.",
    )
    parser.add_argument(
        "--write-category-manifests",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Also write musan_{noise,music,speech}_cuts.jsonl.gz next to "
            "--output for weighted, mutually exclusive category sampling."
        ),
    )
    return parser.parse_args()


def main():
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)

    args = get_args()

    musan_dir = args.musan_manifests_dir or (
        args.lhotse_root / "MUSAN" / "data" / "manifests"
    )
    output = args.output or (args.lhotse_root / "musan_cuts.jsonl.gz")
    category_outputs = {
        name: output.with_name(f"musan_{name}_cuts.jsonl.gz")
        for name in ("noise", "music", "speech")
    }
    expected_outputs = [output]
    if args.write_category_manifests:
        expected_outputs.extend(category_outputs.values())

    if all(path.is_file() for path in expected_outputs) and not args.force:
        logger.info(
            "All MUSAN cut manifests already exist - skipping "
            "(pass --force to overwrite)."
        )
        return

    if not musan_dir.is_dir():
        raise FileNotFoundError(
            f"MUSAN manifests dir {musan_dir} not found. "
            "Pass --musan-manifests-dir explicitly if it lives elsewhere."
        )

    logger.info(f"Reading MUSAN recordings from {musan_dir}")
    manifests = read_manifests_if_cached(
        dataset_parts=("music", "speech", "noise"),
        output_dir=musan_dir,
        prefix="musan",
        suffix="jsonl.gz",
    )
    if not manifests:
        raise RuntimeError(
            f"No musan_recordings_{{music,speech,noise}}.jsonl.gz found under "
            f"{musan_dir}; nothing to combine."
        )

    parts_with_recordings = [
        name for name, m in manifests.items() if m.get("recordings") is not None
    ]
    logger.info(f"Found MUSAN parts: {parts_with_recordings}")
    assert parts_with_recordings, manifests.keys()

    combined = combine(manifests[name]["recordings"] for name in parts_with_recordings)
    logger.info(f"Combined RecordingSet: {len(combined)} recordings")

    musan_cuts = _make_cuts(combined, args.window, args.min_duration)

    output.parent.mkdir(parents=True, exist_ok=True)
    if args.force or not output.is_file():
        musan_cuts.to_file(output)

    if args.write_category_manifests:
        for name in parts_with_recordings:
            category_output = category_outputs[name]
            if category_output.is_file() and not args.force:
                continue
            category_cuts = _make_cuts(
                manifests[name]["recordings"], args.window, args.min_duration
            )
            category_cuts.to_file(category_output)
            logger.info("Wrote category manifest %s", category_output)

    eager = CutSet.from_file(output)
    n = len(eager)
    total_dur = sum(c.duration for c in eager)
    logger.info(f"Wrote {output} ({n} cuts, total duration ≈ {total_dur / 3600:.2f} h)")
    logger.info(
        "Note: this manifest carries only recording metadata (no fbank). "
        "lhotse CutMix mixes audio at the cut level and OnTheFlyFeatures will "
        "compute fbank after mixing, so precomputing fbank for MUSAN is "
        "unnecessary in the lhotse-direct training mode."
    )


if __name__ == "__main__":
    main()
