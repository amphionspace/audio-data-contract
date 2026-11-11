#!/usr/bin/env python3
"""Add sound-alike distractors to the Spanish ASR hotword training rows (CPU only).

For every row of common_voice_es / mls_es @es-train-v1-20261108 that has hotwords
(``custom.hotwords``, clean pass), writes an ``asr_hotwords`` AudioRecord whose
``metadata.confusable_hotwords`` holds up to ``confusables_per_word`` real
Spanish hotwords that sound like each of the row's hotwords. The training data
loader puts them into the hotword list as distractors (``hotword_confusable_prob``).
Audio is not copied: the audio index points at the legacy source files.

Confusables are mined exactly as for hotword_bench@es-v1-20261111
(``build_es.mine``: Spanish reading key, edit distance, closest first), from a
vocabulary built from the training hotword labels only, minus every gold word
of the benchmark's splits. A candidate is dropped when it is a spelling
variant of one of the row's hotwords (same reading key once word breaks are
ignored and ñ / ny / gn, y / i are not told apart: "Sara"/"Sarah",
"Cataluña"/"Catalunya", "Monte Verde"/"Monteverde") or when it occurs in the row's text: a list word
that matches the audio is not a negative.

Each dataset is checked (``qc`` in the recipe); the script exits non-zero
without registering when one fails. It appends the declarations to this
repository's ``catalog/es_train_v1.yaml``.

    python scripts/hotword_bench/build_es_train_confusables.py --workers 64
    python scripts/hotword_bench/build_es_train_confusables.py --out <scratch dir>
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import REPO, ROOT_ALIAS, cjk_join
from build_es import mine, reading_key, strip_accents, vocabulary
from common import (
    DATA_ROOT,
    DATASETS,
    contains,
    iter_jsonl,
    normalize,
    sha256_file,
    write_jsonl,
)

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent
CATALOG_FILE = REPO / "catalog" / "es_train_v1.yaml"
SAMPLES = 20


def variant_key(word):
    """Reading key without word breaks, ñ / ny / gn as n and y as i: equal keys are spellings of one word
    ("Catalunya"/"Cataluña", "espana"/"España", "vizcayno"/"vizcaíno"), not sound-alikes."""
    return re.sub(r"ny|gn|N", "n", reading_key(word).replace(" ", "")).replace("y", "i")


def heldout_forms(recipe):
    gold = set()
    for path in recipe["heldout"]["records"]:
        for row in iter_jsonl(DATASETS / path):
            gold.update(row["hotwords"])
    return {normalize(w) for w in gold} | {strip_accents(normalize(w)) for w in gold}


def is_heldout(word, heldout):
    return normalize(word) in heldout or strip_accents(normalize(word)) in heldout


def label_counts(recipe):
    """How many training rows carry each hotword label (normalized)."""
    counts = Counter()
    for path in recipe["confusables"]["vocabulary"]:
        for row in iter_jsonl(DATASETS / path):
            counts.update(normalize(w) for w in (row.get("custom") or {}).get("hotwords") or [] if normalize(w))
    return counts


def load_rows(spec):
    recordings = {r["id"]: r for r in iter_jsonl(DATASETS / spec["recordings"])}
    rows = []
    for sup in iter_jsonl(DATASETS / spec["supervisions"]):
        custom = sup.get("custom") or {}
        if custom.get("hotwords") and (custom.get("clean") or {}).get("pass") is True:
            rows.append((sup, recordings[sup["recording_id"]]))
    return rows


def pick(hotwords, target, mined, per_word, language, drops):
    own = {variant_key(h) for h in hotwords}
    chosen, kept = [], set()
    for word in hotwords:
        taken = 0
        for candidate in mined.get(word, []):
            if taken == per_word:
                break
            word_ = candidate["confusable"]
            if variant_key(word_) in own:
                drops["spelling_variant"] += 1
                if len(drops["spelling_variant_examples"]) < 30:
                    drops["spelling_variant_examples"].append([word, word_])
                continue
            if contains(target, word_, language):
                drops["in_text"] += 1
                continue
            if variant_key(word_) in kept:  # "Luis Rodríguez" / "Luis Rodriguez" for one word: keep the first
                continue
            kept.add(variant_key(word_))
            chosen.append(word_)
            taken += 1
    return chosen


def audio_index_row(sup, recording):
    (source,) = recording["sources"]
    path = Path(source["source"])
    if source["type"] != "file" or not path.is_relative_to(DATA_ROOT) or len(recording["channel_ids"]) != 1:
        raise ValueError(f"{recording['id']}: expected one mono file under {DATA_ROOT}")
    if sup["start"] < 0 or sup["start"] + sup["duration"] > recording["duration"] + 0.01:
        raise ValueError(f"{sup['id']}: supervision outside its recording")
    return {"cut_id": sup["id"], "root_alias": ROOT_ALIAS, "relative_path": str(path.relative_to(DATA_ROOT)),
            "sample_rate": recording["sampling_rate"], "channels": 1, "num_frames": recording["num_samples"],
            "duration": recording["duration"]}


def build(dataset_id, spec, recipe, mined):
    language, version = recipe["language"], recipe["version"]
    records, index = [], {}
    drops = {"spelling_variant": 0, "in_text": 0, "spelling_variant_examples": []}
    for sup, recording in load_rows(spec):
        hotwords = list(sup["custom"]["hotwords"])
        confusables = pick(hotwords, sup["text"], mined, recipe["confusables_per_word"], language, drops)
        index[sup["id"]] = audio_index_row(sup, recording)
        metadata = {"confusable_hotwords": confusables}
        if sup.get("speaker"):
            metadata["speaker"] = sup["speaker"]
        records.append(AudioRecord.from_dict({
            "schema_version": "audio-record/1.0", "id": sup["id"], "task": "asr_hotwords",
            "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                "dataset_id": dataset_id, "version": version, "split": "train", "cut_id": sup["id"],
                "start": sup["start"], "duration": sup["duration"]}}],
            "target": sup["text"], "language": language, "hotwords": hotwords, "labels": {}, "metadata": metadata,
        }).to_dict())
    return records, index, drops


def quality_check(dataset_id, spec, recipe, records, mined, heldout, bench_confusables):
    """Gates recomputed from the written records; returns (failures, report)."""
    gates, language = recipe["qc"], recipe["language"]
    reading = {w: {c["confusable"]: c["reading_distance"] for c in found} for w, found in mined.items()}
    counts, distances = Counter(), Counter()
    forbidden = Counter({kind: 0 for kind in ("heldout_gold", "own_hotword", "case_or_accent_variant",
                                              "spelling_variant", "in_text", "duplicate", "over_cap")})
    pairs_in_bench = 0
    words = 0
    for r in records:
        confusables, hotwords = r["metadata"]["confusable_hotwords"], r["hotwords"]
        words += len(hotwords)
        counts[len(confusables)] += 1
        own_norm = {normalize(h) for h in hotwords}
        own_plain = {strip_accents(normalize(h)) for h in hotwords}
        own_variant = {variant_key(h) for h in hotwords}
        for c in confusables:
            forbidden["heldout_gold"] += is_heldout(c, heldout)
            forbidden["own_hotword"] += normalize(c) in own_norm
            forbidden["case_or_accent_variant"] += strip_accents(normalize(c)) in own_plain
            forbidden["spelling_variant"] += variant_key(c) in own_variant
            forbidden["in_text"] += contains(r["target"], c, language)
            pairs_in_bench += c in bench_confusables
            distances[min((reading[h].get(c, 99) for h in hotwords), default=99)] += 1
        forbidden["duplicate"] += len(confusables) - len({variant_key(c) for c in confusables})
        forbidden["over_cap"] += len(confusables) > recipe["confusables_per_word"] * len(hotwords)
    with_any = sum(n for k, n in counts.items() if k)
    total = sum(counts.values())
    report = {
        "records": len(records),
        "duration_hours": round(sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600, 2),
        "hotwords": words,
        "records_with_confusables": with_any,
        "records_with_confusables_fraction": round(with_any / max(len(records), 1), 4),
        "confusables": sum(k * n for k, n in counts.items()),
        "mean_confusables_when_any": round(sum(k * n for k, n in counts.items()) / max(with_any, 1), 3),
        "confusables_per_hotword": round(sum(k * n for k, n in counts.items()) / max(words, 1), 3),
        "confusables_per_record": {str(k): counts[k] for k in sorted(counts)},
        "reading_distance": {str(k): distances[k] for k in sorted(distances)},
        "forbidden": dict(forbidden),
        "confusables_also_bench_distractors": pairs_in_bench,
    }
    low, high = gates["confusables_per_hotword_range"]
    checks = [
        (len(records) == spec["rows_with_hotwords"] == total,
         f"records {len(records)} != parent rows_with_hotwords {spec['rows_with_hotwords']}"),
        (report["records_with_confusables_fraction"] >= gates["min_records_with_confusables"],
         f"records with confusables {report['records_with_confusables_fraction']} < {gates['min_records_with_confusables']}"),
        (low <= report["confusables_per_hotword"] <= high,
         f"confusables per hotword {report['confusables_per_hotword']} outside [{low}, {high}]"),
        *((n <= gates["max_forbidden"], f"{n} confusables are {kind}") for kind, n in forbidden.items()),
    ]
    return [f"{dataset_id}: {message}" for ok, message in checks if not ok], report


def bench_distractors(recipe):
    words = set()
    for path in recipe["heldout"]["records"]:
        for row in iter_jsonl(DATASETS / path):
            kinds = row["metadata"]["distractor_kinds"]
            words.update(w for w, kind in kinds.items() if kind == "confusable")
    return words


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-es-train-hwconf-v1.yaml")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--out", type=Path, help="write here instead of the version directories (no registration)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    version = recipe["version"]
    targets = {d: (args.out / d if args.out else DATASETS / d / "versions" / version) for d in recipe["sources"]}
    for path in targets.values():
        if path.exists():
            raise FileExistsError(f"refusing to replace: {path}")

    heldout = heldout_forms(recipe)
    seen = label_counts(recipe)
    words = [w for w in vocabulary(recipe, {})
             if not is_heldout(w, heldout) and seen[normalize(w)] >= recipe["confusables"]["min_candidate_count"]]
    queries = sorted({h for spec in recipe["sources"].values() for sup, _ in load_rows(spec)
                      for h in sup["custom"]["hotwords"]})
    mined = mine(words, queries, recipe["confusables"], recipe["seed"], args.workers)
    print(f"confusables: vocabulary {len(words)} (heldout forms {len(heldout)}), queries {len(queries)}, "
          f"with any {sum(1 for v in mined.values() if v)}", file=sys.stderr)
    bench = bench_distractors(recipe)

    failures, reports, outputs = [], {}, {}
    for dataset_id, spec in recipe["sources"].items():
        records, index, drops = build(dataset_id, spec, recipe, mined)
        fails, report = quality_check(dataset_id, spec, recipe, records, mined, heldout, bench)
        report["dropped_candidates"] = drops
        with_any = [r for r in records if r["metadata"]["confusable_hotwords"]]
        report["samples"] = [{"id": r["id"], "text": r["target"], "hotwords": r["hotwords"],
                              "confusable_hotwords": r["metadata"]["confusable_hotwords"]}
                             for r in random.Random(f"{recipe['seed']}:{dataset_id}").sample(with_any, SAMPLES)]
        failures += fails
        reports[dataset_id] = report
        outputs[dataset_id] = (records, index)

    print(yaml.safe_dump({k: {x: y for x, y in v.items() if x not in {"samples", "dropped_candidates"}}
                          for k, v in reports.items()},
                         allow_unicode=True, sort_keys=False), file=sys.stderr)
    specs = []
    for dataset_id, (records, index) in outputs.items():
        out = targets[dataset_id]
        used = sorted({h for r in records for h in r["hotwords"]})
        write_jsonl(out / "records" / "train.jsonl.gz", records)
        write_jsonl(out / "audio_index" / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
        write_jsonl(out / "mined" / "confusables.jsonl.gz",
                    [{"term": w, "reading_key": reading_key(w), "candidates": mined[w]} for w in used])
        (out / "qc.yaml").write_text(yaml.safe_dump(
            {"passed": not failures, "failures": [f for f in failures if f.startswith(f"{dataset_id}:")],
             **reports[dataset_id]}, allow_unicode=True, sort_keys=False))
        report = reports[dataset_id]
        (out / "state.json").write_text(json.dumps({
            "schema_version": "dataset-state/1.0", "dataset_id": dataset_id, "version": version,
            "state": "prepared", "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": None, "metadata": {"owner": "mingdong", "records": report["records"],
                                        "with_confusables": report["records_with_confusables"]},
        }, indent=1, ensure_ascii=False) + "\n")
        if not args.out:
            specs.append(declaration(dataset_id, recipe, out, report, len(words)))
    if failures:
        sys.exit("QC failed, not registered:\n  " + "\n  ".join(failures))
    if specs:
        register(specs)


def declaration(dataset_id, recipe, out, report, vocabulary_size):
    version, spec = recipe["version"], recipe["sources"][dataset_id]
    parent = f"{dataset_id}@{spec['parent']}"

    def artifact(name, kind, path, metadata=None):
        row = {"name": name, "kind": kind, "root_alias": ROOT_ALIAS, "relative_path": str(path.relative_to(DATA_ROOT)),
               "expected_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        return {**row, "metadata": metadata} if metadata else row

    statistics = {key: report[key] for key in ("records", "duration_hours", "hotwords", "records_with_confusables",
                                                "records_with_confusables_fraction", "confusables",
                                                "mean_confusables_when_any", "confusables_per_hotword",
                                                "confusables_per_record")}
    statistics["duration_basis"] = "sum of supervision durations"
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": [recipe["language"]], "tasks": ["asr_hotwords"], "aliases": [], "derived_from": parent,
        "artifacts": [
            artifact("preparation_state", "dataset-state", out / "state.json"),
            artifact("train", "audio-records", out / "records" / "train.jsonl.gz", {"record_count": report["records"]}),
            artifact("audio_index", "audio-index", out / "audio_index" / "audio-index.jsonl.gz",
                     {"record_count": report["records"], "audio": f"legacy source files of {dataset_id}@legacy, not copied"}),
            artifact("confusables", "jsonl-metadata", out / "mined" / "confusables.jsonl.gz"),
            artifact("qc", "quality-report", out / "qc.yaml", {"passed": True}),
        ],
        "splits": {"train": {
            "artifacts": {"records": ["train"], "audio_index": ["audio_index"], "preparation_state": ["preparation_state"]},
            "statistics": statistics, "provenance": {"preparation_status": "prepared"},
        }},
        "recipe_parameters": {
            "confusables_per_word": recipe["confusables_per_word"],
            "reading_key": "scripts/hotword_bench/build_es.py reading_key (seseo, yeísmo, b/v, silent h, c/qu/k, g/j)",
            "max_reading_distance": recipe["confusables"]["max_distance"],
            "min_key_length": recipe["confusables"]["min_key_length"],
            "vocabulary": f"{vocabulary_size} training hotword labels minus every gold word of {recipe['heldout']['dataset']}",
        },
        "provenance": {
            "preparation_status": "prepared", "owner": "mingdong",
            "description": cjk_join(f"""{parent} 里有热词的行（{report['records']:,} 条，全部 clean 通过）的热词训练版本：每行一条 asr_hotwords 记录，
                文本、热词与父版本相同，metadata.confusable_hotwords 为读音相近的真实西语热词，
                训练时按 hotword_confusable_prob 作为干扰词放进列表（同 police_terms_single_train@hotwords-confusable-v1-20261102）。
                近音词检索复用评测集 hotword_bench@es-v1-20261111 的西语读音键（拉美读法：seseo、yeísmo、b/v、h 不发音等）与编辑距离，
                每个热词最多 {recipe['confusables_per_word']} 个，读音最近的优先；词库只用 CV es / MLS es 训练集的热词标注（{vocabulary_size:,} 个），
                去掉了评测集三个 split 的全部正确词。剔除两类候选：与本条热词只是同一个词不同写法的（读音键忽略空格、ñ/ny/gn 与 n、y 与 i 不区分后相同，
                如 Sara/Sarah、Cataluña/Catalunya、España/espana、Monte Verde/Monteverde，当负例会教模型拒绝与录音一致的写法），以及出现在本条文本里的。
                {report['records_with_confusables']:,} 条（{report['records_with_confusables_fraction']:.1%}）有近音词，平均每条
                {report['mean_confusables_when_any']} 个；近音词与评测正确词重叠 0。录音不复制，audio_index 指向 legacy 源文件。
                检索结果见 mined/confusables.jsonl.gz，质检与 20 条样例见 qc.yaml。"""),
            "sources": [parent, f"{recipe['heldout']['dataset']} (gold words excluded from the vocabulary)"],
            "scripts": ["scripts/hotword_bench/build_es_train_confusables.py",
                        "scripts/hotword_bench/recipe-es-train-hwconf-v1.yaml"],
            "limitations": cjk_join("""近音词按拼写推出的读音键检索，不是声学相似度，也不覆盖英文专名的英语读法；
                词库只收标注里出现至少两次的词，仍有重复出现的 OCR / 拼写错误词（如 Ingalaterra、jesuchristo），
                也有同一人名的历史写法（Moctezuma/Montezuma），按规则分不出来；
                热词是 LLM 抽取、未经人工核对。"""),
        },
    }


def register(specs):
    text = CATALOG_FILE.read_text(encoding="utf-8")
    existing = yaml.safe_load(text)
    for spec in specs:
        if any(r["dataset_id"] == spec["dataset_id"] and r["version"] == spec["version"] for r in existing):
            raise FileExistsError(f"version already registered: {spec['dataset_id']}@{spec['version']}")
    validate_catalog([*load_catalog(REPO / "catalog"), *(DatasetSpec.from_dict(s) for s in specs)])
    # Appended, so the hand-written entries above stay byte for byte.
    addition = yaml.safe_dump(specs, allow_unicode=True, sort_keys=False, width=512)
    CATALOG_FILE.write_text(text.rstrip("\n") + "\n" + addition, encoding="utf-8")
    for spec in specs:
        print("registered", spec["dataset_id"], spec["version"], file=sys.stderr)


if __name__ == "__main__":
    main()
