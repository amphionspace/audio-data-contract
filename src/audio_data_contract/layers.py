"""Durable cleaning patches, independently replayable on AudioRecord JSONL."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .errors import ContractError
from .lance import _hash, _json
from .types import AudioRecord, TransformStep


def _overlaps(left, right):
    return left == right or left.startswith(right + ".") or right.startswith(left + ".")


def _covers(paths, field):
    return any(field == p or field.startswith(p + ".") for p in paths)


def validate_step(step, prior_writes=()):
    allowed = {"target", "language", "hotwords", "metadata", "labels", "$membership"}
    for field in step.writes:
        if field.split(".")[0] not in allowed or any(not p for p in field.split(".")):
            raise ContractError(f"unsupported Layer write field: {field}")
        if "." in field and field.split(".")[0] not in {"metadata", "labels"}:
            raise ContractError(f"unsupported Layer write field: {field}")
        if any(_overlaps(field, old) for old in prior_writes) and not _covers(
            step.overrides, field
        ):
            raise ContractError(f"field conflict for {field}; declare an override")


def apply_patch(record, patch, step):
    """Apply declared dotted field assignments; membership is separate from data."""
    if patch["id"] != record.id:
        raise ContractError("Layer patch ID does not match record")
    if patch.get("status") not in {"keep", "delete"}:
        raise ContractError("Layer status must be keep or delete")
    if patch["status"] == "delete" and "$membership" not in step.writes:
        raise ContractError("Layer deletion requires writes: $membership")
    changes = patch.get("changes")
    if not isinstance(changes, dict):
        raise ContractError("Layer changes must be an object")
    fields = list(changes)
    for i, field in enumerate(fields):
        if field == "$membership" or not _covers(step.writes, field):
            raise ContractError(f"undeclared Layer field: {field}")
        if any(_overlaps(field, other) for other in fields[i + 1 :]):
            raise ContractError(f"overlapping patch fields: {field}")
    data = json.loads(_json(record.to_dict()))
    for field, value in changes.items():
        parts = field.split(".")
        if any(not part for part in parts):
            raise ContractError(f"invalid Layer field: {field}")
        node = data
        for part in parts[:-1]:
            if part not in node:
                node[part] = {}
            if not isinstance(node[part], dict):
                raise ContractError(f"Layer field parent is not an object: {field}")
            node = node[part]
        leaf = parts[-1]
        if leaf in node and node[leaf] != value and not _covers(step.overrides, field):
            raise ContractError(f"existing field {field}; declare an override")
        node[leaf] = value
    return AudioRecord.from_dict(data), patch["status"] == "keep"


def write_layer(destination, patches, *, parent, step, tool, model=None):
    """Persist a batch before materializing it; shared processing facts live in manifest."""
    from .lance import RecordQuery, read_lance

    validate_step(step, parent.rebuild_metadata.get("writes", []))
    if not tool:
        raise ContractError("Layer requires a processing tool")
    destination = Path(destination).resolve()
    if destination.exists():
        raise ContractError(f"Layer destination already exists: {destination}")
    rows, ids = [], set()
    for patch in patches:
        if set(patch) != {"id", "changes", "status"}:
            raise ContractError("patch requires exactly id, changes, status")
        if not isinstance(patch["id"], str) or not patch["id"]:
            raise ContractError("invalid patch ID")
        if patch["id"] in ids:
            raise ContractError(f"duplicate patch ID: {patch['id']}")
        ids.add(patch["id"])
        row = {**patch, "parent_version": parent.snapshot_version}
        rows.append({**row, "patch_hash": _hash(row)})
    if not rows:
        raise ContractError("Layer patch batch may not be empty")
    rows.sort(key=lambda row: row["id"])
    found = {r.id: r for r in read_lance(parent, RecordQuery(ids=tuple(ids)))}
    if ids != found.keys():
        raise ContractError(
            f"unknown or deleted patch IDs: {sorted(ids - found.keys())[:10]}"
        )
    for row in rows:
        apply_patch(found[row["id"]], row, step)
    manifest = {
        "schema_version": "audio-record-layer/1.0",
        "parent": parent.to_dict(),
        "transform": step.to_dict(),
        "tool": tool,
        "model": model,
        "parameters": step.parameters,
        "input_count": len(rows),
        "output_count": sum(row["status"] == "keep" for row in rows),
        "parent_record_count": parent.record_count,
        "result_record_count": parent.record_count
        - sum(row["status"] == "delete" for row in rows),
        "patch_hash": _hash(rows),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".layer-", dir=destination.parent))
    try:
        (work / "patch.jsonl").write_text("".join(_json(row) + "\n" for row in rows))
        (work / "manifest.json").write_text(_json(manifest) + "\n")
        work.rename(destination)
    finally:
        if work.exists():
            shutil.rmtree(work)
    return destination


def read_layer(path):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest["schema_version"] != "audio-record-layer/1.0":
        raise ContractError("unsupported Layer schema")
    rows = [
        json.loads(line) for line in (path / "patch.jsonl").read_text().splitlines()
    ]
    if _hash(rows) != manifest["patch_hash"]:
        raise ContractError("Layer patch hash mismatch")
    ids = set()
    for row in rows:
        if row["id"] in ids:
            raise ContractError(f"duplicate patch ID: {row['id']}")
        ids.add(row["id"])
        payload = {key: value for key, value in row.items() if key != "patch_hash"}
        if _hash(payload) != row["patch_hash"]:
            raise ContractError("individual Layer patch hash mismatch")
        if row["parent_version"] != manifest["parent"]["snapshot_version"]:
            raise ContractError("Layer parent version mismatch")
    step = TransformStep.from_dict(manifest["transform"])
    validate_step(step, manifest["parent"]["rebuild_metadata"].get("writes", []))
    if (
        len(rows) != manifest["input_count"]
        or sum(r["status"] == "keep" for r in rows) != manifest["output_count"]
        or manifest["result_record_count"]
        != manifest["parent_record_count"] - sum(r["status"] == "delete" for r in rows)
    ):
        raise ContractError("Layer count mismatch")
    return manifest, rows, step


def replay_layer(records, layer):
    """Replay onto the declared parent records without importing Lance/PyArrow."""
    manifest, rows, step = read_layer(layer)
    patches = {r["id"]: r for r in rows}
    count = 0
    for record in records:
        count += 1
        patch = patches.pop(record.id, None)
        if patch is None:
            yield record
        else:
            updated, retained = apply_patch(record, patch, step)
            if retained:
                yield updated
    if patches or count != manifest["parent_record_count"]:
        raise ContractError("Layer replay parent IDs/count mismatch")
