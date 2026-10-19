#!/usr/bin/env python3
"""Generate, review and select the text items of the context-correction benchmark.

    load.sh aliyun-llm -- python scripts/context_correction/generate.py text   --out <source dir>
    load.sh aliyun-llm -- python scripts/context_correction/generate.py review --out <source dir>
    python scripts/context_correction/generate.py select --out <source dir>

``text`` asks the generator LLM for minimal pairs (``pairs.jsonl``); ``review`` asks
an LLM of another family to judge every pair (``reviews.jsonl``); ``select`` keeps
pairs that pass the review and the mechanical checks, in generation order
(``items.jsonl``; build.py takes each subtype's target among those whose audio passes
QC). Everything else is written to ``quarantine.jsonl`` with its reasons. Every LLM call is archived in ``llm-log/``.
All stages resume: finished calls are skipped.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts
from common import (
    LLM,
    JsonlAppender,
    MarkupError,
    alt_text,
    han_count,
    parse_json_reply,
    parse_markup,
    plain_text,
    read_jsonl,
    same_sound,
    sha1,
    write_jsonl,
)

HERE = Path(__file__).resolve().parent


def weighted(rng: random.Random, table: dict) -> str:
    keys = list(table)
    return rng.choices(keys, weights=[table[k] for k in keys])[0]


def plan_calls(recipe: dict) -> list[dict]:
    """Deterministic list of generation calls, each with ``pairs_per_call`` specs."""
    rng = random.Random(recipe["seed"])
    per_call = recipe["pairs_per_call"]
    calls = []
    for category, entry in recipe["categories"].items():
        for subtype, target in entry["subtypes"].items():
            pairs = math.ceil(target * entry.get("overprovision", recipe["overprovision"]))
            for index in range(math.ceil(pairs / per_call)):
                specs = []
                for _ in range(per_call):
                    implicit = category == "implicit"
                    specs.append({
                        "subtype": subtype,
                        "position": "after" if implicit else weighted(rng, recipe["positions"]),
                        "distance": weighted(rng, recipe["distances"]),
                        "entity_type": "普通词语" if implicit else weighted(rng, recipe["entity_types"]),
                        "scenario": rng.choice(recipe["scenarios"]),
                        "protected": rng.random() < entry["protected_rate"],
                    })
                calls.append({"call_id": f"{category}-{subtype}-{index:04d}", "category": category,
                              "subtype": subtype, "specs": specs})
    return calls


def spec_lines(specs: list[dict]) -> str:
    lines = []
    for number, spec in enumerate(specs, 1):
        extra = "；另加一个 [[P:...]] 保护词" if spec["protected"] else ""
        lines.append(f"{number}. 子类型={spec['subtype']}，position={spec['position']}，"
                     f"distance={spec['distance']}，实体类型={spec['entity_type']}，"
                     f"场景={spec['scenario']}{extra}")
    return "\n".join(lines)


def mechanical_issues(pair: dict, recipe: dict) -> list[str]:
    """Checks code can make without judging content: markup, length, homophony, twin swap."""
    issues, parsed = [], {}
    low, high = recipe["han_chars"]
    for kind in ("correct", "confirm"):
        try:
            parsed[kind] = parse_markup(pair.get(kind) or "")
        except MarkupError as exc:
            issues.append(f"{kind}: {exc}")
            continue
        targets = [s for s in parsed[kind] if s["role"] == "target"]
        if not targets:
            issues.append(f"{kind}: no target")
        if not any(s["role"] == "evidence" for s in parsed[kind]):
            issues.append(f"{kind}: no evidence span")
        outside = "".join(s["text"] for s in parsed[kind] if s["role"] in (None, "protected"))
        for spelling in {w for s in targets for w in (s["text"], s["alt"]) if len(w) >= 2}:
            if spelling in outside:
                issues.append(f"{kind}: target spelling {spelling} also appears outside the markup")
        for segment in targets:
            if not same_sound(segment["text"], segment["alt"]):
                issues.append(f"{kind}: not a tone-exact homophone: {segment['text']}|{segment['alt']}")
        chars = han_count(plain_text(parsed[kind]))
        if not low <= chars <= high:
            issues.append(f"{kind}: {chars} han chars outside [{low}, {high}]")
    if len(parsed) == 2:
        correct = sorted((s["text"], s["alt"]) for s in parsed["correct"] if s["role"] == "target")
        confirm = sorted((s["alt"], s["text"]) for s in parsed["confirm"] if s["role"] == "target")
        if set(correct) != set(confirm):
            issues.append("confirm does not swap the correct pair's target spellings")
        common = pair.get("common_spelling") or ""
        # The generator may name the whole word or only the differing character.
        if not any(common == alt or (common and common in alt and common not in gold) for gold, alt in correct):
            issues.append(f"generator's common spelling {pair.get('common_spelling')!r} is not the correct item's alt")
        if pair.get("subtype") == "隐式语义":
            def prefix(segments):
                out = []
                for s in segments:
                    if s["role"] == "target":
                        return "".join(out)
                    out.append(s["text"])
                return "".join(out)
            if prefix(parsed["correct"]) != prefix(parsed["confirm"]):
                issues.append("implicit pair texts differ before the target")
    return issues


def cmd_text(recipe: dict, out: Path, limit_calls: int = 0) -> None:
    llm_cfg = recipe["llm"]
    generator = LLM(llm_cfg["generator"], JsonlAppender(out / "llm-log" / "generate.jsonl"),
                    llm_cfg["base_url"], llm_cfg["api_key_env"])
    pairs_path = out / "pairs.jsonl"
    done = {row["call_id"] for row in read_jsonl(pairs_path)}
    calls = plan_calls(recipe)
    if limit_calls:  # pilot: an even sample of the planned calls across subtypes
        calls = calls[:: max(1, len(calls) // limit_calls)][:limit_calls]
    calls = [c for c in calls if c["call_id"] not in done]
    used: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(pairs_path):
        for segment in row.get("targets", []):
            used[row["subtype"]].append(segment)
    sink = JsonlAppender(pairs_path)
    system = prompts.GENERATOR_SYSTEM.format(min_chars=recipe["han_chars"][0], max_chars=recipe["han_chars"][1])

    def run(call):
        avoid = "、".join(used[call["subtype"]][-60:]) or "无"
        user = prompts.GENERATOR_USER.format(n=len(call["specs"]), specs=spec_lines(call["specs"]), avoid=avoid)
        reply = generator.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                               tag=call["call_id"])
        try:
            items = parse_json_reply(reply)
        except ValueError as exc:
            return call, [], f"unparseable reply: {exc}"
        return call, items if isinstance(items, list) else [], ""

    with ThreadPoolExecutor(llm_cfg["workers"]) as pool:
        futures = [pool.submit(run, call) for call in calls]
        for count, future in enumerate(as_completed(futures), 1):
            call, items, error = future.result()
            rows = []
            for position, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                spec_index = item.get("spec")
                spec = call["specs"][spec_index - 1] if isinstance(spec_index, int) and 1 <= spec_index <= len(call["specs"]) else {}
                pair = {
                    "pair_id": f"{call['call_id']}-{position}",
                    "call_id": call["call_id"], "category": call["category"], "subtype": call["subtype"],
                    "requested": spec,
                    **{k: item.get(k) for k in ("position", "distance", "entity_type", "scenario", "common_spelling",
                                                 "correct", "confirm", "reason_correct", "reason_confirm")},
                }
                try:
                    pair["targets"] = sorted({s["text"] for s in parse_markup(pair["correct"] or "") if s["role"] == "target"})
                except MarkupError:
                    pair["targets"] = []
                used[call["subtype"]].extend(pair["targets"])
                rows.append(pair)
            if not rows:  # keep a marker so a resumed run does not repeat a failed call forever
                rows = [{"call_id": call["call_id"], "category": call["category"],
                         "subtype": call["subtype"], "error": error or "no items", "targets": []}]
            for row in rows:
                sink.append(row)
            print(f"[text] {count}/{len(calls)} {call['call_id']}: {len(items)} pairs {error}", flush=True)


def cmd_review(recipe: dict, out: Path) -> None:
    llm_cfg = recipe["llm"]
    reviewer = LLM(llm_cfg["reviewer"], JsonlAppender(out / "llm-log" / "review.jsonl"),
                   llm_cfg["base_url"], llm_cfg["api_key_env"])
    reviews_path = out / "reviews.jsonl"
    done = {row["pair_id"] for row in read_jsonl(reviews_path)}
    pairs = [p for p in read_jsonl(out / "pairs.jsonl") if "pair_id" in p and p["pair_id"] not in done]
    sink = JsonlAppender(reviews_path)

    def run(pair):
        user = prompts.REVIEWER_USER.format(subtype=pair["subtype"], correct=pair["correct"], confirm=pair["confirm"])
        reply = reviewer.chat([{"role": "system", "content": prompts.REVIEWER_SYSTEM},
                               {"role": "user", "content": user}], tag=pair["pair_id"])
        try:
            verdict = parse_json_reply(reply)
        except ValueError as exc:
            verdict = {"error": str(exc)}
        return {"pair_id": pair["pair_id"], "reviewer": reviewer.model, "verdict": verdict}

    with ThreadPoolExecutor(llm_cfg["workers"]) as pool:
        futures = [pool.submit(run, pair) for pair in pairs]
        for count, future in enumerate(as_completed(futures), 1):
            sink.append(future.result())
            if count % 50 == 0 or count == len(pairs):
                print(f"[review] {count}/{len(pairs)}", flush=True)


def review_issues(pair: dict, review: dict | None) -> list[str]:
    if review is None:
        return ["not reviewed"]
    verdict = review.get("verdict") or {}
    if "error" in verdict:
        return [f"review unparseable: {verdict['error']}"]
    issues = []
    for kind in ("correct", "confirm"):
        checks = verdict.get(kind) or {}
        for key in ("unique", "prior_matches", "homophone", "natural", "protected_ok", "description_accurate"):
            # Which spelling is the default is fuzzy for implicit pairs (反映/反应): the gold
            # spellings must still be agreed, but implicit items are scored as pairs, not as
            # correction-from-default, so the prior is not required to match.
            if key == "prior_matches" and pair["subtype"] == "隐式语义":
                continue
            if checks.get(key) is not True:
                issues.append(f"review {kind}.{key}={checks.get(key)}")
    if pair["subtype"] == "隐式语义" and verdict.get("prefix_ambiguous") is not True:
        issues.append(f"review prefix_ambiguous={verdict.get('prefix_ambiguous')}")
    return issues


def to_items(pair: dict) -> list[dict]:
    """One benchmark item per variant, with CoT supervision kept in ``cot``."""
    items = []
    for kind in ("correct", "confirm"):
        segments = parse_markup(pair[kind])
        text = plain_text(segments)
        draft = alt_text(segments) if kind == "correct" else text
        edits = []
        if kind == "correct":
            evidence = "；".join(s["text"] for s in segments if s["role"] == "evidence")
            seen = set()
            for s in segments:
                if s["role"] == "target" and (s["alt"], s["text"]) not in seen:
                    seen.add((s["alt"], s["text"]))
                    edits.append({"from": s["alt"], "to": s["text"], "evidence": evidence,
                                  "reason": pair.get("reason_correct") or ""})
        items.append({
            "id": f"{pair['pair_id']}-{kind}",
            "pair_id": pair["pair_id"],
            "category": pair["category"],
            "subtype": pair["subtype"],
            "kind": kind,
            "position": pair.get("position"),
            "distance": pair.get("distance"),
            "entity_type": pair.get("entity_type"),
            "scenario": pair.get("scenario"),
            "marked_text": pair[kind],
            "text": text,
            "segments": segments,
            "reason": pair.get(f"reason_{kind}") or "",
            "cot": {"draft": draft, "edits": edits, "final": text},
        })
    return items


def cmd_select(recipe: dict, out: Path) -> None:
    reviews = {r["pair_id"]: r for r in read_jsonl(out / "reviews.jsonl")}
    order = {c["call_id"]: i for i, c in enumerate(plan_calls(recipe))}
    pairs = sorted((p for p in read_jsonl(out / "pairs.jsonl") if "pair_id" in p),
                   key=lambda p: (order.get(p["call_id"], 1 << 30), p["pair_id"]))
    targets = {sub: n for entry in recipe["categories"].values() for sub, n in entry["subtypes"].items()}
    taken, seen_texts = Counter(), set()
    items, quarantine = [], []
    for pair in pairs:
        issues = mechanical_issues(pair, recipe) + review_issues(pair, reviews.get(pair["pair_id"]))
        key = sha1((pair.get("correct") or "") + "\x1f" + (pair.get("confirm") or ""))
        if key in seen_texts:
            issues.append("duplicate pair text")
        seen_texts.add(key)
        if issues:
            quarantine.append({**pair, "issues": issues, "review": reviews.get(pair["pair_id"])})
        else:
            # every accepted pair is synthesized; build.py takes the first ``target`` pairs per
            # subtype (plan order) whose audio passes QC, so QC losses do not leave a stratum short
            taken[pair["subtype"]] += 1
            for item in to_items(pair):
                item["review"] = reviews[pair["pair_id"]]
                items.append(item)
    write_jsonl(out / "items.jsonl", items)
    write_jsonl(out / "quarantine.jsonl", quarantine)
    reasons = Counter(issue.split(":")[0].split("=")[0] for q in quarantine for issue in q["issues"])
    print({"accepted_pairs": dict(taken), "targets": targets, "quarantine": len(quarantine),
           "quarantine_reasons": dict(reasons.most_common(20))})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["text", "review", "select"])
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit-calls", type=int, default=0, help="only the first N calls (pilot)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    if args.stage == "text":
        cmd_text(recipe, args.out, args.limit_calls)
    else:
        {"review": cmd_review, "select": cmd_select}[args.stage](recipe, args.out)

if __name__ == "__main__":
    main()
