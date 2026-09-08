#!/usr/bin/env python3
"""Create deterministic, leakage-free train/dev/test manifests for police v5."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

DEFAULT_SOURCE = Path(
    "/ai_sds_wuzz/DATA_ASR/LHOTSE/synthetic/police_synthetic_zh_accent/"
    "v5-20260830-qwen75-cosy25/manifests"
)
DEFAULT_OUTPUT = Path(
    "/ai_sds_wuzz/DATA_ASR/LHOTSE/synthetic/police_synthetic_zh_accent/"
    "v5-20260830-qwen75-cosy25-split80-10-10/manifests"
)
SPLITS = ("train", "dev", "test")


def _read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")


def _rank(seed: str, value: str) -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode()).hexdigest()


def _choose_speaker_split(rows: list[dict], seed: str) -> tuple[dict[str, str], int]:
    """Choose a deterministic partition that best preserves provider duration."""
    speaker_names = {row["speaker"] for row in rows}
    source_cosy = sum(
        row["duration"] for row in rows if row["custom"]["tts_provider"] == "cosyvoice3"
    )
    source_ratio = source_cosy / sum(row["duration"] for row in rows)
    n = len(speaker_names)
    n_dev = round(n * 0.10)
    n_test = round(n * 0.10)
    best = None
    for trial in range(256):
        speakers = sorted(speaker_names, key=lambda x: _rank(f"{seed}:{trial}", x))
        candidate = {
            speaker: ("dev" if i < n_dev else "test" if i < n_dev + n_test else "train")
            for i, speaker in enumerate(speakers)
        }
        durations = Counter()
        cosy = Counter()
        for row in rows:
            split = candidate[row["speaker"]]
            durations[split] += row["duration"]
            if row["custom"]["tts_provider"] == "cosyvoice3":
                cosy[split] += row["duration"]
        score = sum(abs(cosy[s] / durations[s] - source_ratio) for s in SPLITS)
        ranked = (score, trial, candidate)
        if best is None or ranked[:2] < best[:2]:
            best = ranked
    assert best is not None
    return best[2], best[1]


def split_supervisions(
    rows: list[dict], seed: str
) -> tuple[dict[str, list[dict]], dict]:
    speaker_split, partition_trial = _choose_speaker_split(rows, seed)
    speakers = sorted(speaker_split)
    n = len(speakers)

    by_sentence: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_sentence[row["custom"]["sentence_id"]].append(row)

    result: dict[str, list[dict]] = {name: [] for name in SPLITS}
    dropped: list[str] = []
    for sentence_id, sentence_rows in by_sentence.items():
        counts = Counter(speaker_split[row["speaker"]] for row in sentence_rows)
        # Majority keeps the most audio; hash is a deterministic tie breaker.
        chosen = min(
            counts,
            key=lambda name: (-counts[name], _rank(f"{seed}:{sentence_id}", name)),
        )
        for row in sentence_rows:
            if speaker_split[row["speaker"]] == chosen:
                result[chosen].append(row)
            else:
                dropped.append(row["id"])

    # Cross-split duplicate removal disproportionately drops CosyVoice3 rows
    # because many duplicated sentences have more Qwen3-TTS realizations.
    # Deterministically thin Qwen rows back to the source 75/25 duration mix.
    source_cosy_hours = sum(
        r["duration"] for r in rows if r["custom"]["tts_provider"] == "cosyvoice3"
    )
    source_total_hours = sum(r["duration"] for r in rows)
    source_cosy_ratio = source_cosy_hours / source_total_hours
    rebalanced_dropped: list[str] = []
    for split in SPLITS:
        cosy_rows = [
            r for r in result[split] if r["custom"]["tts_provider"] == "cosyvoice3"
        ]
        qwen_rows = sorted(
            (r for r in result[split] if r["custom"]["tts_provider"] == "qwen3_tts"),
            key=lambda r: _rank(f"{seed}:rebalance:{split}", r["id"]),
        )
        qwen_target = (
            sum(r["duration"] for r in cosy_rows)
            * (1 - source_cosy_ratio)
            / source_cosy_ratio
        )
        kept_qwen = []
        kept_duration = 0.0
        for row in qwen_rows:
            if kept_duration < qwen_target:
                kept_qwen.append(row)
                kept_duration += row["duration"]
            else:
                rebalanced_dropped.append(row["id"])
        result[split] = cosy_rows + kept_qwen

    for split in SPLITS:
        result[split].sort(key=lambda row: row["id"])

    summary = {
        "schema_version": 1,
        "seed": seed,
        "partition_trial": partition_trial,
        "strategy": "speaker buckets followed by cross-bucket sentence de-duplication",
        "source_records": len(rows),
        "source_speakers": n,
        "source_sentences": len(by_sentence),
        "dropped_cross_split_duplicates": len(dropped),
        "dropped_ids_sha256": hashlib.sha256(
            "\n".join(sorted(dropped)).encode()
        ).hexdigest(),
        "dropped_for_provider_rebalance": len(rebalanced_dropped),
        "rebalanced_dropped_ids_sha256": hashlib.sha256(
            "\n".join(sorted(rebalanced_dropped)).encode()
        ).hexdigest(),
        "splits": {},
    }
    for split, split_rows in result.items():
        summary["splits"][split] = {
            "records": len(split_rows),
            "duration_hours": round(sum(r["duration"] for r in split_rows) / 3600, 6),
            "speakers": len({r["speaker"] for r in split_rows}),
            "sentences": len({r["custom"]["sentence_id"] for r in split_rows}),
            "target_terms": len(
                {t for r in split_rows for t in r["custom"].get("target_terms", [])}
            ),
            "providers": dict(
                sorted(Counter(r["custom"]["tts_provider"] for r in split_rows).items())
            ),
            "provider_hours": {
                provider: round(
                    sum(
                        r["duration"]
                        for r in split_rows
                        if r["custom"]["tts_provider"] == provider
                    )
                    / 3600,
                    6,
                )
                for provider in sorted(
                    {r["custom"]["tts_provider"] for r in split_rows}
                )
            },
        }

    speaker_sets = [{r["speaker"] for r in result[s]} for s in SPLITS]
    sentence_sets = [{r["custom"]["sentence_id"] for r in result[s]} for s in SPLITS]
    assert not any(
        speaker_sets[i] & speaker_sets[j] for i in range(3) for j in range(i + 1, 3)
    )
    assert not any(
        sentence_sets[i] & sentence_sets[j] for i in range(3) for j in range(i + 1, 3)
    )
    return result, summary


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", default="police-v5-split-v1")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = get_args()
    rec_path = args.source_dir / "police_synthetic_recordings_train.jsonl.gz"
    sup_path = args.source_dir / "police_synthetic_supervisions_train.jsonl.gz"
    outputs = [
        args.output_dir / f"police_terms_v5_{kind}_{split}.jsonl.gz"
        for split in SPLITS
        for kind in ("recordings", "supervisions")
    ]
    summary_path = args.output_dir.parent / "metadata" / "split_summary.json"
    if not args.force and all(path.is_file() for path in [*outputs, summary_path]):
        print(f"Split already exists: {args.output_dir}")
        return

    recordings = _read_jsonl(rec_path)
    supervisions = _read_jsonl(sup_path)
    rec_by_id = {row["id"]: row for row in recordings}
    if len(rec_by_id) != len(recordings):
        raise ValueError("Duplicate recording IDs in source manifest")
    if any(
        not row.get("custom", {}).get("clean", {}).get("pass", False)
        for row in supervisions
    ):
        raise ValueError("Source contains a supervision that did not pass QC")

    splits, summary = split_supervisions(supervisions, args.seed)
    used_recordings: set[str] = set()
    for split, sup_rows in splits.items():
        rec_ids = [row["recording_id"] for row in sup_rows]
        missing = sorted(set(rec_ids) - rec_by_id.keys())
        if missing:
            raise ValueError(f"Missing recordings for {split}: {missing[:5]}")
        overlap = used_recordings & set(rec_ids)
        if overlap:
            raise ValueError(f"Recording leakage into {split}: {sorted(overlap)[:5]}")
        used_recordings.update(rec_ids)
        rec_rows = [rec_by_id[rec_id] for rec_id in rec_ids]
        _write_jsonl(
            args.output_dir / f"police_terms_v5_recordings_{split}.jsonl.gz", rec_rows
        )
        _write_jsonl(
            args.output_dir / f"police_terms_v5_supervisions_{split}.jsonl.gz", sup_rows
        )

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
