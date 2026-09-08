#!/usr/bin/env python3
# Copyright    2024  amphion/yue_en
#
# Compute fbank features for the WenetSpeech-Yue dataset (large-scale
# Cantonese ASR). icefall has no wenetspeech-yue recipe yet, so we own
# the fbank computation here.
#
# Manifest naming (from /ai_sds_wuzz/MULTILINGUAL_DATA/zh/WenetSpeech-Yue/
# data/manifests/, symlinked into <lhotse_root>/WenetSpeech-Yue/data/manifests/):
#   wenetspeech_yue_recordings_all.jsonl.gz       全量
#   wenetspeech_yue_supervisions_all.jsonl.gz
#   wenetspeech_yue_recordings_clean.jsonl.gz     confidence>=0.9 且 DNSMOS>=3.4
#   wenetspeech_yue_supervisions_clean.jsonl.gz
#
# 默认走 _clean 版本（更稳）；想用全量请加 --use-cleaned 0。

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
        default=False,
        help="Apply 0.9/1.1 speed perturb on train; defaults to False because "
        "WenetSpeech-Yue is already several thousand hours.",
    )
    parser.add_argument(
        "--use-cleaned",
        type=str2bool,
        default=True,
        help="True: use _clean variant (confidence>=0.9, DNSMOS>=3.4); "
        "False: use _all (full set, includes lower-quality utterances).",
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE/WenetSpeech-Yue/data/manifests"),
        help="Directory containing wenetspeech_yue_*.jsonl.gz manifests.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/fbank"),
        help="Directory to write fbank cuts.",
    )
    parser.add_argument(
        "--num-splits",
        type=int,
        default=20,
        help="Split the cutset into N pieces and compute fbank piecewise to "
        "limit RAM and to allow restarts.",
    )
    return parser.parse_args()


def compute_fbank_wenetspeech_yue(args):
    src_dir = args.src_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = "clean" if args.use_cleaned else "all"
    rec_path = src_dir / f"wenetspeech_yue_recordings_{suffix}.jsonl.gz"
    sup_path = src_dir / f"wenetspeech_yue_supervisions_{suffix}.jsonl.gz"

    if not rec_path.is_file() or not sup_path.is_file():
        logger.warning(
            f"WenetSpeech-Yue manifests not found:\n  {rec_path}\n  {sup_path}\n"
            "Run: bash /ai_sds_wuzz/MULTILINGUAL_DATA/zh/WenetSpeech-Yue/local/prepare.sh\n"
            "and re-run prepare_from_lhotse.sh stage 1 to symlink the manifests."
        )
        return

    cuts_filename = f"wenetspeech_yue_cuts_{suffix}.jsonl.gz"
    if (output_dir / cuts_filename).is_file():
        logger.info(f"{suffix} already exists - skipping.")
        return

    num_jobs = min(15, os.cpu_count() or 1)
    extractor = Fbank(FbankConfig(num_mel_bins=args.num_mel_bins))

    logger.info(f"Loading recordings from {rec_path}")
    recordings = load_manifest_lazy(str(rec_path))
    logger.info(f"Loading supervisions from {sup_path}")
    supervisions = load_manifest_lazy(str(sup_path))

    cut_set = CutSet.from_manifests(recordings=recordings, supervisions=supervisions)
    cut_set = cut_set.trim_to_supervisions(
        keep_overlapping=False, keep_all_channels=False
    )

    if args.speed_perturb:
        cut_set = cut_set + cut_set.perturb_speed(0.9) + cut_set.perturb_speed(1.1)

    with get_executor() as ex:
        cut_set = cut_set.compute_and_store_features(
            extractor=extractor,
            storage_path=str(output_dir / f"wenetspeech_yue_feats_{suffix}"),
            num_jobs=num_jobs if ex is None else 80,
            executor=ex,
            storage_type=LilcomChunkyWriter,
        )
        cut_set.to_file(output_dir / cuts_filename)


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)
    compute_fbank_wenetspeech_yue(get_args())
