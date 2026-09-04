import json
from pathlib import Path

from audio_data_contract import load_catalog

CATALOG_DIR = Path(__file__).parents[1] / "catalog"


def test_icefall_snapshot_has_39_portable_base_datasets():
    catalog = load_catalog(CATALOG_DIR)
    specs = [spec for spec in catalog if spec.version == "legacy-20260804"]
    assert len(specs) == 39
    assert all("asr" in spec.tasks for spec in specs)
    assert all(not artifact.relative_path.startswith("/") for spec in specs for artifact in spec.artifacts)


def test_traffic_language_matches_base_dataset():
    catalog = load_catalog(CATALOG_DIR)
    base_languages = {
        spec.dataset_id: spec.languages
        for spec in catalog
        if spec.version == "legacy-20260804"
    }
    for spec in catalog:
        if spec.version != "recipe-1" or spec.derived_from is None:
            continue
        assert spec.languages == base_languages[spec.derived_from]


def test_open_audio_eval_view_is_complete_and_portable():
    catalog = load_catalog(CATALOG_DIR)
    specs = [spec for spec in catalog if spec.version == "eval-20260804"]
    assert len(specs) == 108
    assert all(
        spec.provenance.get("consumer") == "open-audio-llm-vllm-eval"
        for spec in specs
    )
    assert all(
        not artifact.relative_path.startswith("/")
        for spec in specs
        for artifact in spec.artifacts
    )


def test_local_lhotse_scan_publishes_only_verified_artifacts():
    catalog = load_catalog(CATALOG_DIR)
    specs = [
        spec
        for spec in catalog
        if spec.provenance.get("source") == "local DATA_ASR lhotse scan"
    ]
    assert len(specs) == 18
    assert all(spec.provenance.get("integrity") == "verified" for spec in specs)
    local_artifacts = [
        artifact
        for spec in specs
        for artifact in spec.artifacts
        if not artifact.relative_path.startswith("LHOTSE/")
    ]
    assert all(artifact.expected_bytes is not None for artifact in local_artifacts)
    assert all(artifact.sha256 is not None for artifact in local_artifacts)
    assert all(
        artifact.metadata.get("record_count", 0) > 0 for artifact in local_artifacts
    )

    scan = json.loads((CATALOG_DIR / "local_lhotse_scan.json").read_text())
    assert len(scan["formal_lhotse_directories"]) == 14
    assert len(scan["published_dataset_keys"]) == 18
    assert len(scan["quarantined_artifacts"]) == 7
    quarantined = {item["path"] for item in scan["quarantined_artifacts"]}
    assert all(
        artifact.relative_path not in quarantined
        for spec in specs
        for artifact in spec.artifacts
    )


def test_synthetic_v5_lineage_separates_dataset_id_and_version():
    catalog = load_catalog(CATALOG_DIR)
    selected = catalog.get(
        "police_synthetic_zh_accent", "v5-20260830-qwen75-cosy25"
    )

    assert selected.derived_from == "police_synthetic_zh_accent"
    assert selected.recipe_parameters["source_version"] == "v5-20260830-qc"
