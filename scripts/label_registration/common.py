"""Shared helpers for the label-registration scripts in this directory.

Each script writes new dataset versions under <root>/datasets/<dataset>/versions/<version>/ (temporary file first,
then rename), reads every written gzip back in full, and returns artifact dictionaries that carry the measured
record count, byte size and sha256.
"""

import gzip
import hashlib
import json
import os
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def new_version_dir(root, dataset, version):
    """Create the version directory; versions are immutable, so an existing one is an error."""
    out = Path(root) / "datasets" / dataset / "versions" / version
    if out.exists():
        raise SystemExit(f"{out} exists; versions are immutable")
    old = os.umask(0o002)
    try:
        out.mkdir(parents=True)
    finally:
        os.umask(old)
    return out


def write_jsonl_gz(path, rows):
    """Write rows (dicts) to a gzip JSONL via <path>.tmp, read it back in full, return (count, bytes, sha256)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as writer:
        for row in rows:
            writer.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    temporary.replace(path)
    with gzip.open(path, "rt", encoding="utf-8") as stream:  # the gzip CRC catches a lost write
        count = sum(1 for _ in stream)
    return count, path.stat().st_size, sha256(path)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path.stat().st_size, sha256(path)


def artifact(name, kind, dataset, version, relative, size, digest, **metadata):
    """Artifact dictionary for a file written under datasets/<dataset>/versions/<version>/."""
    entry = {
        "name": name,
        "kind": kind,
        "root_alias": "aidc_data",
        "relative_path": f"datasets/{dataset}/versions/{version}/{relative}",
        "expected_bytes": size,
        "sha256": digest,
    }
    if metadata:
        entry["metadata"] = metadata
    return entry


def write_declaration_file(path, rows, header):
    """Write catalog / view declarations without YAML anchors and with a one-line Chinese header comment."""
    from audio_data_contract.declarations import write_declarations

    path = Path(path)
    write_declarations(path, json.loads(json.dumps(rows)))  # the round trip makes shared objects separate copies
    path.write_text(f"# {header}\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
