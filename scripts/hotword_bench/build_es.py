#!/usr/bin/env python3
"""Build and register hotword_bench es-v1: Spanish splits with fixed biasing lists (CPU only).

The Spanish counterpart of the cv_zh / cv_en splits of v1-v3: test-set
utterances whose hotwords are already labelled (``labels`` in the recipe),
the first ``local_positive_cap`` positives by sha256(id) per source. Lists are
built by ``build.build_lists`` as in v1: ``gold``, ``k50`` (gold + up to
``confusables_per_word`` confusables per gold word + random gold words of the
split, 50 in all) and ``k50_no_gold`` (the same distractors without gold,
refilled).

Confusables are not LLM-generated as in v1's Chinese splits: they are real
hotwords (the test gold words plus the hotword labels of the Spanish training
sets) whose Spanish reading key (``reading_key``: seseo, yeísmo, b/v, silent h,
c/qu/k, g/j before e/i, ...) is within a small edit distance of the gold
word's key, closest first, spelling distance breaking ties. Variants that only
differ in accents or case are not confusables. The mined pairs are kept in
``<source>/mined/confusables.jsonl``.

The script checks every split (``qc`` in the recipe) and exits non-zero
without registering when one fails. It registers into this repository's
``catalog/hotword_bench.yaml`` only.

    python scripts/hotword_bench/build_es.py --workers 32
    python scripts/hotword_bench/build_es.py --smoke 50 --out <scratch dir>
"""

from __future__ import annotations

import argparse
import math
import sys
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import REPO, ROOT_ALIAS, SR, build_lists, cjk_join, index_row
from common import (
    DATA_ROOT,
    DATASETS,
    compact,
    contains,
    iter_jsonl,
    normalize,
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
LANGUAGE = "es"
DESCRIPTIONS = {
    "cv_es": "Common Voice es 测试集（众包朗读、多口音），沿用已有西语热词标注，按 sha256(id) 取前 N 条正例",
    "fleurs_es": "FLEURS es 测试集（朗读维基句子，同一句话有多个说话人），沿用已有西语热词标注，全部正例",
    "mls_es": "MLS es 测试集（LibriVox 有声书，原标注全小写无标点），沿用已有西语热词标注，全部正例",
    "quarantine": "不参与打分：时长越界的条目，保留原因",
}


# ---------------------------------------------------------------- items ---

def manifest(path):
    return list(iter_jsonl(DATASETS / path))


def collect_items(recipe):
    labels_path = DATASETS / recipe["labels"]["path"]
    if sha256_file(labels_path) != recipe["labels"]["sha256"]:
        raise ValueError(f"{labels_path}: sha256 differs from the recipe")
    labels = defaultdict(lambda: ({}, {}))  # label source -> (by supervision id, by text)
    for row in read_jsonl(labels_path):
        by_id, by_text = labels[row["source"]]
        by_id[row["source_id"]] = row
        by_text.setdefault(row["text"], row)
    out = {}
    for split, spec in recipe["sources"].items():
        recordings = {r["id"]: r for r in manifest(spec["recordings"])}
        by_id, by_text = labels[spec["label_source"]]
        positives, unlabelled = [], 0
        for sup in manifest(spec["supervisions"]):
            label = by_id.get(sup["id"]) or by_text.get(sup["text"])
            if label is None:
                unlabelled += 1
                continue
            if label["text"] != sup["text"]:
                raise ValueError(f"{split}/{sup['id']}: labelled text differs from the supervision")
            gold = list(dict.fromkeys(occurrences(sup["text"], label["hotwords"], LANGUAGE)))
            if not gold:
                continue
            (source,) = recordings[sup["recording_id"]]["sources"]
            item = {"split": split, "id": sup["id"], "language": LANGUAGE, "text": sup["text"], "gold": gold,
                    "labels": {"source": split}, "quarantine": None,
                    "audio": {"path": source["source"], "start": sup.get("start", 0.0),
                              "duration": sup["duration"],
                              "recording_duration": recordings[sup["recording_id"]]["duration"]},
                    "label_id": label["id"]}
            missing = [h for h in label["hotwords"] if h not in gold]
            if missing:
                item["upstream_hotwords_not_in_text"] = missing
            if sup.get("speaker"):  # metadata, not a label: the scorer breaks results down by every string label
                item["speaker"] = sup["speaker"]
            duration = sup["duration"]
            if duration < recipe["min_seconds"] or duration > recipe["max_seconds"]:
                item["quarantine"] = f"duration {duration:.3f} s outside [{recipe['min_seconds']}, {recipe['max_seconds']}] s"
            positives.append(item)
        if unlabelled:
            raise ValueError(f"{split}: {unlabelled} supervisions have no hotword label")
        positives.sort(key=lambda it: order_key(recipe["seed"], split, it["id"]))
        scored = [it for it in positives if not it["quarantine"]][: recipe["local_positive_cap"]]
        kept = {it["id"] for it in scored}
        horizon = positives.index(scored[-1]) + 1 if scored else len(positives)
        out[split] = scored + [it for it in positives[:horizon] if it["quarantine"] and it["id"] not in kept]
        print(f"{split}: {len(positives)} positives, kept {len(scored)}", file=sys.stderr)
    return out


# ---------------------------------------------------------- confusables ---

def strip_accents(text):
    text = text.replace("ñ", "\0")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return text.replace("\0", "ñ")


READING_RULES = [  # applied in order to the accent-free lowercase word (Latin American reading)
    ("ch", "C"), ("ll", "y"), ("rr", "r"), ("ph", "f"), ("th", "t"), ("sh", "S"),
    ("qu", "k"), ("gue", "Ge"), ("gui", "Gi"), ("ce", "se"), ("ci", "si"), ("ge", "je"), ("gi", "ji"),
    ("c", "k"), ("z", "s"), ("x", "ks"), ("v", "b"), ("w", "u"), ("h", ""), ("ñ", "N"), ("G", "g"),
]


def reading_key(word):
    """Approximate Spanish reading of a word or phrase (letters only, words joined by one space)."""
    words = []
    for token in strip_accents(normalize(word)).split():
        token = "".join(c for c in token if c.isalpha())
        for old, new in READING_RULES:
            token = token.replace(old, new)
        token = token[:-1] + "i" if token.endswith("y") and len(token) > 1 else token
        collapsed = "".join(c for i, c in enumerate(token) if i == 0 or c != token[i - 1])
        if collapsed:
            words.append(collapsed)
    return " ".join(words)


def levenshtein_many(query, candidates, lengths):
    """Edit distance of ``query`` to each row of ``candidates`` (int codes, padded), vectorized over rows."""
    n, width = candidates.shape
    previous = np.tile(np.arange(width + 1, dtype=np.int16), (n, 1))
    for i, code in enumerate(query, 1):
        current = np.empty_like(previous)
        current[:, 0] = i
        cost = (candidates != code).astype(np.int16)
        substitution = previous[:, :-1] + cost
        deletion = previous[:, 1:] + 1
        best = np.minimum(substitution, deletion)
        for j in range(1, width + 1):  # insertion depends on the cell to the left
            current[:, j] = np.minimum(best[:, j - 1], current[:, j - 1] + 1)
        previous = current
    return previous[np.arange(n), lengths]


def spelling_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j - 1] + (x != y), previous[j] + 1, current[j - 1] + 1))
        previous = current
    return previous[-1]


G = {}  # worker state set before the pool forks


def mine_one(word):
    spec, buckets = G["spec"], G["buckets"]
    key = reading_key(word)
    if len(key.replace(" ", "")) < spec["min_key_length"]:
        return word, []
    limit = next(d for length, d in spec["max_distance"] if len(key) <= length)
    query = [ord(c) for c in key]
    plain = strip_accents(normalize(word))
    found = []
    for length in range(len(key) - limit, len(key) + limit + 1):
        if length not in buckets:
            continue
        words, codes, lengths = buckets[length]
        distances = levenshtein_many(query, codes, lengths)
        for index in np.nonzero(distances <= limit)[0]:
            candidate = words[index]
            other = strip_accents(normalize(candidate))
            tokens, other_tokens = set(plain.split()), set(other.split())
            if other == plain or tokens <= other_tokens or other_tokens <= tokens:
                continue  # accent / case variant, or one name holds the other ("Lyndon Johnson", "Donald J. Trump")
            found.append((int(distances[index]), spelling_distance(plain, other), candidate))
    found.sort(key=lambda f: (f[0], f[1], order_key(G["seed"], word, f[2])))
    return word, [{"confusable": c, "reading_distance": d, "spelling_distance": s} for d, s, c in found[:8]]


def vocabulary(recipe, items):
    """Test gold words + training hotword labels: names (capitalized) and other labels seen ``min_count`` times.

    Lowercase labels seen once are mostly typos ("madagasear", "alibe"); names are kept even when rare.
    """
    gold, counts, spelling = set(), Counter(), {}
    for rows in items.values():
        for item in rows:
            for word in item["gold"]:
                gold.add(normalize(word))
                spelling.setdefault(normalize(word), word)
    for path in recipe["confusables"]["vocabulary"]:
        for row in iter_jsonl(DATASETS / path):
            for word in (row.get("custom") or {}).get("hotwords") or []:
                if normalize(word):
                    counts[normalize(word)] += 1
                    spelling.setdefault(normalize(word), word)
    kept = gold | {w for w, n in counts.items()
                   if n >= recipe["confusables"]["min_count"] or spelling[w][:1].isupper()}
    return sorted(spelling[w] for w in kept)


def mine_confusables(recipe, items, workers):
    words = vocabulary(recipe, items)
    by_length = defaultdict(list)
    for word in words:
        key = reading_key(word)
        if key:
            by_length[len(key)].append((word, key))
    buckets = {}
    for length, rows in by_length.items():
        codes = np.array([[ord(c) for c in key] for _, key in rows], dtype=np.int32)
        buckets[length] = ([w for w, _ in rows], codes, np.full(len(rows), length))
    G.update(spec=recipe["confusables"], buckets=buckets, seed=recipe["seed"])
    gold = sorted({w for rows in items.values() for it in rows if not it["quarantine"] for w in it["gold"]})
    ctx = __import__("multiprocessing").get_context("fork")
    with ProcessPoolExecutor(workers, mp_context=ctx) as pool:
        mined = dict(pool.map(mine_one, gold, chunksize=16))
    print(f"confusables: vocabulary {len(words)}, gold {len(gold)}, "
          f"with any {sum(1 for v in mined.values() if v)}", file=sys.stderr)
    return words, mined


# -------------------------------------------------------------- overlap ---

def training_overlap(recipe, items):
    wanted = defaultdict(list)
    for rows in items.values():
        for item in rows:
            if not item["quarantine"]:
                wanted[compact(item["text"], LANGUAGE)].append((item["split"], item["id"]))
    found = {}
    for path in recipe["overlap"]["supervisions"]:
        for row in iter_jsonl(DATASETS / path):
            for key in wanted.get(compact(row["text"], LANGUAGE), []):
                found.setdefault(key, path.split("/", 1)[0])
    return found


# ---------------------------------------------------------------- audio ---

def in_place(audio):
    path = Path(audio["path"])
    if path.suffix not in {".wav", ".flac"} or audio["start"] or abs(audio["duration"] - audio["recording_duration"]) > 0.01:
        return False
    info = sf.info(path)
    return path.is_relative_to(DATA_ROOT) and info.samplerate == SR and info.channels == 1


def materialize(job):
    from scipy.signal import resample_poly

    cut_id, audio, destination = job
    wav, rate = sf.read(audio["path"], dtype="float32", always_2d=True)
    wav = wav.mean(axis=1)[round(audio["start"] * rate): round((audio["start"] + audio["duration"]) * rate)]
    if rate != SR:
        g = math.gcd(rate, SR)
        wav = resample_poly(wav, SR // g, rate // g).astype(np.float32)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, np.clip(wav, -1, 1), SR, subtype="PCM_16")
    return index_row(destination, cut_id)


def build_audio(items, audio_root, workers):
    jobs, direct = [], []
    for item in items:
        item["cut_id"] = f"{item['split']}:{item['id']}"
        if in_place(item["audio"]):
            direct.append((Path(item["audio"]["path"]), item["cut_id"]))
        else:
            jobs.append((item["cut_id"], item["audio"], audio_root / item["split"] / f"{item['id']}.wav"))
    with ProcessPoolExecutor(workers) as pool:
        rows = list(pool.map(materialize, jobs, chunksize=16))
        rows += list(pool.map(index_row, *zip(*direct), chunksize=64)) if direct else []
    return {row["cut_id"]: row for row in rows}


# ------------------------------------------------------------------- qc ---

def quality_check(recipe, by_split, index, items):
    """Per-split gates; returns (failures, report)."""
    gates, failures, report = recipe["qc"], [], {}
    size = recipe["list_size"]
    for split, spec in recipe["sources"].items():
        rows = by_split.get(split, [])
        quarantined = sum(1 for it in items[split] if it["quarantine"])
        drift = max((abs(index[r["audio_slots"][0]["ref"]["cut_id"]]["duration"] - r["metadata"]["audio_source"]["duration"])
                     for r in rows), default=0.0)
        bad_lists, gold_words, with_confusable = 0, 0, 0
        for r in rows:
            lists, gold, target = r["metadata"]["bias_lists"], r["hotwords"], r["target"]
            k50, no_gold = lists.get("k50", []), lists.get("k50_no_gold", [])
            distractors = [w for w in k50 if w not in gold] + no_gold
            normalized = [normalize(w) for w in k50]
            if (not gold or len(k50) != size or len(no_gold) != size or set(gold) - set(k50)
                    or set(gold) & set(no_gold) or len(set(normalized)) != len(normalized)
                    or len({normalize(w) for w in no_gold}) != len(no_gold)
                    or any(not contains(target, w, LANGUAGE) for w in gold)
                    or any(contains(target, w, LANGUAGE) for w in distractors)):
                bad_lists += 1
            kinds = r["metadata"]["distractor_kinds"]
            confusables_in_list = {w for w in k50 if kinds.get(w) == "confusable"}
            for word in gold:
                gold_words += 1
                with_confusable += any(c["confusable"] in confusables_in_list for c in G["mined"].get(word, []))
        hours = sum(r["audio_slots"][0]["ref"]["duration"] for r in rows) / 3600
        stats = {"records": len(rows), "hours": round(hours, 3),
                 "mean_seconds": round(hours * 3600 / max(len(rows), 1), 2),
                 "gold_words": gold_words, "gold_per_record": round(gold_words / max(len(rows), 1), 3),
                 "gold_with_confusable": round(with_confusable / max(gold_words, 1), 3),
                 "quarantined": quarantined, "bad_lists": bad_lists, "max_duration_drift": round(drift, 3),
                 "train_text_overlap": sum(1 for r in rows if r["labels"]["train_text_overlap"] != "none")}
        report[split] = stats
        checks = [
            (len(rows) >= spec["min_records"], f"records {len(rows)} < {spec['min_records']}"),
            (quarantined <= gates["max_quarantine_fraction"] * max(len(items[split]), 1),
             f"quarantined {quarantined} of {len(items[split])}"),
            (bad_lists == 0, f"{bad_lists} records with a malformed list"),
            (stats["gold_with_confusable"] >= gates["min_gold_with_confusable"],
             f"gold words with a confusable {stats['gold_with_confusable']} < {gates['min_gold_with_confusable']}"),
            (drift <= gates["max_duration_drift"], f"audio duration drift {drift:.3f} s"),
        ]
        failures += [f"{split}: {message}" for ok, message in checks if not ok]
    return failures, report


# ------------------------------------------------------------------- main ---

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-es-v1.yaml")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--smoke", type=int, help="first N items per split, needs --out (no registration)")
    parser.add_argument("--out", type=Path, help="write here instead of the version directory (no registration)")
    args = parser.parse_args()
    if args.smoke and not args.out:
        parser.error("--smoke needs --out")
    recipe = yaml.safe_load(args.recipe.read_text())
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    version_dir = args.out or DATASETS / dataset_id / "versions" / version
    source = (args.out / "source") if args.out else DATASETS / dataset_id / "source" / version
    for path in (version_dir, source):
        if path.exists():
            raise FileExistsError(f"refusing to replace: {path}")

    items = collect_items(recipe)
    if args.smoke:
        items = {split: rows[: args.smoke] for split, rows in items.items()}
    words, mined = mine_confusables(recipe, items, args.workers)
    vocabulary_size, canonical = len(words), {normalize(w): w for w in words}
    G["mined"] = mined
    write_jsonl(source / "mined" / "confusables.jsonl",
                [{"term": w, "reading_key": reading_key(w), "candidates": c} for w, c in sorted(mined.items())])
    confusables = {w: [c["confusable"] for c in found] for w, found in mined.items()}

    overlap = training_overlap(recipe, items)
    scored = []
    for split, rows in items.items():
        # one spelling per normalized form ("T. Rex" / "T-Rex"), the one confusables use, so a list holds no variants
        pool = sorted({canonical[normalize(w)] for it in rows if not it["quarantine"] for w in it["gold"]})
        for item in rows:
            if item["quarantine"]:
                item["bias_lists"], item["distractor_kinds"] = {}, {}
            else:
                origin = overlap.get((split, item["id"]))
                item["labels"]["train_text_overlap"] = origin or "none"
                item["bias_lists"], item["distractor_kinds"] = build_lists(item, pool, confusables, recipe)
            scored.append(item)

    index = build_audio(scored, source / "audio", args.workers)
    by_split = defaultdict(list)
    for item in scored:
        split = "quarantine" if item["quarantine"] else item["split"]
        labels = dict(item["labels"])
        if split == "quarantine":
            labels.update(quarantine_reason=item["quarantine"], intended_split=item["split"])
        metadata = {"bias_lists": item["bias_lists"], "distractor_kinds": item["distractor_kinds"],
                    "upstream_id": item["id"], "hotword_label_id": item["label_id"],
                    "audio_source": {k: item["audio"][k] for k in ("path", "start", "duration")}}
        if item.get("speaker"):
            metadata["speaker"] = item["speaker"]
        if item.get("upstream_hotwords_not_in_text"):
            metadata["upstream_hotwords_not_in_text"] = item["upstream_hotwords_not_in_text"]
        by_split[split].append(AudioRecord.from_dict({
            "schema_version": "audio-record/1.0",
            "id": f"{version}:{item['split']}:{item['id']}",
            "task": "asr_hotwords",
            "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                "dataset_id": dataset_id, "version": version, "split": split, "cut_id": item["cut_id"],
                "duration": index[item["cut_id"]]["duration"]}}],
            "target": item["text"], "language": LANGUAGE, "hotwords": item["gold"],
            "labels": labels, "metadata": metadata,
        }).to_dict())

    failures, report = quality_check(recipe, by_split, index, items)
    print(yaml.safe_dump(report, allow_unicode=True, sort_keys=False), file=sys.stderr)
    for split, rows in by_split.items():
        write_jsonl(version_dir / "records" / f"{split}.jsonl.gz", rows)
    write_jsonl(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    (version_dir / "qc.yaml").write_text(yaml.safe_dump(
        {"passed": not failures, "failures": failures, "splits": report}, allow_unicode=True, sort_keys=False))
    if failures:
        sys.exit("QC failed, not registered:\n  " + "\n  ".join(failures))
    if args.out:
        return
    register(declaration(recipe, by_split, index, version_dir, source, vocabulary_size, report))


def declaration(recipe, by_split, index, version_dir, source, vocabulary_size, report):
    version, dataset_id = recipe["version"], recipe["dataset_id"]

    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": ROOT_ALIAS,
                "relative_path": str(path.relative_to(DATA_ROOT)), "sha256": sha256_file(path),
                "metadata": {"record_count": count}}

    mined = source / "mined" / "confusables.jsonl"
    artifacts = [artifact("audio-index", "audio-index", version_dir / "audio-index.jsonl.gz", len(index)),
                 artifact("confusables", "jsonl-metadata", mined, sum(1 for _ in mined.open())),
                 {**artifact("qc", "quality-report", version_dir / "qc.yaml", 0), "metadata": {"passed": True}}]
    splits = {}
    for split, rows in sorted(by_split.items()):
        artifacts.append(artifact(f"{split}-records", "audio-records",
                                  version_dir / "records" / f"{split}.jsonl.gz", len(rows)))
        seconds = sum(r["audio_slots"][0]["ref"]["duration"] for r in rows)
        conditions = Counter(c for r in rows for c in r["metadata"]["bias_lists"])
        statistics = {"records": len(rows), "duration_hours": round(seconds / 3600, 4),
                      "duration_basis": "recognized clip",
                      "records_with_hotwords": sum(1 for r in rows if r["hotwords"]),
                      "gold_words": sum(len(r["hotwords"]) for r in rows),
                      "conditions": dict(sorted(conditions.items()))}
        if split in report:
            statistics["gold_with_confusable"] = report[split]["gold_with_confusable"]
            statistics["train_text_overlap"] = report[split]["train_text_overlap"]
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "group": "test", "task": "asr_hotwords", "statistics": statistics,
            "provenance": {"description": DESCRIPTIONS[split]},
        }
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": [LANGUAGE], "tasks": ["asr_hotwords"],
        "artifacts": artifacts, "splits": splits,
        "provenance": {
            "status": "complete", "synthetic": "none", "usage": "evaluation_only",
            "description": cjk_join(f"""西语热词评测集，对应中英 v3-20261020 的 cv_zh / cv_en，只用于评测，不进训练。
                三个西语测试集（Common Voice es、FLEURS es、MLS es）里含热词的句子，
                热词沿用已有标注（ts_asr_hotwords@es-v1-20261111 hotword-labels.jsonl，Qwen3.8-27B 抽取 + 复核）。
                每条记录存好固定的热词列表（metadata.bias_lists，已打乱顺序），评测器另跑不给列表的 none 条件：gold；k50 = 正确词 + 每个正确词最多
                {recipe['confusables_per_word']} 个近音词 + 同 split 正确词池随机词，补到 {recipe['list_size']} 个；
                k50_no_gold 为同一批干扰词去掉正确词再补满。近音词是在 {vocabulary_size:,} 个西语热词（测试集正确词 +
                西语训练集热词标注）里按西语读音键的编辑距离检索出的真实词（只用 CPU，不经 LLM），
                原始候选见 source/{version}/mined/confusables.jsonl。生成脚本 scripts/hotword_bench/build_es.py，配方 recipe-es-v1.yaml。"""),
            "sources": [*(spec["dataset"] for spec in recipe["sources"].values()),
                        "ts_asr_hotwords@es-v1-20261111 (hotword-labels.jsonl)",
                        "common_voice_es@es-train-v1-20261108:train, mls_es@es-train-v1-20261108:train (confusable vocabulary, overlap check)"],
            "limitations": cjk_join("""热词来自 LLM 抽取与复核，未经人工核对；没有中文 v3 的 hotword_types（需要 LLM 标注）；
                没有西语现网词库，不做中文 v2 的 pool50 检索列表；近音词按拼写推出的读音键检索（拉美读法：seseo、yeísmo），
                不是声学相似度，也不覆盖英文专名的英语读法；FLEURS 同一句话有多个说话人，含热词的约 145 句话。
                MLS 转写全小写无标点，热词也是小写。"""),
        },
    }


def register(spec):
    path = REPO / "catalog" / f"{spec['dataset_id']}.yaml"
    rows = list(yaml.safe_load(path.read_text()))
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(spec)])
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", spec["dataset_id"], spec["version"], file=sys.stderr)


if __name__ == "__main__":
    main()
