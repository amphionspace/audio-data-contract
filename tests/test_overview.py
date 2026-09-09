from dataclasses import replace
from pathlib import Path

import pytest

from audio_data_contract import load_catalog
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


def test_overview_lists_datasets_instead_of_consumer_versions():
    rendered = render_data_overview(ROOT / "catalog", ROOT / "views")
    inventory = rendered.split("## 下载来源声明")[0]

    assert (
        "| 数据集 | 语言 | 支持任务 | 时长（小时，注明范围） | 特性 / 备注 |"
        in inventory
    )
    assert inventory.count("| [common_voice_en](") == 1
    assert "| [commonvoice_en_clean](" not in inventory
    assert "| [cv_en_noise_dns](" not in inventory
    assert "| [alimeeting_sdm](" not in inventory
    assert "| [aishell5](" not in inventory
    assert "| [granary](" not in inventory
    assert "| [icefall_v10_farfield_replay](" not in inventory
    assert "| [mls](" in inventory
    assert "| [tal100_en](" in inventory  # Missing duration must not hide data.
    assert "未登记" in next(
        line for line in inventory.splitlines() if "| [tal100_en](" in line
    )
    assert "按版本相加的可汇总时长" not in rendered
    assert "## 下载来源声明" in rendered
    assert "## 训练混合配方" in rendered
    assert "文件校验通过，不等于内容正确" in rendered
    assert "有已知标注问题" in rendered
    assert "不能代表整集准确率" in rendered


def test_family_duration_preserves_scope_and_does_not_add_versions():
    rendered = render_data_overview(ROOT / "catalog", ROOT / "views")
    row = next(line for line in rendered.splitlines() if "| [notsofar](" in line)
    assert "200.0（估算" in row
    assert "176.9（已登记" in row
    assert "376.9" not in row
    cv = next(line for line in rendered.splitlines() if "| [common_voice_en](" in line)
    assert "1,854.0" in cv and "参考表" in cv


def test_cv_cleaning_evidence_distinguishes_report_from_published_manifest():
    catalog = load_catalog(ROOT / "catalog")
    spec = catalog.get("commonvoice_en_clean", "clean-v1-20260805")
    assert spec.recipe_parameters["engines"] == ["Qwen3-ASR-1.7B", "whisper-large-v3"]
    assert spec.splits["train"]["statistics"]["reject"] == 1127
    assert "pass" not in spec.splits["test"]["statistics"]
    evidence = spec.provenance["cleaning_verification"]
    assert evidence["test_report"]["reject"] == 108
    assert evidence["manifest_findings"]["test_filter_applied"] is False
    rendered = render_data_overview(ROOT / "catalog", ROOT / "views")
    row = next(
        line for line in rendered.splitlines() if "| [commonvoice_en_clean@" in line
    )
    assert "有自动筛选记录" in row
    assert "未登记人工抽检" in row
    assert "人工抽检 0 条" not in row


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


def test_chart_data_deduplicates_families_and_excludes_plans():
    from audio_data_contract.overview import _chart_data

    base = load_catalog(ROOT / "catalog").get("librispeech", "legacy-20260804")
    measured = replace(
        base,
        dataset_id="measured",
        version="v1",
        provenance={},
        splits={"train": {"statistics": {"duration_hours": 50}}},
    )
    older = replace(
        measured, version="v0", splits={"train": {"statistics": {"duration_hours": 40}}}
    )
    reference = replace(
        base,
        dataset_id="reference",
        splits={},
        provenance={"reference_duration": {"hours": 100}},
    )
    missing = replace(base, dataset_id="missing", splits={}, provenance={})
    planned = replace(
        measured,
        dataset_id="planned",
        provenance={"inventory_status": "download_planned"},
    )
    mixture = replace(
        measured,
        dataset_id="mixture",
        provenance={"inventory_category": "training_mixture"},
    )
    partial = replace(
        base,
        dataset_id="partial",
        provenance={},
        splits={"train": {"statistics": {"hours_before_filter": 1000}}},
    )
    top, coverage = _chart_data(
        [measured, older, reference, missing, planned, mixture, partial]
    )

    assert [(row[0], row[2], row[3]) for row in top] == [
        ("reference", 100, "reference"),
        ("measured", 50, "reported"),
    ]
    assert [row[2] for row in coverage] == [1, 2, 1]


@pytest.mark.parametrize("missing", [False, True])
def test_overview_check_rejects_stale_or_missing_chart(tmp_path, missing):
    output = tmp_path / "overview.md"
    kwargs = {"catalog_path": ROOT / "catalog", "views_path": ROOT / "views"}
    update_data_overview(output, **kwargs)
    chart = tmp_path / "assets/data-duration-top20.svg"
    if missing:
        chart.unlink()
    else:
        chart.write_text("stale\n", encoding="utf-8")
    with pytest.raises(ContractError, match="missing" if missing else "out of date"):
        update_data_overview(output, check=True, **kwargs)
