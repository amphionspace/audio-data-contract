#!/usr/bin/env python3
# Copyright    2024  amphion
#
# NOTE: This file lives in egs/amphion/shared_amphion/ because both leaf
# recipes (zh_en, yue_en) need MLS English fbank. Each leaf recipe symlinks
# its own compute_fbank_mls.py to this shared file via
# ../../shared_amphion/compute_fbank_mls.py. Do not duplicate it back into
# leaf recipes (would violate egs/amphion/AGENTS.md §5 reverse-example table).
#
# Compute fbank features for MLS English dataset (icefall has no mls recipe yet).
# Reads manifests from data/manifests/mls/ and writes cuts to data/fbank/.
#
# Manifest naming (from lhotse `mls` recipe):
#   mls-english_recordings_<part>.jsonl.gz
#   mls-english_supervisions_<part>.jsonl.gz
# where <part> in {train, dev, test}.

import argparse
import logging
import os
from pathlib import Path

import torch
from consumer import icefall_root
from lhotse import CutSet, Fbank, FbankConfig, LilcomChunkyWriter
from lhotse.recipes.utils import read_manifests_if_cached

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
        help="Apply 0.9/1.1 speed perturb on train split.",
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("data/manifests/mls"),
        help="Directory containing mls-english_*.jsonl.gz manifests.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/fbank"),
        help="Directory to write fbank cuts.",
    )
    return parser.parse_args()


def compute_fbank_mls(args):
    src_dir = args.src_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    num_jobs = min(15, os.cpu_count() or 1)

    dataset_parts = ("train", "dev", "test")
    prefix = "mls-english"
    suffix = "jsonl.gz"

    manifests = read_manifests_if_cached(
        dataset_parts=dataset_parts,
        output_dir=src_dir,
        prefix=prefix,
        suffix=suffix,
    )
    if not manifests:
        logger.warning(
            f"No MLS manifests found under {src_dir}. "
            "Skipping (this is fine if you don't have MLS)."
        )
        return

    extractor = Fbank(FbankConfig(num_mel_bins=args.num_mel_bins))

    with get_executor() as ex:
        for partition, m in manifests.items():
            cuts_filename = f"{prefix}_cuts_{partition}.{suffix}"
            if (output_dir / cuts_filename).is_file():
                logger.info(f"{partition} already exists - skipping.")
                continue
            logger.info(f"Processing {partition}")
            cut_set = CutSet.from_manifests(
                recordings=m["recordings"],
                supervisions=m["supervisions"],
            )
            if "train" in partition and args.speed_perturb:
                cut_set = (
                    cut_set + cut_set.perturb_speed(0.9) + cut_set.perturb_speed(1.1)
                )
            cut_set = cut_set.compute_and_store_features(
                extractor=extractor,
                storage_path=str(output_dir / f"{prefix}_feats_{partition}"),
                num_jobs=num_jobs if ex is None else 80,
                executor=ex,
                storage_type=LilcomChunkyWriter,
            )
            cut_set.to_file(output_dir / cuts_filename)


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)
    compute_fbank_mls(get_args())
