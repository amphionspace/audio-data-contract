import json

import pytest

from audio_data_contract import DatasetState, DownloadState, inspect_download
from audio_data_contract.legacy import convert_legacy_registry
from audio_data_contract.state import load_state, write_state_atomic
from audio_data_contract.errors import StateTransitionError


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
