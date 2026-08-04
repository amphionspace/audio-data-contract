import json
from importlib.resources import files

import pytest

from audio_data_contract import (
    ArtifactRef,
    DatasetSpec,
    load_catalog,
    resolve_artifact,
)
from audio_data_contract.errors import ContractError, ResolutionError


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
