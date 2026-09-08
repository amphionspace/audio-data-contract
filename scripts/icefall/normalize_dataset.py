#!/usr/bin/env python3
"""Drive ``normalize_manifests.py`` over one or more amphion datasets.

Resolves manifest paths via ``DATASET_SPECS`` in
``shared_amphion/zipformer/lhotse_datasets.py`` so the prepare-stage
caller only specifies dataset names (matching ``--train-datasets`` in
the train scripts) and a destination root. Used by
``prepare_from_lhotse.sh`` stage 16 to produce the normalised manifest
tree under ``<lhotse-root>/_amphion_normalized/<dataset>/``.

This is a thin orchestrator: per (dataset, split) it computes
``(src_rec, src_sup, dst_sup)`` and invokes ``normalize_manifests.py``
as a subprocess so each manifest gets its own checkpoint / stats / broken
sidecars without sharing state between datasets.

Failure isolation: by default ``--continue-on-error`` keeps going after a
single dataset fails (logged loudly), so a transient network issue on
one manifest doesn't waste the hours already invested on previous ones.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve(p: str, lhotse_root: Path) -> Path:
    """Lhotse-style: absolute path overrides ``lhotse_root``."""
    if p.startswith("/"):
        return Path(p)
    return lhotse_root / p


def _iter_split_rec_sup_pairs(split):
    """Yield (rec_path, sup_path) pairs from a ``_SplitSpec``.

    Handles both ``str`` and ``List[str]`` forms; raises if rec/sup list
    lengths disagree (which would be an upstream spec bug).
    """
    rec = split.rec
    sup = split.sup
    rec_list = rec if isinstance(rec, list) else [rec]
    sup_list = sup if isinstance(sup, list) else [sup]
    if len(rec_list) != len(sup_list):
        raise ValueError(
            f"split rec/sup list length mismatch: "
            f"len(rec)={len(rec_list)} != len(sup)={len(sup_list)}"
        )
    for rp, sp in zip(rec_list, sup_list):
        if rp is None or sp is None:
            # _SplitSpec may carry rec=None / sup=None when only `cuts` is
            # configured; we only normalise rec+sup pairs here.
            continue
        yield rp, sp


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--datasets",
        required=True,
        help="comma-separated dataset names (matching keys in DATASET_SPECS).",
    )
    parser.add_argument(
        "--splits",
        default="train",
        help="comma-separated split names per dataset (default: 'train').",
    )
    parser.add_argument(
        "--lhotse-root",
        type=Path,
        required=True,
        help="LHOTSE root for resolving relative manifest paths.",
    )
    parser.add_argument(
        "--dst-root",
        type=Path,
        required=True,
        help="Destination root; per-dataset dirs are created underneath "
        "(e.g. <dst-root>/legco_speech/<sup-basename>.jsonl.gz).",
    )
    parser.add_argument(
        "--scan-audio",
        action="store_true",
        help="Pass --scan-audio to normalize_manifests.py (drop broken cuts).",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=64,
        help="Worker count for parallel audio scan.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-normalise even if the destination supervision file exists.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        default=True,
        help="Log and skip rather than abort when one (dataset, split) fails.",
    )
    parser.add_argument(
        "--abort-on-error",
        dest="continue_on_error",
        action="store_false",
        help="Opposite of --continue-on-error (abort the whole run).",
    )
    from consumer import icefall_root

    icefall_root()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    here = Path(__file__).resolve().parent  # shared_amphion/local/
    try:
        from lhotse_datasets import DATASET_SPECS  # type: ignore
    except ImportError as e:
        logger.error("Failed to import lhotse_datasets: %s", e)
        logger.error(
            "Expected to find DATASET_SPECS at "
            "egs/amphion/shared_amphion/zipformer/lhotse_datasets.py; "
            "is PYTHONPATH wired to the amphion shared layer?"
        )
        return 2

    normalize_py = here / "normalize_manifests.py"
    if not normalize_py.is_file():
        logger.error("normalize_manifests.py not found at %s", normalize_py)
        return 2

    ds_names = [n.strip() for n in args.datasets.split(",") if n.strip()]
    split_names = [s.strip() for s in args.splits.split(",") if s.strip()]
    if not ds_names:
        logger.error("--datasets is empty")
        return 2

    n_done = 0
    n_skipped = 0
    n_failed = 0
    t_start = time.time()

    for ds in ds_names:
        spec = DATASET_SPECS.get(ds)
        if spec is None:
            logger.warning("[%s] not in DATASET_SPECS; skip", ds)
            n_skipped += 1
            continue

        # ``_DatasetSpec.test`` may be either a single ``_SplitSpec`` or a
        # ``Dict[str, _SplitSpec]`` for multi-test datasets (see WSYUE).
        # Both cases live under ``spec.splits[<name>]`` for train/dev, but
        # multi-test goes through ``test_dict``. For normalize we only care
        # about train/dev/test single splits in ``spec.splits``.
        for split_name in split_names:
            if split_name not in spec.splits:
                logger.info("[%s/%s] no such split, skip", ds, split_name)
                continue
            split = spec.splits[split_name]
            try:
                pair_idx = 0
                for rec_rel, sup_rel in _iter_split_rec_sup_pairs(split):
                    src_rec = _resolve(rec_rel, args.lhotse_root)
                    src_sup = _resolve(sup_rel, args.lhotse_root)
                    if not src_rec.is_file():
                        logger.warning(
                            "[%s/%s] src_rec missing: %s; skip pair %d",
                            ds,
                            split_name,
                            src_rec,
                            pair_idx,
                        )
                        pair_idx += 1
                        continue
                    if not src_sup.is_file():
                        logger.warning(
                            "[%s/%s] src_sup missing: %s; skip pair %d",
                            ds,
                            split_name,
                            src_sup,
                            pair_idx,
                        )
                        pair_idx += 1
                        continue
                    dst_sup = args.dst_root / ds / src_sup.name
                    dst_sup.parent.mkdir(parents=True, exist_ok=True)
                    if dst_sup.is_file() and not args.force:
                        logger.info(
                            "[%s/%s] %s exists, skip (use --force to redo)",
                            ds,
                            split_name,
                            dst_sup,
                        )
                        n_skipped += 1
                        pair_idx += 1
                        continue
                    logger.info(
                        "[%s/%s] normalize: %s -> %s",
                        ds,
                        split_name,
                        src_sup.name,
                        dst_sup,
                    )
                    cmd = [
                        sys.executable,
                        str(normalize_py),
                        "--src-rec",
                        str(src_rec),
                        "--src-sup",
                        str(src_sup),
                        "--dst-sup",
                        str(dst_sup),
                        "--num-workers",
                        str(args.num_workers),
                    ]
                    if args.scan_audio:
                        cmd.append("--scan-audio")
                    t0 = time.time()
                    subprocess.run(cmd, check=True)
                    logger.info(
                        "[%s/%s] done in %.0fs",
                        ds,
                        split_name,
                        time.time() - t0,
                    )
                    n_done += 1
                    pair_idx += 1
            except subprocess.CalledProcessError as e:
                logger.error("[%s/%s] normalize failed: %s", ds, split_name, e)
                n_failed += 1
                if not args.continue_on_error:
                    return 1
            except Exception:
                logger.exception("[%s/%s] unexpected error", ds, split_name)
                n_failed += 1
                if not args.continue_on_error:
                    return 1

    logger.info(
        "all done: ok=%d, skipped=%d, failed=%d, elapsed=%.0fs",
        n_done,
        n_skipped,
        n_failed,
        time.time() - t_start,
    )
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
