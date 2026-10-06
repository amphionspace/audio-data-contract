import importlib.util
from pathlib import Path

from audio_data_contract.declarations import editable_declarations, read_declarations

SCRIPT = Path(__file__).parents[1] / "scripts/migrate_catalog_v2.py"
spec = importlib.util.spec_from_file_location("migrate_catalog_v2", SCRIPT)
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)

CATALOG = """\
- schema_version: dataset-catalog/1.0
  dataset_id: cv_ar
  version: legacy
  languages: [ar]
  tasks: [asr]
  artifacts:
    - {name: manifests, kind: lhotse-manifest-dir, root_alias: m, relative_path: ar/manifests}
    - {name: notes, kind: metadata, root_alias: m, relative_path: ar/notes.json}
  splits:
    dev:
      manifest_dir_artifact: manifests
      manifest_prefix: cv-ar
      source_split: dev
      sample_cap_per_epoch: 10
      statistics: {hours: 1.0}
- schema_version: dataset-catalog/1.0
  dataset_id: aishell
  version: icefall-20260908
  languages: [zh]
  tasks: [asr]
  artifacts:
    - name: rec
      kind: lhotse-recordings
      root_alias: a
      relative_path: LHOTSE/rec.jsonl.gz
      metadata: {icefall_relative_to_lhotse: true}
    - {name: sup, kind: lhotse-supervisions, root_alias: a, relative_path: LHOTSE/sup.jsonl.gz}
    - {name: cuts, kind: lhotse-cuts, root_alias: a, relative_path: LHOTSE/cuts.jsonl.gz}
    - {name: clean, kind: lhotse-supervisions, root_alias: a, relative_path: clean.jsonl.gz}
  splits:
    train:
      recordings_artifact: rec
      supervisions_artifacts: [sup]
      icefall: {use_punc: true, channel: 0}
    test:
      group: test
      cuts_artifacts: [cuts]
      icefall: {use_punc: true}
    dev:
      recordings_artifact: rec
      supervisions_artifact: sup
      icefall: {use_punc: false}
    clean:
      recordings_artifact: rec
      supervisions_artifact: sup
      clean_supervisions_artifacts: [clean]
      icefall: {use_punc: true}
  recipe_parameters:
    icefall: {language: zh}
- schema_version: dataset-catalog/1.0
  dataset_id: common_voice_en
  version: icefall-20260908
  languages: [en]
  tasks: [asr]
  artifacts:
    - {name: rec, kind: lhotse-recordings, root_alias: a, relative_path: cv_rec.jsonl.gz}
    - {name: sup, kind: lhotse-supervisions, root_alias: a, relative_path: cv_sup_dev_cleaned.jsonl.gz}
  splits:
    dev:
      recordings_artifacts: [rec]
      supervisions_artifacts: [sup]
      icefall: {use_punc: false}
"""


def _migrated(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text(CATALOG)
    migrate.main([str(tmp_path)])
    return path, {row["dataset_id"]: row for _, row in read_declarations(path)}


def _paths(entry):
    return {a["name"]: a["relative_path"] for a in entry["artifacts"]}


def test_manifest_directory_becomes_explicit_files(tmp_path):
    _, rows = _migrated(tmp_path)
    entry = rows["cv_ar"]
    assert entry["schema_version"] == "dataset-catalog/2.0"
    assert _paths(entry) == {
        "notes": "ar/notes.json",
        "dev_recordings": "ar/manifests/cv-ar_recordings_dev.jsonl.gz",
        "dev_supervisions": "ar/manifests/cv-ar_supervisions_dev.jsonl.gz",
    }
    assert entry["splits"]["dev"] == {
        "artifacts": {"recordings": ["dev_recordings"], "supervisions": ["dev_supervisions"]},
        "statistics": {"hours": 1.0},
        "provenance": {"sample_cap_per_epoch": 10},
    }


def test_icefall_policy_becomes_registered_artifacts(tmp_path):
    _, rows = _migrated(tmp_path)
    entry = rows["aishell"]
    splits = entry["splits"]
    assert splits["train"] == {
        "artifacts": {
            "recordings": ["rec"],
            "supervisions": ["sup"],
            "punctuated_supervisions": ["sup_punc"],
        }
    }
    assert splits["test"] == {
        "artifacts": {"cuts": ["cuts"], "punctuated_cuts": ["cuts_punc"]},
        "group": "test",
    }
    assert splits["dev"] == {"artifacts": {"recordings": ["rec"], "supervisions": ["sup"]}}
    assert "punctuated_supervisions" not in splits["clean"]["artifacts"]
    assert _paths(entry)["sup_punc"] == "LHOTSE/sup_punc.jsonl.gz"
    assert _paths(entry)["cuts_punc"] == "LHOTSE/cuts_punc.jsonl.gz"
    assert "metadata" not in entry["artifacts"][0]
    assert "recipe_parameters" not in entry


def test_common_voice_en_keeps_original_punctuation_variant(tmp_path):
    _, rows = _migrated(tmp_path)
    entry = rows["common_voice_en"]
    assert entry["splits"]["dev"]["artifacts"]["punctuated_supervisions"] == ["sup_punc"]
    assert _paths(entry)["sup_punc"] == "cv_sup_dev_orig_punc.jsonl.gz"


def test_migration_is_idempotent(tmp_path):
    path, _ = _migrated(tmp_path)
    once = path.read_text()
    migrate.main([str(tmp_path)])
    assert path.read_text() == once
    assert editable_declarations(path)
