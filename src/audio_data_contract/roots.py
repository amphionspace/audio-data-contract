"""Machine-local root alias configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from .errors import ContractError, ResolutionError

ROOTS_ENV = "AUDIO_DATA_ROOTS_FILE"


def load_roots(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Path]:
    environment = os.environ if environ is None else environ
    selected = path or environment.get(ROOTS_ENV)
    if not selected:
        raise ResolutionError(
            f"no roots file configured; pass one explicitly or set {ROOTS_ENV}"
        )
    roots_path = Path(selected)
    try:
        data = json.loads(roots_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"failed to load roots file {roots_path}: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise ContractError("roots file must contain a non-empty JSON object")
    roots: dict[str, Path] = {}
    for alias, value in data.items():
        if not isinstance(alias, str) or not alias.strip():
            raise ContractError("root aliases must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"root {alias!r} must be a non-empty path string")
        root = Path(value).expanduser()
        if not root.is_absolute():
            raise ContractError(f"root {alias!r} must be an absolute path")
        roots[alias] = root.resolve(strict=False)
    return roots
