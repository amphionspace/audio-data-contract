"""Conversion from the historical language-keyed multilingual registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .errors import ContractError
from .types import ArtifactRef, DatasetSpec


def _portable_location(
    source: str,
    roots: Mapping[str, str | Path],
) -> tuple[str, str]:
    absolute = Path(source).resolve(strict=False)
    candidates: list[tuple[int, str, str]] = []
    for alias, root_value in roots.items():
        root = Path(root_value).resolve(strict=False)
        try:
            relative = absolute.relative_to(root)
        except ValueError:
            continue
        candidates.append((len(root.parts), alias, relative.as_posix()))
    if not candidates:
        raise ContractError(f"legacy path is outside configured roots: {source}")
    _, alias, relative = max(candidates)
    return alias, relative


def convert_legacy_registry(
    data: Mapping[str, Any],
    *,
    roots: Mapping[str, str | Path],
    version: str = "legacy",
    aliases: Mapping[str, list[str]] | None = None,
) -> list[DatasetSpec]:
    result: list[DatasetSpec] = []
    alias_map = aliases or {}
    for language, datasets_value in data.items():
        if not isinstance(datasets_value, Mapping):
            raise ContractError(f"legacy language {language!r} must contain an object")
        for dataset_id, value in datasets_value.items():
            if not isinstance(value, Mapping):
                raise ContractError(f"legacy dataset {dataset_id!r} must be an object")
            manifest_dir = value.get("manifests_dir")
            prefix = value.get("manifest_prefix")
            if not isinstance(manifest_dir, str) or not isinstance(prefix, str):
                raise ContractError(
                    f"legacy dataset {dataset_id!r} needs manifests_dir and manifest_prefix"
                )
            root_alias, relative = _portable_location(manifest_dir, roots)
            splits: dict[str, dict[str, Any]] = {}
            for split_name, split_value in (value.get("splits") or {}).items():
                if not isinstance(split_value, Mapping):
                    raise ContractError(
                        f"legacy dataset {dataset_id!r} split {split_name!r} must be an object"
                    )
                splits[split_name] = {
                    "manifest_dir_artifact": "manifests",
                    "manifest_prefix": prefix,
                    "source_split": split_name,
                    "statistics": dict(split_value),
                }
            provenance = {
                "legacy_total_recordings": value.get("total_recordings"),
                "legacy_total_hours": value.get("total_hours"),
                "has_punctuation": value.get("has_punctuation"),
                "has_true_casing": value.get("has_true_casing"),
            }
            result.append(
                DatasetSpec(
                    dataset_id=dataset_id,
                    version=version,
                    languages=(language,),
                    tasks=("asr",),
                    aliases=tuple(alias_map.get(dataset_id, [])),
                    artifacts=(
                        ArtifactRef(
                            name="manifests",
                            kind="lhotse-manifest-dir",
                            root_alias=root_alias,
                            relative_path=relative,
                        ),
                    ),
                    splits=splits,
                    provenance=provenance,
                )
            )
    return result
