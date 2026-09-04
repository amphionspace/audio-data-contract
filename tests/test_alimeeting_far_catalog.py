import gzip
import hashlib
import json
import runpy
from pathlib import Path

from audio_data_contract import load_catalog, resolve_artifact, verify_artifact_file

REPO_ROOT = Path(__file__).parents[1]
CATALOG_DIR = REPO_ROOT / "catalog"
VERSION = "openslr-119-far-local-20260903"
write_inventory = runpy.run_path(
    str(REPO_ROOT / "scripts/build_alimeeting_far_inventory.py")
)["write_inventory"]


def test_alimeeting_far_raw_catalog_is_portable_and_complete():
    spec = load_catalog(CATALOG_DIR).get("alimeeting", VERSION)

    assert set(spec.splits) == {"train", "dev", "test"}
    assert spec.provenance["subset"] == "far-field only"
    assert spec.provenance["integrity"] == "verified"
    assert spec.provenance["quality_status"] == "known_annotation_bounds_issues"
    assert spec.provenance["quality_findings"][
        "train_annotation_out_of_bounds_count"
    ] == 8

    expected = {
        "train_source": ("Train_Ali_far", 418, 102648299201),
        "dev_source": ("Eval_Ali_far", 16, 3876095062),
        "test_source": ("Test_2023_Ali_far", 40, 9197930853),
    }
    for name, (relative_path, file_count, expected_bytes) in expected.items():
        artifact = spec.artifact(name)
        assert artifact.kind == "source-directory"
        assert artifact.root_alias == "alimeeting_far_raw"
        assert artifact.relative_path == relative_path
        assert artifact.metadata["file_count"] == file_count
        assert artifact.metadata["expected_bytes"] == expected_bytes
        assert len(artifact.metadata["tree_sha256"]) == 64

    inventory = spec.artifact("source_inventory")
    assert inventory.expected_bytes == 30505
    assert inventory.sha256 == (
        "862fb51c686e16e5ba65b1105f3323dc0e615ce0ecc54917c4f87ca46b418a41"
    )
    assert inventory.metadata["record_count"] == 474
    assert not Path(inventory.relative_path).is_absolute()

    result = verify_artifact_file(inventory, REPO_ROOT / inventory.relative_path)
    assert result == {
        "bytes": 30505,
        "sha256": inventory.sha256,
        "records": 474,
    }


def test_alimeeting_far_raw_artifacts_resolve_from_aliases():
    catalog = load_catalog(CATALOG_DIR)
    roots = {
        "alimeeting_far_raw": Path("/data/alimeeting/original/far"),
        "audio_data_contract": REPO_ROOT,
    }

    assert resolve_artifact(
        catalog, "alimeeting", VERSION, "train_source", roots
    ) == Path("/data/alimeeting/original/far/Train_Ali_far")
    assert resolve_artifact(
        catalog, "alimeeting", VERSION, "source_inventory", roots
    ) == CATALOG_DIR / "inventory/alimeeting_far_openslr-119-local-20260903.jsonl.gz"


def test_alimeeting_inventory_is_independent_of_output_filename(tmp_path):
    published = CATALOG_DIR / "inventory/alimeeting_far_openslr-119-local-20260903.jsonl.gz"
    with gzip.open(published, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"

    write_inventory(first, rows)
    write_inventory(second, rows)

    assert first.read_bytes() == second.read_bytes() == published.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == (
        "862fb51c686e16e5ba65b1105f3323dc0e615ce0ecc54917c4f87ca46b418a41"
    )
