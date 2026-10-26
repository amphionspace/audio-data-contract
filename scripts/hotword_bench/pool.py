#!/usr/bin/env python3
"""Register hotword_bench v2: the v1 records with Chinese lists retrieved from hotword pools.

v2 keeps v1's records, audio, gold words and every other list condition. On the
Chinese splits it replaces ``k50`` / ``k50_no_gold`` (gold + confusables + random
words of the split) with lists taken the way a deployment takes them, the
Top-50 of a retriever over a hotword pool:

- ``pool50``: the gold words + the best-scoring other entries of the pool, 50 in all;
- ``pool50_no_gold``: the 50 best-scoring entries that are not gold words.

Pools are per tenant: the base library (the deployed Chinese library, rebuilt
from the lists the online RAG returned, see ``library`` in recipe-v2.yaml) plus
the tenant's own words, i.e. the gold words of its utterances and up to
``confusables_per_word`` reviewed confusables of each. Utterances are grouped
by ``tenant_group`` (real_zh subset, ContextASR seed corpus, else the split)
and dealt in sha256 order into tenants of about ``tenant_size``.

The query is the reference text, so lists do not depend on any evaluated model.
Scores follow open-audio-llm ``retrieve_hotwords._retrieve_zh`` without its
score > 1.0 cut (the online RAG always returns 50); ties break by sha256. As in
v1, an entry the normalized reference contains is never a distractor.
``metadata.distractor_kinds`` marks each distractor ``confusable`` (a reviewed
confusable of this utterance's gold word), ``tenant`` (another word of the
tenant) or ``base`` (library). ``hotword-pools.jsonl.gz`` stores every pool.

    python scripts/hotword_bench/pool.py --source <v2 source dir>
    python scripts/hotword_bench/pool.py --source <v2 source dir> --smoke 20 --out <scratch dir>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pypinyin
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import cjk_join, declaration, register, reviewed_confusables
from common import (
    DATASETS,
    compact,
    contains,
    order_key,
    read_jsonl,
    sha256_file,
    write_jsonl,
)

from audio_data_contract import AudioRecord

HERE = Path(__file__).resolve().parent
REPLACED = ("k50", "k50_no_gold")
CJK = re.compile(r"[一-鿿]")


# -------------------------------------------------------------- retriever ---
# Same features and weights as open-audio-llm retrieve_hotwords._retrieve_zh
# (its own _normalize, _char_ngrams and _to_pinyin), so a word ranks here as it
# would there; only the score > 1.0 cut is dropped.

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _bigrams(text: str) -> set:
    t = _normalize(text).replace(" ", "")
    if len(t) < 2:
        return {t} if t else set()
    return {t[i: i + 2] for i in range(len(t) - 1)}


def _pinyin(text: str) -> list[str]:
    out = []
    for seg in re.findall(r"[一-鿿]+|[^一-鿿]+", text):
        if CJK.search(seg):
            out.extend(pypinyin.lazy_pinyin(seg, style=pypinyin.Style.NORMAL))
        else:
            out.append(seg.lower().strip())
    return " ".join(w for w in out if w).split()


def entry_features(word: str):
    return word, _normalize(word).replace(" ", ""), _bigrams(word), _pinyin(word)


def score_all(entries, query: str) -> list[tuple[float, str]]:
    q_norm = _normalize(query).replace(" ", "")
    q_chars, q_bigrams, q_py = set(q_norm), _bigrams(query), _pinyin(query)
    positions = defaultdict(list)
    for i, syllable in enumerate(q_py):
        positions[syllable].append(i)
    scored = []
    for word, norm, bigrams, py in entries:
        substring = 1.0 if norm and norm in q_norm else 0.0
        overlap = sum(1 for c in norm if c in q_chars) / len(norm) if norm else 0.0
        union = len(bigrams) + len(q_bigrams) - len(bigrams & q_bigrams)
        jaccard = len(bigrams & q_bigrams) / union if bigrams and q_bigrams else 0.0
        pinyin = 0.0
        if py and q_py:
            recall = sum(1 for p in py if p in positions) / len(py)
            if recall > 0:
                if len(py) > len(q_py):
                    pinyin = recall
                else:
                    # windows that align at least one syllable; the others score 0
                    starts = {pos - i for i, p in enumerate(py) for pos in positions.get(p, ())
                              if 0 <= pos - i <= len(q_py) - len(py)}
                    best = max((sum(1 for a, b in zip(py, q_py[s: s + len(py)]) if a == b)
                                for s in starts), default=0)
                    pinyin = best / len(py)
        scored.append((substring * 2.0 + pinyin * 1.5 + overlap * 0.5 + jaccard * 0.3, word))
    return scored


# ------------------------------------------------------------------ pools ---

def base_library(spec) -> list[str]:
    """Every word the online RAG returned (all are library members) plus the target words."""
    root = Path(spec["repo"]) / spec["dir"]
    words = set()
    for name in spec["results"]:
        for row in read_jsonl(root / name):
            if row["language"].startswith("zh"):
                words.update(row["top_50"])
    for name in spec["targets"]:
        for row in read_jsonl(root / name):
            if row["language"].startswith("zh"):
                words.update(t["word"] for t in row["targets"])
    return sorted(w.strip() for w in words if w.strip())


def tenants(recipe, split, records):
    """tenant id -> records; groups by ``tenant_group`` then deals sha256-ordered records round-robin."""
    field = recipe["tenant_group"].get(split)
    groups = defaultdict(list)
    for record in records:
        groups[record["labels"][field] if field else split].append(record)
    out = {}
    for group, rows in sorted(groups.items()):
        rows.sort(key=lambda r: order_key(recipe["seed"], split, r["id"]))
        n = max(1, round(len(rows) / recipe["tenant_size"]))
        for i in range(n):
            out[f"{split}/{group}/{i:02d}"] = rows[i::n]
    return out


def tenant_pool(rows, library, confusables, cap):
    """Pool words in priority order (gold, confusable, base), one entry per normalized form."""
    own = {}
    for record in rows:
        for word in record["hotwords"]:
            own.setdefault(word, "gold")
    for record in rows:
        for word in record["hotwords"]:
            for alt in confusables.get(word, [])[:cap]:
                own.setdefault(alt, "confusable")
    pool, seen = [], set()
    for word in [*own, *library]:
        key = compact(word, "zh")
        if key and key not in seen:
            seen.add(key)
            pool.append(word)
    return pool, own


def tenant_lists(job):
    """bias lists and distractor kinds for every record of one tenant."""
    recipe, rows, pool, own, confusables = job
    size, seed, cap = recipe["list_size"], recipe["seed"], recipe["confusables_per_word"]
    entries = [entry_features(w) for w in pool]
    tie = {w: order_key(seed, "tie", w) for w in pool}
    out = {}
    for record in rows:
        text, gold = record["target"], list(record["hotwords"])
        alternates = {a for w in gold for a in confusables.get(w, [])[:cap]}
        ranked = sorted(score_all(entries, text), key=lambda item: (-item[0], tie[item[1]]))
        distractors = []
        for _, word in ranked:
            if len(distractors) >= size:
                break
            if word not in gold and not contains(text, word, "zh"):
                distractors.append(word)
        kinds = {w: "confusable" if w in alternates else "tenant" if w in own else "base" for w in distractors}
        lists = {}
        if gold:
            lists["gold"] = record["metadata"]["bias_lists"]["gold"]
            chosen = gold + distractors[: max(0, size - len(gold))]
            lists["pool50"] = sample(seed, record["id"], "pool50", chosen)
            lists["pool50_no_gold"] = sample(seed, record["id"], "pool50_no_gold", distractors)
        else:
            lists["pool50"] = sample(seed, record["id"], "pool50", distractors)
        if "official" in record["metadata"]["bias_lists"]:
            lists["official"] = record["metadata"]["bias_lists"]["official"]
        used = {w for words in lists.values() for w in words}
        out[record["id"]] = (lists, {w: k for w, k in kinds.items() if w in used})
    return out


def sample(seed, record_id, condition, words):
    """Send order: shuffled by sha256, so the gold word's place says nothing."""
    return sorted(words, key=lambda w: order_key(seed, record_id, condition, w))


# ------------------------------------------------------------------- main ---

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-v2.yaml")
    parser.add_argument("--base-recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True, help="v2 source dir (library and build log)")
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--smoke", type=int, help="first N records per Chinese split, needs --out")
    parser.add_argument("--out", type=Path, help="write here instead of the version directory (no registration)")
    args = parser.parse_args()
    if args.smoke and not args.out:
        parser.error("--smoke needs --out")
    recipe = yaml.safe_load(args.recipe.read_text())
    base_recipe = yaml.safe_load(args.base_recipe.read_text())
    version, base_version, dataset_id = recipe["version"], recipe["base_version"], recipe["dataset_id"]
    if base_recipe["version"] != base_version:
        raise ValueError(f"{args.base_recipe} is {base_recipe['version']}, expected {base_version}")
    base_dir = DATASETS / dataset_id / "versions" / base_version
    version_dir = args.out or DATASETS / dataset_id / "versions" / version
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace: {version_dir}")
    base_source = DATASETS / dataset_id / "source" / base_version
    confusables = reviewed_confusables(base_source, False)

    library = base_library(recipe["library"])
    args.source.mkdir(parents=True, exist_ok=True)
    (args.source / "library-zh.txt").write_text("\n".join(library) + "\n", encoding="utf-8")

    by_split = {path.name.removesuffix(".jsonl.gz"): read_jsonl(path)
                for path in sorted((base_dir / "records").glob("*.jsonl.gz"))}
    jobs, pools = [], []
    for split, rows in by_split.items():
        if split == "quarantine" or rows[0]["language"] != "zh":
            continue
        rows = rows[: args.smoke] if args.smoke else rows
        for tenant, members in tenants(recipe, split, rows).items():
            pool, own = tenant_pool(members, library, confusables, recipe["confusables_per_word"])
            mine = {w: confusables[w] for r in members for w in r["hotwords"] if w in confusables}
            jobs.append((recipe, members, pool, own, mine))
            pools.append({"tenant": tenant, "split": split, "records": [r["id"] for r in members],
                          "pool_size": len(pool), "own_words": own})
    tenant_of = {rid: p["tenant"] for p in pools for rid in p["records"]}
    lists = {}
    with ProcessPoolExecutor(args.workers) as executor:
        for result in executor.map(tenant_lists, jobs):
            lists.update(result)

    stats = Counter()
    out_split = defaultdict(list)
    for split, rows in by_split.items():
        for row in rows:
            if args.smoke and split != "quarantine" and row["language"] == "zh" and row["id"] not in lists:
                continue
            record = json.loads(json.dumps(row))
            record["id"] = version + record["id"].removeprefix(base_version)
            record["audio_slots"][0]["ref"]["version"] = version
            if row["id"] in lists:
                metadata = record["metadata"]
                if set(metadata["bias_lists"]) - {"gold", "official", *REPLACED}:
                    raise ValueError(f"{row['id']}: unexpected conditions {sorted(metadata['bias_lists'])}")
                metadata["bias_lists"], metadata["distractor_kinds"] = lists[row["id"]]
                metadata["pool_tenant"] = tenant_of[row["id"]]
                stats.update(f"{split}: {k}" for k in metadata["distractor_kinds"].values())
            AudioRecord.from_dict(record)
            out_split[split].append(record)

    for split, rows in out_split.items():
        write_jsonl(version_dir / "records" / f"{split}.jsonl.gz", rows)
    write_jsonl(version_dir / "hotword-pools.jsonl.gz",
                [{"tenant": "library", "words": library}, *pools])
    shutil.copy(base_dir / "audio-index.jsonl.gz", version_dir / "audio-index.jsonl.gz")
    print({s: len(r) for s, r in sorted(out_split.items())}, f"tenants: {len(pools)}",
          f"library: {len(library)}", dict(sorted(stats.items())))
    if not args.out:
        register(v2_declaration(recipe, base_recipe, out_split, version_dir, len(pools), len(library)))


def v2_declaration(recipe, base_recipe, by_split, version_dir, n_tenants, n_library):
    index = read_jsonl(version_dir / "audio-index.jsonl.gz")
    spec = declaration({**base_recipe, "version": recipe["version"]}, by_split,
                       {row["cut_id"]: row for row in index}, version_dir)
    pools = version_dir / "hotword-pools.jsonl.gz"
    spec["artifacts"].append({
        "name": "hotword-pools", "kind": "jsonl-metadata", "root_alias": "aidc_data",
        "relative_path": str(pools.relative_to(DATASETS.parent)),
        "sha256": sha256_file(pools),
        "metadata": {"record_count": n_tenants + 1, "library_words": n_library},
    })
    provenance = spec["provenance"]
    provenance["description"] = cjk_join(f"""热词评测集 v2，只用于评测，不进训练。记录、音频、正确词和其余条件与
        {recipe['base_version']} 相同；中文切片的 k50 / k50_no_gold 换成从热词池检索的 pool50 / pool50_no_gold：
        每个租户（约 {recipe['tenant_size']} 句，按子集 / 领域语料分组）一个池 = 现网中文万词库（由现网 RAG 返回结果还原，
        {n_library} 词）+ 租户句子的正确词及其复核易混词；以参考文本为查询，按 open-audio-llm 规则召回的打分公式取得分最高的
        {recipe['list_size']} 个（不设阈值）。pool50 = 正确词 + 检索出的干扰词，pool50_no_gold = 检索出的前
        {recipe['list_size']} 个干扰词；metadata.distractor_kinds 标出 confusable / tenant / base。
        各租户的池在 hotword-pools.jsonl.gz。生成脚本 scripts/hotword_bench/pool.py。""")
    provenance["sources"] = [f"hotword_bench@{recipe['base_version']}",
                             f"audiollm-go {recipe['library']['commit']} {recipe['library']['dir']}（现网中文词库还原）"]
    provenance["limitations"] = cjk_join(provenance["limitations"] + """检索器是文本规则召回、以参考文本为查询，
        不是现网的音频双塔 RAG，正确词总能被召回，召回失败由 pool50_no_gold 单独衡量；基础词库为还原的约 88% 现网词库。""")
    return spec


if __name__ == "__main__":
    main()
