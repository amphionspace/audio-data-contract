"""Shared helpers for the English board training versions (text-final v3, open-audio-llm A line).

Each version is written as audio-record/1.0 records plus an audio index under
``/workspace/data/datasets/<dataset_id>/versions/<version>/``, the layout of ami_sdm@asr-20261014.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path

DATA = Path("/workspace/data")
FINAL = "final-v3-20261125"
SPEC = "docs/reference/training-text.md（v3）"
RUN_DIR = "/workspace/workspace/mingdong/data/amphiondata/aline-en-20261125"
MIN_S, MAX_S = 0.5, 30.0


def version_dir(ds: str, ver: str) -> Path:
    return Path("datasets") / ds / "versions" / ver


def read_jsonl(path):
    """Rows of a .jsonl or .jsonl.gz file."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            yield json.loads(line)


def write_jsonl_gz(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    # no name or mtime in the gzip header, so a rebuild with the same rows gives the same sha256
    with open(tmp, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz, \
            io.TextIOWrapper(gz, encoding="utf-8") as w:
        for row in rows:
            w.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(path)
    return n


def record(ds, ver, split, cut_id, start, duration, target, metadata, rid=None) -> dict:
    return {
        "schema_version": "audio-record/1.0",
        "id": f"{split}:{rid or cut_id}",
        "task": "asr",
        "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
            "dataset_id": ds, "version": ver, "split": split, "cut_id": cut_id, "channel": 0,
            "start": round(start, 3), "duration": round(duration, 3)}}],
        "target": target,
        "language": "en",
        "labels": {},
        "hotwords": [],
        "metadata": metadata,
    }


def index_row(cut_id, rel, sample_rate, channels, num_frames) -> dict:
    return {"cut_id": cut_id, "root_alias": "aidc_data", "relative_path": str(rel), "sample_rate": sample_rate,
            "channels": channels, "num_frames": num_frames, "duration": round(num_frames / sample_rate, 6)}


def distribution(durations) -> dict:
    d = sorted(durations)
    if not d:
        return {"count": 0, "hours": 0.0}

    def q(p):
        return round(d[min(len(d) - 1, int(p * len(d)))], 2)

    return {"count": len(d), "hours": round(sum(d) / 3600, 4), "min": round(d[0], 2), "p50": q(0.5), "p90": q(0.9),
            "p99": q(0.99), "max": round(d[-1], 2), "mean": round(sum(d) / len(d), 3)}


def artifact(name, kind, rel, record_count=None) -> dict:
    data = (DATA / rel).read_bytes()
    a = {"name": name, "kind": kind, "root_alias": "aidc_data", "relative_path": str(rel), "expected_bytes": len(data),
         "sha256": hashlib.sha256(data).hexdigest()}
    if record_count is not None:
        a["metadata"] = {"record_count": record_count}
    return a
