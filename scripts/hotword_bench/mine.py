#!/usr/bin/env python3
"""LLM stages of the hotword benchmark. Every call is archived under ``<source>/llm-log/``.

``real-zh``
    Hotwords for the real-speech candidates (SpeechIO, WenetSpeech test): the
    extractor applies AmphionData's EXTRACT_HOTWORD prompt, code keeps the words
    found in the reference, the reviewer (another model family) keeps or rejects
    each word. Each subset is scanned in sha256(id) order, ``scan_step`` at a
    time, until it has ``positives_per_subset`` utterances with an accepted word.
``confusables``
    For every Chinese gold word, the generator writes up to ``confusables_per_word``
    same- or near-sounding entries that would be wrong if the gold word was said.
``confusables-review``
    The reviewer keeps or rejects each (gold, confusable) pair.

Stages resume: finished ids / words are skipped on a rerun. With one GPU, run
``real-zh --only extract`` (extractor served), then ``real-zh --only review``
(reviewer served), and repeat until every subset has enough positives.

    load.sh aliyun-llm -- python scripts/hotword_bench/mine.py real-zh --source <source dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts
from common import (
    LLM,
    JsonlAppender,
    compact,
    contains,
    normalize,
    parse_json_reply,
    read_jsonl,
)

HERE = Path(__file__).resolve().parent


def client(recipe, role, source, stage):
    spec = recipe["llm"]
    role_spec = spec[role]  # a role may use its own server
    return LLM(role_spec, JsonlAppender(source / "llm-log" / f"{stage}.jsonl"),
               role_spec.get("base_url", spec["base_url"]), role_spec.get("api_key_env", spec["api_key_env"]))


def run_batches(batches, work, workers, label):
    done = failed = 0
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(work, batch): batch for batch in batches}
        for future in as_completed(futures):
            try:
                future.result()
                done += 1
            except Exception as exc:  # noqa: BLE001 - a failed batch stays unprocessed for the next run
                failed += 1
                print(f"{label}: batch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            if (done + failed) % 50 == 0:
                print(f"{label}: {done + failed}/{len(batches)} batches", file=sys.stderr)
    print(f"{label}: {done} batches done, {failed} failed", file=sys.stderr)


def chunks(rows, size):
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def bisect(work, refused):
    """Run ``work`` on a batch; when the model refuses or garbles it, retry the halves.

    Hosted models refuse some content (news on sensitive topics); this keeps the
    rest of the batch and records the single refused item via ``refused``.
    """
    def run(batch):
        try:
            work(batch)
        except ValueError:
            if len(batch) == 1:
                refused(batch[0])
                return
            half = len(batch) // 2
            run(batch[:half])
            run(batch[half:])
    return run


def ask_json(llm, messages, tag, attempts=3):
    last = None
    for attempt in range(attempts):
        # a malformed reply at temperature 0 repeats exactly; later attempts sample
        reply = llm.chat(messages, tag=tag, temperature=None if attempt == 0 else 0.5)
        try:
            return parse_json_reply(reply)["results"]
        except (ValueError, KeyError, TypeError) as exc:
            last = exc
    raise ValueError(f"unparseable reply after {attempts} attempts: {last}")


def real_zh(recipe, source, only=None):
    spec = recipe["sources"]["real_zh"]
    llm_cfg = recipe["llm"]
    extractor = client(recipe, "extractor", source, "real_zh-extract")
    reviewer = client(recipe, "reviewer", source, "real_zh-review")
    system = prompts.extract_prompt(recipe["amphiondata"]["repo"])
    extract_path = source / "mined" / "real_zh-extract.jsonl"
    review_path = source / "mined" / "real_zh-review.jsonl"
    extract_out, review_out = JsonlAppender(extract_path), JsonlAppender(review_path)

    candidates = read_jsonl(source / "candidates" / "real_zh.jsonl")
    by_subset = defaultdict(list)
    for item in candidates:
        if not item["quarantine"]:
            by_subset[item["labels"]["subset"]].append(item)

    def extract(batch):
        texts = "\n".join(f"[{i}] {item['text']}" for i, item in enumerate(batch, 1))
        results = ask_json(extractor, [{"role": "system", "content": system},
                                       {"role": "user", "content": prompts.EXTRACT_BATCH.format(n=len(batch), texts=texts)}],
                           tag="extract")
        found = {int(r["id"]): r.get("hotwords") or [] for r in results}
        for i, item in enumerate(batch, 1):
            if i not in found:
                continue
            raw = [h for h in found[i] if isinstance(h, str)]
            kept = list(dict.fromkeys(h.strip() for h in raw if normalize(h) and contains(item["text"], h, "zh")))
            extract_out.append({"id": item["id"], "raw_hotwords": raw, "hotwords": kept})

    def review(batch):
        lines = "\n".join(f"[{i}] 转写：{item['text']}\n    热词：{json.dumps(item['hotwords'], ensure_ascii=False)}"
                          for i, item in enumerate(batch, 1))
        results = ask_json(reviewer, [{"role": "system", "content": prompts.REVIEW_SYSTEM},
                                      {"role": "user", "content": prompts.REVIEW_USER.format(items=lines)}],
                           tag="review")
        verdicts = {int(r["id"]): r.get("terms") or [] for r in results}
        for i, item in enumerate(batch, 1):
            terms = {t.get("term"): t for t in verdicts.get(i, []) if isinstance(t, dict)}
            if set(item["hotwords"]) - set(terms):
                continue  # incomplete verdict: retried on the next run
            review_out.append({"id": item["id"], "terms": [
                {"term": h, "keep": bool(terms[h].get("keep")), "type": terms[h].get("type"),
                 "reason": terms[h].get("reason", "")} for h in item["hotwords"]]})

    target = spec["positives_per_subset"]
    for _ in range(spec.get("max_rounds", 50)):  # a batch that keeps failing must not loop forever
        extracted = {r["id"]: r for r in read_jsonl(extract_path)}
        reviewed = {r["id"]: r for r in read_jsonl(review_path)}
        to_review = [{"id": i, "text": None, "hotwords": r["hotwords"]} for i, r in extracted.items()
                     if r["hotwords"] and i not in reviewed]
        texts = {item["id"]: item["text"] for item in candidates}
        for row in to_review:
            row["text"] = texts[row["id"]]
        if to_review and only != "extract":
            run_batches(chunks(to_review, llm_cfg["review_batch"]),
                        bisect(review, lambda item: review_out.append({"id": item["id"], "refused": True, "terms": []})),
                        llm_cfg["workers"], "review")
            reviewed = {r["id"]: r for r in read_jsonl(review_path)}
        if only == "review":
            break
        scan = []
        status = {}
        for subset, items in sorted(by_subset.items()):
            positives = sum(1 for it in items if any(t["keep"] for t in reviewed.get(it["id"], {}).get("terms", [])))
            if only == "extract":
                # reviewer not served: count unreviewed extractions, aiming above target for rejections
                positives += sum(1 for it in items if it["id"] not in reviewed and extracted.get(it["id"], {}).get("hotwords"))
            pending = [it for it in items if it["id"] not in extracted]
            status[subset] = (positives, len(items) - len(pending), len(items))
            goal = target * (spec["extract_margin"] if only == "extract" else 1)
            if positives < goal and pending:
                scan.extend(pending[:spec["scan_step"]])
        print("subset positives / scanned / total:", json.dumps(status, ensure_ascii=False), file=sys.stderr)
        if not scan and (not to_review or only == "extract"):
            break
        if scan:
            run_batches(chunks(scan, llm_cfg["extract_batch"]),
                        bisect(extract, lambda item: extract_out.append({"id": item["id"], "refused": True,
                                                                         "raw_hotwords": [], "hotwords": []})),
                        llm_cfg["workers"], "extract")


def gold_words(source, unreviewed=False):
    """Chinese gold words; ``unreviewed`` adds real_zh extractions not yet reviewed."""
    words = set()
    for path in sorted((source / "items").glob("*.jsonl")):
        for item in read_jsonl(path):
            if item["language"] == "zh" and not item["quarantine"]:
                words.update(item["gold"])
    reviewed = read_jsonl(source / "mined" / "real_zh-review.jsonl")
    for row in reviewed:
        words.update(t["term"] for t in row["terms"] if t["keep"])
    if unreviewed:
        done = {row["id"] for row in reviewed}
        for row in read_jsonl(source / "mined" / "real_zh-extract.jsonl"):
            if row["id"] not in done:
                words.update(row["hotwords"])
    return sorted(words)


def confusables(recipe, source, unreviewed=False):
    llm_cfg = recipe["llm"]
    k = recipe["confusables_per_word"]
    generator = client(recipe, "generator", source, "confusables")
    path = source / "mined" / "confusables.jsonl"
    out = JsonlAppender(path)
    done = {r["term"] for r in read_jsonl(path)}
    todo = [w for w in gold_words(source, unreviewed) if w not in done]
    system = prompts.CONFUSABLE_SYSTEM.format(k=k)

    def work(batch):
        results = ask_json(generator, [{"role": "system", "content": system},
                                       {"role": "user", "content": "\n".join(batch)}], tag="confusables")
        got = {r.get("term"): r.get("confusables") or [] for r in results if isinstance(r, dict)}
        for term in batch:
            if term not in got:
                continue
            raw = [c for c in got[term] if isinstance(c, str)]
            # mechanical: a different written form after normalization, at most k
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
    needed = set(gold_words(source))  # real_zh words the reviewer rejected need no confusables
    pairs = [(r["term"], c) for r in read_jsonl(source / "mined" / "confusables.jsonl")
             for c in r["confusables"] if r["term"] in needed and (r["term"], c) not in done]

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


STAGES = {"real-zh": real_zh, "confusables": confusables, "confusables-review": confusables_review}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--only", choices=["extract", "review"],
                        help="real-zh: one extraction round or only the pending reviews (one model served at a time)")
    parser.add_argument("--include-unreviewed", action="store_true",
                        help="confusables: also for real_zh extractions not reviewed yet (saves a model swap)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    if args.stage == "real-zh":
        real_zh(recipe, args.source, args.only)
    elif args.stage == "confusables":
        confusables(recipe, args.source, args.include_unreviewed)
    else:
        STAGES[args.stage](recipe, args.source)


if __name__ == "__main__":
    main()
