#!/usr/bin/env python3
"""Hotword prompts the 10.28 model has not memorized, as GRPO mining candidates.

Stages (each resumes; every LLM call is archived under ``<source>/llm-log/``):

``select``
    Train-split utterances (recipe ``sources``; upstream clean pass with the text kept
    as is where a clean version exists), minus audio and text the SFT recipe used
    (``recipe_refs.py`` output and ``seen_records``) and anything an eval set contains
    (``eval_refs.py`` output). Corpora with AmphionData hotword labels keep them;
    primewords goes to extraction. Writes ``<source>/candidates.jsonl``.
``extract``
    primewords hotwords with AmphionData's EXTRACT_HOTWORD (code keeps the words
    found in the transcript).
``review``
    The reviewer (another model family) keeps or rejects every extracted word and
    gives its type (人名 / 地名 / 机构品牌 / 专业术语 / 其他).
``confusables`` / ``confusables-review``
    For every kept word the generator writes up to ``confusables_per_word``
    same- or near-sounding real entries; the reviewer keeps or rejects each pair.
``build``
    Records + audio index (``records_zh.jsonl.gz``, ``audio_index_zh.jsonl.gz``) in
    the version directory, utterances with a person name first.

    load.sh volcengine-ark -- python scripts/grpo_candidates/hotwords.py <stage> \\
        --source /workspace/data/datasets/hw_grpo_candidates/source/v1-20261101 \\
        --eval-refs eval-refs.json.gz --recipe-refs recipe-refs.json.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "hotword_bench"))
import prompts
from common import (
    DATASETS,
    JsonlAppender,
    compact,
    contains,
    iter_jsonl,
    normalize,
    order_key,
    read_jsonl,
    write_jsonl,
)
from mine import ask_json, bisect, chunks, client, run_batches

ROOT_ALIAS = "aidc_data"
DATA_ROOT = Path("/workspace/data")
TASK = "asr_hotwords"
PERSON = "人名"

# The GRPO hotword reward's units (open_audio_llm rewards/qwen3_asr.py): a listed word counts as
# spoken when its unit sequence is in the reference's, so no distractor may be.
_UNITS = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]|[a-z0-9]+(?:'[a-z0-9]+)*")


def units(text: str) -> list[str]:
    return _UNITS.findall(unicodedata.normalize("NFKC", text).lower())


def in_reference(text: str, word: str) -> bool:
    ref, needle = units(text), units(word)
    by_units = bool(needle) and f" {' '.join(needle)} " in f" {' '.join(ref)} "
    return by_units or contains(text, word, "zh")


def usable_word(word: str) -> bool:
    # the reward and the prompt split the list on ASCII commas
    found = units(word)
    if not normalize(word) or "," in word or word.strip() != word or not found:
        return False
    # one Chinese character is too ambiguous to be a hotword (AmphionData's extraction prompt says the same),
    # and in the reward it fires on any other word that contains it
    return not (len(found) == 1 and len(found[0]) == 1 and not found[0].isascii())


def clean_ok(supervision: dict) -> bool:
    clean = (supervision.get("custom") or {}).get("clean") or {}
    return clean.get("pass") is True and clean.get("action") == "keep_original"


def read_refs(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def load_recipe(path):
    return yaml.safe_load(Path(path).read_text())


# ---------------------------------------------------------------- select ---

def select(recipe, source, eval_refs, recipe_refs):
    refs = read_refs(eval_refs)
    eval_texts, eval_utts, eval_audio = set(refs["texts"]), set(refs["utterances"]), set(refs["audio"])
    trained = read_refs(recipe_refs)
    seen_audio, seen_texts = set(trained["audio"]), set(trained["texts"])
    seen_files = set()
    for pattern in recipe["seen_records"]:
        for row in iter_jsonl(DATASETS / pattern):
            seen_files.add(Path(row["metadata"]["audio_path"]).name)
            seen_texts.add(compact(row["target"], "zh"))
    drops = Counter()
    out, texts_taken = [], set()
    for corpus, spec in recipe["sources"].items():
        recordings = {r["id"]: r for r in iter_jsonl(DATASETS / spec["recordings"])}
        labels = ({r["id"]: r for r in iter_jsonl(DATASETS / spec["hotwords"])} if spec.get("hotwords") else None)
        rows = []
        clean_version = "clean_supervisions" in spec
        for sup in iter_jsonl(DATASETS / (spec["clean_supervisions"] if clean_version else spec["hotwords"])):
            if clean_version and not clean_ok(sup):
                drops[f"{corpus}:clean"] += 1
                continue
            rec = recordings[sup["recording_id"]]
            (audio,) = rec["sources"]
            path = os.path.normpath(audio["source"])
            text = sup["text"]
            extracted = None
            if labels is not None:
                label = labels.get(sup["id"])
                if label is None or compact(label["text"], "zh") != compact(text, "zh"):
                    drops[f"{corpus}:label_text_mismatch"] += 1
                    continue
                text = label["text"]  # punctuated, as hw_sft targets are
                extracted = [h.strip() for h in label["custom"].get("hotwords") or []
                             if isinstance(h, str) and normalize(h) and contains(text, h, "zh")]
                if not extracted:
                    drops[f"{corpus}:no_hotword_label"] += 1
                    continue
            key = compact(text, "zh")
            reason = (
                "duration" if not recipe["min_seconds"] <= sup["duration"] <= recipe["max_seconds"]
                else "partial_recording" if sup["start"] or abs(sup["duration"] - rec["duration"]) > 0.05
                else "seen_audio" if Path(path).name in seen_files or path in seen_audio
                else "seen_text" if key in seen_texts
                else "eval_text" if key in eval_texts
                else "eval_utterance" if f"{corpus}:{sup['id']}" in eval_utts or sup["id"] in eval_utts
                else "eval_audio" if path in eval_audio
                else "empty_text" if not key
                else None
            )
            if reason:
                drops[f"{corpus}:{reason}"] += 1
                continue
            rows.append({"id": f"{corpus}:{sup['id']}", "corpus": corpus, "text": text, "speaker": sup.get("speaker"),
                         "extracted": extracted, "clean_pass": clean_version,
                         "audio": {"path": path, "duration": rec["duration"], "sample_rate": rec["sampling_rate"],
                                   "num_frames": rec["num_samples"], "channels": len(rec["channel_ids"])}})
        rows.sort(key=lambda r: order_key(recipe["seed"], r["id"]))
        for row in rows:  # one utterance per sentence
            key = compact(row["text"], "zh")
            if key in texts_taken:
                drops[f"{corpus}:duplicate_text"] += 1
                continue
            texts_taken.add(key)
            out.append(row)
    write_jsonl(source / "candidates.jsonl", out)
    report = {"candidates": dict(Counter(r["corpus"] for r in out)),
              "with_labels": sum(1 for r in out if r["extracted"]), "dropped": dict(sorted(drops.items())),
              "eval_refs": refs["report"] | {"file": str(eval_refs)}}
    (source / "select-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "eval_refs"}, ensure_ascii=False, indent=1))


# --------------------------------------------------------------- extract ---

def extract(recipe, source):
    llm_cfg = recipe["llm"]
    extractor = client(recipe, "extractor", source, "extract")
    system = prompts.extract_prompt(recipe["amphiondata"]["repo"])
    path = source / "mined" / "extract.jsonl"
    out = JsonlAppender(path)
    done = {r["id"] for r in read_jsonl(path)}
    todo = [r for r in read_jsonl(source / "candidates.jsonl") if r["extracted"] is None and r["id"] not in done]

    def work(batch):
        texts = "\n".join(f"[{i}] {item['text']}" for i, item in enumerate(batch, 1))
        results = ask_json(extractor, [{"role": "system", "content": system},
                                       {"role": "user", "content": prompts.EXTRACT_BATCH.format(n=len(batch), texts=texts)}],
                           tag="extract")
        found = {int(r["id"]): r.get("hotwords") or [] for r in results if isinstance(r, dict) and "id" in r}
        for i, item in enumerate(batch, 1):
            if i not in found:
                continue
            raw = [h for h in found[i] if isinstance(h, str)]
            kept = list(dict.fromkeys(h.strip() for h in raw if normalize(h) and contains(item["text"], h, "zh")))
            out.append({"id": item["id"], "raw_hotwords": raw, "hotwords": kept})

    print(f"extract: {len(todo)} to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["extract_batch"]),
                bisect(work, lambda item: out.append({"id": item["id"], "refused": True, "raw_hotwords": [], "hotwords": []})),
                llm_cfg["workers"], "extract")


def extracted_words(source):
    """id -> extracted hotwords (MagicData labels, primewords extraction)."""
    mined = {r["id"]: r["hotwords"] for r in read_jsonl(source / "mined" / "extract.jsonl")}
    words = {}
    for row in read_jsonl(source / "candidates.jsonl"):
        found = row["extracted"] if row["extracted"] is not None else mined.get(row["id"])
        if found:
            words[row["id"]] = found
    return words


# ---------------------------------------------------------------- review ---

def review(recipe, source):
    llm_cfg = recipe["llm"]
    reviewer = client(recipe, "reviewer", source, "review")
    path = source / "mined" / "review.jsonl"
    out = JsonlAppender(path)
    done = {r["id"] for r in read_jsonl(path)}
    words = extracted_words(source)
    todo = [{"id": r["id"], "text": r["text"], "hotwords": words[r["id"]]}
            for r in read_jsonl(source / "candidates.jsonl") if r["id"] in words and r["id"] not in done]

    def work(batch):
        lines = "\n".join(f"[{i}] 转写：{item['text']}\n    热词：{json.dumps(item['hotwords'], ensure_ascii=False)}"
                          for i, item in enumerate(batch, 1))
        results = ask_json(reviewer, [{"role": "system", "content": prompts.REVIEW_SYSTEM},
                                      {"role": "user", "content": prompts.REVIEW_USER.format(items=lines)}], tag="review")
        verdicts = {int(r["id"]): r.get("terms") or [] for r in results if isinstance(r, dict) and "id" in r}
        for i, item in enumerate(batch, 1):
            terms = {t.get("term"): t for t in verdicts.get(i, []) if isinstance(t, dict)}
            if set(item["hotwords"]) - set(terms):
                continue  # incomplete verdict: retried on the next run
            out.append({"id": item["id"], "terms": [
                {"term": h, "keep": bool(terms[h].get("keep")), "type": terms[h].get("type"),
                 "reason": terms[h].get("reason", "")} for h in item["hotwords"]]})

    print(f"review: {len(todo)} to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["review_batch"]),
                bisect(work, lambda item: out.append({"id": item["id"], "refused": True, "terms": []})),
                llm_cfg["workers"], "review")


def kept_golds(source):
    """id -> [(word, type)] the reviewer kept."""
    golds = {}
    current = {r["id"] for r in read_jsonl(source / "candidates.jsonl")}
    for row in read_jsonl(source / "mined" / "review.jsonl"):
        if row["id"] not in current:  # dropped by a later select
            continue
        kept = [(t["term"], t.get("type")) for t in row["terms"] if t["keep"] and usable_word(t["term"])]
        if kept:
            golds[row["id"]] = kept
    return golds


# ------------------------------------------------------------ confusables ---

def confusables(recipe, source):
    llm_cfg = recipe["llm"]
    generator = client(recipe, "generator", source, "confusables")
    path = source / "mined" / "confusables.jsonl"
    out = JsonlAppender(path)
    done = {r["term"] for r in read_jsonl(path)}
    todo = sorted({w for kept in kept_golds(source).values() for w, _ in kept} - done)
    k = recipe["confusables_per_word"]
    system = prompts.CONFUSABLE_SYSTEM.format(k=k)

    def work(batch):
        results = ask_json(generator, [{"role": "system", "content": system},
                                       {"role": "user", "content": "\n".join(batch)}], tag="confusables")
        got = {r.get("term"): r.get("confusables") or [] for r in results if isinstance(r, dict)}
        for term in batch:
            if term not in got:
                continue
            raw = [c for c in got[term] if isinstance(c, str)]
            kept = []
            for c in raw:
                c = c.strip()
                if normalize(c) and compact(c, "zh") != compact(term, "zh") and c not in kept:
                    kept.append(c)
            out.append({"term": term, "raw": raw, "confusables": kept[:k]})

    print(f"confusables: {len(todo)} words to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["confusable_batch"]),
                bisect(work, lambda term: out.append({"term": term, "raw": [], "confusables": [], "refused": True})),
                llm_cfg["workers"], "confusables")


def confusables_review(recipe, source):
    llm_cfg = recipe["llm"]
    reviewer = client(recipe, "reviewer", source, "confusables-review")
    path = source / "mined" / "confusables-review.jsonl"
    out = JsonlAppender(path)
    done = {(r["term"], r["confusable"]) for r in read_jsonl(path)}
    pairs = [(r["term"], c) for r in read_jsonl(source / "mined" / "confusables.jsonl")
             for c in r["confusables"] if (r["term"], c) not in done]

    def work(batch):
        lines = "\n".join(f"[{i}] 原词：{t}  干扰词：{c}" for i, (t, c) in enumerate(batch, 1))
        results = ask_json(reviewer, [{"role": "system", "content": prompts.CONFUSABLE_REVIEW_SYSTEM},
                                      {"role": "user", "content": lines}], tag="confusables-review")
        verdicts = {int(r["id"]): r for r in results if isinstance(r, dict) and "id" in r}
        for i, (term, confusable) in enumerate(batch, 1):
            if i in verdicts:
                out.append({"term": term, "confusable": confusable, "keep": bool(verdicts[i].get("keep")),
                            "reason": verdicts[i].get("reason", "")})

    print(f"confusables-review: {len(pairs)} pairs to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(pairs, 3 * llm_cfg["confusable_batch"]),
                bisect(work, lambda pair: out.append({"term": pair[0], "confusable": pair[1], "keep": False,
                                                      "reason": "reviewer refused", "refused": True})),
                llm_cfg["workers"], "confusables-review")


# ----------------------------------------------------------------- build ---

def pinyin_match(a: str, b: str) -> str:
    """'tone' (same syllables and tones), 'toneless' (same syllables), else 'other' - analysis only."""
    from pypinyin import Style, lazy_pinyin

    if lazy_pinyin(a, style=Style.TONE3) == lazy_pinyin(b, style=Style.TONE3):
        return "tone"
    return "toneless" if lazy_pinyin(a) == lazy_pinyin(b) else "other"


def fill(rng, pool, n, banned, text):
    chosen = []
    for _ in range(50 * max(n, 1)):
        if len(chosen) >= n:
            break
        word = pool[rng.randrange(len(pool))]
        if word not in banned and word not in chosen and not in_reference(text, word):
            chosen.append(word)
    return chosen


def shuffled(rng, words, golds):
    words = rng.sample(words, len(words))
    if golds and words[0] in golds:  # never gold-first
        swap = next(i for i, w in enumerate(words) if w not in golds)
        words[0], words[swap] = words[swap], words[0]
    return words


def build(recipe, source, version_dir):
    candidates = {r["id"]: r for r in read_jsonl(source / "candidates.jsonl")}
    golds = kept_golds(source)
    alts = defaultdict(list)
    for row in read_jsonl(source / "mined" / "confusables-review.jsonl"):
        if row["keep"] and usable_word(row["confusable"]) and row["confusable"] not in alts[row["term"]]:
            alts[row["term"]].append(row["confusable"])
    reverse = defaultdict(set)  # confusable -> words it was written for
    for term, words in alts.items():
        for word in words:
            reverse[word].add(term)

    items, drops = [], Counter()
    for cid, kept in golds.items():
        row = candidates[cid]
        words = [w for w, _ in kept]
        per_gold = {}
        for word in words:
            per_gold[word] = [a for a in alts.get(word, []) if a not in words and not in_reference(row["text"], a)]
        confusable_list = list(dict.fromkeys(a for word in words for a in per_gold[word]))
        if not confusable_list:
            drops["no_kept_confusable"] += 1
            continue
        items.append({"row": row, "golds": words, "types": {w: t for w, t in kept},
                      "confusables": per_gold, "alternates": confusable_list,
                      "person": any(t == PERSON for _, t in kept)})

    # person names first, then the rest, each in a model-independent order; cap repeats of one word
    items.sort(key=lambda it: (not it["person"], order_key(recipe["seed"], "select", it["row"]["id"])))
    uses, chosen = Counter(), []
    for item in items:
        if len(chosen) >= recipe["target_records"]:
            drops["over_target"] += 1
            continue
        if any(uses[w] >= recipe["max_per_gold"] for w in item["golds"]):
            drops["gold_cap"] += 1
            continue
        uses.update(item["golds"])
        chosen.append(item)

    pool = sorted({w for it in items for w in it["golds"]} | {a for it in items for a in it["alternates"]})
    low, high = recipe["list_size"]
    # One list per utterance (kind by hash); below the target, the same utterances also get the other kind.
    jobs = [(item, "gold" if order_key(recipe["seed"], "kind", item["row"]["id"]) < "8" else "no_gold") for item in chosen]
    jobs += [(item, "no_gold" if kind == "gold" else "gold") for item, kind in jobs][:recipe["target_records"] - len(jobs)]
    records, index_rows = [], {}
    for number, (item, kind) in enumerate(sorted(jobs, key=lambda job: (job[0]["row"]["id"], job[1]))):
        row, gold = item["row"], item["golds"]
        rng = random.Random(order_key(recipe["seed"], "list", row["id"], kind))
        size = rng.randint(low, high)
        alternates = item["alternates"]
        head = (gold if kind == "gold" else []) + alternates
        banned = set(gold) | set(alternates) | {w for g in gold for w in alts.get(g, [])}
        banned |= {t for g in gold for t in reverse.get(g, ())}  # words this gold was a confusable of
        randoms = fill(rng, pool, max(0, size - len(head)), banned, row["text"])
        hotwords = shuffled(rng, head + randoms, set(gold))
        assert not any(in_reference(row["text"], w) for w in alternates + randoms)
        cut_id = row["id"]
        audio = row["audio"]
        records.append({
            "schema_version": "audio-record/1.0", "id": f"{recipe['split']}:{number:06d}", "task": TASK,
            "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                "dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": recipe["split"],
                "cut_id": cut_id, "duration": audio["duration"], "channel": 0}}],
            "target": row["text"], "language": "zh", "labels": {}, "hotwords": hotwords,
            "metadata": {
                "kind": kind, "golds": gold, "gold_types": item["types"], "confusables": item["confusables"],
                "confusable_pinyin": {a: pinyin_match(g, a) for g in gold for a in item["confusables"][g]},
                "random_words": randoms, "list_size": len(hotwords), "source_corpus": row["corpus"],
                "source_id": row["id"].split(":", 1)[1], "speaker": f"{row['corpus']}:{row['speaker']}",
                "audio_path": os.path.relpath(audio["path"], DATA_ROOT),
                **({"clean_pass": True} if row["clean_pass"] else {}),
                "hotword_prompt": ",".join(hotwords)}})
        index_rows[cut_id] = {"cut_id": cut_id, "root_alias": ROOT_ALIAS,
                              "relative_path": os.path.relpath(audio["path"], DATA_ROOT),
                              "sample_rate": audio["sample_rate"], "channels": audio["channels"],
                              "num_frames": audio["num_frames"], "duration": audio["duration"]}

    version_dir.mkdir(parents=True, exist_ok=True)
    split = recipe["split"]
    write_jsonl(version_dir / f"records_{split}.jsonl.gz", records)
    write_jsonl(version_dir / f"audio_index_{split}.jsonl.gz", sorted(index_rows.values(), key=lambda r: r["cut_id"]))
    kinds = Counter(r["metadata"]["kind"] for r in records)
    by = lambda key: dict(Counter(key(r) for r in records))
    report = {
        "records": len(records), "kinds": dict(kinds),
        "by_corpus": by(lambda r: r["metadata"]["source_corpus"]),
        "by_corpus_kind": by(lambda r: f"{r['metadata']['source_corpus']}:{r['metadata']['kind']}"),
        "with_person_gold": sum(1 for r in records if PERSON in r["metadata"]["gold_types"].values()),
        "gold_types": dict(Counter(t for r in records for t in r["metadata"]["gold_types"].values())),
        "distinct_golds": len({g for r in records for g in r["metadata"]["golds"]}),
        "confusables_per_record": round(sum(len({a for words in r["metadata"]["confusables"].values() for a in words})
                                            for r in records) / max(1, len(records)), 2),
        "confusable_pinyin": dict(Counter(v for r in records for v in r["metadata"]["confusable_pinyin"].values())),
        "list_size_mean": round(sum(len(r["hotwords"]) for r in records) / max(1, len(records)), 1),
        "hours": round(sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600, 2),
        "utterances": len(chosen), "eligible_utterances": len(items), "dropped": dict(drops), "pool_words": len(pool),
    }
    (version_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))


STAGES = ("select", "extract", "review", "confusables", "confusables-review", "build")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-hotwords.yaml")
    parser.add_argument("--source", type=Path, required=True, help="work directory (candidates, LLM logs)")
    parser.add_argument("--eval-refs", type=Path, help="select: eval_refs.py output")
    parser.add_argument("--recipe-refs", type=Path, help="select: recipe_refs.py output")
    parser.add_argument("--version-dir", type=Path, help="build: output dataset version directory")
    args = parser.parse_args()
    recipe = load_recipe(args.recipe)
    args.source.mkdir(parents=True, exist_ok=True)
    if args.stage == "select":
        select(recipe, args.source, args.eval_refs, args.recipe_refs)
    elif args.stage == "extract":
        extract(recipe, args.source)
    elif args.stage == "review":
        review(recipe, args.source)
    elif args.stage == "confusables":
        confusables(recipe, args.source)
    elif args.stage == "confusables-review":
        confusables_review(recipe, args.source)
    else:
        build(recipe, args.source, args.version_dir)


if __name__ == "__main__":
    main()
