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
