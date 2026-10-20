#!/usr/bin/env python3
"""Register hotword_bench v3: the v2 records with each gold word's type and ContextASR's domain group.

v3 keeps v2's records, audio, gold words and lists, so every request is the
same and v2 and v3 metrics compare directly. It adds two LLM labels:

- ``metadata.hotword_types``: gold word -> one of ``prompts.TYPES``, judged by
  what the word means in its own sentence (the same string can differ between
  utterances);
- ``labels.domain_group`` on contextasr_speech_zh: the free-form
  ``labels.domain`` ContextASR ships with mapped to one of
  ``prompts.DOMAIN_GROUPS``.

The labeler assigns, the reviewer (another model family) sees that label and
writes the type it judges right; the reviewer's answer is final. An item the
reviewer refused keeps the labeler's type; one both refused gets none and is
left out of ``hotword_types`` (the scorer only breaks down typed words).
Every call is archived under ``<source>/llm-log/``; stages resume.

    load.sh volcengine-ark -- python scripts/hotword_bench/annotate.py label --source <v3 source dir>
    load.sh volcengine-ark -- python scripts/hotword_bench/annotate.py review --source <v3 source dir>
    python scripts/hotword_bench/annotate.py build --source <v3 source dir>
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts
from build import REPO, cjk_join, register
from common import DATASETS, JsonlAppender, read_jsonl, sha256_file, write_jsonl
from mine import ask_json, bisect, chunks, client, run_batches

from audio_data_contract import AudioRecord

HERE = Path(__file__).resolve().parent
DOMAIN_SPLIT = "contextasr_speech_zh"


def base_records(recipe) -> dict[str, list[dict]]:
    base_dir = DATASETS / recipe["dataset_id"] / "versions" / recipe["base_version"]
    return {path.name.removesuffix(".jsonl.gz"): read_jsonl(path)
            for path in sorted((base_dir / "records").glob("*.jsonl.gz"))}


def context(text: str, word: str, width: int) -> str:
    """The sentence around the first occurrence of ``word`` (``width`` characters each side)."""
    start = text.find(word)
    if start < 0:
        start = text.lower().find(word.lower())
    if start < 0:  # the scorer's normalization matched it (spacing, punctuation): show the start
        return text[: 2 * width] + ("…" if len(text) > 2 * width else "")
    lo, hi = max(0, start - width), start + len(word) + width
    return ("…" if lo else "") + text[lo:hi] + ("…" if hi < len(text) else "")


def type_items(recipe, by_split) -> list[dict]:
    """One item per (record, distinct gold word) of the evaluated splits."""
    items = []
    for split, rows in by_split.items():
        if split == "quarantine":
            continue
        for row in rows:
            width = recipe["context_chars"][row["language"]]
            for word in dict.fromkeys(row["hotwords"]):
                items.append({"id": row["id"], "word": word,
                              "context": context(row["target"], word, width)})
    return items


def domain_items(by_split) -> list[str]:
    return sorted({row["labels"]["domain"] for row in by_split.get(DOMAIN_SPLIT, [])})


def label(recipe, source):
    by_split = base_records(recipe)
    llm_cfg = recipe["llm"]

    labeler = client(recipe, "labeler", source, "types")
    path = source / "mined" / "types.jsonl"
    out = JsonlAppender(path)
    done = {(r["id"], r["word"]) for r in read_jsonl(path)}
    todo = [it for it in type_items(recipe, by_split) if (it["id"], it["word"]) not in done]

    def work(batch):
        lines = "\n".join(f"[{i}] 热词：{it['word']}\n    句子：{it['context']}" for i, it in enumerate(batch, 1))
        results = ask_json(labeler, [{"role": "system", "content": prompts.TYPE_SYSTEM},
                                     {"role": "user", "content": lines}], tag="types")
        got = {int(r["id"]): r.get("type") for r in results if isinstance(r, dict) and "id" in r}
        for i, it in enumerate(batch, 1):
            if got.get(i) in prompts.TYPES:  # anything else is retried on the next run
                out.append({"id": it["id"], "word": it["word"], "type": got[i]})

    print(f"types: {len(todo)} to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["type_batch"]),
                bisect(work, lambda it: out.append({"id": it["id"], "word": it["word"], "type": None,
                                                    "refused": True})),
                llm_cfg["workers"], "types")

    labeler = client(recipe, "labeler", source, "domains")
    path = source / "mined" / "domains.jsonl"
    out = JsonlAppender(path)
    done = {r["domain"] for r in read_jsonl(path)}
    todo = [d for d in domain_items(by_split) if d not in done]

    def work_domains(batch):
        lines = "\n".join(f"[{i}] {d}" for i, d in enumerate(batch, 1))
        results = ask_json(labeler, [{"role": "system", "content": prompts.DOMAIN_SYSTEM},
                                     {"role": "user", "content": lines}], tag="domains")
        got = {int(r["id"]): r.get("group") for r in results if isinstance(r, dict) and "id" in r}
        for i, d in enumerate(batch, 1):
            if got.get(i) in prompts.DOMAIN_GROUPS:
                out.append({"domain": d, "group": got[i]})

    print(f"domains: {len(todo)} to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["domain_batch"]),
                bisect(work_domains, lambda d: out.append({"domain": d, "group": None, "refused": True})),
                llm_cfg["workers"], "domains")


def review(recipe, source):
    by_split = base_records(recipe)
    llm_cfg = recipe["llm"]

    reviewer = client(recipe, "reviewer", source, "types-review")
    path = source / "mined" / "types-review.jsonl"
    out = JsonlAppender(path)
    done = {(r["id"], r["word"]) for r in read_jsonl(path)}
    proposed = {(r["id"], r["word"]): r["type"] for r in read_jsonl(source / "mined" / "types.jsonl")}
    todo = [{**it, "proposed": proposed[key]} for it in type_items(recipe, by_split)
            if (key := (it["id"], it["word"])) in proposed and key not in done]

    def work(batch):
        lines = "\n".join(f"[{i}] 热词：{it['word']}  标注：{it['proposed'] or ''}\n    句子：{it['context']}"
                          for i, it in enumerate(batch, 1))
        results = ask_json(reviewer, [{"role": "system", "content": prompts.TYPE_REVIEW_SYSTEM},
                                      {"role": "user", "content": lines}], tag="types-review")
        got = {int(r["id"]): r.get("type") for r in results if isinstance(r, dict) and "id" in r}
        for i, it in enumerate(batch, 1):
            if got.get(i) in prompts.TYPES:
                out.append({"id": it["id"], "word": it["word"], "type": got[i]})

    print(f"types-review: {len(todo)} to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["type_batch"]),
                bisect(work, lambda it: out.append({"id": it["id"], "word": it["word"], "type": None,
                                                    "refused": True})),
                llm_cfg["workers"], "types-review")

    reviewer = client(recipe, "reviewer", source, "domains-review")
    path = source / "mined" / "domains-review.jsonl"
    out = JsonlAppender(path)
    done = {r["domain"] for r in read_jsonl(path)}
    proposed = {r["domain"]: r["group"] for r in read_jsonl(source / "mined" / "domains.jsonl")}
    todo = [d for d in domain_items(by_split) if d in proposed and d not in done]

    def work_domains(batch):
        lines = "\n".join(f"[{i}] {d}  归类：{proposed[d] or ''}" for i, d in enumerate(batch, 1))
        results = ask_json(reviewer, [{"role": "system", "content": prompts.DOMAIN_REVIEW_SYSTEM},
                                      {"role": "user", "content": lines}], tag="domains-review")
        got = {int(r["id"]): r.get("group") for r in results if isinstance(r, dict) and "id" in r}
        for i, d in enumerate(batch, 1):
            if got.get(i) in prompts.DOMAIN_GROUPS:
                out.append({"domain": d, "group": got[i]})

    print(f"domains-review: {len(todo)} to do ({len(done)} done)", file=sys.stderr)
    run_batches(chunks(todo, llm_cfg["domain_batch"]),
                bisect(work_domains, lambda d: out.append({"domain": d, "group": None, "refused": True})),
                llm_cfg["workers"], "domains-review")


def final(labels: list[dict], reviews: list[dict], key, field) -> tuple[dict, Counter]:
    """Reviewer's answer, else (reviewer refused) the labeler's; both refused -> absent."""
    proposed = {key(r): r[field] for r in labels}
    reviewed = {key(r): r[field] for r in reviews}
    missing = set(proposed) - set(reviewed)
    if missing:
        raise ValueError(f"{len(missing)} labels not reviewed yet, e.g. {sorted(missing)[:3]}")
    out, stats = {}, Counter()
    for k, first in proposed.items():
        second = reviewed[k]
        value = second or first
        if value:
            out[k] = value
        stats["agreed" if first and first == second else "changed" if first and second
              else "reviewer_only" if second else "unreviewed" if first else "unlabeled"] += 1
    return out, stats


def build(recipe, source, out_dir=None):
    version, base_version, dataset_id = recipe["version"], recipe["base_version"], recipe["dataset_id"]
    base_dir = DATASETS / dataset_id / "versions" / base_version
    version_dir = out_dir or DATASETS / dataset_id / "versions" / version
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace: {version_dir}")
    by_split = base_records(recipe)
    mined = source / "mined"
    labels = read_jsonl(mined / "types.jsonl")
    pending = {(it["id"], it["word"]) for it in type_items(recipe, by_split)} - {(r["id"], r["word"]) for r in labels}
    if pending:
        raise ValueError(f"{len(pending)} gold words not labeled yet, e.g. {sorted(pending)[:3]}")
    types, type_stats = final(labels, read_jsonl(mined / "types-review.jsonl"), lambda r: (r["id"], r["word"]), "type")
    groups, group_stats = final(read_jsonl(mined / "domains.jsonl"), read_jsonl(mined / "domains-review.jsonl"),
                                lambda r: r["domain"], "group")
    if set(domain_items(by_split)) - set(groups):
        raise ValueError(f"domains without a group: {sorted(set(domain_items(by_split)) - set(groups))[:5]}")

    out_split, counts = {}, defaultdict(Counter)
    for split, rows in by_split.items():
        out_split[split] = []
        for row in rows:
            record = copy.deepcopy(row)
            record["id"] = version + record["id"].removeprefix(base_version)
            record["audio_slots"][0]["ref"]["version"] = version
            if split != "quarantine" and row["hotwords"]:
                record["metadata"]["hotword_types"] = {
                    w: types[(row["id"], w)] for w in dict.fromkeys(row["hotwords"]) if (row["id"], w) in types}
                counts[split].update(record["metadata"]["hotword_types"].values())
            if split == DOMAIN_SPLIT:
                record["labels"]["domain_group"] = groups[row["labels"]["domain"]]
                counts[f"{split}:domain_group"][record["labels"]["domain_group"]] += 1
            AudioRecord.from_dict(record)
            out_split[split].append(record)
    for split, rows in out_split.items():
        write_jsonl(version_dir / "records" / f"{split}.jsonl.gz", rows)
    for name in ("audio-index.jsonl.gz", "hotword-pools.jsonl.gz"):
        shutil.copy(base_dir / name, version_dir / name)
    print("types:", dict(type_stats), "domains:", dict(group_stats), file=sys.stderr)
    print(json.dumps({k: dict(v.most_common()) for k, v in counts.items()}, ensure_ascii=False), file=sys.stderr)
    if not out_dir:
        register(v3_declaration(recipe, version_dir, out_split, counts, type_stats))


def v3_declaration(recipe, version_dir, by_split, counts, type_stats):
    """v2's catalog entry with v3 paths and hashes, label statistics and provenance."""
    version, base_version = recipe["version"], recipe["base_version"]
    rows = yaml.safe_load((REPO / "catalog" / f"{recipe['dataset_id']}.yaml").read_text())
    spec = copy.deepcopy(next(r for r in rows if r["version"] == base_version))
    spec["version"] = version
    for artifact in spec["artifacts"]:
        artifact["relative_path"] = artifact["relative_path"].replace(
            f"/versions/{base_version}/", f"/versions/{version}/")
        artifact["sha256"] = sha256_file(DATASETS.parent / artifact["relative_path"])
    for split, entry in spec["splits"].items():
        if len(by_split[split]) != entry["statistics"]["records"]:
            raise ValueError(f"{split}: {len(by_split[split])} records, {base_version} has {entry['statistics']['records']}")
        if counts.get(split):
            entry["statistics"]["hotword_types"] = dict(sorted(counts[split].items()))
        if counts.get(f"{split}:domain_group"):
            entry["statistics"]["domain_groups"] = dict(sorted(counts[f"{split}:domain_group"].items()))
    llm = recipe["llm"]
    reviewed = sum(type_stats.values()) - type_stats["unreviewed"] - type_stats["unlabeled"]
    provenance = spec["provenance"]
    provenance["description"] = cjk_join(f"""热词评测集 v3，只用于评测，不进训练。记录、音频、正确词和全部列表与
        {base_version} 相同（请求逐条一致，总指标可与 {base_version} 直接比较），另加两种标签：
        metadata.hotword_types 为每个正确词按所在句子的意思标的类型（{' / '.join(prompts.TYPES)}），
        contextasr_speech_zh 的 labels.domain_group 把 ContextASR 自带的自由文本领域归到
        {len(prompts.DOMAIN_GROUPS)} 个大类。{llm['labeler']['model']} 标注，{llm['reviewer']['model']}
        看着标注复核并以复核为准（类型复核后不变的占 {type_stats['agreed'] / reviewed:.1%}）。
        生成脚本 scripts/hotword_bench/annotate.py，类型定义见 prompts.py。""")
    provenance["sources"] = [f"hotword_bench@{base_version}"]
    provenance["limitations"] = cjk_join(provenance["limitations"] + """类型和领域大类是 LLM 标签，
        未经人工核对；一个正确词只有一个类型，作品名里含人名等嵌套情况按整体归类。""")
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["label", "review", "build"])
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-v3.yaml")
    parser.add_argument("--source", type=Path, required=True, help="v3 source dir (mined labels, LLM log)")
    parser.add_argument("--out", type=Path, help="build: write here instead of the version directory (no registration)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    args.source.mkdir(parents=True, exist_ok=True)
    if args.stage == "label":
        label(recipe, args.source)
    elif args.stage == "review":
        review(recipe, args.source)
    else:
        build(recipe, args.source, args.out)


if __name__ == "__main__":
    main()
