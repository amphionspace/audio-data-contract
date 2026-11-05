import gzip
import json

import pytest

from audio_data_contract import ArtifactRef, DatasetSpec, Split
from audio_data_contract.catalog import (
    DatasetCatalog,
    check_dangling,
    find_dependents,
)
from audio_data_contract.errors import ContractError


def _spec(version, retired=None):
    return DatasetSpec(
        dataset_id="demo",
        version=version,
        languages=("en",),
        tasks=("asr",),
        artifacts=(
            ArtifactRef(
                name="index",
                kind="audio-index",
                root_alias="managed",
                relative_path=f"demo/{version}/index.jsonl.gz",
            ),
        ),
        splits={"train": Split(artifacts={"audio_index": ("index",)})},
        provenance={"retired": retired} if retired else {},
    )


def _write_index(root, version, audio_paths):
    path = root / "demo" / version / "index.jsonl.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt") as stream:
        for audio in audio_paths:
            stream.write(json.dumps({"root_alias": "managed", "relative_path": audio}) + "\n")


def test_check_dangling_reports_live_versions_pointing_at_removed_audio(tmp_path):
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "a.m4a").write_bytes(b"x" * 100)
    _write_index(tmp_path, "1", ["audio/a.m4a"])
    _write_index(tmp_path, "2", ["audio/removed.m4a"])
    catalog = DatasetCatalog([_spec("1"), _spec("2")])
    broken = check_dangling(catalog, {"managed": tmp_path})
    assert list(broken) == ["demo@2"]


def test_check_dangling_skips_retired_versions(tmp_path):
    _write_index(tmp_path, "1", ["audio/removed.m4a"])
    retired = {"date": "2026-11-04", "reason": "gone"}
    assert check_dangling(DatasetCatalog([_spec("1", retired)]), {"managed": tmp_path}) == {}


def test_superseded_by_must_be_registered():
    with pytest.raises(ContractError, match="superseded_by"):
        DatasetCatalog([_spec("1", {"superseded_by": "demo@9", "reason": "x"})])


def test_find_dependents_by_artifact_path_and_index_rows(tmp_path):
    _write_index(tmp_path, "1", ["audio/a.m4a", "audio/b.m4a", "other/c.m4a"])
    catalog = DatasetCatalog([_spec("1")])
    assert find_dependents(catalog, "managed:demo/1") != []
    assert find_dependents(catalog, "managed:audio") == []
    rows = find_dependents(catalog, "managed:audio", {"managed": tmp_path})
    assert [item["via"] for item in rows] == ["2 index rows"]
