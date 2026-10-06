"""One-time rewrite of dataset-catalog/1.0 YAML declarations to dataset-catalog/2.0.

    python scripts/migrate_catalog_v2.py catalog

Splits gain one ``artifacts: {role: [names]}`` mapping; Lhotse manifest directories
become explicit file artifacts; Icefall read policy becomes registered
punctuated artifacts. Running it again on migrated files changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from audio_data_contract.declarations import (
    declaration_files,
    editable_declarations,
    write_declarations,
)

OLD = "dataset-catalog/1.0"
NEW = "dataset-catalog/2.0"
ICEFALL_VERSION = "icefall-20260908"
SPLIT_FIELDS = ("group", "task", "statistics", "provenance")
ROLE_RENAMES = {"supervisions_punc": "punctuated_supervisions"}


def _role(key):
    for suffix in ("_artifacts", "_artifact"):
        if key.endswith(suffix):
            role = key[: -len(suffix)]
            return ROLE_RENAMES.get(role, role)
    return None


def _names(value, where):
    names = [value] if isinstance(value, str) else list(value)
    if not names or not all(isinstance(name, str) for name in names):
        raise SystemExit(f"{where}: expected artifact name(s), got {value!r}")
    return names


def _punctuated(path, dataset_id):
    if dataset_id == "common_voice_en":
        if path.endswith("_cleaned.jsonl.gz"):
            return path.replace("_cleaned.jsonl.gz", "_orig_punc.jsonl.gz")
        return None
    if path.endswith(".jsonl.gz"):
        return path[: -len(".jsonl.gz")] + "_punc.jsonl.gz"
    return None


def _add_artifact(entry, artifacts, name, kind, root_alias, relative_path):
    if name in artifacts:
        existing = artifacts[name]
        if (existing["kind"], existing["root_alias"], existing["relative_path"]) != (
            kind,
            root_alias,
            relative_path,
        ):
            raise SystemExit(f"{entry['dataset_id']}: artifact name clash {name}")
        return
    artifact = CommentedMap(
        name=name, kind=kind, root_alias=root_alias, relative_path=relative_path
    )
    entry["artifacts"].append(artifact)
    artifacts[name] = artifact


def _migrate_split(entry, artifacts, split_name, split, consumed):
    where = f"{entry['dataset_id']}@{entry['version']}/{split_name}"
    roles = CommentedMap()
    provenance = CommentedMap(split.get("provenance") or {})
    icefall = split.get("icefall") or {}
    for key, value in split.items():
        role = _role(key)
        if key in ("artifacts", "icefall") or (
            key in ("manifest_prefix", "source_split") and "manifest_dir_artifact" in split
        ):
            continue
        if key == "manifest_dir_artifact":
            directory = artifacts[value]
            consumed.add(value)
            for kind in ("recordings", "supervisions"):
                name = f"{split_name}_{kind}"
                path = (
                    f"{directory['relative_path']}/{split['manifest_prefix']}_{kind}_"
                    f"{split['source_split']}.jsonl.gz"
                )
                _add_artifact(
                    entry,
                    artifacts,
                    name,
                    f"lhotse-{kind}",
                    directory["root_alias"],
                    path,
                )
                roles.setdefault(kind, CommentedSeq()).append(name)
        elif role is not None:
            seq = roles.setdefault(role, CommentedSeq())
            seq.extend(n for n in _names(value, f"{where}.{key}") if n not in seq)
        elif key not in SPLIT_FIELDS:
            provenance[key] = value
    if "artifacts" in split:
        for role, names in split["artifacts"].items():
            roles.setdefault(role, CommentedSeq()).extend(names)
    consumed_by_icefall = entry["version"] == ICEFALL_VERSION and "asr" in entry["tasks"]
    if consumed_by_icefall and "clean_supervisions" not in roles:
        # Icefall appended _punc unless the split opted out; CommonVoice EN used
        # _orig_punc variants. Register each variant instead of deriving names.
        use_punc = icefall.get("use_punc", True)
        source_role = "cuts" if "cuts" in roles else "supervisions"
        target_role = f"punctuated_{source_role}"
        if target_role not in roles:
            punctuated = CommentedSeq()
            for name in roles.get(source_role, ()):
                artifact = artifacts[name]
                path = artifact["relative_path"]
                common_voice_en = entry["dataset_id"] == "common_voice_en"
                variant = _punctuated(path, entry["dataset_id"])
                if variant is None or not (use_punc or common_voice_en):
                    continue
                variant_name = f"{name}_punc"
                _add_artifact(
                    entry,
                    artifacts,
                    variant_name,
                    artifact["kind"],
                    artifact["root_alias"],
                    variant,
                )
                punctuated.append(variant_name)
            if punctuated:
                roles[target_role] = punctuated
    result = CommentedMap()
    result["artifacts"] = roles
    for key in ("group", "task", "statistics"):
        if key in split:
            result[key] = split[key]
    if provenance:
        result["provenance"] = provenance
    return result


def migrate_entry(entry):
    if entry.get("schema_version") == NEW:
        return False
    if entry.get("schema_version") != OLD:
        raise SystemExit(f"unexpected schema_version {entry.get('schema_version')!r}")
    entry["schema_version"] = NEW
    artifacts = {artifact["name"]: artifact for artifact in entry["artifacts"]}
    consumed = set()
    for split_name in list(entry.get("splits", {})):
        entry["splits"][split_name] = _migrate_split(
            entry, artifacts, split_name, entry["splits"][split_name], consumed
        )
    referenced = {
        name
        for split in entry["splits"].values()
        for names in split["artifacts"].values()
        for name in names
    }
    for artifact in list(entry["artifacts"]):
        if artifact["name"] in consumed - referenced:
            entry["artifacts"].remove(artifact)
        metadata = artifact.get("metadata")
        if metadata is not None and "icefall_relative_to_lhotse" in metadata:
            del metadata["icefall_relative_to_lhotse"]
            if not metadata:
                del artifact["metadata"]
    parameters = entry.get("recipe_parameters")
    if parameters is not None and "icefall" in parameters:
        del parameters["icefall"]
        if not parameters:
            del entry["recipe_parameters"]
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args(argv)
    for path in declaration_files(args.catalog):
        if path.suffix not in {".yaml", ".yml"}:
            continue
        rows = editable_declarations(path)
        changed = [migrate_entry(row) for row in rows]
        if any(changed):
            write_declarations(path, rows)
            print(f"{path}: {sum(changed)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
