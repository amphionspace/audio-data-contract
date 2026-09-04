"""Deterministic Markdown overview of registered datasets and logical views."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .catalog import load_catalog
from .errors import ContractError
from .types import DatasetSpec
from .views import load_view_catalog


def _sources(path: str | Path) -> list[Path]:
    selected = Path(path)
    return sorted(selected.glob("*.jsonl")) if selected.is_dir() else [selected]


def _cell(value: object) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text or "—"


def _joined(values: object) -> str:
    return ", ".join(str(value) for value in values) or "—"


def _integrity(spec: DatasetSpec) -> str:
    return str(spec.provenance.get("integrity", "unspecified"))


def render_data_overview(
    catalog_path: str | Path = "catalog",
    views_path: str | Path = "views",
) -> str:
    """Render the current catalog and view state as stable Markdown."""

    catalog = load_catalog(catalog_path)
    views = load_view_catalog(views_path, catalog)
    specs = sorted(catalog, key=lambda spec: (spec.dataset_id, spec.version))
    registered_views = sorted(views, key=lambda view: (view.view_id, view.version))
    grouped_specs = [
        (
            source.name,
            sorted(load_catalog(source), key=lambda spec: (spec.dataset_id, spec.version)),
        )
        for source in _sources(catalog_path)
    ]

    integrity_counts = Counter(_integrity(spec) for spec in specs)
    task_counts = Counter(task for spec in specs for task in spec.tasks)
    artifact_count = sum(len(spec.artifacts) for spec in specs)
    split_count = sum(len(spec.splits) for spec in specs)
    derived_count = sum(spec.derived_from is not None for spec in specs)

    lines = [
        "# 数据总览",
        "",
        "> 本文件由 catalog 和 view 声明自动生成，请勿手工编辑。",
        "> 修改数据声明后，请运行 `audio-data-contract generate-overview`；CI 会用 `--check` 检查同步状态。",
        "",
        "## 整体状态",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 数据集标识 | {len({spec.dataset_id for spec in specs})} |",
        f"| 数据集版本 | {len(specs)} |",
        f"| 派生版本 | {derived_count} |",
        f"| 物理产物 | {artifact_count} |",
        f"| Split 声明 | {split_count} |",
        f"| 逻辑 View | {len(registered_views)} |",
        "",
        "## 完整性状态",
        "",
        "| 状态 | 数据集版本 | 占比 |",
        "|---|---:|---:|",
    ]
    for status, count in sorted(
        integrity_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"| {_cell(status)} | {count} | {count / len(specs):.1%} |")

    lines.extend(
        [
            "",
            "## 任务覆盖",
            "",
            "同一数据集版本可支持多个任务，因此下表数量可能重复计算。",
            "",
            "| Task | 数据集版本 |",
            "|---|---:|",
        ]
    )
    for task, count in sorted(task_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {_cell(task)} | {count} |")

    lines.extend(
        [
            "",
            "## Catalog 分布",
            "",
            "| 声明文件 | 数据集版本 | 数据集标识 | 物理产物 | 已验证版本 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for source_name, source_specs in grouped_specs:
        lines.append(
            f"| `{_cell(source_name)}` | {len(source_specs)} | "
            f"{len({spec.dataset_id for spec in source_specs})} | "
            f"{sum(len(spec.artifacts) for spec in source_specs)} | "
            f"{sum(_integrity(spec) == 'verified' for spec in source_specs)} |"
        )

    lines.extend(["", "## 数据集版本索引", ""])
    for source_name, source_specs in grouped_specs:
        lines.extend(
            [
                f"<details><summary><code>{_cell(source_name)}</code> — {len(source_specs)} 个版本</summary>",
                "",
                "| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |",
                "|---|---|---|---|---|---:|---|---|",
            ]
        )
        for spec in source_specs:
            lines.append(
                f"| {_cell(spec.dataset_id)} | {_cell(spec.version)} | "
                f"{_cell(_joined(spec.languages))} | {_cell(_joined(spec.tasks))} | "
                f"{_cell(_joined(spec.splits))} | {len(spec.artifacts)} | "
                f"{_cell(_integrity(spec))} | {_cell(spec.derived_from or '—')} |"
            )
        lines.extend(["", "</details>", ""])

    lines.extend(
        [
            "## 逻辑 View",
            "",
            "| View | Version | Source | Result | Transforms | Materialization | Lineage |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for view in registered_views:
        transforms = " → ".join(
            f"{step.name}@{step.version}" for step in view.transforms
        )
        lines.append(
            f"| {_cell(view.view_id)} | {_cell(view.version)} | "
            f"{_cell(view.source.key)} | {_cell(view.result.key)} | "
            f"{_cell(transforms)} | {_cell(view.materialization)} | "
            f"{_cell(view.lineage_status)} |"
        )
    lines.append("")
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
