"""Deterministic, human-readable overview of registered data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import load_catalog
from .errors import ContractError
from .types import DatasetSpec
from .views import load_view_catalog


TASK_NAMES = {
    "asr": "语音识别",
    "asr_hotwords": "热词增强语音识别",
    "ast": "语音翻译",
    "code_switch_asr": "语码转换语音识别",
    "continuous_speech_separation": "连续语音分离",
    "esc": "背景声场景描述",
    "overlap_speech": "重叠语音检测",
    "sec": "说话人情感分类",
    "sepc": "情感与说话风格描述",
    "ser": "语音情感识别",
    "speaker_attributed_asr": "带说话人标注的语音识别",
    "speaker_diarization": "说话人分段与归属",
    "ts_asr": "目标说话人语音识别",
}


@dataclass(frozen=True)
class DurationSummary:
    """A duration that can be included in totals, or a reason it cannot."""

    hours: float | None
    kind: str
    basis: str

    @property
    def included(self) -> bool:
        return self.kind in {"reported", "nominal"}


def _cell(value: object) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text or "—"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _duration(spec: DatasetSpec) -> DurationSummary:
    legacy_total = _number(spec.provenance.get("legacy_total_hours"))
    if legacy_total is not None:
        return DurationSummary(legacy_total, "reported", "发布方或原登记总时长")

    root_splits = [split for split in spec.splits.values() if not split.get("group")]
    reported: list[float] = []
    before_filter: list[float] = []
    missing = 0
    for split in root_splits:
        statistics = split.get("statistics", {})
        value = _number(statistics.get("duration_hours", statistics.get("hours")))
        if value is not None:
            reported.append(value)
            continue
        previous = _number(statistics.get("hours_before_filter"))
        if previous is not None:
            before_filter.append(previous)
        else:
            missing += 1

    if root_splits and len(reported) == len(root_splits):
        return DurationSummary(sum(reported), "reported", "各顶层 split 时长之和")

    nominal_total = _number(spec.provenance.get("nominal_duration_hours"))
    if nominal_total is not None:
        return DurationSummary(nominal_total, "nominal", "名义时长（估算）")

    if reported:
        return DurationSummary(sum(reported), "partial", "仅部分顶层 split 登记了时长")
    if before_filter and not missing:
        return DurationSummary(
            sum(before_filter), "before_filter", "仅有过滤前时长，不代表当前版本"
        )
    return DurationSummary(None, "missing", "未登记")


def _integrity(spec: DatasetSpec) -> str:
    return str(spec.provenance.get("integrity", "unspecified"))


def _has_content_quality_evidence(spec: DatasetSpec) -> bool:
    if "quality_status" in spec.provenance or "manual_review" in spec.provenance:
        return True
    return any(
        "pass" in split.get("statistics", {}) or "reject" in split.get("statistics", {})
        for split in spec.splits.values()
    )


def _format_hours(value: float) -> str:
    return f"{value:,.1f}"


def _task_name(task: str) -> str:
    return TASK_NAMES.get(task, task)


def _task_list(tasks: tuple[str, ...]) -> str:
    return "、".join(_task_name(task) for task in tasks)


def _quality_rows(specs: list[DatasetSpec]) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for spec in specs:
        status = spec.provenance.get("quality_status")
        findings = spec.provenance.get("quality_findings", {})
        if status == "known_annotation_bounds_issues":
            train = int(findings.get("train_annotation_out_of_bounds_count", 0))
            dev = int(findings.get("dev_annotation_out_of_bounds_count", 0))
            test = int(findings.get("test_annotation_out_of_bounds_count", 0))
            overrun = float(findings.get("max_overrun_seconds", 0.0))
            rows.append(
                (
                    spec.key,
                    "有已知标注问题",
                    f"训练集 {train} 条标注越过音频边界；开发集 {dev} 条；测试集 {test} 条",
                    f"最大越界 {overrun:.3f} 秒，使用前应处理异常标注",
                )
            )

        review = spec.provenance.get("manual_review")
        split_statistics = [
            split.get("statistics", {}) for split in spec.splits.values()
        ]
        passed = sum(int(item.get("pass", 0)) for item in split_statistics)
        rejected = sum(int(item.get("reject", 0)) for item in split_statistics)
        if review or passed or rejected:
            total = passed + rejected
            rate = passed / total if total else 0.0
            reviewed = 0
            confirmed = 0
            if isinstance(review, dict):
                reviewed = int(review.get("content_review", 0)) + int(
                    review.get("replaced_review", 0)
                )
                confirmed = int(review.get("proposal_confirmed", 0))
            rows.append(
                (
                    spec.key,
                    "有自动筛选和人工抽检记录",
                    f"自动筛选通过 {passed:,} 条、拒绝 {rejected:,} 条，通过率 {rate:.2%}",
                    f"人工抽检 {reviewed} 条，其中确认 {confirmed} 条；样本很小，不能代表整集准确率",
                )
            )
    return rows


def render_data_overview(
    catalog_path: str | Path = "catalog",
    views_path: str | Path = "views",
) -> str:
    """Render the current catalog and view state as stable Markdown."""

    catalog = load_catalog(catalog_path)
    views = load_view_catalog(views_path, catalog)
    specs = sorted(catalog, key=lambda spec: (spec.dataset_id, spec.version))
    durations = {spec.key: _duration(spec) for spec in specs}

    task_counts = Counter(task for spec in specs for task in spec.tasks)
    integrity_counts = Counter(_integrity(spec) for spec in specs)
    derived_count = sum(spec.derived_from is not None for spec in specs)
    quality_rows = _quality_rows(specs)
    quality_count = sum(_has_content_quality_evidence(spec) for spec in specs)

    reported_hours = sum(
        item.hours or 0.0 for item in durations.values() if item.kind == "reported"
    )
    nominal_hours = sum(
        item.hours or 0.0 for item in durations.values() if item.kind == "nominal"
    )
    covered_count = sum(item.included for item in durations.values())

    lines = [
        "# 数据总览",
        "",
        "这里回答四个最常见的问题：现在有多少数据、能做什么任务、时长统计覆盖到什么程度，以及已有的质量证据是什么。",
        "",
        "> 本页由 catalog 和 view 声明自动生成。这里的“总时长”按数据集版本相加，可能包含同一音频的不同版本，不能理解为去重后的物理音频时长。",
        "",
        "## 一眼看懂当前数据",
        "",
        "| 你可能关心的问题 | 当前答案 |",
        "|---|---:|",
        f"| 登记了多少个数据集 | {len({spec.dataset_id for spec in specs})} 个 |",
        f"| 登记了多少个版本 | {len(specs)} 个，其中 {derived_count} 个是派生版本 |",
        f"| 支持多少类任务 | {len(task_counts)} 类 |",
        f"| 按版本相加的可汇总时长 | {_format_hours(reported_hours + nominal_hours)} 小时 |",
        f"| 其中：已登记时长 | {_format_hours(reported_hours)} 小时 |",
        f"| 其中：名义时长 | {_format_hours(nominal_hours)} 小时 |",
        f"| 有可汇总时长的版本 | {covered_count} / {len(specs)} 个 |",
        f"| 完成文件完整性校验的版本 | {integrity_counts['verified']} / {len(specs)} 个 |",
        f"| 有内容质量记录的版本 | {quality_count} / {len(specs)} 个 |",
        f"| 已登记的逻辑数据视图 | {len(views)} 个 |",
        "",
        "“已登记时长”来自发布方统计、历史登记值或顶层 split 的时长；“名义时长”是数据声明中的估算值。还有 "
        f"{len(specs) - covered_count} 个版本没有可汇总的当前时长，因此上面的数字不是仓库全部数据的真实总量。",
        "",
        "## 支持哪些任务",
        "",
        "同一个数据版本可以同时服务多个任务。下表会把该版本的全部时长记到每个适用任务中，所以各任务时长不能再次相加。",
        "",
        "| 任务 | 标识 | 数据版本 | 已登记时长（小时） | 名义时长（小时） | 时长覆盖 |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for task, count in sorted(
        task_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        task_specs = [spec for spec in specs if task in spec.tasks]
        reported = sum(
            durations[spec.key].hours or 0.0
            for spec in task_specs
            if durations[spec.key].kind == "reported"
        )
        nominal = sum(
            durations[spec.key].hours or 0.0
            for spec in task_specs
            if durations[spec.key].kind == "nominal"
        )
        covered = sum(durations[spec.key].included for spec in task_specs)
        lines.append(
            f"| {_cell(_task_name(task))} | `{_cell(task)}` | {count} | "
            f"{_format_hours(reported) if reported else '—'} | "
            f"{_format_hours(nominal) if nominal else '—'} | {covered} / {count} |"
        )

    lines.extend(
        [
            "",
            "## 数据质量如何",
            "",
            "质量要分成两件事看：",
            "",
            "- **文件完整性**：文件大小、哈希或清单是否核验过。它只能说明文件没有悄悄变化。",
            "- **内容质量**：转写、标签、时间边界等是否准确。文件校验通过，不等于内容正确。",
            "",
            "| 检查项 | 数据版本 | 占全部版本 |",
            "|---|---:|---:|",
            f"| 文件完整性已核验 | {integrity_counts['verified']} | {integrity_counts['verified'] / len(specs):.1%} |",
            f"| 文件完整性未标记为已核验 | {len(specs) - integrity_counts['verified']} | {(len(specs) - integrity_counts['verified']) / len(specs):.1%} |",
            f"| 有内容质量记录 | {quality_count} | {quality_count / len(specs):.1%} |",
            f"| 暂无内容质量记录 | {len(specs) - quality_count} | {(len(specs) - quality_count) / len(specs):.1%} |",
            "",
            "目前有明确证据可展示的内容质量记录如下。没有出现在表里，不代表质量差，只表示 catalog 里还没有足够信息可判断。",
            "",
            "| 数据版本 | 当前结论 | 已记录证据 | 使用时要注意 |",
            "|---|---|---|---|",
        ]
    )
    for key, conclusion, evidence, caution in quality_rows:
        lines.append(
            f"| `{_cell(key)}` | {_cell(conclusion)} | {_cell(evidence)} | {_cell(caution)} |"
        )

    included_specs = [spec for spec in specs if durations[spec.key].included]
    excluded_with_reference = [
        spec
        for spec in specs
        if durations[spec.key].kind in {"partial", "before_filter"}
    ]
    lines.extend(
        [
            "",
            "## 哪些版本已经登记时长",
            "",
            f"下面列出计入总览的 {len(included_specs)} 个版本。派生版本和不同版本可能复用同一批音频，所以这里只做版本口径统计。",
            "",
            f"<details><summary>展开 {len(included_specs)} 个版本的时长明细</summary>",
            "",
            "| 数据版本 | 可用于 | 时长（小时） | 统计口径 |",
            "|---|---|---:|---|",
        ]
    )
    for spec in included_specs:
        duration = durations[spec.key]
        lines.append(
            f"| `{_cell(spec.key)}` | {_cell(_task_list(spec.tasks))} | "
            f"{_format_hours(duration.hours or 0.0)} | {_cell(duration.basis)} |"
        )
    lines.extend(["", "</details>", ""])

    if excluded_with_reference:
        lines.extend(
            [
                "以下版本虽然有参考数字，但不能作为当前版本完整时长计入合计：",
                "",
                "| 数据版本 | 参考时长（小时） | 原因 |",
                "|---|---:|---|",
            ]
        )
        for spec in excluded_with_reference:
            duration = durations[spec.key]
            lines.append(
                f"| `{_cell(spec.key)}` | {_format_hours(duration.hours or 0.0)} | {_cell(duration.basis)} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 数据变动时必须同步什么",
            "",
            "1. 新增或修改数据版本时，在 catalog 的顶层 split 中登记 `statistics.duration_hours`。历史声明中的 `statistics.hours` 仍可读取。",
            "2. 细分统计必须通过 `group` 指向所属顶层 split；总览不会重复累加这些子分组。",
            "3. 过滤后的版本要登记过滤后的实际时长。只有 `hours_before_filter` 时，总览只把它当参考值，不计入当前版本合计。",
            "4. 文件校验结果写入 `provenance.integrity`；内容抽检、自动筛选和已知问题分别写入 `manual_review`、split 统计和 `quality_findings`，不要把文件完整性当成内容质量。",
            "5. 修改 catalog 或 view 后运行 `audio-data-contract generate-overview`。CI 会运行 `audio-data-contract generate-overview --check`，总览未同步就不能通过。",
            "",
            "完整的机器可读声明位于 `catalog/` 和 `views/`；本页只保留协作者做判断时最需要的信息。",
            "",
        ]
    )
    return "\n".join(lines)


def update_data_overview(
    output: str | Path,
    *,
    catalog_path: str | Path = "catalog",
    views_path: str | Path = "views",
    check: bool = False,
) -> str:
    """Write the overview, or fail when a checked overview is stale."""

    destination = Path(output)
    rendered = render_data_overview(catalog_path, views_path)
    if check:
        try:
            current = destination.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContractError(f"data overview is missing: {destination}") from exc
        if current != rendered:
            raise ContractError(
                "data overview is out of date; run "
                "`audio-data-contract generate-overview`"
            )
        return "current"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    return "written"
