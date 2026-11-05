#!/usr/bin/env python3
"""Register the hotword labels of the TS scene-pool utterances as <source>@hotwords-v1-20261102 versions plus views.

The TS + hotword training round labelled every utterance used as target or interferer speech in the TS scene pools
(open-audio-llm recipe train-data-v7set30): Qwen3.8-27B with label_hotwords.py (this directory), 12 texts per request,
no review pass, a word kept only if it occurs verbatim in the labelled text and has at least two non-space
characters; CV-en and MagicData utterances already in hw_sft@hw-20261014 reuse those labels. Each version keeps the
labelled utterances of its parent (punctuated text unchanged) and writes
- hotwords (Lhotse custom.hotwords): the labelled words as written in the row's text (Chinese: substring; English:
  whole word, any case, a possessive 's still counts); a word the row's text does not contain is dropped and counted;
- metadata.hotword_labeling (custom.hotword_labeling): labeller, the text it saw and its raw extraction.
Recordings stay the parent's; no audio is copied. Every written file is read back for counts, bytes and sha256.

    python scripts/ts_hotwords/register_hotwords.py --root /workspace/data --catalog /workspace/data/registry/catalog \
        --labels qwen=train-hotwords.jsonl qwen=train-hotwords-csd.jsonl hw_sft=train-hotwords-hwsft.jsonl \
        --output catalog/hotwords_v1_20261102.yaml --views views/hotwords_v1_20261102.yaml \
        --record /workspace/data/migration/register-hotwords-v1-20261102
"""

import argparse
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

VERSION = "hotwords-v1-20261102"
LABELERS = {"qwen": "qwen3.8-27b", "hw_sft": "hw_sft@hw-20261014"}
# label-id prefix -> source dataset, parent version, parent supervision artifacts, (recordings dataset version,
# recording artifacts); magicdata@punc-written-v1-20261102 declares supervisions only, its rows are legacy's.
SOURCES = {
    "aishell2": ("aishell2", "train-punc-v1-20261102", ["train_supervisions_punc_0"], (None, ["train_rec_0"])),
    "kespeech": ("kespeech", "train-punc-v1-20261102", ["train_supervisions_punc_0", "train_supervisions_punc_1"],
                 (None, ["train_rec_0", "train_rec_1"])),
    "magicdata": ("magicdata", "punc-written-v1-20261102", ["train_supervisions_punc_0"],
                  ("legacy-20260804", ["train_rec_0"])),
    "common_voice_en": ("common_voice_en", "train-punc-v1-20261102", ["train_supervisions_punc_0"], (None, ["train_rec_0"])),
    "librispeech": ("librispeech", "train-punc-v1-20261102",
                    ["train_supervisions_punc_0", "train_supervisions_punc_1", "train_supervisions_punc_2"],
                    (None, ["train_rec_0", "train_rec_1", "train_rec_2"])),
    "cs_dialogue_en": ("cs_dialogue_en", "legacy-20260804", ["train_sup_0"], (None, ["train_rec_0"])),
}
ENGLISH = {"common_voice_en", "librispeech", "cs_dialogue_en"}
PROMPT = "amphiondata src/amphiondata/llm/prompts.py PROMPTS['extract_hotword'] at 64fc16e2"


def said_in(word, text, english):
    """The word as written in the text, or None."""
    if not english:
        return word if word in text else None
    # A possessive 's or a trailing ' (Ahuja's, Filipinos') still counts as the word; "don" in "don't" does not.
    found = re.search(rf"(?<![\w']){re.escape(word)}(?!\w)(?!'(?!s\b)\w)", text, re.IGNORECASE)
    return found.group(0) if found else None


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def load_labels(specs):
    labels, inputs = {}, []
    for spec in specs:
        kind, path = spec.split("=", 1)
        inputs.append({"labeler": LABELERS[kind], "file": Path(path).name, "sha256": sha256(path)})
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["id"] in labels:
                    raise SystemExit(f"duplicate label id {row['id']}")
                labels[row["id"]] = (row, LABELERS[kind])
    return labels, inputs


def labeling(row, labeler):
    info = {"labeler": labeler, "text": row["text"]}
    if labeler == LABELERS["qwen"]:
        info["extracted"] = row["extracted"]
    return info


def write_version(prefix, labels, catalog, roots, root):
    dataset, parent, sup_names, (rec_version, rec_names) = SOURCES[prefix]
    spec = catalog.get(dataset, parent)
    mine = {k.split(":", 1)[1]: v for k, v in labels.items() if k.split(":", 1)[0] == prefix}
    english = prefix in ENGLISH
    out_dir = root / "datasets" / dataset / "versions" / VERSION
    if out_dir.exists():
        raise SystemExit(f"{out_dir} exists; versions are immutable")
    out_dir.mkdir(parents=True)
    facts, seen, seconds, artifacts = Counter(labels=len(mine)), set(), 0.0, []
    for i, name in enumerate(sup_names):
        source = resolve_artifact(catalog, dataset, parent, name, roots)
        verify_artifact_file(spec.artifact(name), source)
        relative = f"datasets/{dataset}/versions/{VERSION}/{source.name.removesuffix('.jsonl.gz')}_hotwords.jsonl.gz"
        destination = root / relative
        temporary = destination.with_name(destination.name + ".tmp")
        with gzip.open(source, "rt", encoding="utf-8") as reader, open(temporary, "wb") as raw, \
                gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as writer:
            for line in reader:
                row = json.loads(line)
                hit = mine.get(row["id"])
                if hit is None:
                    continue
                if row["id"] in seen:
                    raise SystemExit(f"{dataset}: duplicate supervision id {row['id']}")
                seen.add(row["id"])
                label, labeler = hit
                words = [said_in(w, row["text"], english) for w in label["hotwords"]]
                kept = list(dict.fromkeys(w for w in words if w))
                facts["words"] += len(words)
                facts["words dropped (not in the row text)"] += words.count(None)
                facts["rows"] += 1
                facts["rows with hotwords"] += bool(kept)
                facts[f"rows labelled by {labeler}"] += 1
                seconds += float(row["duration"])
                row["custom"] = {**(row.get("custom") or {}), "hotwords": kept,
                                 "hotword_labeling": labeling(label, labeler)}
                writer.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        temporary.replace(destination)
        with gzip.open(destination, "rt", encoding="utf-8") as stream:  # full read-back: the gzip CRC catches lost writes
            count = sum(1 for _ in stream)
        artifacts.append({"name": f"train_supervisions_hotwords_{i}", "kind": "lhotse-supervisions",
                          "root_alias": "aidc_data", "relative_path": relative,
                          "expected_bytes": destination.stat().st_size, "sha256": sha256(destination),
                          "metadata": {"record_count": count, "punctuated": dataset != "cs_dialogue_en"}})
    facts["labels without a parent row"] = len(mine) - len(seen)
    if facts["labels without a parent row"] or sum(a["metadata"]["record_count"] for a in artifacts) != facts["rows"]:
        raise SystemExit(f"{dataset}: count mismatch {dict(facts)}")
    rec_spec = catalog.get(dataset, rec_version) if rec_version else spec
    recordings = [copy.deepcopy(next(a for a in rec_spec.to_dict()["artifacts"] if a["name"] == n)) for n in rec_names]
    return spec, facts, seconds / 3600, recordings, artifacts


def declaration(prefix, spec, facts, hours, recordings, supervisions):
    dataset, parent, _, (rec_version, _) = SOURCES[prefix]
    source = spec.to_dict()
    reused = facts.get(f"rows labelled by {LABELERS['hw_sft']}", 0)
    return {
        "schema_version": source["schema_version"], "dataset_id": dataset, "version": VERSION,
        "languages": list(source["languages"]), "tasks": ["asr_hotwords"], "aliases": [],
        "artifacts": recordings + supervisions,
        "splits": {"train": {
            "artifacts": {"recordings": [r["name"] for r in recordings], "supervisions": [s["name"] for s in supervisions]},
            "statistics": {"records": facts["rows"], "records_with_hotwords": facts["rows with hotwords"],
                           "duration_hours": round(hours, 4), "duration_basis": "sum of supervision durations"},
        }},
        "recipe_parameters": {"adds": ["custom.hotwords", "custom.hotword_labeling"], "rows": "labelled utterances only"},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{parent}",
            "description": (
                f"{dataset}@{parent} 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，"
                f"带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（{'英文按整词匹配、不分大小写，所有格算同一个词' if prefix in ENGLISH else '中文按子串匹配'}；"
                "本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。"
                f"{facts['rows']} 句里 {facts['rows with hotwords']} 句有热词"
                + (f"，其中 {reused} 句复用 hw_sft@hw-20261014 的已有标注" if reused else "")
                + "。只含标过的句子，文本与父版本相同；录音沿用"
                + (f" {dataset}@{rec_version}" if rec_version else "父版本")
                + "，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py。"),
            "facts": dict(facts),
        },
    }


def view(prefix, facts, inputs):
    dataset, parent, _, _ = SOURCES[prefix]
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/hotwords", "version": VERSION,
        "source": {"dataset_id": dataset, "version": parent},
        "result": {"dataset_id": dataset, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [
            {"name": "ts-pool-utterances", "version": "train-data-v7set30", "kind": "filter", "writes": ["$membership"],
             "parameters": {"kept": "utterances used as target or interferer speech in the TS scene pools of open-audio-llm "
                                    "recipe train-data-v7set30 (ts_scene_pool *-punchw-20261102 / *-punchw2-20261102)",
                            "rows": facts["rows"]}},
            {"name": "hotwords", "version": "v1-20261102", "kind": "annotate",
             "writes": ["hotwords", "metadata.hotword_labeling"],
             "parameters": {
                 "model": "Qwen3.8-27B", "server": "vLLM 0.18, temperature 0, thinking off", "prompt": PROMPT,
                 "texts_per_request": 12, "review_pass": False,
                 "verbatim_filter": "word occurs in the labelled text and has at least two non-space characters",
                 "surface_form": "word as written in the row text; English whole word, case-insensitive, possessive 's allowed",
                 "reused_labels": "hw_sft@hw-20261014 for utterances it already labels (metadata.hotword_labeling.labeler)",
                 "tool": "scripts/ts_hotwords/label_hotwords.py", "label_inputs": inputs,
                 "words_dropped_not_in_text": facts["words dropped (not in the row text)"],
             }},
        ],
        "provenance": {"registered_at": "2026-11-03"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--labels", nargs="+", required=True, help="KIND=PATH, KIND in qwen, hw_sft")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    labels, inputs = load_labels(args.labels)
    prefixes = sorted({k.split(":", 1)[0] for k in labels})
    if set(prefixes) != set(SOURCES):
        raise SystemExit(f"label prefixes {prefixes} != {sorted(SOURCES)}")
    declarations, views, record = [], [], {}
    for prefix in SOURCES:
        spec, facts, hours, recordings, supervisions = write_version(prefix, labels, catalog, roots, args.root)
        declarations.append(declaration(prefix, spec, facts, hours, recordings, supervisions))
        views.append(view(prefix, facts, inputs))
        record[prefix] = dict(facts)
        print(prefix, json.dumps(dict(facts), ensure_ascii=False), flush=True)
    write_declarations(args.output, declarations)
    write_declarations(args.views, views)
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "facts.json").write_text(json.dumps({"inputs": inputs, "facts": record}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
