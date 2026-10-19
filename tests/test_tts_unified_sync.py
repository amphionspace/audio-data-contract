"""sync-tts-unified: register what DATA-TTS-UNIFIED/PUBLICATIONS.md lists, nothing else."""

import json

import pytest

from audio_data_contract.catalog import load_catalog
from audio_data_contract.errors import ContractError
from audio_data_contract.tts_unified_sync import sync

OVERVIEW = """# 正式发布登记

## 当前发布总览

| 类别 | ID | 内容 | 完成（北京时间） | 用途 |
| --- | --- | --- | --- | --- |
| 基础数据集 | emilia/v0.1 | 2 条 | 2026-09-28 23:17 | |
{annotations}
## 按类别的事件记录
"""


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def annotation(root, task, run_id):
    write_json(
        root / "annotations" / task / run_id / "manifest.json",
        {
            "status": "complete",
            "run_id": run_id,
            "task": task,
            "schema_version": f"{task}-v1",
            "profile": {"name": f"{task}-profile"},
            "outputs": [
                {
                    "dataset_id": "emilia",
                    "release_id": "v0.1",
                    "coverage": {"total_targets": 2, "ok": 2, "failed": 0},
                    "table": {
                        "table_path": f"datasets/emilia/v0.1/annotations/{task}/{run_id}/results.lance",
                        "branch": None,
                        "lance_version": 2,
                        "rows": 2,
                    },
                }
            ],
        },
    )


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data" / "DATA-TTS-UNIFIED"
    write_json(
        root / "datasets/emilia/v0.1/manifest.json",
        {
            "status": "complete",
            "dataset_id": "emilia",
            "release_id": "v0.1",
            "contract_version": "v0.1",
            "release_digest": "d" * 64,
            "languages": {"zh": 2},
            "inputs": [{}],
            "finished_at": "2026-09-28T15:17:37+00:00",
            "lance_version": 1,
            "rows": 2,
            "schema_sha256": "s" * 64,
            "storage_version": "2.2",
            "duration_seconds": 7200.0,
        },
    )
    annotation(root, "transcription", "tts-ann-transcription-1")
    # Complete but not yet listed in PUBLICATIONS.md: must not be registered.
    annotation(root, "speaker_structure", "tts-ann-speaker_structure-1")
    return tmp_path / "data"


OTHER = """- schema_version: dataset-catalog/2.0
  dataset_id: {dataset_id}
  version: {version}
  languages: [zh]
  tasks: [asr]
  artifacts:
    - {{name: cuts, kind: lhotse-cuts, root_alias: aidc_data, relative_path: cuts.jsonl}}
  splits:
    train: {{artifacts: {{cuts: [cuts]}}}}
"""


@pytest.fixture
def catalog_dir(tmp_path):
    # Like the registry: other declaration files sit next to tts_unified.yaml.
    directory = tmp_path / "catalog"
    directory.mkdir()
    (directory / "other.yaml").write_text(
        OTHER.format(dataset_id="aishell1", version="v1"), encoding="utf-8"
    )
    return directory


def publish(data_root, *run_ids):
    rows = "".join(f"| Annotation | `{run_id}` | | | |\n" for run_id in run_ids)
    (data_root / "DATA-TTS-UNIFIED/PUBLICATIONS.md").write_text(
        OVERVIEW.format(annotations=rows), encoding="utf-8"
    )


def test_sync_registers_listed_runs_and_drops_removed_ones(data_root, catalog_dir):
    publish(data_root, "tts-ann-transcription-1")

    summary = sync(data_root, catalog_dir)
    assert summary["changed"]
    assert summary["added"] == [
        "emilia@tts-unified-v0.1:samples",
        "emilia@tts-unified-v0.1:tts-ann-transcription-1",
    ]
    spec = load_catalog(catalog_dir).get("emilia", "tts-unified-v0.1")
    ref = spec.artifact("tts-ann-transcription-1")
    assert ref.kind == "tts-lance-annotation"
    assert ref.relative_path == (
        "DATA-TTS-UNIFIED/annotations/transcription/tts-ann-transcription-1/manifest.json"
    )
    assert ref.metadata["table_path"].startswith("DATA-TTS-UNIFIED/datasets/emilia/")
    assert spec.split("train").artifacts == {
        "samples": ("samples",),
        "transcription": ("tts-ann-transcription-1",),
    }
    assert not sync(data_root, catalog_dir)["changed"]

    publish(data_root)
    summary = sync(data_root, catalog_dir)
    assert summary["removed"] == ["emilia@tts-unified-v0.1:tts-ann-transcription-1"]
    spec = load_catalog(catalog_dir).get("emilia", "tts-unified-v0.1")
    assert [a.name for a in spec.artifacts] == ["samples"]


def test_sync_leaves_the_catalog_alone_when_publications_are_unusable(
    data_root, catalog_dir
):
    publish(data_root, "tts-ann-transcription-1")
    sync(data_root, catalog_dir)
    before = (catalog_dir / "tts_unified.yaml").read_text(encoding="utf-8")

    publications = data_root / "DATA-TTS-UNIFIED/PUBLICATIONS.md"
    text = publications.read_text(encoding="utf-8")
    publications.write_text(text.split("## 按类别")[0], encoding="utf-8")
    with pytest.raises(ContractError, match="no complete"):
        sync(data_root, catalog_dir)

    publish(data_root, "tts-ann-transcription-1", "tts-ann-missing-1")
    with pytest.raises(ContractError, match="expected one manifest"):
        sync(data_root, catalog_dir)

    # A key another declaration file already owns fails validation before the swap.
    publish(data_root)
    (catalog_dir / "other.yaml").write_text(
        OTHER.format(dataset_id="emilia", version="tts-unified-v0.1"), encoding="utf-8"
    )
    with pytest.raises(ContractError, match="duplicate dataset key"):
        sync(data_root, catalog_dir)
    assert (catalog_dir / "tts_unified.yaml").read_text(encoding="utf-8") == before


def test_notify_alerts_once_per_error_and_on_recovery(
    data_root, catalog_dir, tmp_path, monkeypatch
):
    import argparse

    from audio_data_contract import tts_unified_sync

    cards = []
    monkeypatch.setattr(tts_unified_sync, "notify_feishu", cards.append)
    state = tmp_path / "alert.state"
    args = argparse.Namespace(
        data_root=data_root,
        catalog_dir=catalog_dir,
        views=None,
        roots=None,
        dry_run=False,
        notify=True,
        state=str(state),
    )
    publish(data_root, "tts-ann-missing-1")
    for _ in range(2):
        with pytest.raises(ContractError):
            tts_unified_sync.run(args)
    assert [card["header"]["template"] for card in cards] == ["red"]
    assert "tts-ann-missing-1" in cards[0]["body"]["elements"][0]["content"]

    publish(data_root, "tts-ann-transcription-1")
    assert tts_unified_sync.run(args) == 0
    assert [card["header"]["template"] for card in cards] == ["red", "green"]
    assert not state.exists()
    assert tts_unified_sync.run(args) == 0
    assert len(cards) == 2
