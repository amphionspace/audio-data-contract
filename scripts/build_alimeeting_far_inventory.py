#!/usr/bin/env python3
"""Validate ALiMeeting far source data and write a deterministic inventory."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import struct
from pathlib import Path

SPLITS = {
    "train": "Train_Ali_far",
    "dev": "Eval_Ali_far",
    "test": "Test_2023_Ali_far",
}
AUDIO_STEM = re.compile(r"^(?P<meeting>R\d+_M\d+)_MS\d+$")
TEXTGRID_SUFFIXES = {".textgrid"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(rows: list[dict[str, object]], split_dir: str) -> str:
    prefix = f"{split_dir}/"
    digest = hashlib.sha256()
    for row in rows:
        relative_path = str(row["relative_path"])
        if not relative_path.startswith(prefix):
            continue
        path_within_artifact = relative_path[len(prefix) :]
        digest.update(
            f"{path_within_artifact}\0{row['bytes']}\0{row['sha256']}\n".encode()
        )
    return digest.hexdigest()


def inspect_audio(path: Path) -> dict[str, int | float]:
    fmt: bytes | None = None
    data_bytes: int | None = None
    with path.open("rb") as stream:
        if stream.read(4) != b"RIFF":
            raise ValueError(f"not a RIFF file: {path}")
        stream.seek(4, 1)
        if stream.read(4) != b"WAVE":
            raise ValueError(f"not a WAVE file: {path}")
        while fmt is None or data_bytes is None:
            chunk_id = stream.read(4)
            if len(chunk_id) != 4:
                break
            chunk_size_data = stream.read(4)
            if len(chunk_size_data) != 4:
                break
            chunk_size = struct.unpack("<I", chunk_size_data)[0]
            if chunk_id == b"fmt ":
                fmt = stream.read(chunk_size)
            elif chunk_id == b"data":
                data_bytes = chunk_size
                stream.seek(chunk_size, 1)
            else:
                stream.seek(chunk_size, 1)
            if chunk_size % 2:
                stream.seek(1, 1)
    if fmt is None or len(fmt) < 16 or data_bytes is None:
        raise ValueError(f"WAV is missing fmt or data chunk: {path}")
    format_tag, channels, sample_rate, _, block_align, sample_width_bits = struct.unpack(
        "<HHIIHH", fmt[:16]
    )
    if format_tag not in {1, 65534}:
        raise ValueError(f"unsupported WAV format {format_tag} for {path}")
    frames = data_bytes // block_align
    if (channels, sample_rate, sample_width_bits) != (8, 16000, 16):
        raise ValueError(
            f"unexpected WAV format for {path}: "
            f"{channels} channels, {sample_rate} Hz, {sample_width_bits}-bit"
        )
    return {
        "channels": channels,
        "sample_rate": sample_rate,
        "sample_width_bits": sample_width_bits,
        "num_frames": frames,
        "duration": frames / sample_rate,
    }


def inspect_textgrid(path: Path, duration: float) -> dict[str, float]:
    text = path.read_text(encoding="utf-8")
    if 'Object class = "TextGrid"' not in text:
        raise ValueError(f"not a TextGrid file: {path}")
    maxima = [float(value) for value in re.findall(r"^\s*xmax = ([0-9.]+)\s*$", text, re.MULTILINE)]
    if not maxima:
        raise ValueError(f"TextGrid has no xmax values: {path}")
    max_time = max(maxima)
    return {
        "max_time": max_time,
        "audio_overrun": max(0.0, max_time - duration),
    }


def build_inventory(root: Path) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    rows: list[dict[str, object]] = []
    summaries: dict[str, dict[str, object]] = {}
    meetings_by_split: dict[str, set[str]] = {}

    for split, split_dir in SPLITS.items():
        audio_paths = sorted((root / split_dir / "audio_dir").glob("*.wav"))
        textgrid_paths = sorted(
            path
            for path in (root / split_dir / "textgrid_dir").iterdir()
            if path.is_file() and path.suffix.lower() in TEXTGRID_SUFFIXES
        )
        audio_by_meeting: dict[str, Path] = {}
        for path in audio_paths:
            match = AUDIO_STEM.fullmatch(path.stem)
            if match is None:
                raise ValueError(f"unexpected WAV name: {path}")
            audio_by_meeting[match.group("meeting")] = path
        textgrid_by_meeting = {path.stem: path for path in textgrid_paths}
        if audio_by_meeting.keys() != textgrid_by_meeting.keys():
            raise ValueError(f"WAV/TextGrid meeting mismatch in {split_dir}")
        meetings_by_split[split] = set(audio_by_meeting)

        for meeting_id in sorted(audio_by_meeting):
            audio_path = audio_by_meeting[meeting_id]
            textgrid_path = textgrid_by_meeting[meeting_id]
            audio_metadata = inspect_audio(audio_path)
            textgrid_metadata = inspect_textgrid(
                textgrid_path, float(audio_metadata["duration"])
            )
            for kind, path, metadata in (
                ("audio", audio_path, audio_metadata),
                ("annotation", textgrid_path, textgrid_metadata),
            ):
                rows.append(
                    {
                        "split": split,
                        "kind": kind,
                        "meeting_id": meeting_id,
                        "relative_path": path.relative_to(root).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        **metadata,
                    }
                )

    for left, left_meetings in meetings_by_split.items():
        for right, right_meetings in meetings_by_split.items():
            if left < right and left_meetings & right_meetings:
                raise ValueError(f"meeting IDs overlap between {left} and {right}")

    rows.sort(key=lambda row: str(row["relative_path"]))
    for split, split_dir in SPLITS.items():
        split_rows = [row for row in rows if row["split"] == split]
        summaries[split] = {
            "relative_path": split_dir,
            "file_count": len(split_rows),
            "expected_bytes": sum(int(row["bytes"]) for row in split_rows),
            "tree_sha256": tree_sha256(rows, split_dir),
            "annotation_out_of_bounds_count": sum(
                1
                for row in split_rows
                if row["kind"] == "annotation"
                and float(row.get("audio_overrun", 0.0)) > 0.02
            ),
            "max_annotation_overrun_seconds": max(
                (
                    float(row.get("audio_overrun", 0.0))
                    for row in split_rows
                    if row["kind"] == "annotation"
                ),
                default=0.0,
            ),
        }
    return rows, summaries


def write_inventory(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8") as stream,
    ):
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows, summaries = build_inventory(args.root.resolve())
    write_inventory(args.output, rows)
    print(json.dumps({"records": len(rows), "splits": summaries}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
