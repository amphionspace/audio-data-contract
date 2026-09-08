#!/usr/bin/env python3
"""Build balanced WenetSpeech replay shards from cleaned podcast cuts.

The existing shared shards were created with a bounded shuffle buffer and still
cluster strongly by source.  This builder deliberately samples several
podcast-dominant source shards, joins the Qwen-cleaned supervision text, applies
the cleaning pass gate, and redistributes the selected cuts so every output
shard has the same short/long quota.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
from collections import Counter
from pathlib import Path

DEFAULT_SOURCE_DIR = Path("egs/amphion/data/shards/wenetspeech")
DEFAULT_CLEAN_SUPERVISIONS = Path(
    "/ai_sds_wuzz/DATA_ASR/WenetSpeech/lhotse/clean/v1/"
    "wenetspeech_supervisions_L_punc.jsonl.gz"
)
DEFAULT_SOURCE_INDICES = (1, 2, 3, 11, 12, 14, 0, 4, 5, 6, 7, 8, 9, 10, 13)

_PUNC_CHARS = frozenset(
    "，。！？、；：「」『』（）《》〈〉｛｝【】…—–“”„‟‘’,.!?;:()[]{}"
)
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")
_HAN_RE = re.compile(r"[\u3400-\u9fff]")


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--clean-supervisions", type=Path, default=DEFAULT_CLEAN_SUPERVISIONS
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--source-indices",
        type=str,
        default=",".join(str(i) for i in DEFAULT_SOURCE_INDICES),
    )
    parser.add_argument("--num-shards", type=int, default=6)
    parser.add_argument("--cuts-per-shard", type=int, default=100_000)
    parser.add_argument("--meeting-share", type=float, default=0.15)
    parser.add_argument("--meeting-min-duration", type=float, default=5.0)
    parser.add_argument("--meeting-min-text-chars", type=int, default=20)
    parser.add_argument("--max-cuts-per-recording", type=int, default=50)
    parser.add_argument(
        "--candidate-factor",
        type=float,
        default=1.15,
        help="Oversample before joining clean metadata so rejected cuts can be dropped.",
    )
    parser.add_argument("--seed", type=int, default=20260818)
    return parser.parse_args()


def strip_punc_and_tags(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = "".join(" " if char in _PUNC_CHARS else char for char in text)
    return _WS_RE.sub(" ", text).strip()


def is_meeting_like(cut: dict, min_duration: float, min_text_chars: int) -> bool:
    text = "".join(
        supervision.get("text", "").replace(" ", "")
        for supervision in cut.get("supervisions", [])
    )
    return float(cut["duration"]) >= min_duration and len(text) >= min_text_chars


def recording_id(cut: dict) -> str:
    supervisions = cut.get("supervisions") or []
    if supervisions and supervisions[0].get("recording_id"):
        return str(supervisions[0]["recording_id"])
    return str((cut.get("recording") or {}).get("id", cut["id"]))


def collect_candidates(args: argparse.Namespace) -> dict[str, dict]:
    source_indices = [int(item) for item in args.source_indices.split(",") if item]
    if not source_indices:
        raise ValueError("--source-indices must not be empty")

    target_total = args.num_shards * args.cuts_per_shard
    meeting_target = round(target_total * args.meeting_share)
    general_target = target_total - meeting_target
    meeting_candidate_target = round(meeting_target * args.candidate_factor)
    general_candidate_target = round(general_target * args.candidate_factor)
    # The first ``num_shards`` inputs are podcast-dominant.  Later inputs are
    # overflow sources, not reasons to reduce the quota of the primary pool.
    quota_divisor = min(args.num_shards, len(source_indices))
    per_source_meeting = (meeting_candidate_target + quota_divisor - 1) // quota_divisor
    per_source_general = (general_candidate_target + quota_divisor - 1) // quota_divisor

    candidates: dict[str, dict] = {}
    recording_counts: Counter[str] = Counter()
    stratum_counts: Counter[str] = Counter()
    for source_idx in source_indices:
        path = args.source_dir / f"wenetspeech.{source_idx:08d}.jsonl.gz"
        if not path.is_file():
            raise FileNotFoundError(path)
        selected = {"general": 0, "meeting": 0}
        with gzip.open(path, "rt", encoding="utf-8") as source:
            for line in source:
                cut = json.loads(line)
                if not str(cut.get("id", "")).startswith("X"):
                    continue
                rec_id = recording_id(cut)
                if recording_counts[rec_id] >= args.max_cuts_per_recording:
                    continue
                stratum = (
                    "meeting"
                    if is_meeting_like(
                        cut,
                        args.meeting_min_duration,
                        args.meeting_min_text_chars,
                    )
                    else "general"
                )
                limit = (
                    per_source_meeting if stratum == "meeting" else per_source_general
                )
                if selected[stratum] >= limit:
                    continue
                candidates[cut["id"]] = {
                    "cut": cut,
                    "stratum": stratum,
                    "source_shard": source_idx,
                }
                recording_counts[rec_id] += 1
                selected[stratum] += 1
                stratum_counts[stratum] += 1
                if (
                    selected["general"] >= per_source_general
                    and selected["meeting"] >= per_source_meeting
                ):
                    break
        print(
            f"source={source_idx:02d} candidates: "
            f"general={selected['general']} meeting={selected['meeting']}"
        )
        if (
            stratum_counts["general"] >= general_candidate_target
            and stratum_counts["meeting"] >= meeting_candidate_target
        ):
            break

    if len(candidates) < target_total:
        raise RuntimeError(
            f"only collected {len(candidates)} candidates for {target_total} cuts"
        )
    return candidates


def join_clean_text(
    candidates: dict[str, dict], clean_supervisions: Path
) -> dict[str, dict]:
    matched = 0
    passed = 0
    with gzip.open(clean_supervisions, "rt", encoding="utf-8") as source:
        for line in source:
            supervision = json.loads(line)
            item = candidates.get(supervision.get("id"))
            if item is None:
                continue
            matched += 1
            custom = supervision.get("custom") or {}
            clean = custom.get("clean") or {}
            text = strip_punc_and_tags(str(supervision.get("text", "")))
            if clean.get("pass") is False or not text or not _HAN_RE.search(text):
                item["eligible"] = False
                continue
            cut_supervisions = item["cut"].get("supervisions") or []
            if len(cut_supervisions) != 1:
                item["eligible"] = False
                continue
            cut_supervision = cut_supervisions[0]
            cut_supervision["text"] = text
            merged_custom = dict(cut_supervision.get("custom") or {})
            merged_custom.update(custom)
            cut_supervision["custom"] = merged_custom
            item["eligible"] = True
            passed += 1
            if matched == len(candidates):
                break
    print(
        f"clean join: candidates={len(candidates)} matched={matched} eligible={passed}"
    )
    return {key: value for key, value in candidates.items() if value.get("eligible")}


def write_shards(args: argparse.Namespace, eligible: dict[str, dict]) -> None:
    total = args.num_shards * args.cuts_per_shard
    meeting_total = round(total * args.meeting_share)
    general_total = total - meeting_total
    meeting = [item for item in eligible.values() if item["stratum"] == "meeting"]
    general = [item for item in eligible.values() if item["stratum"] == "general"]
    if len(meeting) < meeting_total or len(general) < general_total:
        raise RuntimeError(
            "not enough eligible cuts: "
            f"general={len(general)}/{general_total}, "
            f"meeting={len(meeting)}/{meeting_total}"
        )

    rng = random.Random(args.seed)
    rng.shuffle(general)
    rng.shuffle(meeting)
    general = general[:general_total]
    meeting = meeting[:meeting_total]
    per_shard_meeting = meeting_total // args.num_shards
    per_shard_general = general_total // args.num_shards
    if (
        per_shard_meeting * args.num_shards != meeting_total
        or per_shard_general * args.num_shards != general_total
    ):
        raise ValueError("stratum totals must divide evenly by --num-shards")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "source_indices": [
            int(item) for item in args.source_indices.split(",") if item
        ],
        "clean_supervisions": str(args.clean_supervisions),
        "num_shards": args.num_shards,
        "cuts_per_shard": args.cuts_per_shard,
        "meeting_share": args.meeting_share,
        "max_cuts_per_recording": args.max_cuts_per_recording,
        "seed": args.seed,
        "shards": [],
    }
    for shard_idx in range(args.num_shards):
        selected = (
            general[shard_idx * per_shard_general : (shard_idx + 1) * per_shard_general]
            + meeting[
                shard_idx * per_shard_meeting : (shard_idx + 1) * per_shard_meeting
            ]
        )
        rng.shuffle(selected)
        output = args.output_dir / f"wenetspeech.{shard_idx:08d}.jsonl.gz"
        temporary = output.with_suffix(output.suffix + ".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as sink:
            for item in selected:
                sink.write(json.dumps(item["cut"], ensure_ascii=False) + "\n")
        temporary.replace(output)
        source_counts = Counter(item["source_shard"] for item in selected)
        shard_summary = {
            "path": str(output),
            "cuts": len(selected),
            "general": per_shard_general,
            "meeting": per_shard_meeting,
            "source_counts": dict(sorted(source_counts.items())),
        }
        summary["shards"].append(shard_summary)
        print(json.dumps(shard_summary, ensure_ascii=False))

    summary_path = args.output_dir / "_build_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote provenance: {summary_path}")


def main() -> None:
    args = get_args()
    if not 0.0 < args.meeting_share < 1.0:
        raise ValueError("--meeting-share must be between 0 and 1")
    if args.candidate_factor <= 1.0:
        raise ValueError("--candidate-factor must be greater than 1")
    candidates = collect_candidates(args)
    eligible = join_clean_text(candidates, args.clean_supervisions)
    write_shards(args, eligible)


if __name__ == "__main__":
    main()
