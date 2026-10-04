"""Optional backend acceptance: lossless facts, snapshots, patches and failures."""

import json
from dataclasses import replace

import pytest

from audio_data_contract import (
    AudioRecord,
    AudioRef,
    AudioSlot,
    TransformStep,
    read_artifact,
    write_records,
)
from audio_data_contract.errors import ContractError
from audio_data_contract.lance import (
    LanceArtifact,
    RecordQuery,
    import_jsonl,
    materialize_layer,
)
from audio_data_contract.layers import replay_layer, write_layer

lance = pytest.importorskip("lance")
pytest.importorskip("pyarrow")


def records():
    return [
        AudioRecord(
            id=f"sample-{i}",
            task="ts_asr",
            target="" if i == 0 else "你好",
            language="zh",
            audio_slots=(
                AudioSlot(
                    "enrollment",
                    AudioRef(
                        "demo",
                        "v1",
                        "train",
                        "enroll",
                        channel=0,
                        start=1.25,
                        duration=2.5,
                    ),
                ),
                AudioSlot(
                    "mixture",
                    AudioRef(
                        "demo", "v1", "test", "mix", channel=(0, 1), start=0, duration=4
                    ),
                ),
            ),
            metadata={"clean": {"pass": i % 2 == 0}, "arbitrary": [None, {"x": 1}]},
            labels={"nested": {"precise": 9007199254740993}},
            hotwords=("你好",),
        )
        for i in range(5)
    ]


@pytest.fixture
def imported(tmp_path):
    source = tmp_path / "records.jsonl.gz"
    write_records(records(), source)
    artifact = import_jsonl(
        source, tmp_path / "initial", source_view="demo/raw@v1", batch_size=2
    )
    return source, artifact


def test_roundtrip_queries_and_manifest(imported, tmp_path):
    source, artifact = imported
    assert artifact == LanceArtifact.read(tmp_path / "initial/artifact.json")
    assert [r.to_dict() for r in read_artifact(artifact)] == [
        r.to_dict() for r in records()
    ]
    for query in [
        RecordQuery(clean_pass=True),
        RecordQuery(clean_pass=False),
        RecordQuery(ids=("sample-2", "sample-0")),
        RecordQuery(ids=()),
        RecordQuery(task="ts_asr", language="zh", split="test"),
        RecordQuery(split="train"),
        RecordQuery(task="x' OR true --"),
    ]:
        assert {r.id for r in read_artifact(source, query)} == {
            r.id for r in read_artifact(artifact, query)
        }
    output = tmp_path / "export.jsonl"
    write_records(read_artifact(artifact), output)
    assert list(read_artifact(output)) == records()


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"schema_hash": "bad"}, "schema hash"),
        ({"snapshot_version": 999}, "snapshot 999"),
        ({"storage_version": "999"}, "storage version"),
    ],
)
def test_incompatible_snapshots(imported, mutation, match):
    with pytest.raises(ContractError, match=match):
        list(read_artifact(replace(imported[1], **mutation)))


def test_duplicate_across_batches_never_published(tmp_path):
    source = tmp_path / "bad.jsonl"
    write_records([*records(), records()[0]], source)
    with pytest.raises(ContractError, match="duplicate"):
        import_jsonl(source, tmp_path / "bad", source_view="demo/raw@v1", batch_size=2)
    assert not (tmp_path / "bad").exists()
    assert not list(tmp_path.glob(".lance-import-*"))


def test_parallel_import_matches_single_process(tmp_path):
    source = tmp_path / "records.jsonl"
    write_records(records(), source)
    single = import_jsonl(source, tmp_path / "one", source_view="d/r@v1", batch_size=2)
    parallel = import_jsonl(
        source, tmp_path / "many", source_view="d/r@v1", batch_size=2, workers=2
    )
    assert parallel.rebuild_metadata == single.rebuild_metadata
    assert parallel.record_count == 5
    assert list(read_artifact(parallel)) == list(read_artifact(single)) == records()


@pytest.mark.parametrize("workers", [1, 2])
def test_parallel_import_rejects_duplicates_and_bad_lines(tmp_path, workers):
    source = tmp_path / "dup.jsonl"
    write_records([*records(), records()[0]], source)
    with pytest.raises(ContractError, match="duplicate record ID: sample-0"):
        import_jsonl(
            source,
            tmp_path / "dup",
            source_view="d/r@v1",
            batch_size=2,
            workers=workers,
        )
    write_records(records(), source)
    with source.open("a") as stream:
        stream.write("{not json\n")
    with pytest.raises(ContractError, match="dup.jsonl:6"):
        import_jsonl(
            source,
            tmp_path / "bad",
            source_view="d/r@v1",
            batch_size=2,
            workers=workers,
        )
    assert not list(tmp_path.glob("dup")) + list(tmp_path.glob("bad"))
    assert not list(tmp_path.glob(".lance-import-*"))


def step():
    return TransformStep(
        "clean",
        "v1",
        "filter-and-correct",
        ("target", "metadata.clean.pass", "$membership"),
        ("target", "metadata.clean.pass"),
        {"threshold": 0.5},
    )


def patches():
    return [
        {
            "id": "sample-0",
            "changes": {"target": "修正", "metadata.clean.pass": False},
            "status": "keep",
        },
        {"id": "sample-1", "changes": {}, "status": "delete"},
    ]


def test_layer_snapshot_replay_and_multiple_views(imported, tmp_path):
    source, parent = imported
    layer = write_layer(
        tmp_path / "clean",
        patches(),
        parent=parent,
        step=step(),
        tool="test-cleaner",
        model="test-model",
    )
    new = materialize_layer(layer, source_view="demo/clean@v1")
    expected = list(replay_layer(read_artifact(source), layer))
    assert {r.id: r for r in read_artifact(new)} == {r.id: r for r in expected}
    assert new.record_count == 4
    assert list(read_artifact(parent)) == records()
    other_view = replace(new, source_view="demo/quality@v1")
    assert list(read_artifact(other_view)) == list(read_artifact(new))
    assert [r.id for r in read_artifact(new, RecordQuery(clean_pass=True))] == [
        "sample-2",
        "sample-4",
    ]
    stale = write_layer(
        tmp_path / "stale", patches(), parent=parent, step=step(), tool="t"
    )
    with pytest.raises(ContractError, match="stale"):
        materialize_layer(stale, source_view="demo/stale@v1")
    assert (stale / "manifest.json").exists()
    assert not (stale / "artifact.json").exists()


@pytest.mark.parametrize(
    "bad,match",
    [
        ([patches()[0], patches()[0]], "duplicate"),
        ([{"id": "absent", "changes": {}, "status": "keep"}], "unknown"),
        (
            [{"id": "sample-0", "changes": {"id": "changed"}, "status": "keep"}],
            "undeclared",
        ),
        ([{"id": "sample-0", "changes": {}, "status": "unknown"}], "status"),
    ],
)
def test_invalid_patches_not_published(imported, tmp_path, bad, match):
    with pytest.raises(ContractError, match=match):
        write_layer(tmp_path / "bad", bad, parent=imported[1], step=step(), tool="t")
    assert not (tmp_path / "bad").exists()
    assert lance.dataset(imported[1].table_path).version == imported[1].snapshot_version


def test_overrides_and_parent_child_conflicts(imported, tmp_path):
    no_override = replace(step(), overrides=())
    with pytest.raises(ContractError, match="override"):
        write_layer(
            tmp_path / "conflict",
            patches(),
            parent=imported[1],
            step=no_override,
            tool="t",
        )
    parent = replace(
        imported[1],
        rebuild_metadata={**imported[1].rebuild_metadata, "writes": ["metadata.clean"]},
    )
    child = TransformStep("x", "v2", "annotate", ("metadata.clean.score",))
    with pytest.raises(ContractError, match="conflict"):
        write_layer(
            tmp_path / "nested",
            [
                {
                    "id": "sample-0",
                    "changes": {"metadata.clean.score": 0.9},
                    "status": "keep",
                }
            ],
            parent=parent,
            step=child,
            tool="t",
        )


def test_merge_failure_keeps_canonical_layer(imported, tmp_path, monkeypatch):
    layer = write_layer(
        tmp_path / "failure", patches(), parent=imported[1], step=step(), tool="t"
    )

    def fail(*args, **kwargs):
        raise OSError("injected write failure")

    monkeypatch.setattr(lance.LanceDataset, "merge_insert", fail)
    with pytest.raises(ContractError, match="canonical patch retained"):
        materialize_layer(layer, source_view="demo/clean@v1")
    assert not (layer / "artifact.json").exists()
    assert len(list(replay_layer(read_artifact(imported[0]), layer))) == 4
    assert list(read_artifact(imported[1])) == records()


def test_patch_tampering_detected(imported, tmp_path):
    layer = write_layer(
        tmp_path / "tampered", patches(), parent=imported[1], step=step(), tool="t"
    )
    path = layer / "patch.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["changes"]["target"] = "tampered"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ContractError, match="hash mismatch"):
        materialize_layer(layer, source_view="demo/clean@v1")


def test_rebuild_without_old_lance_table(imported, tmp_path):
    from audio_data_contract.lance import rebuild_artifact, verify_equivalence
    from audio_data_contract.lance_export import export_artifact

    layer = write_layer(
        tmp_path / "clean", patches(), parent=imported[1], step=step(), tool="t"
    )
    clean = materialize_layer(layer, source_view="demo/clean@v1")
    expected = list(replay_layer(read_artifact(imported[0]), layer))
    (tmp_path / "initial/table.lance").rename(tmp_path / "unavailable-table")
    rebuilt = rebuild_artifact(clean, tmp_path / "rebuilt")
    assert list(read_artifact(rebuilt)) == expected
    export_artifact(rebuilt, tmp_path / "export.jsonl.gz")
    assert verify_equivalence(rebuilt, tmp_path / "export.jsonl.gz")["records_equal"]


def test_empty_import_and_all_deleted_rebuild(tmp_path):
    from audio_data_contract.lance import rebuild_artifact

    source = tmp_path / "empty.jsonl"
    source.write_text("")
    empty = import_jsonl(source, tmp_path / "empty", source_view="demo/empty@v1")
    assert list(read_artifact(empty)) == []
    write_records(records()[:1], source)
    one = import_jsonl(source, tmp_path / "one", source_view="demo/one@v1")
    layer = write_layer(
        tmp_path / "delete",
        [{"id": "sample-0", "changes": {}, "status": "delete"}],
        parent=one,
        step=step(),
        tool="t",
    )
    deleted = materialize_layer(layer, source_view="demo/deleted@v1")
    assert list(read_artifact(deleted)) == []
    rebuilt = rebuild_artifact(deleted, tmp_path / "rebuilt")
    assert rebuilt.record_count == 0


def test_lhotse_export_preserves_channels_segments_and_empty_target(imported, tmp_path):
    import gzip

    from audio_data_contract.lance_export import export_artifact

    def resolve_audio(record):
        return {
            slot.name: {
                "path": "/audio/" + slot.ref.cut_id + ".wav",
                "sample_rate": 16000,
                "channels": 2,
                "duration": 10,
            }
            for slot in record.audio_slots
        }

    for slot in ("mixture", "enrollment"):
        output = tmp_path / (slot + ".jsonl.gz")
        export_artifact(imported[1], output, slot=slot, resolve_audio=resolve_audio)
        with gzip.open(output, "rt") as stream:
            cuts = [json.loads(line) for line in stream]
        assert cuts[0]["supervisions"][0]["text"] == ""
        assert cuts[0]["custom"]["audio_record"] == records()[0].to_dict()
        assert cuts[0]["custom"]["hotwords"] == list(records()[0].hotwords)
        assert cuts[0]["custom"]["labels"] == records()[0].labels
        assert cuts[0]["custom"]["clean"] == records()[0].metadata["clean"]
        assert cuts[0]["start"] == (0 if slot == "mixture" else 1.25)
        assert cuts[0]["duration"] == (4 if slot == "mixture" else 2.5)
        assert cuts[0]["channel"] == ([0, 1] if slot == "mixture" else 0)


def test_failed_export_not_published(imported, tmp_path):
    from audio_data_contract.lance_export import export_artifact

    def fail(record):
        raise ContractError("missing audio index")

    with pytest.raises(ContractError, match="missing audio"):
        export_artifact(
            imported[1], tmp_path / "cuts.jsonl", slot="mixture", resolve_audio=fail
        )
    assert not (tmp_path / "cuts.jsonl").exists()
    assert not list(tmp_path.glob(".export-*"))


def test_commit_succeeds_publication_fails_then_rebuild(
    imported, tmp_path, monkeypatch
):
    from pathlib import Path

    from audio_data_contract.lance import rebuild_layer

    layer = write_layer(
        tmp_path / "late-failure", patches(), parent=imported[1], step=step(), tool="t"
    )
    original = Path.write_text

    def fail_publication(path, *args, **kwargs):
        if path.name == ".artifact.json.tmp":
            raise OSError("injected manifest publication failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_publication)
    with pytest.raises(ContractError, match="canonical patch retained"):
        materialize_layer(layer, source_view="demo/clean@v1")
    assert not (layer / "artifact.json").exists()
    # The merge commit and its index update landed but were never published.
    assert lance.dataset(imported[1].table_path).version > imported[1].snapshot_version
    assert list(read_artifact(imported[1])) == records()
    rebuilt = rebuild_layer(layer, tmp_path / "recovered", source_view="demo/clean@v1")
    expected = list(replay_layer(read_artifact(imported[0]), layer))
    assert list(read_artifact(rebuilt)) == expected


def test_rebuild_rejects_changed_source(imported, tmp_path):
    from audio_data_contract.lance import rebuild_artifact

    source, artifact = imported
    changed = records()
    changed[0] = replace(changed[0], target="changed upstream")
    write_records(changed, source)
    with pytest.raises(ContractError, match="source JSONL hash"):
        rebuild_artifact(artifact, tmp_path / "rebuilt")
    assert not (tmp_path / "rebuilt").exists()


def test_cli_import_verify_export(tmp_path, capsys):
    from audio_data_contract.lance_cli import main

    source = tmp_path / "source.jsonl"
    write_records(records(), source)
    output = tmp_path / "cli"
    assert (
        main(["import", str(source), str(output), "--source-view", "demo/raw@v1"]) == 0
    )
    manifest = output / "artifact.json"
    assert main(["verify", str(manifest), str(source)]) == 0
    exported = tmp_path / "selected.jsonl"
    assert main(["export", str(manifest), str(exported), "--clean-pass", "false"]) == 0
    assert [r.id for r in read_artifact(exported)] == ["sample-1", "sample-3"]


def test_portable_artifact_survives_moving_roots(tmp_path):
    from audio_data_contract.lance import rebuild_artifact, verify_equivalence

    old, new = tmp_path / "old", tmp_path / "new"
    (old / "data").mkdir(parents=True)
    write_records(records(), old / "data/records.jsonl")
    roots = {"managed": old / "managed", "source": old / "data"}
    raw = import_jsonl(
        old / "data/records.jsonl",
        old / "managed/raw",
        source_view="demo/raw@v1",
        roots=roots,
    )
    assert raw.table_path == {
        "root_alias": "managed",
        "relative_path": "raw/table.lance",
    }
    assert raw.rebuild_metadata["source_jsonl"] == {
        "root_alias": "source",
        "relative_path": "records.jsonl",
    }
    layer = write_layer(
        old / "managed/clean-layer", patches(), parent=raw, step=step(), tool="t"
    )
    clean = materialize_layer(layer, source_view="demo/clean@v1", roots=roots)
    assert clean.rebuild_metadata["layers"] == [
        {"root_alias": "managed", "relative_path": "clean-layer"}
    ]
    old.rename(new)
    moved = {"managed": new / "managed", "source": new / "data"}
    reread = LanceArtifact.read(new / "managed/clean-layer/artifact.json", moved)
    assert reread == clean
    expected = list(
        replay_layer(
            read_artifact(new / "data/records.jsonl"), new / "managed/clean-layer"
        )
    )
    assert {r.id: r for r in read_artifact(reread)} == {r.id: r for r in expected}
    rebuilt = rebuild_artifact(reread, new / "managed/rebuilt")
    assert rebuilt.table_path["relative_path"] == "rebuilt/table.lance"
    assert list(read_artifact(rebuilt)) == expected
    with pytest.raises(ContractError, match="not configured"):
        list(read_artifact(LanceArtifact.read(new / "managed/raw/artifact.json", {})))
    write_records(expected, new / "expected.jsonl")
    assert verify_equivalence(rebuilt, new / "expected.jsonl")["records_equal"]


def test_portable_import_rejects_paths_outside_roots(tmp_path):
    write_records(records(), tmp_path / "records.jsonl")
    with pytest.raises(ContractError, match="outside every configured root"):
        import_jsonl(
            tmp_path / "records.jsonl",
            tmp_path / "managed/raw",
            source_view="demo/raw@v1",
            roots={"managed": tmp_path / "managed"},
        )
    assert not (tmp_path / "managed/raw").exists()


def test_catalog_lance_table_pins_snapshot(tmp_path):
    from audio_data_contract import ArtifactRef, DatasetSpec, validate_catalog
    from audio_data_contract.lance import catalog_ref, open_catalog_artifact

    roots = {"managed": tmp_path}
    write_records(records(), tmp_path / "records.jsonl")
    artifact = import_jsonl(
        tmp_path / "records.jsonl",
        tmp_path / "raw",
        source_view="demo/raw@v1",
        roots=roots,
    )
    sidecar = tmp_path / "raw/artifact.json"
    ref = catalog_ref(artifact, sidecar, name="lance", roots=roots)
    assert ref.relative_path == "raw/artifact.json"
    assert ArtifactRef.from_dict(ref.to_dict()) == ref

    def catalog(ref):
        spec = DatasetSpec.from_dict(
            {
                "schema_version": "dataset-catalog/1.0",
                "dataset_id": "demo",
                "version": "v1",
                "languages": ["zh"],
                "tasks": ["ts_asr"],
                "splits": {},
                "artifacts": [ref.to_dict()],
            }
        )
        return validate_catalog([spec])

    opened = open_catalog_artifact(catalog(ref), "demo", "v1", "lance", roots)
    assert list(read_artifact(opened)) == records()
    stale = replace(ref, metadata={**ref.metadata, "snapshot_version": 2})
    with pytest.raises(ContractError, match="snapshot_version differs"):
        open_catalog_artifact(catalog(stale), "demo", "v1", "lance", roots)
    with pytest.raises(ContractError, match="snapshot_version"):
        replace(ref, metadata={"record_count": 5, "schema_hash": "0" * 64})


def test_cli_portable_import_and_catalog_ref(tmp_path, capsys):
    from audio_data_contract.lance_cli import main

    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"managed": str(tmp_path)}))
    write_records(records(), tmp_path / "source.jsonl")
    args = ["--roots", str(roots_file)]
    assert (
        main(
            [
                *args,
                "import",
                str(tmp_path / "source.jsonl"),
                str(tmp_path / "raw"),
                "--source-view",
                "demo/raw@v1",
            ]
        )
        == 0
    )
    capsys.readouterr()
    sidecar = str(tmp_path / "raw/artifact.json")
    assert main([*args, "catalog-ref", sidecar, "--name", "lance"]) == 0
    ref = json.loads(capsys.readouterr().out)
    assert ref["kind"] == "lance-table"
    assert ref["relative_path"] == "raw/artifact.json"
    assert ref["metadata"]["record_count"] == 5


def _exit_worker(chunk):
    import os

    os._exit(1)


def test_dead_import_worker_fails_instead_of_hanging():
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool

    from audio_data_contract.lance import _ordered

    context = multiprocessing.get_context("spawn")
    with (
        ProcessPoolExecutor(1, mp_context=context) as pool,
        pytest.raises(BrokenProcessPool),
    ):
        list(_ordered(pool, _exit_worker, range(3), 2))


def test_queries_use_scalar_indexes_after_import_and_layer(imported, tmp_path):
    from audio_data_contract.lance import INDICES, _open_artifact

    layer = write_layer(
        tmp_path / "clean", patches(), parent=imported[1], step=step(), tool="t"
    )
    clean = materialize_layer(layer, source_view="demo/clean@v1")
    query = RecordQuery(
        ids=("sample-0", "sample-2"),
        task="ts_asr",
        language="zh",
        split="test",
        clean_pass=False,
    )
    for artifact in (imported[1], clean):
        dataset = _open_artifact(artifact)
        for column, _ in INDICES:
            stats = dataset.stats.index_stats(f"{column}_idx")
            assert stats["num_unindexed_rows"] == 0
        plan = dataset.scanner(filter=query.expression()).explain_plan()
        assert "ScalarIndexQuery" in plan
        assert all(f"@{column}_idx(" in plan for column, _ in INDICES)
        indexed = dataset.to_table(filter=query.expression(), columns=["id"])
        scanned = dataset.to_table(
            filter=query.expression(), columns=["id"], use_scalar_index=False
        )
        assert indexed.equals(scanned)
    assert [r.id for r in read_artifact(clean, query)] == ["sample-0"]


def test_chunked_layer_matches_replay_and_fails_atomically(
    imported, tmp_path, monkeypatch
):
    from audio_data_contract import layers

    monkeypatch.setattr(layers, "CHUNK_SIZE", 2)
    many = [
        {"id": f"sample-{i}", "changes": {"target": f"t{i}"}, "status": "keep"}
        for i in (4, 0, 3, 2)
    ] + [{"id": "sample-1", "changes": {}, "status": "delete"}]
    layer = write_layer(
        tmp_path / "chunked", many, parent=imported[1], step=step(), tool="t"
    )
    ids = [json.loads(line)["id"] for line in (layer / "patch.jsonl").open()]
    assert ids == sorted(ids)
    _, rows, _ = layers.read_layer(layer)
    manifest = json.loads((layer / "manifest.json").read_text())
    assert layers._hash(rows) == manifest["patch_hash"]

    calls = []
    original = layers.apply_patch

    def fail_in_second_chunk(record, patch, step):
        calls.append(patch["id"])
        if len(calls) == 3:
            raise ContractError("injected chunk failure")
        return original(record, patch, step)

    monkeypatch.setattr(layers, "apply_patch", fail_in_second_chunk)
    with pytest.raises(ContractError, match="injected chunk failure"):
        materialize_layer(layer, source_view="demo/clean@v1")
    assert lance.dataset(imported[1].table_path).version == imported[1].snapshot_version
    assert not list(tmp_path.glob(".layer-rows-*"))
    monkeypatch.setattr(layers, "apply_patch", original)
    clean = materialize_layer(layer, source_view="demo/clean@v1")
    expected = list(replay_layer(read_artifact(imported[0]), layer))
    assert {r.id: r for r in read_artifact(clean)} == {r.id: r for r in expected}


def test_unsorted_patch_file_rejected(imported, tmp_path):
    layer = write_layer(
        tmp_path / "clean", patches(), parent=imported[1], step=step(), tool="t"
    )
    path = layer / "patch.jsonl"
    path.write_text("".join(reversed(path.read_text().splitlines(True))))
    with pytest.raises(ContractError, match="unsorted"):
        materialize_layer(layer, source_view="demo/clean@v1")


def _by_id(artifact):
    return {r.id: r for r in read_artifact(artifact)}


def test_rerun_resumes_after_sidecar_publication_failure(
    imported, tmp_path, monkeypatch
):
    from pathlib import Path

    from audio_data_contract.lance import inspect_table

    layer = write_layer(
        tmp_path / "clean", patches(), parent=imported[1], step=step(), tool="t"
    )
    original = Path.write_text

    def fail_publication(path, *args, **kwargs):
        if path.name == ".artifact.json.tmp":
            raise OSError("injected manifest publication failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_publication)
    with pytest.raises(ContractError, match="Rerun to resume"):
        materialize_layer(layer, source_view="demo/clean@v1")
    monkeypatch.undo()
    committed = inspect_table(imported[1])
    assert committed["unpublished"] == []
    clean = materialize_layer(layer, source_view="demo/clean@v1")
    assert clean.snapshot_version == committed["latest"]
    assert inspect_table(clean)["latest"] == committed["latest"]
    assert clean == LanceArtifact.read(layer / "artifact.json")
    expected = list(replay_layer(read_artifact(imported[0]), layer))
    assert _by_id(clean) == {r.id: r for r in expected}


def test_untagged_commits_after_parent_are_rolled_back(imported, tmp_path, monkeypatch):
    from lance.dataset import DatasetOptimizer

    from audio_data_contract.lance import inspect_table

    first = write_layer(
        tmp_path / "first", patches(), parent=imported[1], step=step(), tool="t"
    )

    def crash(*args, **kwargs):
        raise OSError("injected crash after merge commit")

    monkeypatch.setattr(DatasetOptimizer, "optimize_indices", crash)
    with pytest.raises(ContractError, match="injected crash"):
        materialize_layer(first, source_view="demo/first@v1")
    monkeypatch.undo()
    report = inspect_table(imported[1])
    assert report["unpublished"] == [report["latest"]]
    other = [{"id": "sample-3", "changes": {"target": "other"}, "status": "keep"}]
    second = write_layer(
        tmp_path / "second", other, parent=imported[1], step=step(), tool="t2"
    )
    result = materialize_layer(second, source_view="demo/second@v1")
    expected = list(replay_layer(read_artifact(imported[0]), second))
    assert _by_id(result) == {r.id: r for r in expected}
    assert list(read_artifact(imported[1])) == records()
    assert inspect_table(result)["unpublished"] == []


def test_untagged_legacy_table_stays_strict(imported, tmp_path):
    lance.dataset(imported[1].table_path).tags.delete("import")
    first = write_layer(
        tmp_path / "first", patches(), parent=imported[1], step=step(), tool="t"
    )
    materialize_layer(first, source_view="demo/first@v1")
    second = write_layer(
        tmp_path / "second", patches(), parent=imported[1], step=step(), tool="t2"
    )
    with pytest.raises(ContractError, match="stale"):
        materialize_layer(second, source_view="demo/second@v1")


def test_compact_cleanup_and_protect(imported, tmp_path):
    from audio_data_contract.lance import (
        cleanup_artifact,
        compact_artifact,
        inspect_table,
        protect_artifact,
    )

    layer = write_layer(
        tmp_path / "clean", patches(), parent=imported[1], step=step(), tool="t"
    )
    clean = materialize_layer(layer, source_view="demo/clean@v1")
    table = lance.dataset(clean.table_path)
    assert any(f.deletion_file() is not None for f in table.get_fragments())
    compacted = compact_artifact(clean, tmp_path / "compacted.json")
    assert compacted == LanceArtifact.read(tmp_path / "compacted.json")
    assert compacted.snapshot_version > clean.snapshot_version
    assert _by_id(compacted) == _by_id(clean)
    table = lance.dataset(clean.table_path, version=compacted.snapshot_version)
    assert all(f.deletion_file() is None for f in table.get_fragments())
    with pytest.raises(ContractError, match="newest published"):
        compact_artifact(clean, tmp_path / "again.json")

    before = inspect_table(compacted)
    stats = cleanup_artifact(compacted, older_than_days=0)
    assert stats["old_versions"] > 0
    remaining = [v["version"] for v in lance.dataset(clean.table_path).versions()]
    assert sorted(remaining) == before["published"]
    for artifact in (imported[1], clean, compacted):
        assert list(read_artifact(artifact))

    lance.dataset(clean.table_path).tags.delete("import")
    with pytest.raises(ContractError, match="protect"):
        cleanup_artifact(imported[1], older_than_days=0)
    assert imported[1].snapshot_version in protect_artifact(imported[1])
    cleanup_artifact(imported[1], older_than_days=0)
    assert list(read_artifact(imported[1])) == records()


def test_cli_governance_commands(imported, tmp_path, capsys):
    from audio_data_contract.lance_cli import main

    layer = write_layer(
        tmp_path / "clean", patches(), parent=imported[1], step=step(), tool="t"
    )
    materialize_layer(layer, source_view="demo/clean@v1")
    sidecar = str(layer / "artifact.json")
    capsys.readouterr()
    assert main(["doctor", sidecar]) == 0
    assert json.loads(capsys.readouterr().out)["unpublished"] == []
    compacted = str(tmp_path / "compacted.json")
    assert main(["compact", sidecar, compacted]) == 0
    assert main(["cleanup", compacted, "--older-than-days", "0"]) == 0
    assert main(["protect", compacted]) == 0


def test_mirror_to_url_root_is_incremental_and_read_only(tmp_path):
    from audio_data_contract.lance import compact_artifact, mirror_artifact
    from audio_data_contract.roots import load_roots

    local = {"managed": tmp_path / "managed"}
    write_records(records(), tmp_path / "managed/records.jsonl")
    raw = import_jsonl(
        tmp_path / "managed/records.jsonl",
        tmp_path / "managed/raw",
        source_view="demo/raw@v1",
        roots=local,
    )
    remote = (tmp_path / "bucket").as_uri()
    first = mirror_artifact(raw, remote)
    assert first["copied"] > 0
    assert first["target"] == remote + "/raw/table.lance"

    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"managed": remote}))
    with pytest.raises(ContractError, match="absolute path"):
        load_roots(roots_file)
    reader = load_roots(roots_file, allow_urls=True)
    mirrored = LanceArtifact.read(tmp_path / "managed/raw/artifact.json", reader)
    assert mirrored.table_uri == remote + "/raw/table.lance"
    assert list(read_artifact(mirrored)) == records()
    with pytest.raises(ContractError, match="read-only"):
        compact_artifact(mirrored, tmp_path / "compacted.json")

    layer = write_layer(
        tmp_path / "managed/clean", patches(), parent=raw, step=step(), tool="t"
    )
    clean = materialize_layer(layer, source_view="demo/clean@v1", roots=local)
    second = mirror_artifact(clean, remote)
    # Unchanged immutable files from the first mirror are not copied again.
    assert second["skipped"] > 0
    remote_clean = LanceArtifact.read(layer / "artifact.json", reader)
    assert _by_id(remote_clean) == _by_id(clean)
    assert list(read_artifact(mirrored)) == records()
