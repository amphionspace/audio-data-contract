#!/usr/bin/env python3
"""Build a police training shard whose written numbers match the audio."""

from __future__ import annotations

import argparse
import gzip
import json
import os
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from consumer import icefall_root

icefall_root()


_NORMALIZER = None


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--source", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-j", "--jobs", type=int, default=8)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _init_worker(cache_dir: str) -> None:
    global _NORMALIZER

    from text_norm import WeTextNormalizer

    _NORMALIZER = WeTextNormalizer(
        "zh",
        cache_dir=cache_dir,
        traditional_to_simple=True,
        full_to_half=True,
        remove_puncts=False,
        remove_interjections=False,
        remove_erhua=False,
        tag_oov=False,
    )


def _normalize_line(line: str) -> tuple[str, int, int]:
    obj: dict[str, Any] = json.loads(line)
    changed = 0
    numeric = 0
    for supervision in obj.get("supervisions", []):
        text = supervision.get("text", "")
        if not text:
            continue
        numeric += int(any(char.isdigit() for char in text))
        normalized = _NORMALIZER.normalize(text)
        if normalized != text:
            supervision["text"] = normalized
            changed += 1
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")), changed, numeric


def main() -> None:
    args = get_args()
    if args.jobs < 1:
        raise ValueError("--jobs must be positive")
    if not args.source.is_file():
        raise FileNotFoundError(args.source)
    if args.output.exists() and not args.force:
        raise FileExistsError(
            f"Output exists; pass --force to replace it: {args.output}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_name(f".{args.output.name}.tmp-{os.getpid()}")
    total = changed = numeric = 0
    try:
        with (
            gzip.open(args.source, "rt", encoding="utf-8") as src,
            Pool(
                processes=args.jobs,
                initializer=_init_worker,
                initargs=(str(args.cache_dir),),
            ) as pool,
            gzip.open(tmp, "wt", encoding="utf-8") as dst,
        ):
            for normalized, num_changed, num_numeric in pool.imap(
                _normalize_line, src, chunksize=64
            ):
                dst.write(normalized + "\n")
                total += 1
                changed += num_changed
                numeric += num_numeric
        tmp.replace(args.output)
    finally:
        if tmp.exists():
            tmp.unlink()

    print(
        f"Wrote {total} cuts to {args.output}; "
        f"changed_supervisions={changed}, numeric_supervisions={numeric}"
    )


if __name__ == "__main__":
    main()
