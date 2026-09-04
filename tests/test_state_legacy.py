import json
from importlib.resources import files

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from audio_data_contract import DatasetState, DownloadState, inspect_download
from audio_data_contract.errors import ContractError, StateTransitionError
from audio_data_contract.legacy import convert_legacy_registry
from audio_data_contract.state import load_state, write_state_atomic


def test_download_state_and_atomic_round_trip(tmp_path):
    state = DatasetState("demo", "1.0", DownloadState.PLANNED)
    state = state.transition(DownloadState.DOWNLOADING)
    path = tmp_path / "state/demo.json"
    write_state_atomic(state, path)
    assert load_state(path) == state
    with pytest.raises(StateTransitionError):
        state.transition(DownloadState.PREPARED)


def test_aria2_is_authoritative(tmp_path):
    artifact = tmp_path / "archive.tar.gz"
    artifact.write_bytes(b"complete")
    assert inspect_download(artifact, 8) == DownloadState.DOWNLOADED
    (tmp_path / "archive.tar.gz.aria2").write_text("active", encoding="utf-8")
    assert inspect_download(artifact, 8) == DownloadState.DOWNLOADING


def test_legacy_registry_conversion_has_no_absolute_paths(tmp_path):
    manifests = tmp_path / "multilingual/en/demo/data/manifests"
    legacy = {
        "en": {
            "demo": {
                "manifests_dir": str(manifests),
                "manifest_prefix": "demo",
                "splits": {"train": {"recordings": 1, "hours": 0.1}},
                "total_recordings": 1,
                "total_hours": 0.1,
                "has_punctuation": False,
                "has_true_casing": False,
            }
        }
    }
    specs = convert_legacy_registry(
        legacy, roots={"multilingual": tmp_path / "multilingual"}
    )
    encoded = json.dumps(specs[0].to_dict())
    assert str(tmp_path) not in encoded
    assert specs[0].artifacts[0].relative_path == "en/demo/data/manifests"


def test_state_round_trip_matches_packaged_schema():
    state = DatasetState("demo", "1.0", DownloadState.PLANNED)
    schema = json.loads(
        files("audio_data_contract")
        .joinpath("schemas", "dataset-state-1.0.json")
        .read_text()
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        state.to_dict()
    )
    assert DatasetState.from_dict(
        {
            "schema_version": "dataset-state/1.0",
            "dataset_id": "demo",
            "version": "1.0",
            "state": "planned",
        }
    ).artifacts == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_id", 1),
        ("version", 2),
        ("artifacts", []),
        ("artifacts", {"archive": []}),
        ("metadata", []),
        ("updated_at", "not-a-time"),
        ("error", 1),
    ],
)
def test_state_rejects_invalid_field_types(field, value):
    data = {
        "schema_version": "dataset-state/1.0",
        "dataset_id": "demo",
        "version": "1.0",
        "state": "planned",
        field: value,
    }

    schema = json.loads(
        files("audio_data_contract")
        .joinpath("schemas", "dataset-state-1.0.json")
        .read_text()
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
    with pytest.raises(ContractError):
        DatasetState.from_dict(data)


def test_state_rejects_non_object_payload():
    with pytest.raises(ContractError, match="must be an object"):
        DatasetState.from_dict([])
