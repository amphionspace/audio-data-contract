#!/usr/bin/env python3
"""Register wenetspeech_clean@clean-v3-pass-20261027: the clean-v3 L supervisions whose upstream marker is
custom.clean.pass = true, so the version can carry a Lance record index and still be read as clean-only.

The record index stores supervision text but not custom.clean, and open-audio-llm keeps any source with
require_clean_pass on the JSONL cache. Filtering here, by the marker clean-v3 already wrote, gives a version whose
every row passed; recipe_parameters.clean_pass_only declares that, and the rows keep their custom.clean unchanged.
Recordings are clean-v3's own manifest; no audio is copied. Plain (unpunctuated) text only.

    python scripts/wenetspeech_clean_pass.py --root /workspace/data --catalog /workspace/data/registry/catalog \
        --output catalog/wenetspeech_clean_pass.yaml --record /workspace/data/migration/register-wenetspeech-clean-pass-20261027
"""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact, verify_artifact_file
from audio_data_contract.declarations import write_declarations

SOURCE = ("wenetspeech_clean", "clean-v3-20260828")
VERSION = "clean-v3-pass-20261027"
OUTPUT = f"datasets/wenetspeech_clean/versions/{VERSION}/supervisions/train.jsonl.gz"


def passed(row):
    return ((row.get("custom") or {}).get("clean") or {}).get("pass") is True


def filter_supervisions(source, destination):
    """Copy the rows that passed, byte for byte per line; return counts and hours."""
    kept = total = 0
    seconds = 0.0
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with gzip.open(source, "rt", encoding="utf-8") as reader, open(temporary, "wb") as raw, \
            gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as writer:
        for line in reader:
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            if passed(row):
                kept += 1
                seconds += float(row["duration"])
                writer.write(line.rstrip("\n").encode("utf-8") + b"\n")
    temporary.replace(destination)
    return {"rows": total, "kept": kept, "hours": seconds / 3600}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def declaration(source_spec, facts, path, relative):
    artifacts = {a["name"]: a for a in source_spec["artifacts"]}
    supervisions = {
        "name": "train_supervisions", "kind": "lhotse-supervisions", "root_alias": "aidc_data",
        "relative_path": relative, "expected_bytes": path.stat().st_size, "sha256": sha256(path),
        "metadata": {"record_count": facts["kept"], "pass_count": facts["kept"], "punctuated": False},
    }
    return {
        "schema_version": source_spec["schema_version"],
        "dataset_id": SOURCE[0],
        "version": VERSION,
        "languages": list(source_spec["languages"]),
        "tasks": list(source_spec["tasks"]),
        "aliases": [],
        "derived_from": f"{SOURCE[0]}@{SOURCE[1]}",
        "artifacts": [copy.deepcopy(artifacts["train_recordings"]), supervisions],
        "splits": {"train": {
            "artifacts": {"recordings": ["train_recordings"], "supervisions": ["train_supervisions"]},
            "statistics": {"duration_hours": round(facts["hours"], 4),
                           "duration_basis": "sum of supervision durations of the kept rows"},
        }},
        "recipe_parameters": {
            **{k: source_spec["recipe_parameters"][k] for k in ("filter_rules", "rewrite_rules")},
            "filters": f"rows of {SOURCE[0]}@{SOURCE[1]} train_supervisions (plain text) with custom.clean.pass=true",
            "clean_pass_only": True,
        },
        "provenance": {
            "description": (
                f"{SOURCE[0]}@{SOURCE[1]} 训练集（WenetSpeech L）里上游清洗标记 custom.clean.pass=true 的分段，"
                f"共 {facts['kept']} 条 / {facts['hours']:.1f} 小时（源 {facts['rows']} 条，去掉未通过的 "
                f"{facts['rows'] - facts['kept']} 条）；每行原样保留，包括 custom.clean，只用无标点文本。"
                "录音清单沿用源版本，不复制音频。用途：带 Lance 记录索引的 clean-only 版本，"
                "recipe_parameters.clean_pass_only 声明每行都已通过，open-audio-llm 据此让 require_clean_pass 的来源走 Lance 索引。"
                "脚本 scripts/wenetspeech_clean_pass.py。"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    spec = catalog.get(*SOURCE)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    source = resolve_artifact(catalog, *SOURCE, "train_supervisions", roots)
    verify_artifact_file(spec.artifact("train_supervisions"), source)
    expected = spec.artifact("train_supervisions").metadata["pass_count"]
    destination = args.root / OUTPUT
    facts = filter_supervisions(source, destination)
    if facts["kept"] != expected:
        raise SystemExit(f"kept {facts['kept']} rows, the source declares pass_count {expected}")
    write_declarations(args.output, [declaration(spec.to_dict(), facts, destination, OUTPUT)])
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "facts.json").write_text(json.dumps({**facts, "source": f"{SOURCE[0]}@{SOURCE[1]}",
                                                        "output": OUTPUT}, indent=1) + "\n")
    print(json.dumps(facts))


if __name__ == "__main__":
    main()
