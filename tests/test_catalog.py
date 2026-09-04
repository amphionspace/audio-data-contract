import gzip
import hashlib
import json
from importlib.resources import files

import pytest

from audio_data_contract import (
    ArtifactRef,
    DatasetSpec,
    load_catalog,
    resolve_artifact,
)
from audio_data_contract.catalog import verify_artifact_file
from audio_data_contract.errors import ContractError, IntegrityError, ResolutionError


def _spec() -> DatasetSpec:
    return DatasetSpec(
        dataset_id="demo",
        version="1.0",
        languages=("en",),
        tasks=("asr",),
        aliases=("demo_alias",),
        artifacts=(
            ArtifactRef(
                name="cuts",
                kind="lhotse-cuts",
                root_alias="managed",
                relative_path="demo/1.0/manifests/lhotse/cuts.jsonl.gz",
            ),
        ),
        splits={"train": {"cuts_artifact": "cuts"}},
    )


def test_catalog_round_trip_and_alias(tmp_path):
    path = tmp_path / "catalog.jsonl"
    path.write_text(json.dumps(_spec().to_dict()) + "\n", encoding="utf-8")
    catalog = load_catalog(path)
    assert catalog.get("demo_alias", "1.0").dataset_id == "demo"
    assert resolve_artifact(
        catalog, "demo", "1.0", "cuts", {"managed": tmp_path}
    ) == tmp_path / "demo/1.0/manifests/lhotse/cuts.jsonl.gz"


def test_rejects_absolute_and_parent_paths():
    with pytest.raises(ContractError):
        ArtifactRef("x", "cuts", "root", "/absolute")
    with pytest.raises(ContractError):
        ArtifactRef("x", "cuts", "root", "../escape")


def test_unknown_schema_field_and_missing_alias_fail(tmp_path):
    data = _spec().to_dict()
    data["surprise"] = True
    with pytest.raises(ContractError, match="unknown fields"):
        DatasetSpec.from_dict(data)
    path = tmp_path / "catalog.jsonl"
    path.write_text(json.dumps(_spec().to_dict()) + "\n", encoding="utf-8")
    with pytest.raises(ResolutionError, match="not configured"):
        resolve_artifact(load_catalog(path), "demo", "1.0", "cuts", {})


def test_json_schemas_are_packaged():
    schemas = files("audio_data_contract").joinpath("schemas")
    assert json.loads(schemas.joinpath("dataset-catalog-1.0.json").read_text())["title"] == "DatasetSpec"
    assert json.loads(schemas.joinpath("audio-record-1.0.json").read_text())["title"] == "AudioRecord"
    assert json.loads(schemas.joinpath("audio-example-1.0.json").read_text())["title"] == "AudioExample"


def test_catalog_directory_loads_all_jsonl_files(tmp_path):
    first = _spec().to_dict()
    second = _spec().to_dict()
    second["dataset_id"] = "second"
    second["aliases"] = []
    (tmp_path / "a.jsonl").write_text(json.dumps(first) + "\n", encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(json.dumps(second) + "\n", encoding="utf-8")
    assert len(load_catalog(tmp_path)) == 2


def test_canonical_dataset_id_takes_precedence_over_an_alias(tmp_path):
    legacy = _spec().to_dict()
    legacy["dataset_id"] = "common_voice_en"
    legacy["version"] = "legacy"
    legacy["aliases"] = []
    current = _spec().to_dict()
    current["dataset_id"] = "common-voice-en"
    current["version"] = "26.0"
    current["aliases"] = ["common_voice_en"]
    path = tmp_path / "catalog.jsonl"
    path.write_text(
        json.dumps(legacy) + "\n" + json.dumps(current) + "\n",
        encoding="utf-8",
    )
    catalog = load_catalog(path)
    assert catalog.get("common_voice_en", "legacy").dataset_id == "common_voice_en"


def test_verify_artifact_file_checks_size_digest_and_record_count(tmp_path):
    path = tmp_path / "records.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write('{"id":"one"}\n')
        stream.write('{"id":"two"}\n')
    content = path.read_bytes()
    artifact = ArtifactRef(
        "records",
        "lhotse-supervisions",
        "root",
        "records.jsonl.gz",
        expected_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        metadata={"record_count": 2},
    )

    assert verify_artifact_file(artifact, path)["records"] == 2

    path.write_bytes(content[:-4])
    with pytest.raises(IntegrityError, match="byte size mismatch"):
        verify_artifact_file(artifact, path)


def test_verify_artifact_file_rejects_truncated_gzip_without_size_facts(tmp_path):
    path = tmp_path / "records.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write('{"id":"one"}\n')
    path.write_bytes(path.read_bytes()[:-4])
    artifact = ArtifactRef(
        "records",
        "lhotse-supervisions",
        "root",
        "records.jsonl.gz",
        metadata={"record_count": 1},
    )

    with pytest.raises(IntegrityError, match="cannot be read completely"):
        verify_artifact_file(artifact, path)


def test_verify_artifact_file_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_bytes(b"\xff\n")
    artifact = ArtifactRef(
        "records",
        "jsonl-metadata",
        "root",
        "records.jsonl",
        metadata={"record_count": 1},
    )

    with pytest.raises(IntegrityError, match="cannot be read completely"):
        verify_artifact_file(artifact, path)


def test_verify_artifact_directory_checks_tree_facts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    nested = source / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("beta", encoding="utf-8")

    tree_digest = hashlib.sha256()
    for relative_path in ("a.txt", "nested/b.txt"):
        content = (source / relative_path).read_bytes()
        tree_digest.update(
            f"{relative_path}\0{len(content)}\0{hashlib.sha256(content).hexdigest()}\n".encode()
        )
    artifact = ArtifactRef(
        "source",
        "source-directory",
        "root",
        "source",
        metadata={
            "file_count": 2,
            "expected_bytes": 9,
            "tree_sha256": tree_digest.hexdigest(),
        },
    )

    result = verify_artifact_file(artifact, source)
    assert result == {
        "bytes": 9,
        "files": 2,
        "tree_sha256": tree_digest.hexdigest(),
    }

    (source / "a.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(IntegrityError, match="byte size mismatch"):
        verify_artifact_file(artifact, source)


@pytest.mark.parametrize(
    ("integrity_fact", "value"),
    [("expected_bytes", 9), ("sha256", "0" * 64)],
)
def test_verify_artifact_directory_rejects_file_integrity_fields(
    tmp_path, integrity_fact, value
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    artifact = ArtifactRef(
        "source",
        "source-directory",
        "root",
        "source",
        **{integrity_fact: value},
    )

    with pytest.raises(IntegrityError, match="directory artifact integrity facts"):
        verify_artifact_file(artifact, source)
