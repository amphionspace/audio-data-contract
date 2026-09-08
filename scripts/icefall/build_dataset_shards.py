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


"""为 --shard-rotation 训练把 capped 数据集离线切成每片固定大小的 shard。

本文件位于 egs/amphion/shared_amphion/build_dataset_shards.py（amphion 私有
共享层），被 zh_en / yue_en 等 recipe 通过 ASR/build_dataset_shards.py 软链
复用（与 build_musan_cuts.py 同理；不能放进 ./local/，那是 multi_zh_en 的
软链，写入会污染上游 recipe，违反 AGENTS.md 黄金规则）。

背景与动机见 docs/full_data_shard_rotation.md。一句话：训练侧
multi_dataset.py 在 --shard-rotation 下对每个 capped 数据集按
shard[epoch % num_shards] 取片，多 epoch 即确定性覆盖全量；本脚本负责离线
产出这些 shard。

行为
====
对 --train-dataset-samples 中的每个 ``name=cap``：

    cuts = make_dataset(name, lhotse_root, use_punc, target_sr).train_cuts()
    if shuffle:
        cuts = cuts.shuffle(buffer_size=..., rng=seed)   # 缓解单片域集中
    cuts.split_lazy(output_dir=<shard_dir>/<name>, chunk_size=cap, prefix=name)

产出 ``<shard_dir>/<name>/<name>.NNNNNNNN.jsonl.gz``，每片 cap 条（末片可能
少）。num_shards = ceil(全量 / cap)。``cap >= 全量`` 的小集只产 1 片（等价于
每 epoch 全量），无害——训练侧 epoch % 1 == 0 永远取该片。

重要约束
========
``--use-punc`` / ``--target-sampling-rate`` 必须与 train.sh 一致，否则 shard
内的 cut 与训练期望不符（manifest 变体选择 / 重采样标记不同）。默认值已对齐
train.sh（use_punc=0, target_sr=16000）。

shuffle 说明
============
lhotse 的 ``CutSet.shuffle`` 是 buffer-based reservoir，buffer_size 远小于
全量时只能做窗口内打散。若 manifest 全局按说话人/录制时间强排序、需要更彻底
的打散，请把 --shuffle-buffer 调到接近单片 cap 的量级，或先对 manifest 做
一次性外部 shuf 再跑本脚本。详见 docs/full_data_shard_rotation.md §5。

用法
====
    # 一次性预处理：传与 train.sh 的 TRAIN_DATASET_SAMPLES 一致的字符串
    python3 ./build_dataset_shards.py \\
        --lhotse-root /ai_sds_wuzz/DATA_ASR/LHOTSE \\
        --shard-dir ../../data/shards \\
        --train-dataset-samples "wenetspeech=1000000,gigaspeech=1000000,mls=500000"

    # 强制重切（删掉已有 shard）
    python3 ./build_dataset_shards.py ... --force
"""

import argparse
import logging
import random
from pathlib import Path

# lhotse_datasets / language_id 位于 shared_amphion/zipformer/。本脚本被软链进
# <recipe>/ASR/ 后从那里直接运行，__file__ 经 realpath 解析到 shared_amphion/
# 真身，故 zipformer 子目录可由它推出（不依赖 _setup_env.sh）。repo_root 仅作
# 兜底加入 sys.path。注意：本脚本刻意不 import icefall —— 其包 __init__ 会拉起
# k2/torch（icefall/decode.py: import k2），而离线切片只是 lhotse 的 manifest
# IO，不需要 ASR 框架。这样分片可在任何带 lhotse 的环境跑，无需 GPU/k2。
from consumer import icefall_root

icefall_root()

from lhotse_datasets import list_datasets, make_dataset

logger = logging.getLogger(__name__)


def str2bool(v):
    """argparse-friendly bool parser.

    Local copy of icefall.utils.str2bool so this script never imports the
    icefall package (whose __init__ pulls in k2/torch); see the sys.path note
    above for why offline sharding stays k2-free.
    """
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    if v.lower() in ("no", "false", "f", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"boolean value expected, got {v!r}")


def _parse_samples(s: str) -> "dict[str, int]":
    """Parse 'name=int,name=int' CSV into an ordered {name: cap} dict.

    Mirrors multi_dataset._parse_kv_int_csv but standalone (this script does
    not import the training module). Unknown dataset names raise so a typo in
    the CSV surfaces immediately instead of silently producing no shards.
    """
    out: dict[str, int] = {}
    known = set(list_datasets())
    for chunk in (x.strip() for x in s.split(",") if x.strip()):
        if "=" not in chunk:
            raise ValueError(
                f"--train-dataset-samples entry must be 'name=int', got {chunk!r}"
            )
        name, val = chunk.split("=", 1)
        name = name.strip()
        try:
            cap = int(val.strip())
        except ValueError as e:
            raise ValueError(
                f"--train-dataset-samples cap for {name!r} must be int, got {val!r}"
            ) from e
        if cap <= 0:
            raise ValueError(f"cap for {name!r} must be positive, got {cap}")
        if name not in known:
            raise ValueError(
                f"unknown dataset {name!r}; available: {', '.join(sorted(known))}"
            )
        if name in out:
            raise ValueError(f"duplicate dataset {name!r} in --train-dataset-samples")
        out[name] = cap
    if not out:
        raise ValueError("--train-dataset-samples parsed to empty; nothing to shard.")
    return out


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--lhotse-root",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE"),
        help="LHOTSE manifests root, passed to make_dataset "
        "(= train.py's --lhotse-root).",
    )
    parser.add_argument(
        "--shard-dir",
        type=Path,
        default=Path("../../data/shards"),
        help="Output root: shards go to "
        "<shard-dir>/<name>/<name>.NNNNNNNN.jsonl.gz. Must match train.py's "
        "--shard-dir.",
    )
    parser.add_argument(
        "--train-dataset-samples",
        type=str,
        required=True,
        help="CSV 'name=cap' (the same string as train.sh's "
        "TRAIN_DATASET_SAMPLES). Each listed dataset is split into shards of "
        "`cap` cuts.",
    )
    parser.add_argument(
        "--use-punc",
        type=str2bool,
        default=False,
        help="Must match train.py --use-punc so shard cuts pick the same "
        "manifest variant.",
    )
    parser.add_argument(
        "--target-sampling-rate",
        type=int,
        default=16000,
        help="Must match train.py --target-sampling-rate (the lazy resample "
        "marker is baked into the shard cuts). 0 disables resampling.",
    )
    parser.add_argument(
        "--shuffle",
        type=str2bool,
        default=True,
        help="Buffer-shuffle before splitting, to reduce per-shard domain "
        "clustering (see docstring).",
    )
    parser.add_argument(
        "--shuffle-buffer",
        type=int,
        default=100000,
        help="Reservoir buffer size for --shuffle. Larger = better mixing, "
        "more RAM (~buffer * cut_metadata_size).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for --shuffle, so shards are reproducible.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-split even if <shard-dir>/<name>/ already has shards "
        "(removes the existing ones first).",
    )
    return parser.parse_args()


def main():
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)

    args = get_args()
    samples = _parse_samples(args.train_dataset_samples)
    target_sr = args.target_sampling_rate or None  # 0 -> None (no resample)

    logger.info(
        f"Building shards for {len(samples)} dataset(s) under {args.shard_dir} "
        f"(use_punc={args.use_punc}, target_sr={target_sr}, "
        f"shuffle={args.shuffle}, buffer={args.shuffle_buffer}, seed={args.seed})."
    )

    for name, cap in samples.items():
        out_subdir = args.shard_dir / name
        existing = (
            sorted(out_subdir.glob(f"{name}.*.jsonl.gz")) if out_subdir.is_dir() else []
        )
        if existing and not args.force:
            logger.info(
                f"[{name}] {len(existing)} shard(s) already exist under "
                f"{out_subdir}; skipping (pass --force to re-split)."
            )
            continue
        if existing and args.force:
            logger.info(
                f"[{name}] --force: removing {len(existing)} existing shard(s) "
                f"under {out_subdir}."
            )
            for f in existing:
                f.unlink()

        logger.info(f"[{name}] loading train cuts ...")
        ds = make_dataset(
            name,
            args.lhotse_root,
            use_punc=args.use_punc,
            target_sampling_rate=target_sr,
        )
        cuts = ds.train_cuts()

        if args.shuffle:
            logger.info(
                f"[{name}] buffer-shuffling (buffer={args.shuffle_buffer}) "
                "before split ..."
            )
            cuts = cuts.shuffle(
                rng=random.Random(args.seed), buffer_size=args.shuffle_buffer
            )

        logger.info(
            f"[{name}] splitting into shards of {cap} cuts -> {out_subdir}/ "
            "(reads the full manifest once; may take a while for large corpora)."
        )
        shards = cuts.split_lazy(output_dir=out_subdir, chunk_size=cap, prefix=name)
        logger.info(
            f"[{name}] wrote {len(shards)} shard(s) (chunk_size={cap}). "
            f"{len(shards)} epochs cover this corpus once."
        )

    logger.info(
        "Done. Enable rotation in train.sh with "
        "`--shard-rotation 1 --shard-dir <shard-dir>` (shard-dir must match)."
    )


if __name__ == "__main__":
    main()
