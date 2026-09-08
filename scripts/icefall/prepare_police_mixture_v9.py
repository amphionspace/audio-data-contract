#!/usr/bin/env python3
"""Build the verified WenetSpeech disfluency subset used by police v9."""

import argparse
import gzip
import json
import os
from collections import Counter
from pathlib import Path

DEFAULT_SOURCE = Path(
    "/ai_sds_wuzz/DATA_ASR/WenetSpeech/lhotse/clean/v3-firered/"
    "wenetspeech_supervisions_L_clean.jsonl.gz"
)
DEFAULT_OUTPUT = Path(
    "/ai_sds_wuzz/DATA_ASR/WenetSpeech/lhotse/clean/v3-firered/derived/"
    "police-v9/wenetspeech_supervisions_restore_disfluency.jsonl.gz"
)
FILLERS = "呃啊嗯呢呀哎诶哦噢哇"
TRAILING_PUNCTUATION = " \t\r\n，。！？、,.!?；;：:“”‘’（）()【】[]《》<>…—-"


def build_subset(source: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    total = 0
    selected = 0
    any_filler = 0
    final_fillers: Counter[str] = Counter()

    try:
        with (
            gzip.open(source, "rt", encoding="utf-8") as src,
            gzip.open(temporary, "wt", encoding="utf-8") as dst,
        ):
            for line in src:
                total += 1
                row = json.loads(line)
                clean = (row.get("custom") or {}).get("clean") or {}
                if clean.get("action") != "restore_disfluency":
                    continue
                if clean.get("pass") is False:
                    continue

                text = row.get("text") or ""
                selected += 1
                if any(filler in text for filler in FILLERS):
                    any_filler += 1
                stripped = text.rstrip(TRAILING_PUNCTUATION)
                if stripped and stripped[-1] in FILLERS:
                    final_fillers[stripped[-1]] += 1
                dst.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                dst.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    summary = {
        "source": str(source),
        "output": str(output),
        "source_rows": total,
        "selected_rows": selected,
        "rows_with_fillers": any_filler,
        "final_fillers": dict(sorted(final_fillers.items())),
        "selection": "custom.clean.action == restore_disfluency and pass != false",
    }
    summary_path = output.with_name(
        output.name.removesuffix(".jsonl.gz") + "_summary.json"
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = get_args()
    if not args.source.is_file():
        raise SystemExit(f"Missing clean WenetSpeech supervisions: {args.source}")
    if args.output.exists() and not args.force:
        print(f"Already prepared: {args.output} (pass --force to rebuild)")
        return
    print(
        json.dumps(build_subset(args.source, args.output), ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
