"""Optional, local Lance materializations; JSONL and Layers remain authoritative."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path

from .errors import ContractError
from .records import load_records
from .types import RECORD_SCHEMA_VERSION, AudioRecord

STORAGE_VERSION = "2.0"
MAPPING_VERSION = "audio-record-lance/1.0"


def _dependencies():
    try:
        import lance
        import pyarrow as pa
    except ImportError as exc:
        raise ContractError(
            "Lance requires: pip install 'audio-data-contract[lance]'"
        ) from exc
    return lance, pa


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _schema():
    _, pa = _dependencies()
    return pa.schema(
        [
            pa.field("id", pa.string(), nullable=False),
            pa.field("task", pa.string(), nullable=False),
            pa.field("language", pa.string(), nullable=False),
            pa.field("splits", pa.list_(pa.string()), nullable=False),
            pa.field("clean_pass", pa.bool_()),
            pa.field("retained", pa.bool_(), nullable=False),
            pa.field("record_json", pa.large_string(), nullable=False),
        ],
        metadata={b"mapping": MAPPING_VERSION.encode()},
    )


def schema_hash():
    contract = json.loads(
        files("audio_data_contract")
        .joinpath("schemas/audio-record-1.0.json")
        .read_text()
    )
    return _hash(
        {"contract": contract, "mapping": MAPPING_VERSION, "arrow": str(_schema())}
    )


@dataclass(frozen=True)
class LanceArtifact:
    table_path: str
    snapshot_version: int
    storage_version: str
    audio_record_schema: str
    record_count: int
    schema_hash: str
    source_view: str
    rebuild_metadata: dict
    kind: str = "lance"

    def __post_init__(self):
        if self.kind != "lance" or self.audio_record_schema != RECORD_SCHEMA_VERSION:
            raise ContractError("unsupported Lance artifact or AudioRecord schema")
        if self.storage_version != STORAGE_VERSION:
            raise ContractError(
                f"unsupported Lance storage version: {self.storage_version}"
            )
        if (
            type(self.snapshot_version) is not int
            or self.snapshot_version < 1
            or type(self.record_count) is not int
            or self.record_count < 0
        ):
            raise ContractError("invalid Lance snapshot version or record count")
        if not self.source_view or "@" not in self.source_view:
            raise ContractError(
                "source_view must include a fixed version: view@version"
            )

    def to_dict(self):
        return asdict(self)

    @classmethod
    def read(cls, path):
        try:
            return cls(**json.loads(Path(path).read_text()))
        except (TypeError, ValueError, OSError) as exc:
            raise ContractError(
                f"invalid Lance artifact manifest {path}: {exc}"
            ) from exc


@dataclass(frozen=True)
class RecordQuery:
    ids: tuple[str, ...] | None = None
    task: str | None = None
    language: str | None = None
    split: str | None = None
    clean_pass: bool | None = None

    def __post_init__(self):
        if self.clean_pass is not None and type(self.clean_pass) is not bool:
            raise ContractError("clean_pass must be boolean")

    def matches(self, record):
        clean = record.metadata.get("clean")
        passed = clean.get("pass") if isinstance(clean, dict) else None
        return (
            (self.ids is None or record.id in self.ids)
            and (self.task is None or record.task == self.task)
            and (self.language is None or record.language == self.language)
            and (
                self.split is None
                or any(s.ref.split == self.split for s in record.audio_slots)
            )
            and (self.clean_pass is None or passed is self.clean_pass)
        )

    def expression(self):
        def quote(value):
            return "'" + value.replace("'", "''") + "'"

        parts = ["retained = true"]
        if self.ids is not None:
            parts.append(
                "id IN (" + ",".join(map(quote, self.ids)) + ")"
                if self.ids
                else "false"
            )
        for name in ("task", "language"):
            value = getattr(self, name)
            if value is not None:
                parts.append(f"{name} = {quote(value)}")
        if self.split is not None:
            parts.append(f"array_has(splits, {quote(self.split)})")
        if self.clean_pass is not None:
            parts.append("clean_pass = " + str(self.clean_pass).lower())
        return " AND ".join(parts)


def _row(record, retained=True):
    # Revalidate before writing, including objects constructed directly by callers.
    record = AudioRecord.from_dict(record.to_dict())
    clean = record.metadata.get("clean")
    passed = clean.get("pass") if isinstance(clean, dict) else None
    return {
        "id": record.id,
        "task": record.task,
        "language": record.language,
        "splits": sorted({s.ref.split for s in record.audio_slots}),
        "clean_pass": passed if type(passed) is bool else None,
        "retained": retained,
        "record_json": _json(record.to_dict()),
    }


def _open_artifact(artifact, *, verify_count=False):
    lance, _ = _dependencies()
    if artifact.schema_hash != schema_hash():
        raise ContractError(
            "Lance schema hash mismatch; rebuild with this mapping version"
        )
    try:
        dataset = lance.dataset(artifact.table_path, version=artifact.snapshot_version)
        if not dataset.schema.equals(_schema(), check_metadata=True):
            raise ContractError("Lance physical schema mismatch")
        if dataset.data_storage_version != artifact.storage_version:
            raise ContractError("Lance storage version mismatch")
        if (
            verify_count
            and dataset.count_rows(filter="retained = true") != artifact.record_count
        ):
            raise ContractError("Lance snapshot record count mismatch")
        return dataset
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(
            f"cannot read Lance snapshot {artifact.snapshot_version} at "
            f"{artifact.table_path}; check version/schema compatibility: {exc}"
        ) from exc


def read_lance(artifact, query=None, *, batch_size=4096):
    dataset = _open_artifact(artifact)
    try:
        for batch in dataset.to_batches(
            columns=["record_json"],
            filter=(query or RecordQuery()).expression(),
            batch_size=batch_size,
        ):
            for value in batch.column(0).to_pylist():
                yield AudioRecord.from_dict(json.loads(value))
    except Exception as exc:
        raise ContractError(f"Lance snapshot read/schema error: {exc}") from exc


def import_jsonl(
    source, destination, *, source_view, batch_size=4096, rebuild_metadata=None
):
    """Publish a new local directory only after all batches validate successfully."""
    lance, pa = _dependencies()
    if batch_size < 1:
        raise ContractError("batch_size must be positive")
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ContractError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".lance-import-", dir=destination.parent))
    count = 0
    digest = hashlib.sha256()
    try:
        with sqlite3.connect(work / "ids.sqlite", check_same_thread=False) as ids:
            ids.execute("CREATE TABLE ids (id TEXT PRIMARY KEY)")

            def batches():
                nonlocal count
                rows = []
                for record in load_records(source):
                    try:
                        ids.execute("INSERT INTO ids VALUES (?)", (record.id,))
                    except sqlite3.IntegrityError as exc:
                        raise ContractError(
                            f"duplicate record ID: {record.id}"
                        ) from exc
                    row = _row(record)
                    digest.update((row["record_json"] + "\n").encode())
                    count += 1
                    rows.append(row)
                    if len(rows) == batch_size:
                        yield pa.RecordBatch.from_pylist(rows, schema=_schema())
                        rows = []
                if rows:
                    yield pa.RecordBatch.from_pylist(rows, schema=_schema())

            dataset = lance.write_dataset(
                batches(),
                work / "table.lance",
                schema=_schema(),
                data_storage_version=STORAGE_VERSION,
            )
        (work / "ids.sqlite").unlink()
        artifact = LanceArtifact(
            str(destination / "table.lance"),
            dataset.version,
            STORAGE_VERSION,
            RECORD_SCHEMA_VERSION,
            count,
            schema_hash(),
            source_view,
            rebuild_metadata
            or {
                "source_jsonl": str(source),
                "source_records_sha256": digest.hexdigest(),
                "mapping": MAPPING_VERSION,
                "layers": [],
                "writes": [],
                "pylance": lance.__version__,
            },
        )
        if dataset.count_rows() != count:
            raise ContractError("Lance import record count mismatch")
        (work / "artifact.json").write_text(_json(artifact.to_dict()) + "\n")
        work.rename(destination)
        return artifact
    except Exception as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError(f"Lance import failed; nothing published: {exc}") from exc
    finally:
        if work.exists():
            shutil.rmtree(work)


def materialize_layer(layer, *, source_view):
    """One local writer, one merge commit, then publish an immutable artifact manifest.

    If this fails, patch.jsonl and manifest.json remain available for JSONL replay.
    All writers to a managed table must use this adapter (local POSIX lock).
    """
    import fcntl

    from .layers import apply_patch, read_layer

    lance, pa = _dependencies()
    layer = Path(layer).resolve()
    manifest, patches, step = read_layer(layer)
    parent = LanceArtifact(**manifest["parent"])
    output = layer / "artifact.json"
    if output.exists():
        raise ContractError(f"Layer already published: {output}")
    with (Path(parent.table_path).parent / ".writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        dataset = _open_artifact(parent)
        latest = lance.dataset(parent.table_path)
        if latest.version != parent.snapshot_version:
            raise ContractError(
                "stale Layer parent snapshot; replay or rebuild required"
            )
        found = {
            r.id: r
            for r in read_lance(
                parent, RecordQuery(ids=tuple(p["id"] for p in patches))
            )
        }
        rows = []
        for patch in patches:
            if patch["id"] not in found:
                raise ContractError(f"unknown or deleted patch ID: {patch['id']}")
            record, retained = apply_patch(found[patch["id"]], patch, step)
            rows.append(_row(record, retained))
        # Validate identity before creating any new table version.
        metadata = {
            **parent.rebuild_metadata,
            "layers": [*parent.rebuild_metadata["layers"], str(layer)],
            "writes": sorted(set(parent.rebuild_metadata["writes"]) | set(step.writes)),
        }
        artifact = LanceArtifact(
            parent.table_path,
            parent.snapshot_version + 1,
            parent.storage_version,
            parent.audio_record_schema,
            manifest["result_record_count"],
            parent.schema_hash,
            source_view,
            metadata,
        )
        try:
            dataset.merge_insert("id").when_matched_update_all().execute(
                pa.Table.from_pylist(rows, schema=_schema())
            )
            # Local lock guarantees this adapter is the only writer to this table.
            committed = lance.dataset(parent.table_path)
            artifact = LanceArtifact(
                **{**artifact.to_dict(), "snapshot_version": committed.version}
            )
            _open_artifact(artifact, verify_count=True)
            temporary = layer / ".artifact.json.tmp"
            temporary.write_text(_json(artifact.to_dict()) + "\n")
            temporary.rename(output)
        except Exception as exc:
            raise ContractError(
                f"Lance Layer materialization failed; canonical patch retained at {layer}. "
                f"Replay/rebuild from its parent: {exc}"
            ) from exc
        return artifact


def verify_equivalence(artifact, source):
    """Streaming exact ID/fact comparison with a disk-backed uniqueness index."""
    dataset = _open_artifact(artifact, verify_count=True)
    del dataset
    with (
        tempfile.TemporaryDirectory(prefix="lance-verify-") as directory,
        sqlite3.connect(Path(directory) / "facts.sqlite") as db,
    ):
        db.execute("CREATE TABLE facts (id TEXT PRIMARY KEY, payload TEXT)")
        count = 0
        for record in load_records(source):
            try:
                db.execute(
                    "INSERT INTO facts VALUES (?, ?)",
                    (record.id, _json(record.to_dict())),
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError(f"duplicate JSONL ID: {record.id}") from exc
            count += 1
        for record in read_lance(artifact):
            found = db.execute(
                "SELECT payload FROM facts WHERE id=?", (record.id,)
            ).fetchone()
            if found is None or found[0] != _json(record.to_dict()):
                raise ContractError(f"Lance/JSONL record mismatch: {record.id}")
            db.execute("DELETE FROM facts WHERE id=?", (record.id,))
        if db.execute("SELECT count(*) FROM facts").fetchone()[0]:
            raise ContractError("Lance/JSONL ID sets differ")
    return {"record_count": count, "ids_equal": True, "records_equal": True}


def rebuild_artifact(artifact, destination):
    """Rebuild entirely from the original JSONL and canonical Layers, without old table."""
    from .layers import read_layer, replay_layer
    from .records import write_records

    metadata = artifact.rebuild_metadata

    def source_records():
        digest = hashlib.sha256()
        for record in load_records(metadata["source_jsonl"]):
            digest.update((_json(record.to_dict()) + "\n").encode())
            yield record
        if digest.hexdigest() != metadata["source_records_sha256"]:
            raise ContractError("rebuild source JSONL hash mismatch")

    records = source_records()
    previous_layers = []
    for layer in metadata["layers"]:
        manifest, _, _ = read_layer(layer)
        parent_metadata = manifest["parent"]["rebuild_metadata"]
        if (
            parent_metadata["source_records_sha256"]
            != metadata["source_records_sha256"]
            or parent_metadata["layers"] != previous_layers
        ):
            raise ContractError("rebuild Layer parent lineage mismatch")
        records = replay_layer(records, layer)
        previous_layers.append(layer)
    with tempfile.TemporaryDirectory(prefix="lance-rebuild-") as directory:
        source = Path(directory) / "records.jsonl"
        write_records(records, source)
        # Check count before publication, including a rebuild from an empty result.
        if sum(1 for _ in load_records(source)) != artifact.record_count:
            raise ContractError("rebuild record count mismatch")
        rebuilt = import_jsonl(
            source,
            destination,
            source_view=artifact.source_view,
            rebuild_metadata=metadata,
        )
    return rebuilt


def rebuild_layer(layer, destination, *, source_view):
    """Recover a failed query-layer write using only durable processing facts."""
    from .layers import read_layer

    manifest, _, step = read_layer(layer)
    parent = LanceArtifact(**manifest["parent"])
    metadata = {
        **parent.rebuild_metadata,
        "layers": [*parent.rebuild_metadata["layers"], str(Path(layer).resolve())],
        "writes": sorted(set(parent.rebuild_metadata["writes"]) | set(step.writes)),
    }
    intended = LanceArtifact(
        **{
            **parent.to_dict(),
            "source_view": source_view,
            "record_count": manifest["result_record_count"],
            "rebuild_metadata": metadata,
        }
    )
    return rebuild_artifact(intended, destination)
