#!/usr/bin/env python3
"""Build and register hotword_bench pt-v1: Portuguese splits with fixed biasing lists (CPU only).

The Portuguese counterpart of es-v1 (``build_es.py``), same recipe layout, list conditions (gold / k50 /
k50_no_gold), per-split QC gates and registration; only the language differs:

- ``reading_key`` is an approximate Brazilian Portuguese reading (ç / ce / ci -> s, nh, lh, ch / x, rr and initial
  r, qu / gu, silent h, nasal vowels, final l -> u, final e / o -> i / u, ...), so confusables are real Portuguese
  hotwords whose reading is close to the gold word's;
- descriptions and the catalog text are Portuguese-specific.

    python scripts/hotword_bench/build_pt.py --workers 32
    python scripts/hotword_bench/build_pt.py --smoke 50 --out <scratch dir>
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_es
from build import cjk_join
from common import normalize

HERE = Path(__file__).resolve().parent
DESCRIPTIONS = {
    "cv_pt": "Common Voice 27.0 pt 测试集（众包朗读，多为巴西口音），葡语热词标注（Qwen3.8-27B 抽取 + 复核），按 sha256(id) 取前 N 条正例",
    "fleurs_pt": "FLEURS pt_br 测试集（朗读维基句子，同一句话有多个说话人），葡语热词标注，全部正例",
    "mls_pt": "MLS pt 测试集（LibriVox 有声书，原标注全小写无标点），葡语热词标注，全部正例",
    "quarantine": "不参与打分：时长越界的条目，保留原因",
}

NASAL = [("ão", "aN"), ("ãe", "aN"), ("õe", "oN"), ("ã", "aN"), ("õ", "oN")]
READING_RULES = [  # applied in order to the accent-free lowercase word (Brazilian reading)
    ("nh", "Y"), ("lh", "L"), ("ch", "S"), ("sh", "S"), ("ph", "f"), ("th", "t"), ("rr", "R"),
    ("sce", "se"), ("sci", "si"), ("xce", "se"), ("xci", "si"), ("ss", "s"),
    ("qu", "k"), ("gue", "Ge"), ("gui", "Gi"), ("ce", "se"), ("ci", "si"), ("ge", "je"), ("gi", "ji"),
    ("c", "k"), ("z", "s"), ("x", "S"), ("w", "u"), ("y", "i"), ("h", ""), ("G", "g"),
]
ENDINGS = [("am", "aN"), ("em", "eN"), ("ens", "eNs"), ("es", "is"), ("os", "us"), ("e", "i"), ("o", "u"), ("l", "u")]


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def reading_key(word):
    """Approximate Brazilian Portuguese reading of a word or phrase (letters only, words joined by one space)."""
    words = []
    for token in normalize(word).split():
        token = "".join(c for c in token.replace("ç", "s") if c.isalpha())
        for old, new in NASAL:
            token = token.replace(old, new)
        token = strip_accents(token)
        for old, new in READING_RULES:
            token = token.replace(old, new)
        if token.startswith("r"):
            token = "R" + token[1:]
        for old, new in ENDINGS:
            if token.endswith(old) and len(token) > len(old):
                token = token[: -len(old)] + new
                break
        token = re.sub(r"[mn](?=[^aeiouAEIOU]|$)", "N", token)
        collapsed = "".join(c for i, c in enumerate(token) if i == 0 or c != token[i - 1])
        if collapsed:
            words.append(collapsed)
    return " ".join(words)


def declaration(recipe, by_split, index, version_dir, source, vocabulary_size, report):
    spec = ORIGINAL_DECLARATION(recipe, by_split, index, version_dir, source, vocabulary_size, report)
    version = recipe["version"]
    spec["provenance"]["description"] = cjk_join(f"""葡语热词评测集，与西语 es-v1-20261111 同一做法（对应中英 v3-20261020 的 cv_zh / cv_en），只用于评测，不进训练。
        三个葡语测试集（Common Voice 27.0 pt、FLEURS pt_br、MLS pt）里含热词的句子，热词由 Qwen3.8-27B 抽取 + 复核
        （label_hotwords.py，与西语同设置；原始标注 {recipe['labels']['path']}）。
        每条记录存好固定的热词列表（metadata.bias_lists，已打乱顺序），评测器另跑不给列表的 none 条件：gold；k50 = 正确词 + 每个正确词最多
        {recipe['confusables_per_word']} 个近音词 + 同 split 正确词池随机词，补到 {recipe['list_size']} 个；
        k50_no_gold 为同一批干扰词去掉正确词再补满。近音词是在 {vocabulary_size:,} 个葡语热词（测试集正确词 +
        葡语训练集热词标注 + YODAS 葡语字幕热词标注）里按葡语（巴西读法）读音键的编辑距离检索出的真实词（检索只用 CPU），
        原始候选见 source/{version}/mined/confusables.jsonl。生成脚本 scripts/hotword_bench/build_pt.py，配方 recipe-pt-v1.yaml。""")
    spec["provenance"]["sources"] = [*(s["dataset"] for s in recipe["sources"].values()),
                                     f"{recipe['labels']['path']} (Qwen3.8-27B hotword labels)",
                                     "common_voice_pt@pt-train-v1-20261117:train, mls_pt@pt-train-v1-20261117:train (confusable vocabulary, overlap check)",
                                     "yodas_granary_es_pt@pt000-clean-v1-20261114 (confusable vocabulary only: Qwen3.8-27B hotword labels, source/pt-v1-20261117-vocabulary)"]
    spec["provenance"]["limitations"] = cjk_join("""热词来自 LLM 抽取与复核，未经人工核对；没有中文 v3 的 hotword_types（需要 LLM 标注）；
        没有葡语现网词库，不做中文 v2 的 pool50 检索列表；近音词按拼写推出的读音键检索（巴西读法），
        不是声学相似度，也不覆盖英文专名的英语读法；FLEURS 同一句话有多个说话人。MLS 转写全小写无标点（旧正字法），热词也是小写。""")
    return spec


ORIGINAL_DECLARATION = build_es.declaration
build_es.LANGUAGE = "pt"
build_es.DESCRIPTIONS = DESCRIPTIONS
build_es.reading_key = reading_key
build_es.strip_accents = strip_accents
build_es.declaration = declaration
build_es.HERE = HERE


if __name__ == "__main__":
    if not any(a.startswith("--recipe") for a in sys.argv[1:]):
        sys.argv[1:1] = ["--recipe", str(HERE / "recipe-pt-v1.yaml")]
    build_es.main()
