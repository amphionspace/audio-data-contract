#!/usr/bin/env python3
# Copyright    2024  amphion/yue_en
#
# Compute fbank features for the CU-MIX 2017 (cumix2017) dataset, a
# Cantonese-English code-switching corpus from CUHK that mirrors the role of
# TAL-CSASR in zh-en code-switching but for yue-en.
#
# icefall has no cumix2017 recipe yet, so we own the fbank computation here
# (analogous to compute_fbank_mls.py in amphion/shared_amphion).
#
# Manifest naming (from /ai_sds_wuzz/DATA_ASR/LHOTSE/cumix2017/data/manifests):
#   cumix2017_recordings_all.jsonl.gz
#   cumix2017_supervisions_all.jsonl.gz
#   cumix2017_supervisions_all_cleaned.jsonl.gz  (preferred when --use-cleaned 1)
#
# CU-MIX 2017 only has a single split called "all" — we treat it entirely
# as training data (similar to aidatatang in zh_en).

import argparse
import logging
import os
from pathlib import Path

import torch
from consumer import icefall_root
from lhotse import CutSet, Fbank, FbankConfig, LilcomChunkyWriter, load_manifest_lazy

icefall_root()

from icefall.utils import get_executor, str2bool

logger = logging.getLogger(__name__)


torch.set_num_threads(1)
torch.set_num_interop_threads(1)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--num-mel-bins",
        type=int,
        default=80,
        help="The number of mel bins for Fbank.",
    )
    parser.add_argument(
        "--speed-perturb",
        type=str2bool,
        default=True,
        help="Apply 0.9/1.1 speed perturb on the train (=all) split.",
    )
    parser.add_argument(
        "--use-cleaned",
        type=str2bool,
        default=True,
        help="Prefer cumix2017_supervisions_all_cleaned.jsonl.gz when available.",
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("data/manifests/cumix2017"),
        help="Directory containing cumix2017_*.jsonl.gz manifests "
        "(symlinked from <lhotse_root>/cumix2017/data/manifests/ via "
        "prepare_from_lhotse.sh stage 1).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/fbank"),
        help="Directory to write fbank cuts.",
    )
    return parser.parse_args()


def compute_fbank_cumix2017(args):
    src_dir = args.src_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    num_jobs = min(15, os.cpu_count() or 1)

    rec_path = src_dir / "cumix2017_recordings_all.jsonl.gz"
    if args.use_cleaned:
        sup_path = src_dir / "cumix2017_supervisions_all_cleaned.jsonl.gz"
        if not sup_path.is_file():
            logger.warning(
                f"--use-cleaned True but {sup_path} not found, "
                "falling back to cumix2017_supervisions_all.jsonl.gz"
            )
            sup_path = src_dir / "cumix2017_supervisions_all.jsonl.gz"
    else:
        sup_path = src_dir / "cumix2017_supervisions_all.jsonl.gz"

    if not rec_path.is_file() or not sup_path.is_file():
        logger.warning(
            f"cumix2017 manifests not found:\n  {rec_path}\n  {sup_path}\n"
            "Skipping (this is fine if you don't have cumix2017)."
        )
        return

    partition = "all"
    cuts_filename = f"cumix2017_cuts_{partition}.jsonl.gz"
    if (output_dir / cuts_filename).is_file():
        logger.info(f"{partition} already exists - skipping.")
        return

    extractor = Fbank(FbankConfig(num_mel_bins=args.num_mel_bins))

    logger.info(f"Loading recordings from {rec_path}")
    recordings = load_manifest_lazy(str(rec_path))
    logger.info(f"Loading supervisions from {sup_path}")
    supervisions = load_manifest_lazy(str(sup_path))

    cut_set = CutSet.from_manifests(recordings=recordings, supervisions=supervisions)
    # cumix2017 cuts are short utterances already; just trim defensively.
    cut_set = cut_set.trim_to_supervisions(
        keep_overlapping=False, keep_all_channels=False
    )

    if args.speed_perturb:
        cut_set = cut_set + cut_set.perturb_speed(0.9) + cut_set.perturb_speed(1.1)

    with get_executor() as ex:
        cut_set = cut_set.compute_and_store_features(
            extractor=extractor,
            storage_path=str(output_dir / f"cumix2017_feats_{partition}"),
            num_jobs=num_jobs if ex is None else 80,
            executor=ex,
            storage_type=LilcomChunkyWriter,
        )
        cut_set.to_file(output_dir / cuts_filename)


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)
    compute_fbank_cumix2017(get_args())
