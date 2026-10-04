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
    assert lance.dataset(imported[1].table_path).version == 1


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
    assert lance.dataset(imported[1].table_path).version == 2
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
