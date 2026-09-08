"""Locate an optional icefall checkout for recipe-specific transforms.

Standalone corpus download/cleaning tools do not use this module.
"""

import argparse
import sys
from pathlib import Path


def icefall_root():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--icefall-root", type=Path)
    args, remaining = parser.parse_known_args()
    sys.argv[1:] = remaining
    root = args.icefall_root
    if root is None:
        # When invoked through the submodule's compatibility entry points.
        root = Path(__file__).resolve().parents[5]
    if not (root / "egs/amphion/shared_amphion/zipformer").is_dir():
        raise RuntimeError(
            "This recipe transform requires --icefall-root /path/to/icefall"
        )
    root = root.resolve()
    for path in (
        root,
        root / "egs/amphion/shared_amphion/zipformer",
        root / "egs/amphion/zh_en/ASR/low_volume_benchmark",
    ):
        sys.path.insert(0, str(path))
    return root
