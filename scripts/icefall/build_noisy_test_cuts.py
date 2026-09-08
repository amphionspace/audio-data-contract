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


"""为交通噪声鲁棒性评测预生成 deterministic 带噪测试 cuts。

本文件位于 egs/amphion/shared_amphion/build_noisy_test_cuts.py（amphion 私
有共享层），被 zh_en / yue_en 等 amphion recipe 通过
ASR/build_noisy_test_cuts.py 软链复用。

设计动机
========

训练侧用 ``_CutMixAllowPadding`` 在 dataloader 里把 AudioSet RoadTraffic
噪声随机混入到训练 cut（mix_prob=0.3、snr=(5,15) dB、每个 epoch 不同
seed）。测试侧没有对应路径：``AsrDataModule.test_dataloaders`` 不挂任何
cut_transforms。直接挪用训练时的 CutMix 到 test_dataloaders 有两个问题：

  1) 不 deterministic — sampler 每次重启都换 seed，跨 ckpt 跑出来的 WER
     差异里夹杂了噪声采样方差，无法解释哪部分是模型差异。
  2) 难以记录"用了什么 SNR、用了哪条 noise" — 复现需要额外补丁。

更干净的做法是把"混入"这件事一次性固化到磁盘：把 clean test 与 noise
经 ``CutSet.mix(..., seed=int, mix_prob=1.0).to_eager().to_file(...)`` 写成
新的 manifest。MixedCut 的 tracks 字段把 noise selection / offset / SNR
全部记录下来，``load_audio()`` 每次都按 tracks 描述合成同一份波形（PoC
已验证：bit-identical 即 ``np.array_equal``）。

输入
====

  * clean test cuts：复用 ``lhotse_datasets.DATASET_SPECS`` 注册的 4 个
    base test 集（用户在 plan 阶段拍板的"4 个核心代表"）。
  * 噪声 pool：``<lhotse_root>/traffic_noise_cuts.jsonl.gz``（由
    ``build_traffic_noise_cuts.py`` 产出，AudioSet RoadTraffic 16 kHz mono
    10 秒段）。

输出
====

每个 (base_sub, snr) 一个 jsonl.gz manifest，写到
``<lhotse_root>/eval_traffic/{base}_{sub}_traffic_noisy_snr{N}db_cuts.jsonl.gz``，
与 ``lhotse_datasets.py`` 中 noisy spec 的 ``cuts=`` 路径一致。文件只含
MixedCut metadata，audio bytes 仍引用原 source（base + noise 两份 source），
每个文件 < 10 MB，总开销 < 100 MB。

5 档 SNR × 5 个 base sub-split = 25 个文件：
  - librispeech_test_clean
  - librispeech_test_other
  - wenetspeech_test_net
  - mdcc_test
  - talcs_test

为什么不把 base test 集硬编码在 shared_amphion 而是从 lhotse_datasets 读：
将来想加风扇 / 空调 / babble 等噪声只需复用本脚本传不同的 noise source；
将来想换 base 集只需改 ``--bases`` CLI（默认就是 plan 拍板的 4 个核心）。

Determinism
===========

PoC 已验证（搭配 lhotse 1.33.0）：

  * 同一 (base, seed, snr) 二次 build 出来的 manifest 文件本身不一致
    （MixedCut 的 cut id 是 UUID4 随机生成），但**load_audio 后的 numpy
    数组完全 bit-identical**（``np.array_equal``）。
  * 同一 manifest 二次 load_audio 完全一致。
  * 长 ref cut（> 10s noise 长度）会自动拼接多条 noise 覆盖到
    ``ref_dur - 0.05s`` 处，最后 50 ms 是 lhotse LazyCutMixer 故意减去的
    边界保护（防止 0-frame noise edge case），对 fbank 评测无害。

每个 (base_sub, snr) 用独立派生 seed（base_seed XOR hash(base_sub, snr)），
避免 5 档 SNR 在同一条 ref cut 上抽到完全相同的 noise selection（不影响
正确性，但独立采样能让 SNR 阶梯之间的对比更"干净"）。

用法
====

  # 默认：生成 25 个文件到 <lhotse_root>/eval_traffic/
  python3 ./build_noisy_test_cuts.py

  # 只跑某个 SNR 子集
  python3 ./build_noisy_test_cuts.py --snrs 5,10,15

  # 自定义输出目录 + 覆盖已存在文件
  python3 ./build_noisy_test_cuts.py --output-dir /tmp/eval_traffic --force

  # 自定义 base 集（沿用 lhotse_datasets 注册名）
  python3 ./build_noisy_test_cuts.py \\
      --bases librispeech:test_clean,librispeech:test_other,mdcc:test
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path

# `lhotse_datasets` lives under shared_amphion/zipformer/ and depends on
# `language_id` (same dir). Add zipformer/ to sys.path so this script can
# `from lhotse_datasets import ...` without requiring the caller to set
# PYTHONPATH. Both modules pull only `lhotse` itself (no torch / k2),
# so import overhead is sub-second.
from consumer import icefall_root
from lhotse import CutSet

icefall_root()

from lhotse_datasets import make_dataset

logger = logging.getLogger(__name__)


# Default 4-base × 5-SNR matrix the user picked in the plan phase. Each
# entry is (registry_name, sub_filter_or_None). ``sub_filter=None`` means
# "use every sub-split the dataset exposes" (librispeech, mdcc, talcs);
# wenetspeech is explicitly narrowed to test_net per user instruction
# (test_meeting is a meeting-style domain, different from "general ASR
# under traffic noise" scope).
_DEFAULT_BASES: list[tuple[str, list[str] | None]] = [
    ("librispeech", None),  # test_clean + test_other
    ("wenetspeech", ["test_net"]),
    ("mdcc", None),  # single 'test' split
    ("talcs", None),  # single 'test' split
]

_DEFAULT_SNRS: list[int] = [0, 5, 10, 15, 20]
_DEFAULT_SEED: int = 12345
_TARGET_SAMPLING_RATE: int = 16000


def _parse_bases(s: str) -> list[tuple[str, list[str] | None]]:
    """Parse a CLI ``--bases`` spec.

    Two equivalent forms accepted::

        # explicit (sub-split per entry)
        --bases librispeech:test_clean,librispeech:test_other,mdcc:test

        # collapsed (all sub-splits of a dataset)
        --bases librispeech,mdcc,talcs

    Items can be mixed; e.g. ``wenetspeech:test_net,mdcc`` means
    "wenetspeech only test_net + mdcc's single test split".
    """
    by_base: dict[str, list[str] | None] = {}
    for chunk in [x.strip() for x in s.split(",") if x.strip()]:
        if ":" in chunk:
            base, sub = chunk.split(":", 1)
            base, sub = base.strip(), sub.strip()
            cur = by_base.get(base)
            if cur is None and base not in by_base:
                by_base[base] = [sub]
            elif cur is None:
                # already registered as "all subs"; an explicit sub is a no-op
                pass
            else:
                if sub not in cur:
                    cur.append(sub)
        else:
            by_base[chunk] = None  # all subs (overrides any prior sub list)
    return [(b, subs) for b, subs in by_base.items()]


def _collect_test_splits(
    base_name: str,
    sub_filter: Sequence[str] | None,
    lhotse_root: Path,
) -> dict[str, CutSet]:
    """Return ``{sub_name: clean_cuts}`` for one base dataset.

    Wraps the heterogeneous return type of
    ``LhotseDataset.test_cuts()`` (``CutSet`` for single-split datasets vs
    ``Dict[str, CutSet]`` for multi-split ones) into a uniform dict, so the
    caller can iterate (base, sub) pairs without branching. Single-split
    datasets get the synthetic sub-name ``"test"`` to keep output filenames
    self-describing.
    """
    # use_punc=False is fine for noisy eval: the supervisions text we
    # propagate is only used as ASR reference; punctuation choice is the
    # decode side's job (test.sh -s / --strip-punc).
    ds = make_dataset(
        base_name,
        lhotse_root,
        use_punc=False,
        target_sampling_rate=_TARGET_SAMPLING_RATE,
    )
    cuts = ds.test_cuts()
    if isinstance(cuts, dict):
        out = dict(cuts)
        if sub_filter is not None:
            missing = sorted(set(sub_filter) - set(out))
            if missing:
                raise KeyError(
                    f"Sub-split filter {sub_filter!r} for base {base_name!r} "
                    f"references unknown sub-splits: {missing}. "
                    f"Available: {sorted(out)}"
                )
            out = {k: v for k, v in out.items() if k in sub_filter}
        return out
    return {"test": cuts}


def _derive_seed(base_seed: int, base_sub: str, snr: int) -> int:
    """Stable 31-bit seed for one (base_sub, snr) build.

    XOR base_seed with a stable hash of (base_sub, snr) so different SNRs
    on the same base sample independent noise selections. Pure-Python
    ``hash()`` is salted per interpreter restart, so we roll a tiny custom
    deterministic hash. Mask to 31 bits to stay inside
    ``random.Random.seed`` happy range.
    """
    key = f"{base_sub}|snr={snr}".encode()
    h = 0
    for b in key:
        h = (h * 131 + b) & 0xFFFFFFFFFFFFFFFF
    return (base_seed ^ (h & 0x7FFFFFFF)) & 0x7FFFFFFF


def _build_one(
    base_sub_name: str,
    base_cuts: CutSet,
    noise_cuts: CutSet,
    snr: int,
    seed: int,
    output_path: Path,
) -> tuple[int, float]:
    """Mix one (base_sub, snr) and write the resulting MixedCut manifest.

    Returns (n_cuts, total_duration_seconds) for the produced manifest.
    """
    noisy = base_cuts.mix(
        cuts=noise_cuts,
        snr=snr,  # single float -> fixed SNR for every cut
        mix_prob=1.0,  # every clean cut MUST receive noise
        allow_padding=True,  # 8-decimal precision defense
        preserve_id="left",  # MixedCut.id == clean ref id
        seed=seed,  # int -> deterministic via Random(seed)
        random_mix_offset=True,  # if noise > ref, pick random sub-window
        tag="traffic_noise_eval",
    ).to_eager()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a sibling tmp file then atomic-rename. Critical detail:
    # ``CutSet.to_file`` picks the on-disk format (plain JSONL vs gzipped
    # JSONL) from the path suffix. If the tmp name appends ".tmp" so that
    # the suffix becomes ".jsonl.gz.tmp", lhotse writes uncompressed JSONL
    # under a file that *looks* like ".gz" — the rename then produces a
    # 假冒-gzip file that future loaders crash on with
    # ``gzip.BadGzipFile: Not a gzipped file (b'{"')``. Prefix the tmp
    # name instead so the .jsonl.gz suffix is preserved during write.
    tmp = output_path.with_name("~" + output_path.name)
    noisy.to_file(str(tmp))
    tmp.replace(output_path)

    n = len(noisy)
    total = float(sum(c.duration for c in noisy))
    return n, total


def get_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=__doc__,
    )
    p.add_argument(
        "--lhotse-root",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE"),
        help="LHOTSE root; default location of traffic_noise_cuts.jsonl.gz "
        "and the default --output-dir parent.",
    )
    p.add_argument(
        "--noise-cuts",
        type=Path,
        default=None,
        help="Override the noise CutSet path. Defaults to "
        "<lhotse_root>/traffic_noise_cuts.jsonl.gz.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for the generated noisy cuts. "
        "Defaults to <lhotse_root>/eval_traffic/.",
    )
    p.add_argument(
        "--snrs",
        type=str,
        default=",".join(str(x) for x in _DEFAULT_SNRS),
        help="Comma-separated SNR levels in dB.",
    )
    p.add_argument(
        "--bases",
        type=str,
        default="librispeech,wenetspeech:test_net,mdcc,talcs",
        help="Comma-separated base test-set names. Each item is either "
        "'<name>' (use all sub-splits exposed by lhotse_datasets) or "
        "'<name>:<sub_split>' (use only that sub-split).",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_SEED,
        help="Base seed; each (base_sub, snr) build derives an independent "
        "31-bit seed from it.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files. Without --force we skip "
        "files that already exist (the default; matches "
        "build_traffic_noise_cuts.py and build_musan_cuts.py).",
    )
    return p.parse_args()


def main() -> int:
    fmt = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=fmt, level=logging.INFO)

    args = get_args()
    snrs = [int(x) for x in args.snrs.split(",") if x.strip()]
    bases = _parse_bases(args.bases)
    noise_path = args.noise_cuts or (args.lhotse_root / "traffic_noise_cuts.jsonl.gz")
    out_dir = args.output_dir or (args.lhotse_root / "eval_traffic")

    if not noise_path.is_file():
        raise FileNotFoundError(
            f"Noise CutSet not found: {noise_path}. Run "
            "build_traffic_noise_cuts.py (prepare_from_lhotse.sh stage 14) first."
        )

    logger.info(f"lhotse_root  = {args.lhotse_root}")
    logger.info(f"noise_cuts   = {noise_path}")
    logger.info(f"output_dir   = {out_dir}")
    logger.info(f"snrs         = {snrs}")
    logger.info(f"bases        = {bases}")
    logger.info(f"base_seed    = {args.seed}")
    logger.info(f"force        = {args.force}")

    logger.info("loading noise CutSet (eager, ~%d cuts expected)", 109406)
    noise_cuts = (
        CutSet.from_file(str(noise_path)).resample(_TARGET_SAMPLING_RATE).to_eager()
    )
    logger.info(f"noise loaded: {len(noise_cuts)} cuts")

    # Build matrix of (base, sub, clean_cuts) up-front so a single typo in
    # --bases / missing manifest surfaces before any heavy work begins.
    plan: list[tuple[str, str, CutSet]] = []
    for base_name, sub_filter in bases:
        try:
            splits = _collect_test_splits(base_name, sub_filter, args.lhotse_root)
        except Exception:
            logger.exception("[%s] failed to load test cuts", base_name)
            return 2
        for sub_name, cuts in splits.items():
            plan.append((base_name, sub_name, cuts))

    total_jobs = len(plan) * len(snrs)
    logger.info(
        "planning %d (base_sub) × %d (snr) = %d build jobs",
        len(plan),
        len(snrs),
        total_jobs,
    )

    n_done, n_skipped, n_failed = 0, 0, 0
    job_idx = 0
    for base_name, sub_name, base_cuts in plan:
        base_sub = f"{base_name}_{sub_name}"
        # Materialize the clean cuts once per base_sub (eager), shared
        # across all SNR levels of this base. Avoids re-parsing the
        # lhotse manifest 5 times. wenetspeech_test_net (~25k cuts) is
        # the biggest; that's ~30 MB of cut metadata, trivial.
        base_eager = base_cuts.to_eager()
        n_base = len(base_eager)
        dur_base = float(sum(c.duration for c in base_eager))
        logger.info(
            f"[{base_sub}] base cuts: {n_base}, total dur {dur_base / 3600:.2f}h"
        )

        for snr in snrs:
            job_idx += 1
            out_path = out_dir / f"{base_sub}_traffic_noisy_snr{snr}db_cuts.jsonl.gz"
            tag = f"[{job_idx}/{total_jobs}] {base_sub} snr={snr}dB"
            if out_path.is_file() and not args.force:
                logger.info(f"{tag} skip (exists): {out_path}")
                n_skipped += 1
                continue
            seed = _derive_seed(args.seed, base_sub, snr)
            t0 = time.time()
            try:
                n_out, dur_out = _build_one(
                    base_sub_name=base_sub,
                    base_cuts=base_eager,
                    noise_cuts=noise_cuts,
                    snr=snr,
                    seed=seed,
                    output_path=out_path,
                )
            except Exception:
                logger.exception("%s FAILED", tag)
                n_failed += 1
                continue
            dt = time.time() - t0
            size_mb = out_path.stat().st_size / 1e6
            logger.info(
                f"{tag} wrote {out_path.name} "
                f"(n={n_out}, dur={dur_out / 3600:.2f}h, size={size_mb:.1f} MB, "
                f"seed={seed}, took {dt:.1f}s)"
            )
            n_done += 1

    logger.info(
        f"summary: done={n_done}, skipped={n_skipped}, failed={n_failed}, "
        f"total={total_jobs}"
    )
    logger.info(
        "Note: manifests carry only MixedCut metadata. Audio is still "
        "synthesized on the fly via MixedCut.load_audio() (mixing is "
        "deterministic per cut: noise selection / offset / SNR are pinned "
        "in cut.tracks). To pre-render audio bytes, use lhotse Shar "
        "export downstream of this script."
    )
    return 1 if n_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
