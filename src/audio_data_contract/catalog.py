"""Dataset catalog loading, validation, and artifact resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from .errors import ContractError, ResolutionError
from .types import ArtifactRef, DatasetSpec


class DatasetCatalog:
    def __init__(self, specs: Iterable[DatasetSpec]):
        self._by_key: dict[str, DatasetSpec] = {}
        self._versions: dict[str, list[DatasetSpec]] = {}
        self._aliases: dict[str, str] = {}
        for spec in specs:
            if spec.key in self._by_key:
                raise ContractError(f"duplicate dataset key: {spec.key}")
            self._by_key[spec.key] = spec
            self._versions.setdefault(spec.dataset_id, []).append(spec)
            for alias in spec.aliases:
                existing = self._aliases.get(alias)
                if existing is not None and existing != spec.dataset_id:
                    raise ContractError(
                        f"alias {alias!r} maps to both {existing!r} and {spec.dataset_id!r}"
                    )
                self._aliases[alias] = spec.dataset_id
        for versions in self._versions.values():
            versions.sort(key=lambda item: item.version)

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self):
        return iter(self._by_key.values())

    def get(self, dataset_id: str, version: str | None = None) -> DatasetSpec:
        # A stable dataset ID takes precedence over an alias owned by another
        # versioned dataset. This permits migration entries such as the legacy
        # ``common_voice_en`` ID to coexist with a newer canonical dataset that
        # advertises that spelling as a compatibility alias.
        canonical = (
            dataset_id
            if dataset_id in self._versions
            else self._aliases.get(dataset_id, dataset_id)
        )
        versions = self._versions.get(canonical)
        if not versions:
            raise ContractError(f"unknown dataset or alias: {dataset_id!r}")
        if version is None:
            if len(versions) != 1:
                available = [item.version for item in versions]
                raise ContractError(
                    f"dataset {canonical!r} requires a version; available: {available}"
                )
            return versions[0]
        key = f"{canonical}@{version}"
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise ContractError(f"unknown dataset version: {key}") from exc


def validate_catalog(specs: Iterable[DatasetSpec]) -> DatasetCatalog:
    return DatasetCatalog(specs)


def load_catalog(path: str | Path) -> DatasetCatalog:
    """Load one JSONL catalog or every ``*.jsonl`` file in a catalog directory."""

    specs: list[DatasetSpec] = []
    selected = Path(path)
    sources = sorted(selected.glob("*.jsonl")) if selected.is_dir() else [selected]
    if not sources:
        raise ContractError(f"catalog directory contains no JSONL files: {selected}")
    for source in sources:
        with source.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    specs.append(DatasetSpec.from_dict(json.loads(line)))
                except (json.JSONDecodeError, ContractError) as exc:
                    raise ContractError(f"{source}:{line_number}: {exc}") from exc
    return validate_catalog(specs)


def resolve_artifact(
    catalog: DatasetCatalog,
    dataset_id: str,
    version: str,
    artifact_name: str,
    roots: Mapping[str, str | Path],
) -> Path:
    artifact: ArtifactRef = catalog.get(dataset_id, version).artifact(artifact_name)
    if artifact.root_alias not in roots:
        raise ResolutionError(
            f"root alias {artifact.root_alias!r} is not configured for "
            f"{dataset_id}@{version}:{artifact_name}"
        )
    root = Path(roots[artifact.root_alias]).expanduser().resolve(strict=False)
    resolved = (root / artifact.relative_path).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ResolutionError(f"artifact escaped configured root: {resolved}") from exc
    return resolved
