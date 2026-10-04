"""Optional, local Lance materializations; JSONL and Layers remain authoritative."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, field
from functools import cache
from importlib.resources import files
from pathlib import Path

from .errors import ContractError
from .records import load_records
from .roots import load_roots, portable_path, resolve_root_path
from .types import RECORD_SCHEMA_VERSION, AudioRecord, _portable_path

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


@cache
def schema_hash():
    contract = json.loads(
        files("audio_data_contract")
        .joinpath("schemas/audio-record-1.0.json")
        .read_text()
    )
    return _hash(
        {"contract": contract, "mapping": MAPPING_VERSION, "arrow": str(_schema())}
    )


def _is_ref(value):
    return isinstance(value, dict)


def _check_location(value, where):
    """A location is a legacy absolute path or a {root_alias, relative_path} ref."""
    if isinstance(value, str) and value:
        return
    if (
        _is_ref(value)
        and set(value) == {"root_alias", "relative_path"}
        and isinstance(value["root_alias"], str)
        and value["root_alias"]
    ):
        _portable_path(value["relative_path"], where)
        return
    raise ContractError(f"{where} must be a path or a root_alias reference")


def _location(path, roots):
    return str(Path(path).resolve()) if roots is None else portable_path(path, roots)


def _local(value, roots):
    if not _is_ref(value):
        return Path(value)
    return resolve_root_path(
        value["root_alias"],
        value["relative_path"],
        load_roots() if roots is None else roots,
        "Lance artifact",
    )


@dataclass(frozen=True)
class LanceArtifact:
    table_path: str | dict
    snapshot_version: int
    storage_version: str
    audio_record_schema: str
    record_count: int
    schema_hash: str
    source_view: str
    rebuild_metadata: dict
    kind: str = "lance"
    # Machine-local root aliases; never serialized. None means AUDIO_DATA_ROOTS_FILE.
    roots: dict | None = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        _check_location(self.table_path, "table_path")
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

    @property
    def portable(self):
        return _is_ref(self.table_path)

    @property
    def table_uri(self):
        return str(_local(self.table_path, self.roots))

    def local(self, value):
        """Resolve a stored location (table, source JSONL or Layer) on this machine."""
        return _local(value, self.roots)

    def location_roots(self):
        """Roots used to store new locations: None keeps legacy absolute paths."""
        if not self.portable:
            return None
        return load_roots() if self.roots is None else self.roots

    def replace(self, **changes):
        return type(self)(**{**self.to_dict(), "roots": self.roots, **changes})

    def to_dict(self):
        data = asdict(self)
        del data["roots"]
        return data

    @classmethod
    def read(cls, path, roots=None):
        try:
            return cls(**json.loads(Path(path).read_text()), roots=roots)
        except (TypeError, ValueError, OSError) as exc:
            raise ContractError(
                f"invalid Lance artifact manifest {path}: {exc}"
            ) from exc


def catalog_ref(artifact, sidecar, *, name, roots):
    """Catalog ArtifactRef that pins a published sidecar and its snapshot."""
    from .types import ArtifactRef

    if not artifact.portable:
        raise ContractError("catalog registration requires a portable Lance artifact")
    return ArtifactRef(
        name=name,
        kind="lance-table",
        **portable_path(sidecar, roots),
        metadata={
            "snapshot_version": artifact.snapshot_version,
            "record_count": artifact.record_count,
            "schema_hash": artifact.schema_hash,
            "source_view": artifact.source_view,
        },
    )


def open_catalog_artifact(catalog, dataset_id, version, artifact_name, roots):
    """Open a registered lance-table at exactly the snapshot the catalog pins."""
    from .catalog import resolve_artifact

    ref = catalog.get(dataset_id, version).artifact(artifact_name)
    if ref.kind != "lance-table":
        raise ContractError(f"artifact {artifact_name!r} is not a lance-table")
    sidecar = resolve_artifact(catalog, dataset_id, version, artifact_name, roots)
    artifact = LanceArtifact.read(sidecar, roots)
    for key in ("snapshot_version", "record_count", "schema_hash"):
        if getattr(artifact, key) != ref.metadata[key]:
            raise ContractError(f"Lance sidecar {key} differs from catalog: {sidecar}")
    return artifact


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


def _row(record, retained=True, *, validate=True):
    if validate:
        # Revalidate objects constructed directly by callers.
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


# Scalar indexes on every query projection; each build commits a table version.
INDICES = (
    ("id", "BTREE"),
    ("task", "BITMAP"),
    ("language", "BITMAP"),
    ("splits", "LABEL_LIST"),
    ("clean_pass", "BITMAP"),
    ("retained", "BITMAP"),
)


def _create_indices(dataset):
    for column, kind in INDICES:
        dataset.create_scalar_index(column, kind)
    return dataset


def _encode_lines(chunk):
    """Validate one chunk of raw JSONL lines into an Arrow batch, in source order.

    Runs in import worker processes; returns the batch, its IDs and the canonical
    record stream bytes that feed the source digest.
    """
    _, pa = _dependencies()
    source, first_line, lines = chunk
    rows = []
    for number, line in enumerate(lines, first_line):
        line = line.strip()
        if not line:
            continue
        try:
            record = AudioRecord.from_dict(json.loads(line))
        except ValueError as exc:
            raise ContractError(f"{source}:{number}: {exc}") from exc
        rows.append(_row(record, validate=False))
    stream = "".join(row["record_json"] + "\n" for row in rows).encode()
    batch = pa.RecordBatch.from_pylist(rows, schema=_schema())
    return batch, [row["id"] for row in rows], stream


def _line_chunks(source, size):
    from .records import _open

    with _open(source, "r") as stream:
        lines, first = [], 1
        for number, line in enumerate(stream, 1):
            lines.append(line)
            if len(lines) == size:
                yield str(source), first, lines
                lines, first = [], number + 1
        if lines:
            yield str(source), first, lines


def _ordered(executor, function, items, window):
    """Lazy, order-preserving map with at most `window` chunks in flight."""
    from collections import deque

    pending = deque()
    for item in items:
        pending.append(executor.submit(function, item))
        if len(pending) >= window:
            yield pending.popleft().result()
    while pending:
        yield pending.popleft().result()


def _claim_ids(db, ids):
    """Reserve a batch of IDs in the disk-backed index; reject any duplicate."""
    try:
        db.executemany("INSERT INTO ids VALUES (?)", ((i,) for i in ids))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        seen = set()
        for i in ids:
            if i in seen or db.execute("SELECT 1 FROM ids WHERE id=?", (i,)).fetchone():
                raise ContractError(f"duplicate record ID: {i}") from None
            seen.add(i)
        raise


def _open_artifact(artifact, *, verify_count=False):
    lance, _ = _dependencies()
    if artifact.schema_hash != schema_hash():
        raise ContractError(
            "Lance schema hash mismatch; rebuild with this mapping version"
        )
    try:
        dataset = lance.dataset(artifact.table_uri, version=artifact.snapshot_version)
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
    source,
    destination,
    *,
    source_view,
    batch_size=4096,
    rebuild_metadata=None,
    roots=None,
    workers=1,
):
    """Publish a new local directory only after all batches validate successfully.

    With roots, stored locations become portable root_alias references. Workers > 1
    validate/encode batches in spawned processes; output order stays source order.
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    lance, _ = _dependencies()
    if batch_size < 1 or workers < 1:
        raise ContractError("batch_size and workers must be positive")
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ContractError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".lance-import-", dir=destination.parent))
    count = 0
    digest = hashlib.sha256()
    pool = None
    try:
        chunks = _line_chunks(source, batch_size)
        if workers == 1:
            encoded = map(_encode_lines, chunks)
        else:
            # A dead worker raises BrokenProcessPool instead of hanging the import.
            pool = ProcessPoolExecutor(
                workers, mp_context=multiprocessing.get_context("spawn")
            )
            encoded = _ordered(pool, _encode_lines, chunks, 2 * workers)
        with sqlite3.connect(work / "ids.sqlite", check_same_thread=False) as ids:
            ids.execute("PRAGMA journal_mode=MEMORY")
            ids.execute("PRAGMA synchronous=OFF")
            ids.execute("CREATE TABLE ids (id TEXT PRIMARY KEY)")

            def batches():
                nonlocal count
                for batch, batch_ids, stream in encoded:
                    if not batch_ids:
                        continue
                    _claim_ids(ids, batch_ids)
                    digest.update(stream)
                    count += len(batch_ids)
                    yield batch

            dataset = lance.write_dataset(
                batches(),
                work / "table.lance",
                schema=_schema(),
                data_storage_version=STORAGE_VERSION,
            )
        (work / "ids.sqlite").unlink()
        if count:
            dataset = _create_indices(dataset)
        artifact = LanceArtifact(
            _location(destination / "table.lance", roots),
            dataset.version,
            STORAGE_VERSION,
            RECORD_SCHEMA_VERSION,
            count,
            schema_hash(),
            source_view,
            rebuild_metadata
            or {
                "source_jsonl": _location(source, roots),
                "source_records_sha256": digest.hexdigest(),
                "mapping": MAPPING_VERSION,
                "layers": [],
                "writes": [],
                "pylance": lance.__version__,
            },
            roots=roots,
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
        if pool is not None:
            pool.shutdown(cancel_futures=True)
        if work.exists():
            shutil.rmtree(work)


def materialize_layer(layer, *, source_view, roots=None):
    """One local writer, one merge commit, then publish an immutable artifact manifest.

    If this fails, patch.jsonl and manifest.json remain available for JSONL replay.
    All writers to a managed table must use this adapter (local POSIX lock).
    """
    import fcntl

    from .layers import apply_patch, read_layer

    lance, pa = _dependencies()
    layer = Path(layer).resolve()
    manifest, patches, step = read_layer(layer)
    parent = LanceArtifact(**manifest["parent"], roots=roots)
    output = layer / "artifact.json"
    if output.exists():
        raise ContractError(f"Layer already published: {output}")
    with (Path(parent.table_uri).parent / ".writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        dataset = _open_artifact(parent)
        latest = lance.dataset(parent.table_uri)
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
            "layers": [
                *parent.rebuild_metadata["layers"],
                _location(layer, parent.location_roots()),
            ],
            "writes": sorted(set(parent.rebuild_metadata["writes"]) | set(step.writes)),
        }
        artifact = parent.replace(
            snapshot_version=parent.snapshot_version + 1,
            record_count=manifest["result_record_count"],
            source_view=source_view,
            rebuild_metadata=metadata,
        )
        try:
            dataset.merge_insert("id").when_matched_update_all().execute(
                pa.Table.from_pylist(rows, schema=_schema())
            )
            # Local lock guarantees this adapter is the only writer to this table.
            committed = lance.dataset(parent.table_uri)
            if committed.describe_indices():
                # Index the rewritten rows; this commits one more table version.
                committed.optimize.optimize_indices()
                committed = lance.dataset(parent.table_uri)
            artifact = artifact.replace(snapshot_version=committed.version)
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


def _digest(record):
    return hashlib.sha256(_json(record.to_dict()).encode()).digest()


def verify_equivalence(artifact, source):
    """Streaming exact ID/fact comparison with a disk-backed uniqueness index."""
    dataset = _open_artifact(artifact, verify_count=True)
    del dataset
    with (
        tempfile.TemporaryDirectory(prefix="lance-verify-") as directory,
        sqlite3.connect(Path(directory) / "facts.sqlite") as db,
    ):
        # Digests instead of payloads keep the full-scale index small.
        db.execute("CREATE TABLE facts (id TEXT PRIMARY KEY, digest BLOB)")
        count = 0
        for record in load_records(source):
            try:
                db.execute(
                    "INSERT INTO facts VALUES (?, ?)",
                    (record.id, _digest(record)),
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError(f"duplicate JSONL ID: {record.id}") from exc
            count += 1
        for record in read_lance(artifact):
            found = db.execute(
                "SELECT digest FROM facts WHERE id=?", (record.id,)
            ).fetchone()
            if found is None or found[0] != _digest(record):
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
        for record in load_records(artifact.local(metadata["source_jsonl"])):
            digest.update((_json(record.to_dict()) + "\n").encode())
            yield record
        if digest.hexdigest() != metadata["source_records_sha256"]:
            raise ContractError("rebuild source JSONL hash mismatch")

    records = source_records()
    previous_layers = []
    for layer in metadata["layers"]:
        manifest, _, _ = read_layer(artifact.local(layer))
        parent_metadata = manifest["parent"]["rebuild_metadata"]
        if (
            parent_metadata["source_records_sha256"]
            != metadata["source_records_sha256"]
            or parent_metadata["layers"] != previous_layers
        ):
            raise ContractError("rebuild Layer parent lineage mismatch")
        records = replay_layer(records, artifact.local(layer))
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
            roots=artifact.location_roots(),
        )
    return rebuilt


def rebuild_layer(layer, destination, *, source_view, roots=None):
    """Recover a failed query-layer write using only durable processing facts."""
    from .layers import read_layer

    manifest, _, step = read_layer(layer)
    parent = LanceArtifact(**manifest["parent"], roots=roots)
    metadata = {
        **parent.rebuild_metadata,
        "layers": [
            *parent.rebuild_metadata["layers"],
            _location(layer, parent.location_roots()),
        ],
        "writes": sorted(set(parent.rebuild_metadata["writes"]) | set(step.writes)),
    }
    intended = parent.replace(
        source_view=source_view,
        record_count=manifest["result_record_count"],
        rebuild_metadata=metadata,
    )
    return rebuild_artifact(intended, destination)
