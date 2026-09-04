from dataclasses import replace
from pathlib import Path

import pytest

from audio_data_contract import load_catalog, load_view_catalog
from audio_data_contract.cli import main
from audio_data_contract.errors import ContractError
from audio_data_contract.overview import (
    _duration,
    render_data_overview,
    update_data_overview,
)

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


def test_overview_answers_scale_task_duration_and_quality_questions():
    catalog = load_catalog(ROOT / "catalog")
    views = load_view_catalog(ROOT / "views", catalog)
    rendered = render_data_overview(ROOT / "catalog", ROOT / "views")
    supported_tasks = {task for spec in catalog for task in spec.tasks}

    assert f"| 登记了多少个版本 | {len(catalog)} 个" in rendered
    assert f"| 支持多少类任务 | {len(supported_tasks)} 类 |" in rendered
    assert f"| 已登记的逻辑数据视图 | {len(views)} 个 |" in rendered
    assert "## 支持哪些任务" in rendered
    assert "语音识别" in rendered
    assert "已登记时长（小时）" in rendered
    assert "## 数据质量如何" in rendered
    assert "文件校验通过，不等于内容正确" in rendered
    assert "有已知标注问题" in rendered
    assert "不能代表整集准确率" in rendered


def test_grouped_split_durations_are_not_counted_twice():
    catalog = load_catalog(ROOT / "catalog")
    spec = catalog.get("police_synthetic_zh_accent", "v2-20260818")

    duration = _duration(spec)

    assert duration.kind == "reported"
    assert duration.hours == pytest.approx(46.411 + 6.220856)


def test_nominal_and_pre_filter_hours_are_clearly_separated():
    catalog = load_catalog(ROOT / "catalog")

    nominal = _duration(catalog.get("notsofar", "hf-ba8fd0f034ce-sim-v1.5-200h"))
    filtered = _duration(catalog.get("wenetspeech", "clean-weak-v1-20260904"))

    assert nominal.kind == "nominal"
    assert nominal.hours == 200
    assert filtered.kind == "before_filter"
    assert filtered.hours == pytest.approx(2477.941)
    assert not filtered.included


def test_reported_split_hours_take_priority_over_nominal_hours():
    catalog = load_catalog(ROOT / "catalog")
    spec = catalog.get("notsofar", "hf-ba8fd0f034ce-sim-v1.5-200h")
    spec_with_reported_hours = replace(
        spec, splits={"train": {"statistics": {"duration_hours": 198.5}}}
    )

    duration = _duration(spec_with_reported_hours)

    assert duration.kind == "reported"
    assert duration.hours == 198.5


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
