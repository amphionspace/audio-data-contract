#!/usr/bin/env python3
"""Register magicdata_ramc@clean-dual-pass-20261027: the train supervisions of magicdata_ramc@clean-dual-qwen-moss-v1-20261008
(plain text) whose clean marker is custom.clean.pass = true, so the version can carry a Lance record index and still be read
as clean-only. Same construction as scripts/wenetspeech_clean_pass.py; made for the RAMC target-speaker scene pools
(build_ts_scene_pool.py --ramc), which read speakers and spans from the Lance record index.

The record index stores supervision text but not custom.clean, and open-audio-llm keeps any source with
require_clean_pass on the JSONL cache. Filtering here, by the marker clean-v3 already wrote, gives a version whose
every row passed; recipe_parameters.clean_pass_only declares that, and the rows keep their custom.clean unchanged.
Recordings are the source's own manifest (shared with magicdata_ramc@icefall-20260908); no audio is copied. Plain
(unpunctuated) text only. Rows of every speaker are kept; held-out speakers are a reader's choice.

    python scripts/ramc_clean_pass.py --root /workspace/data --catalog /workspace/data/registry/catalog \
        --output catalog/magicdata_ramc_clean_pass.yaml --record /workspace/data/migration/register-magicdata-ramc-clean-pass-20261027
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

SOURCE = ("magicdata_ramc", "clean-dual-qwen-moss-v1-20261008")
VERSION = "clean-dual-pass-20261027"
OUTPUT = f"datasets/magicdata_ramc/versions/{VERSION}/supervisions/train.jsonl.gz"
SOURCE_SUPERVISIONS = "train_supervisions_no_punc"


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
            "filters": f"rows of {SOURCE[0]}@{SOURCE[1]} {SOURCE_SUPERVISIONS} (plain text) with custom.clean.pass=true",
            "clean_pass_only": True,
        },
        "provenance": {
            "description": (
                f"{SOURCE[0]}@{SOURCE[1]} 训练集（MagicData-RAMC 电话对话）里清洗标记 custom.clean.pass=true 的分段，"
                f"共 {facts['kept']} 条 / {facts['hours']:.1f} 小时（源 {facts['rows']} 条，去掉未通过的 "
                f"{facts['rows'] - facts['kept']} 条）；每行原样保留，包括 custom.clean，只用无标点文本。"
                "录音清单沿用源版本（与 icefall-20260908 共用），不复制音频；保留所有说话人，留出测试 / 验证集说话人由读取方决定。"
                "用途：带 Lance 记录索引的 clean-only 版本，供 RAMC 目标说话人场景池（build_ts_scene_pool.py --ramc）按说话人取句；"
                "recipe_parameters.clean_pass_only 声明每行都已通过。脚本 scripts/ramc_clean_pass.py。"),
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
    source = resolve_artifact(catalog, *SOURCE, SOURCE_SUPERVISIONS, roots)
    verify_artifact_file(spec.artifact(SOURCE_SUPERVISIONS), source)
    expected = spec.artifact(SOURCE_SUPERVISIONS).metadata["pass_count"]
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
