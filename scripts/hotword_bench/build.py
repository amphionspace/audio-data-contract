#!/usr/bin/env python3
"""Register the hotword benchmark as AudioRecords with fixed biasing lists.

Inputs (in the version's source directory): ``items/<split>.jsonl`` from
sources.py and gigaspeech.py, the real_zh candidates and the LLM outputs of
mine.py. Each record has ``hotwords`` (gold words spoken in it),
``metadata.bias_lists`` (condition -> list, in the order it is sent) and
``metadata.distractor_kinds`` (word -> confusable / random). Conditions:

- ``gold``: the gold words only;
- ``k50``: gold + reviewed confusables of each gold word + random words of the
  same split's gold pool, ``list_size`` in total (Chinese; cv_en has no confusables);
- ``k50_no_gold``: the same distractors without the gold words, refilled;
- ``official`` (AISHELL1-NE): SeACo's split-wide list, as published;
- ``n100`` / ``n1000`` (LibriSpeech): Le et al.'s lists as published, ``n100_no_gold``;
- ``l20`` / ``l50`` / ``l100`` / ``l50_no_gold`` (GigaSpeech): see gigaspeech.py.

A word is never a distractor of an utterance whose normalized reference
contains it. Utterances without gold words keep only lists without gold.
Items quarantined upstream go to the ``quarantine`` split (not scored).
``labels.train_text_overlap`` names the training set (``overlap`` in the recipe)
holding the same normalized text, or ``none``: AISHELL-1 / AISHELL-3 test texts
reappear in AISHELL-2 training transcripts, so the scorer's breakdown by this
label gives the subset a model trained on them has not read.

Audio: 16 kHz mono single-utterance files are referenced in place; segments of
long recordings and other formats are written as 16 kHz mono PCM16 WAV under
``<source>/audio/<split>/``.

    python scripts/hotword_bench/build.py --source <source dir>
    python scripts/hotword_bench/build.py --source <source dir> --smoke 20 --out <scratch dir>
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    DATA_ROOT,
    DATASETS,
    compact,
    contains,
    iter_jsonl,
    iter_manifest,
    occurrences,
    order_key,
    read_jsonl,
    sha256_file,
    write_jsonl,
)

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROOT_ALIAS = "aidc_data"
SR = 16000
SPLITS = {
    "aishell1_ne_test": ("zh", "SeACo-Paraformer 的 Test-AISHELL1-NE：AISHELL-1 测试集中含命名实体热词的 808 句，全局热词表 400 词（R1 子集 226 词）"),
    "aishell1_ne_dev": ("zh", "SeACo-Paraformer 的 Dev-AISHELL1-NE：AISHELL-1 开发集 1,334 句，全局热词表 600 词（R1 子集 371 词），用于挑选"),
    "contextasr_speech_zh": ("zh", "ContextASR-Bench Speech-Mandarin 全量：DeepSeek-R1 生成的多领域实体文本、零样本 TTS 合成；正确词为上游 entity_list 中出现在转写里的实体"),
    "real_zh": ("zh", "真实口语：SpeechIO 27 个子集与 WenetSpeech test_net / test_meeting；热词按 AmphionData EXTRACT_HOTWORD 由 LLM 抽取、另一模型家族复核，每子集按 sha256(id) 取前 N 条正例"),
    "cv_zh": ("zh", "Common Voice zh-CN 测试集，沿用已有热词标注（AmphionData amphion-data hotwords），按 sha256(id) 取前 N 条正例"),
    "aishell2": ("zh", "AISHELL-2 测试集，沿用已有热词标注，全部正例"),
    "aishell3": ("zh", "AISHELL-3 测试集，沿用已有热词标注，按 sha256(id) 取前 N 条正例"),
    "kespeech": ("zh", "KeSpeech 测试集（各地方言口音普通话），沿用已有热词标注，按 sha256(id) 取前 N 条正例"),
    "cv_en": ("en", "Common Voice en 测试集，沿用已有热词标注，按 sha256(id) 取前 N 条正例；干扰词只取随机词"),
    "gigaspeech_test": ("en", "GigaSpeech 测试集全量，按 SALMONN-2 的协议重建稀有词列表（L=20/50/100）"),
    "librispeech_test_clean": ("en", "LibriSpeech test-clean，Le et al. 2021 官方稀有词列表（N=100/1000）"),
    "librispeech_test_other": ("en", "LibriSpeech test-other，Le et al. 2021 官方稀有词列表（N=100/1000）"),
    "quarantine": (None, "不参与打分：上游质检未通过、无可用热词、两个 LLM 意见不一致或时长越界的条目，保留原因"),
}


# ---------------------------------------------------------------- real_zh ---

def real_zh_items(recipe, source, smoke):
    spec = recipe["sources"]["real_zh"]
    extracted = {r["id"]: r for r in read_jsonl(source / "mined" / "real_zh-extract.jsonl")}
    reviewed = {r["id"]: r for r in read_jsonl(source / "mined" / "real_zh-review.jsonl")}
    if not reviewed and not smoke:
        raise FileNotFoundError("real_zh needs mine.py real-zh outputs")
    by_subset = defaultdict(list)
    for item in read_jsonl(source / "candidates" / "real_zh.jsonl"):
        by_subset[item["labels"]["subset"]].append(item)
    out = []
    for subset, items in sorted(by_subset.items()):
        items.sort(key=lambda it: it["order"])
        taken = 0
        for item in items:
            if taken >= spec["positives_per_subset"]:
                break
            if item["id"] not in extracted:
                continue  # scanning stopped before this item
            verdict = reviewed.get(item["id"]) or {}
            terms = verdict.get("terms", [])
            kept = [t for t in terms if t["keep"]]
            item.pop("order", None)
            if item["quarantine"]:
                out.append(item)
                continue
            if extracted[item["id"]].get("refused") or verdict.get("refused") or (
                    extracted[item["id"]]["hotwords"] and not verdict):
                item["quarantine"] = "hosted model refused or did not review this utterance"
                out.append(item)
                continue
            if not kept:
                if extracted[item["id"]]["hotwords"]:
                    item["quarantine"] = "reviewer rejected every extracted hotword"
                    item["labels"]["rejected_terms"] = [t["term"] for t in terms]
                    out.append(item)
                continue
            item["gold"] = list(dict.fromkeys(occurrences(item["text"], [t["term"] for t in kept], "zh")))
            item["labels"]["entity_types"] = {t["term"]: t["type"] for t in kept if t["term"] in item["gold"]}
            rejected = [t["term"] for t in terms if not t["keep"]]
            if rejected:
                item["labels"]["rejected_terms"] = rejected
            out.append(item)
            taken += 1
    return out


# ------------------------------------------------------------------ lists ---

def reviewed_confusables(source, smoke):
    path = source / "mined" / "confusables-review.jsonl"
    if not path.exists():
        if smoke:
            return {}
        raise FileNotFoundError("Chinese splits need mine.py confusables + confusables-review outputs")
    kept = defaultdict(list)
    for row in read_jsonl(path):
        if row["keep"] and row["confusable"] not in kept[row["term"]]:
            kept[row["term"]].append(row["confusable"])
    return kept


def fill(rng, pool, n, banned, text, language):
    """``n`` random pool words, none in ``banned`` or in the reference (fewer if the pool runs out)."""
    chosen = []

    def take(word):
        if word not in banned and word not in chosen and not contains(text, word, language):
            chosen.append(word)

    if len(pool) > 20 * max(n, 1):  # large pool (LibriSpeech rare words): draw, do not shuffle it all
        for _ in range(50 * max(n, 1)):
            if len(chosen) >= n:
                break
            take(pool[rng.randrange(len(pool))])
    else:
        for word in rng.sample(pool, len(pool)):
            if len(chosen) >= n:
                break
            take(word)
    return chosen


def build_lists(item, pool, confusables, recipe):
    size, language, text = recipe["list_size"], item["language"], item["text"]
    gold = list(item["gold"])

    def rng(condition):
        return random.Random(order_key(recipe["seed"], item["split"], item["id"], condition))

    lists, kinds = {}, {}
    upstream = item.get("lists") or {}
    if gold:
        lists["gold"] = rng("gold").sample(gold, len(gold))
    if item["split"].startswith("librispeech"):
        lists.update(upstream)
        if gold:
            # Le et al.'s distractors can equal a reference word after normalization (``was'``)
            distractors = [w for w in upstream["n100"] if w not in gold and not contains(text, w, language)]
            extra = fill(rng("n100_no_gold"), pool, 100 - len(distractors), set(upstream["n100"]), text, language)
            lists["n100_no_gold"] = rng("n100_no_gold").sample(distractors + extra, len(distractors) + len(extra))
        return lists, {}
    if item["split"] == "gigaspeech_test":
        lists.update(upstream)
        return lists, {}
    # Chinese splits and cv_en: gold + confusables + random, then the same without gold
    alternates = []
    for word in gold:
        for alt in confusables.get(word, [])[: recipe["confusables_per_word"]]:
            if alt not in gold and alt not in alternates and not contains(text, alt, language):
                alternates.append(alt)
    room = max(0, size - len(gold))
    if len(alternates) > room:  # keep confusables of every gold word before a second one of any
        by_rank = sorted(alternates, key=lambda a: min(
            confusables.get(w, []).index(a) for w in gold if a in confusables.get(w, [])))
        alternates = by_rank[:room]
    random_words = fill(rng("k50"), pool, room - len(alternates), set(gold) | set(alternates), text, language)
    distractors = alternates + random_words
    if gold or distractors:
        lists["k50"] = rng("k50-order").sample(gold + distractors, len(gold) + len(distractors))
    if gold:
        refill = fill(rng("k50_no_gold"), pool, size - len(distractors), set(gold) | set(distractors), text, language)
        no_gold = distractors + refill
        lists["k50_no_gold"] = rng("k50_no_gold-order").sample(no_gold, len(no_gold))
        random_words += refill
    kinds.update({w: "confusable" for w in alternates})
    kinds.update({w: "random" for w in random_words})
    if "official" in upstream:
        lists["official"] = list(upstream["official"])
    return lists, kinds


# ---------------------------------------------------------------- overlap ---

def training_overlap(recipe, items):
    """(split, id) -> training source whose normalized text equals the item's reference."""
    wanted = defaultdict(dict)  # language -> compact text -> [(split, id)]
    groups = defaultdict(set)  # overlap group -> languages
    for split, rows in items.items():
        for item in rows:
            if not item["quarantine"]:
                wanted[item["language"]].setdefault(compact(item["text"], item["language"]), []).append((split, item["id"]))
                groups[group_of(split)].add(item["language"])
    found = {}

    def check(text, language, origin):
        for key in wanted[language].get(compact(text, language), []):
            found.setdefault(key, origin)

    for path in recipe["overlap"]["records"]:
        for row in iter_jsonl(DATASETS / path):
            check(row["target"], "zh" if (row.get("language") or "").startswith("zh") else "en", path)
    for group, languages in groups.items():
        for pattern in recipe["overlap"]["supervisions"].get(group, []):
            for row in iter_manifest(pattern):
                for language in languages:
                    check(row["text"], language, pattern)
    return found


def group_of(split):
    if split.startswith("aishell1_ne"):
        return "aishell1_ne"
    if split.startswith("librispeech"):
        return "librispeech"
    if split == "gigaspeech_test":
        return "gigaspeech"
    if split == "contextasr_speech_zh":
        return "contextasr"
    return split


# ------------------------------------------------------------------ audio ---

def in_place(audio):
    path = Path(audio["path"])
    if audio["start"] or abs(audio["duration"] - audio["recording_duration"]) > 0.01:
        return False
    if not path.is_relative_to(DATA_ROOT):
        return False
    info = sf.info(path)
    return info.samplerate == SR and info.channels == 1


def materialize(job):
    """Write the segments of one source file as 16 kHz mono PCM16 WAV; return index rows."""
    import soxr

    path, segments = job
    wav, rate = sf.read(path, dtype="float32", always_2d=True)
    wav = wav.mean(axis=1)
    rows = []
    for cut_id, start, duration, destination in segments:
        clip = wav[round(start * rate): round((start + duration) * rate)]
        if rate != SR:
            clip = soxr.resample(clip, rate, SR)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sf.write(destination, np.clip(clip, -1, 1), SR, subtype="PCM_16")
        rows.append(index_row(destination, cut_id))
    return rows


def index_row(path, cut_id):
    info = sf.info(path)
    if info.samplerate != SR or info.channels != 1:
        raise ValueError(f"{path}: expected 16 kHz mono, got {info.samplerate} Hz x{info.channels}")
    path = Path(path)  # a smoke run outside the data root keeps absolute paths
    relative = path.relative_to(DATA_ROOT) if path.is_relative_to(DATA_ROOT) else path
    return {"cut_id": cut_id, "root_alias": ROOT_ALIAS, "relative_path": str(relative),
            "sample_rate": SR, "channels": 1, "num_frames": info.frames,
            "duration": round(info.frames / SR, 4), "sha256": sha256_file(path)}


def build_audio(items, audio_root, workers):
    jobs, direct = defaultdict(list), []
    for item in items:
        cut_id = f"{item['split']}:{item['id']}"
        item["cut_id"] = cut_id
        if in_place(item["audio"]):
            direct.append((Path(item["audio"]["path"]), cut_id))
        else:
            destination = audio_root / item["split"] / f"{item['id']}.wav"
            jobs[item["audio"]["path"]].append((cut_id, item["audio"]["start"], item["audio"]["duration"], destination))
    with ProcessPoolExecutor(workers) as pool:
        rows = [row for batch in pool.map(materialize, jobs.items(), chunksize=4) for row in batch]
        rows += list(pool.map(index_row, *zip(*direct), chunksize=64)) if direct else []
    return {row["cut_id"]: row for row in rows}


# ------------------------------------------------------------------- main ---

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--smoke", type=int, help="first N items per split, LLM outputs optional, needs --out")
    parser.add_argument("--out", type=Path, help="write here instead of the version directory (no registration)")
    args = parser.parse_args()
    if args.smoke and not args.out:
        parser.error("--smoke needs --out")
    recipe = yaml.safe_load(args.recipe.read_text())
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    version_dir = args.out or DATASETS / dataset_id / "versions" / version
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace: {version_dir}")
    source = args.source

    items = {}
    for split in SPLITS:
        if split == "quarantine":
            continue
        rows = real_zh_items(recipe, source, args.smoke) if split == "real_zh" else read_jsonl(source / "items" / f"{split}.jsonl")
        if not rows and not args.smoke:
            raise FileNotFoundError(f"no items for {split}")
        items[split] = rows[: args.smoke] if args.smoke else rows
    confusables = reviewed_confusables(source, args.smoke)
    fbai_rare = (source / "upstream" / "fbai-is21-deep-bias" / "words" / "all_rare_words.txt")
    librispeech_pool = [w.strip() for w in fbai_rare.read_text().splitlines() if w.strip()] if fbai_rare.exists() else []

    overlap = training_overlap(recipe, items) if not args.smoke else {}
    stats = Counter()
    by_split = defaultdict(list)
    scored_items = []
    for split, rows in items.items():
        pool = librispeech_pool if split.startswith("librispeech") else sorted(
            {w for it in rows if not it["quarantine"] for w in it["gold"]})
        for item in rows:
            origin = overlap.get((split, item["id"]))
            if not item["quarantine"]:
                # kept and labelled, so the official sets stay whole and the clean subset is a breakdown
                item["labels"]["train_text_overlap"] = origin.split("/", 1)[0] if origin else "none"
                stats[f"{split}: training overlap"] += bool(origin)
            if item["quarantine"]:
                item["bias_lists"], item["distractor_kinds"] = {}, {}
            else:
                item["bias_lists"], item["distractor_kinds"] = build_lists(item, pool, confusables, recipe)
            scored_items.append(item)

    # a smoke run keeps its audio next to its output
    index = build_audio(scored_items, (args.out if args.smoke else source) / "audio", args.workers)
    for item in scored_items:
        split = "quarantine" if item["quarantine"] else item["split"]
        labels = dict(item["labels"])
        metadata = {"bias_lists": item["bias_lists"], "distractor_kinds": item["distractor_kinds"],
                    "upstream_id": item["id"], "audio_source": {k: item["audio"][k] for k in ("path", "start", "duration")}}
        for key in ("upstream_entities_not_in_text", "upstream_hotwords_not_in_text"):
            if item.get(key):
                metadata[key] = item[key]
        if split == "quarantine":
            labels.update(quarantine_reason=item["quarantine"], intended_split=item["split"])
        record = AudioRecord.from_dict({
            "schema_version": "audio-record/1.0",
            "id": f"{version}:{item['split']}:{item['id']}",
            "task": "asr_hotwords",
            "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                "dataset_id": dataset_id, "version": version, "split": split, "cut_id": item["cut_id"],
                "duration": index[item["cut_id"]]["duration"]}}],
            "target": item["text"], "language": item["language"], "hotwords": item["gold"],
            "labels": labels, "metadata": metadata,
        }).to_dict()
        by_split[split].append(record)

    for split, rows in by_split.items():
        write_jsonl(version_dir / "records" / f"{split}.jsonl.gz", rows)
    write_jsonl(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    print({s: len(r) for s, r in sorted(by_split.items())}, dict(stats), f"audio files: {len(index)}")
    if not args.out:
        register(declaration(recipe, by_split, index, version_dir))


def cjk_join(text):
    """Join a wrapped Chinese paragraph: no spaces after Chinese punctuation."""
    return re.sub(r"(?<=[，；。、）])\s+", "", " ".join(text.split()))


def declaration(recipe, by_split, index, version_dir):
    version, dataset_id = recipe["version"], recipe["dataset_id"]

    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": ROOT_ALIAS,
                "relative_path": str(path.relative_to(DATA_ROOT)), "sha256": sha256_file(path),
                "metadata": {"record_count": count}}

    artifacts = [artifact("audio-index", "audio-index", version_dir / "audio-index.jsonl.gz", len(index))]
    splits = {}
    for split, rows in sorted(by_split.items()):
        _, description = SPLITS[split]
        artifacts.append(artifact(f"{split}-records", "audio-records",
                                  version_dir / "records" / f"{split}.jsonl.gz", len(rows)))
        seconds = sum(r["audio_slots"][0]["ref"]["duration"] for r in rows)
        conditions = Counter(c for r in rows for c in r["metadata"]["bias_lists"])
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "group": "test",
            "task": "asr_hotwords",
            "statistics": {"records": len(rows), "duration_hours": round(seconds / 3600, 4),
                           "duration_basis": "recognized clip",
                           "records_with_hotwords": sum(1 for r in rows if r["hotwords"]),
                           "gold_words": sum(len(r["hotwords"]) for r in rows),
                           "conditions": dict(sorted(conditions.items()))},
            "provenance": {"description": description},
        }
    languages = sorted({SPLITS[s][0] for s in by_split if SPLITS[s][0]})
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": languages, "tasks": ["asr_hotwords"],
        "artifacts": artifacts, "splits": splits,
        "provenance": {
            "status": "complete", "synthetic": "partial", "usage": "evaluation_only",
            "description": cjk_join(f"""热词评测集，只用于评测，不进训练。每条记录存好固定的热词列表（metadata.bias_lists，
                已打乱顺序），评测器另跑不给列表的 none 条件。中文列表 = 正确词 + {recipe['llm']['generator']['model']}
                生成、{recipe['llm']['reviewer']['model']} 复核的易混词 + 同 split 热词池随机词，补到 {recipe['list_size']} 个；
                *_no_gold 为同一批干扰词去掉正确词。AISHELL1-NE、LibriSpeech 另含官方列表。生成脚本 scripts/hotword_bench/。"""),
            "sources": [
                "aishell@legacy-20260804 + SeACo-Paraformer 855b0fb (Test/Dev-AISHELL1-NE)",
                "ContextASR-Bench 7906fd9 Speech-Mandarin (MIT)",
                "speechio@eval-original-20261011, wenetspeech@eval-20261011 (real_zh)",
                ("commonvoice_zh_hotwords, aishell2_hotwords, aishell3_hotwords, kespeech_hotwords, "
                 "commonvoice_en_hotwords @hotwords-v1-20260805"),
                "gigaspeech@legacy-20260804 (test + XL training word counts)",
                "librispeech@legacy-20260804 + fbai-speech is21_deep_bias 43cdb3c",
            ],
            "limitations": cjk_join("""contextasr_speech_zh 为 TTS 合成音频；GigaSpeech 列表按 SALMONN-2 的描述重建，与其原表不完全相同；
                打分口径（规范化、B/U 归属）与各论文不完全一致，与公开数字只能近似对照；本地热词集与 real_zh 的
                正确词来自 LLM 抽取。AISHELL-1/AISHELL-3 测试文本大量出现在 AISHELL-2 训练转写中，
                labels.train_text_overlap 标出与训练文本相同的条目，用过这些训练集的模型应看 none 子集。"""),
        },
    }


def register(spec):
    path = REPO / "catalog" / f"{spec['dataset_id']}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    current = load_catalog(REPO / "catalog")
    validate_catalog([*current, DatasetSpec.from_dict(spec)])
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    shutil.copy(path, Path("/workspace/data/registry/catalog") / path.name)


if __name__ == "__main__":
    main()
