#!/usr/bin/env python3
# Copyright    2024  amphion (shared)
#
# CLI front-end for shared_amphion/zipformer/text_norm.py.
#
# 目的：把训练侧的 per-language 归一化 pipeline 暴露成一个可批量处理文本文件
# 的命令行工具，主要使用场景：
#
#   1. 未来重训 BBPE / 字表时，把训练语料里 zh / yue / en 的句子按对应 normalizer
#      重写一遍（详见 prepare.sh stage 4 周边代码），保证 BBPE 训练目标与运行时
#      MultiDataset._tag_language 后输出的 supervision.text 处于同一字符空间。
#
#   2. 离线调试 / 数据审查：肉眼对比某条句子归一化前后的差异。
#
# 不在训练循环中调用本脚本（训练侧直接 import text_norm.get_language_normalizers
# 以避免子进程开销）。
#
# 用法：
#   ./local/normalize_text_by_language.py --language zh \
#     --input data/lang_bbpe_chars_12000/text \
#     --output data/lang_bbpe_chars_12000/text.norm \
#     --cache-dir data/wetext_fst_cache
#
#   # 从 stdin 读、写 stdout：
#   echo '香港人發明咗茶餐廳' | ./local/normalize_text_by_language.py --language zh
#
# 此文件是 shared 实现；zh_en/ASR/local/ 与 yue_en/ASR/local/ 通过软链复用，
# 参考 train_bbpe_model.py 的 fork 模式。

from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

# text_norm.py lives in shared_amphion/zipformer/, which prepare.sh does not
# add to PYTHONPATH (only repo_root is exported). Resolve the symlink and
# inject the zipformer dir ourselves so the CLI works from any leaf recipe.
from consumer import icefall_root

icefall_root()

from text_norm import get_language_normalizers, normalize_text


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Per-language text normalization CLI; see "
        "shared_amphion/zipformer/text_norm.py for the per-language "
        "best-practice registry and dependency install steps.",
    )
    parser.add_argument(
        "--language",
        type=str,
        required=True,
        help="Language code (e.g. zh / yue / en). Unregistered languages "
        "fall back to Identity passthrough.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default="-",
        help="Input text file (one sentence per line). Use '-' for stdin.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="-",
        help="Output text file. Use '-' for stdout. Parent directories are "
        "created on demand.",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="data/wetext_fst_cache",
        help="WeTextProcessing FST cache directory. Pass empty ('') to fall "
        "back to the package default (site-packages/tn/).",
    )
    return parser.parse_args()


def main() -> None:
    args = get_args()

    cache_dir = args.cache_dir or None
    # Build (and cache) the normalizer once; iterating over normalize_text
    # would also hit the cache but the explicit call documents the warmup.
    get_language_normalizers(cache_dir=cache_dir)

    with ExitStack() as stack:
        in_stream = (
            sys.stdin
            if args.input == "-"
            else stack.enter_context(open(args.input, encoding="utf-8"))
        )
        if args.output == "-":
            out_stream = sys.stdout
        else:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_stream = stack.enter_context(open(out_path, "w", encoding="utf-8"))
        for line in in_stream:
            normalized = normalize_text(
                line.rstrip("\n"), language=args.language, cache_dir=cache_dir
            )
            out_stream.write(normalized + "\n")


if __name__ == "__main__":
    main()
