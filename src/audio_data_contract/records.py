"""Streaming JSONL serialization for stable records and frozen examples."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterable, Iterator, TextIO

from .types import AudioExample, AudioRecord


def _open(path: Path, mode: str) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def _load(path: str | Path) -> Iterator[dict]:
    source = Path(path)
    with _open(source, "r") as stream:
        for line_number, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number}: {exc}") from exc


def load_records(path: str | Path) -> Iterator[AudioRecord]:
    for item in _load(path):
        yield AudioRecord.from_dict(item)


def load_examples(path: str | Path) -> Iterator[AudioExample]:
    for item in _load(path):
        yield AudioExample.from_dict(item)


def _write(items: Iterable[dict], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _open(destination, "w") as stream:
        for item in items:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
            stream.write("\n")


def write_records(records: Iterable[AudioRecord], path: str | Path) -> None:
    _write((record.to_dict() for record in records), path)


def write_examples(examples: Iterable[AudioExample], path: str | Path) -> None:
    _write((example.to_dict() for example in examples), path)
