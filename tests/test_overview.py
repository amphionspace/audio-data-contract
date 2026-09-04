from pathlib import Path

import pytest

from audio_data_contract import load_catalog, load_view_catalog
from audio_data_contract.cli import main
from audio_data_contract.errors import ContractError
from audio_data_contract.overview import render_data_overview, update_data_overview

ROOT = Path(__file__).parents[1]


def test_tracked_overview_matches_registered_data(capsys):
    overview = ROOT / "docs/data-overview.md"

    assert overview.read_text(encoding="utf-8") == render_data_overview(
        ROOT / "catalog", ROOT / "views"
    )
    assert (
        main(
            [
                "generate-overview",
                "--catalog",
                str(ROOT / "catalog"),
                "--views",
                str(ROOT / "views"),
                "--output",
                str(overview),
                "--check",
            ]
        )
        == 0
    )
    assert '"status": "current"' in capsys.readouterr().out


def test_overview_exposes_summary_dataset_index_and_views():
    catalog = load_catalog(ROOT / "catalog")
    views = load_view_catalog(ROOT / "views", catalog)
    rendered = render_data_overview(ROOT / "catalog", ROOT / "views")

    assert f"| 数据集版本 | {len(catalog)} |" in rendered
    assert f"| 逻辑 View | {len(views)} |" in rendered
    assert "## 数据集版本索引" in rendered
    assert "## 逻辑 View" in rendered
    assert "wenetspeech/clean" in rendered


def test_overview_check_rejects_stale_content(tmp_path):
    output = tmp_path / "overview.md"
    output.write_text("stale\n", encoding="utf-8")

    with pytest.raises(ContractError, match="out of date"):
        update_data_overview(
            output,
            catalog_path=ROOT / "catalog",
            views_path=ROOT / "views",
            check=True,
        )
