#!/usr/bin/env python3
"""Register the hotword labels of the TS benchmark transcripts as <source>@<v>-hotword-labels-20261102 plus views.

ts_asr_hotwords@v1-20261102 (eval set ts-asr-hotwords@v1-20261102) was built from hotword labels of every transcript
in the records of ts-asr-benchmark@v12-20261022 and ts-asr-benchmark-en@v1-20261031: the target transcript and the
other speakers' transcripts (synthetic records: metadata.interferers[*].utts[*].text; real records:
metadata.window_utts of speakers other than metadata.target_speaker). Labels came from label_hotwords.py (this
directory) with Qwen3.8-27B, one text per request plus a review pass. Each version copies its source's records
unchanged except metadata.hotword_labels = {"target": LABEL or null, "others": [LABEL, ...]} with
LABEL = {"text", "hotwords", "extracted", "review"}; audio indexes stay the source's. These versions are label
carriers only: eval sets keep pinning the source versions.

    python scripts/ts_hotwords/register_eval_hotword_labels.py --root /workspace/data \
        --catalog /workspace/data/registry/catalog --labels eval-hotwords.jsonl eval-hotwords-real.jsonl \
        --output catalog/ts_benchmark_hotword_labels.yaml --views views/ts_benchmark_hotword_labels.yaml \
        --record /workspace/data/migration/register-ts-benchmark-hotword-labels-20261102
"""

import argparse
import ast
import copy
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact, verify_artifact_file
from audio_data_contract.declarations import write_declarations

DATE = "20261102"
SOURCES = [("ts_asr_benchmark", "v4-20261022"), ("ts_asr_farfield", "v2-20261022"), ("ts_asr_handover", "v2-20261022"),
           ("ts_asr_nearfar", "v3-20261022"), ("ts_asr_nearshort", "v3-20261022"), ("ts_asr_noise", "v2-20261022"),
           ("ts_asr_real", "v4-20261022"), ("ts_asr_shortseg", "v2-20261022"),
           ("ts_asr_benchmark", "en-v1-20261031"), ("ts_asr_farfield", "en-v1-20261031"),
           ("ts_asr_handover", "en-v1-20261031"), ("ts_asr_nearshort", "en-v1-20261031"),
           ("ts_asr_noise", "en-v1-20261031"), ("ts_asr_real", "en-v2-20261031"), ("ts_asr_shortseg", "en-v1-20261031")]
PROMPT = "amphiondata src/amphiondata/llm/prompts.py PROMPTS['extract_hotword'] at 64fc16e2"


def new_version(version):
    return re.sub(r"-\d{8}$", f"-hotword-labels-{DATE}", version)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def other_texts(record):
    """Same texts build_eval_set used for ts_asr_hotwords@v1-20261102."""
    meta = record.get("metadata") or {}
    texts = [u.get("text") or "" for i in meta.get("interferers") or [] for u in i.get("utts", [])]
    window = meta.get("window_utts") or []
    if isinstance(window, str):
        window = ast.literal_eval(window)
    target = meta.get("target_speaker")
    texts += [u.get("text") or "" for u in window if u.get("speaker") != target]
    return [t.strip() for t in texts if t and t.strip()]


def load_labels(paths):
    labels, inputs = {}, []
    for path in paths:
        inputs.append({"file": Path(path).name, "sha256": sha256(path)})
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                labels[row["text"].strip()] = {k: row[k] for k in ("text", "hotwords", "extracted", "review")}
    return labels, inputs


def write_version(dataset, version, labels, catalog, roots, root, used):
    spec = catalog.get(dataset, version)
    source = spec.to_dict()
    target_version = new_version(version)
    out_dir = root / "datasets" / dataset / "versions" / target_version
    if out_dir.exists():
        raise SystemExit(f"{out_dir} exists; versions are immutable")
    out_dir.mkdir(parents=True)
    by_name = {a["name"]: a for a in source["artifacts"]}
    artifacts, splits, facts, kept_names = [], {}, Counter(), set()
    for split, entry in source["splits"].items():
        roles = entry["artifacts"]
        if set(roles) - {"records", "audio_index"} or len(roles.get("records", [])) != 1:
            raise SystemExit(f"{dataset}@{version}:{split}: unexpected roles {roles}")
        name = roles["records"][0]
        path = resolve_artifact(catalog, dataset, version, name, roots)
        verify_artifact_file(spec.artifact(name), path)
        relative = f"datasets/{dataset}/versions/{target_version}/records/{path.name}"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with gzip.open(path, "rt", encoding="utf-8") as reader, open(temporary, "wb") as raw, \
                gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as writer:
            for line in reader:
                record = json.loads(line)
                target = (record.get("target") or "").strip()
                texts = ([target] if target else []) + other_texts(record)
                missing = [t for t in texts if t not in labels]
                if missing:
                    raise SystemExit(f"{dataset}@{version}:{split}: unlabelled text {missing[0][:40]!r}")
                used.update(texts)
                record.setdefault("metadata", {})["hotword_labels"] = {
                    "target": labels[target] if target else None, "others": [labels[t] for t in other_texts(record)]}
                facts["records"] += 1
                facts["records with target hotwords"] += bool(target and labels[target]["hotwords"])
                facts["labelled texts"] += len(texts)
                writer.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
        temporary.replace(destination)
        with gzip.open(destination, "rt", encoding="utf-8") as stream:  # full read-back: the gzip CRC catches lost writes
            count = sum(1 for _ in stream)
        if count != by_name[name]["metadata"]["record_count"]:
            raise SystemExit(f"{dataset}@{version}:{split}: wrote {count} records, source has {by_name[name]['metadata']['record_count']}")
        artifacts.append({**{k: v for k, v in by_name[name].items() if k not in ("relative_path", "expected_bytes", "sha256")},
                          "root_alias": "aidc_data", "relative_path": relative,
                          "expected_bytes": destination.stat().st_size, "sha256": sha256(destination)})
        for index in roles.get("audio_index", []):
            if index not in kept_names:
                artifacts.append(copy.deepcopy(by_name[index]))
                kept_names.add(index)
        splits[split] = copy.deepcopy(entry)
    return {
        "schema_version": source["schema_version"], "dataset_id": dataset, "version": target_version,
        "languages": list(source["languages"]), "tasks": list(source["tasks"]), "aliases": [],
        "artifacts": artifacts, "splits": splits,
        "recipe_parameters": {"adds": ["metadata.hotword_labels"], "records": "unchanged otherwise"},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{version}",
            "description": (
                f"{dataset}@{version} 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels："
                "target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 "
                "metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。"
                "这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，"
                "音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py。"),
            "facts": dict(facts),
        },
    }, facts


def view(dataset, version, facts, inputs):
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/hotword-labels", "version": new_version(version),
        "source": {"dataset_id": dataset, "version": version},
        "result": {"dataset_id": dataset, "version": new_version(version)},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "hotword-labels", "version": f"v1-{DATE}", "kind": "annotate", "writes": ["metadata.hotword_labels"],
            "parameters": {
                "model": "Qwen3.8-27B", "server": "vLLM 0.18, temperature 0, thinking off", "prompt": PROMPT,
                "texts_per_request": 1, "review_pass": True,
                "verbatim_filter": "word occurs in the labelled text and has at least two non-space characters",
                "texts": "target transcript; synthetic metadata.interferers[*].utts[*].text; real metadata.window_utts "
                         "of speakers other than metadata.target_speaker",
                "tool": "scripts/ts_hotwords/label_hotwords.py", "label_inputs": inputs,
                "records": facts["records"],
            }}],
        "provenance": {"registered_at": "2026-11-03"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--labels", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    labels, inputs = load_labels(args.labels)
    declarations, views, record, used = [], [], {}, set()
    for dataset, version in SOURCES:
        entry, facts = write_version(dataset, version, labels, catalog, roots, args.root, used)
        declarations.append(entry)
        views.append(view(dataset, version, facts, inputs))
        record[f"{dataset}@{version}"] = dict(facts)
        print(dataset, version, json.dumps(dict(facts), ensure_ascii=False), flush=True)
    unused = sorted(set(labels) - used)
    write_declarations(args.output, declarations)
    write_declarations(args.views, views)
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "facts.json").write_text(json.dumps(
        {"inputs": inputs, "facts": record, "labels": len(labels), "labels_not_in_sources": unused},
        ensure_ascii=False, indent=1) + "\n")
    print("labels not in any source record:", len(unused))


if __name__ == "__main__":
    main()
