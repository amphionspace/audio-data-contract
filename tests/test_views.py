import json
from pathlib import Path

import pytest

from audio_data_contract import load_catalog, load_view_catalog, resolve_view
from audio_data_contract.cli import main
from audio_data_contract.errors import ContractError

ROOT = Path(__file__).parents[1]


def _write_catalog(path):
    source = {
        "schema_version": "dataset-catalog/1.0",
        "dataset_id": "demo",
        "version": "source-1",
        "languages": ["en"],
        "tasks": ["asr"],
        "artifacts": [],
        "splits": {"train": {}},
    }
    result = {
        **source,
        "dataset_id": "demo_hotwords",
        "version": "hotwords-1",
        "derived_from": "demo",
    }
    path.write_text(
        json.dumps(source) + "\n" + json.dumps(result) + "\n",
        encoding="utf-8",
    )


def _view(result_id="demo_hotwords"):
    return {
        "schema_version": "dataset-view/1.0",
        "view_id": "demo/hotwords",
        "version": "v1",
        "source": {"dataset_id": "demo", "version": "source-1"},
        "transforms": [
            {
                "name": "hotwords",
                "version": "v1",
                "kind": "annotate",
                "writes": ["hotwords"],
            }
        ],
        "result": {"dataset_id": result_id, "version": "hotwords-1"},
        "materialization": "full",
        "lineage_status": "exact",
    }


def test_view_catalog_resolves_materialized_dataset(tmp_path):
    catalog_path = tmp_path / "catalog.jsonl"
    views_path = tmp_path / "views.jsonl"
    _write_catalog(catalog_path)
    views_path.write_text(json.dumps(_view()) + "\n", encoding="utf-8")

    datasets = load_catalog(catalog_path)
    views = load_view_catalog(views_path, datasets)
    result = resolve_view(views, datasets, "demo/hotwords", "v1")

    assert result.key == "demo_hotwords@hotwords-1"
    assert views.get("demo/hotwords").transforms[0].writes == ("hotwords",)


def test_view_catalog_rejects_missing_dataset_reference(tmp_path):
    catalog_path = tmp_path / "catalog.jsonl"
    views_path = tmp_path / "views.jsonl"
    _write_catalog(catalog_path)
    views_path.write_text(json.dumps(_view("missing")) + "\n", encoding="utf-8")

    with pytest.raises(ContractError, match="unknown dataset"):
        load_view_catalog(views_path, load_catalog(catalog_path))


def test_exact_view_rejects_cross_dataset_result_without_lineage(tmp_path):
    catalog_path = tmp_path / "catalog.jsonl"
    views_path = tmp_path / "views.jsonl"
    _write_catalog(catalog_path)
    records = [json.loads(line) for line in catalog_path.read_text().splitlines()]
    records[1].pop("derived_from")
    catalog_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    views_path.write_text(json.dumps(_view()) + "\n", encoding="utf-8")

    with pytest.raises(ContractError, match="result derives from None"):
        load_view_catalog(views_path, load_catalog(catalog_path))


def test_exact_view_allows_same_dataset_version_change_without_lineage(tmp_path):
    catalog_path = tmp_path / "catalog.jsonl"
    views_path = tmp_path / "views.jsonl"
    _write_catalog(catalog_path)
    records = [json.loads(line) for line in catalog_path.read_text().splitlines()]
    records[1]["dataset_id"] = "demo"
    records[1].pop("derived_from")
    catalog_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    view = _view("demo")
    views_path.write_text(json.dumps(view) + "\n", encoding="utf-8")

    assert len(load_view_catalog(views_path, load_catalog(catalog_path))) == 1


def test_view_rejects_undeclared_field_conflict(tmp_path):
    catalog_path = tmp_path / "catalog.jsonl"
    views_path = tmp_path / "views.jsonl"
    _write_catalog(catalog_path)
    view = _view()
    view["transforms"].append(
        {
            "name": "second-hotword-pass",
            "version": "v2",
            "kind": "annotate",
            "writes": ["hotwords"],
        }
    )
    views_path.write_text(json.dumps(view) + "\n", encoding="utf-8")

    with pytest.raises(ContractError, match="declare an override"):
        load_view_catalog(views_path, load_catalog(catalog_path))


def test_registered_local_views_are_valid_and_resolvable(capsys):
    datasets = load_catalog(ROOT / "catalog")
    views = load_view_catalog(ROOT / "views", datasets)

    assert len(views) == 19
    assert all(view.materialization == "full" for view in views)
    assert (
        resolve_view(views, datasets, "wenetspeech/clean", "v1-20260805").dataset_id
        == "wenetspeech_clean"
    )
    current = resolve_view(views, datasets, "wenetspeech/clean", "v3-20260828")
    assert current.key == "wenetspeech_clean@clean-v3-20260828"
    assert views.get("wenetspeech/clean", "v3-20260828").lineage_status == "exact"
    weak = resolve_view(views, datasets, "wenetspeech/clean", "weak-v1-20260904")
    assert weak.key == "wenetspeech@clean-weak-v1-20260904"
    assert views.get("wenetspeech/clean", "weak-v1-20260904").lineage_status == "exact"

    assert main(["validate-views", str(ROOT / "views"), str(ROOT / "catalog")]) == 0
    assert json.loads(capsys.readouterr().out) == {"views": 19}
