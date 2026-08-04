"""Command line validation and migration helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import load_catalog, resolve_artifact
from .legacy import convert_legacy_registry
from .records import load_records
from .roots import load_roots
from .state import DownloadState, inspect_download, load_state, write_state_atomic


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audio-data-contract")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-catalog")
    validate.add_argument("catalog")

    records = commands.add_parser("validate-records")
    records.add_argument("records")

    state = commands.add_parser("validate-state")
    state.add_argument("state_file")

    inspect = commands.add_parser("inspect-download")
    inspect.add_argument("path")
    inspect.add_argument("--expected-bytes", type=int)

    transition = commands.add_parser("transition-state")
    transition.add_argument("state_file")
    transition.add_argument("target", choices=[state.value for state in DownloadState])
    transition.add_argument("--error")

    resolve = commands.add_parser("resolve")
    resolve.add_argument("catalog")
    resolve.add_argument("dataset_id")
    resolve.add_argument("version")
    resolve.add_argument("artifact")
    resolve.add_argument("--roots")

    legacy = commands.add_parser("convert-legacy")
    legacy.add_argument("input")
    legacy.add_argument("output")
    legacy.add_argument("--version", default="legacy")
    legacy.add_argument("--root", action="append", default=[], metavar="ALIAS=PATH")
    return parser


def _root_args(values: list[str]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for value in values:
        alias, separator, path = value.partition("=")
        if not separator or not alias or not path:
            raise SystemExit(f"invalid --root {value!r}; expected ALIAS=PATH")
        roots[alias] = path
    return roots


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-catalog":
        catalog = load_catalog(args.catalog)
        print(json.dumps({"datasets": len(catalog)}, sort_keys=True))
        return 0
    if args.command == "validate-records":
        count = sum(1 for _ in load_records(args.records))
        print(json.dumps({"records": count}, sort_keys=True))
        return 0
    if args.command == "validate-state":
        state = load_state(args.state_file)
        print(
            json.dumps(
                {
                    "dataset_id": state.dataset_id,
                    "version": state.version,
                    "state": state.state.value,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "inspect-download":
        state = inspect_download(args.path, args.expected_bytes)
        print(json.dumps({"state": state.value}, sort_keys=True))
        return 0
    if args.command == "transition-state":
        state = load_state(args.state_file).transition(args.target, error=args.error)
        write_state_atomic(state, args.state_file)
        print(json.dumps({"state": state.state.value}, sort_keys=True))
        return 0
    if args.command == "resolve":
        catalog = load_catalog(args.catalog)
        roots = load_roots(args.roots)
        print(
            resolve_artifact(
                catalog, args.dataset_id, args.version, args.artifact, roots
            )
        )
        return 0
    if args.command == "convert-legacy":
        source = json.loads(Path(args.input).read_text(encoding="utf-8"))
        specs = convert_legacy_registry(
            source, roots=_root_args(args.root), version=args.version
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as stream:
            for spec in specs:
                stream.write(json.dumps(spec.to_dict(), ensure_ascii=False, sort_keys=True))
                stream.write("\n")
        print(json.dumps({"datasets": len(specs), "output": str(output)}, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
