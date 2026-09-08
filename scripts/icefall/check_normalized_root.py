#!/usr/bin/env python3
"""Dry-run checker for AMPHION_NORMALIZED_ROOT before flipping a training run.

Walks DATASET_SPECS for the given dataset list and reports for each
``(dataset, split, rec/sup pair)`` whether a normalised copy exists under
the candidate root. Use this before exporting AMPHION_NORMALIZED_ROOT for
a real training restart -- a partial-normalise tree is *safe* (the runtime
redirect falls back to the source path) but knowing the actual coverage
prevents surprises.

Example:
  python3 shared_amphion/local/check_normalized_root.py \\
      --datasets librispeech,mls,gigaspeech,common_voice_en,cumix2017,\
mdcc,wenetspeech_yue,legco_speech,legco_speech_en \\
      --lhotse-root /ai_sds_wuzz/DATA_ASR/LHOTSE \\
      --normalized-root /ai_sds_wuzz/DATA_ASR/LHOTSE/_amphion_normalized

Exit code:
  0 -- every requested (dataset, split, pair) has a normalised copy
  1 -- some are missing (still safe to train; see stdout for details)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _resolve(p: str, lhotse_root: Path) -> Path:
    if p.startswith("/"):
        return Path(p)
    return lhotse_root / p


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--datasets", required=True, help="comma-separated dataset names."
    )
    parser.add_argument(
        "--splits",
        default="train",
        help="comma-separated splits to check (default: train).",
    )
    parser.add_argument("--lhotse-root", type=Path, required=True)
    parser.add_argument("--normalized-root", type=Path, required=True)
    from consumer import icefall_root

    icefall_root()
    args = parser.parse_args()

    try:
        from lhotse_datasets import DATASET_SPECS  # type: ignore
    except ImportError as e:
        print(f"ERROR: cannot import DATASET_SPECS: {e}", file=sys.stderr)
        return 2

    ds_names = [n.strip() for n in args.datasets.split(",") if n.strip()]
    split_names = [s.strip() for s in args.splits.split(",") if s.strip()]

    n_total = 0
    n_present = 0
    n_missing = 0
    missing: list[str] = []

    for ds in ds_names:
        spec = DATASET_SPECS.get(ds)
        if spec is None:
            print(f"[{ds}]  NOT IN DATASET_SPECS  -- skipped")
            continue
        for split_name in split_names:
            if split_name not in spec.splits:
                print(f"[{ds}/{split_name}]  no such split")
                continue
            split = spec.splits[split_name]
            sup = split.sup
            sup_list = sup if isinstance(sup, list) else [sup]
            for sp in sup_list:
                if sp is None:
                    continue
                n_total += 1
                src = _resolve(sp, args.lhotse_root)
                norm = args.normalized_root / ds / src.name
                if norm.is_file():
                    print(f"[{ds}/{split_name}]  OK     {norm}")
                    n_present += 1
                else:
                    print(
                        f"[{ds}/{split_name}]  MISS   "
                        f"expected at {norm} (source: {src})"
                    )
                    n_missing += 1
                    missing.append(f"{ds}/{split_name}: {src.name}")

    print()
    print(
        f"summary: {n_present}/{n_total} normalised copies present, {n_missing} missing"
    )
    if missing:
        print(
            "missing details (these will silently fall back to the source path "
            "at training time):"
        )
        for m in missing:
            print(f"  - {m}")
    return 0 if n_missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
