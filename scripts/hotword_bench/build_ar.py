#!/usr/bin/env python3
"""Build and register hotword_bench ar-v1: Arabic splits with fixed biasing lists (CPU only).

The Arabic counterpart of es-v1 / pt-v1 (``build_es.py`` / ``build_pt.py``), same recipe layout, list conditions
(gold / k50 / k50_no_gold), per-split QC gates and registration; only the language differs:

- ``strip_accents`` folds Arabic spelling variants the way AmphionEval scores Arabic (the Open Universal Arabic ASR
  Leaderboard normalizer plus tatweel and superscript alef): diacritics dropped, alef / hamza seats unified, so a
  candidate that differs from the gold word only by diacritics or hamza spelling is a variant, not a confusable;
- ``reading_key`` merges consonants an ASR system confuses by ear (emphatic and plain pairs, ث / س, ذ / ز, ح / ه,
  ق / ك, غ / خ, ع / ا ...), so confusables are real Arabic hotwords whose reading is close to the gold word's;
- descriptions and the catalog text are Arabic-specific.

    python scripts/hotword_bench/build_ar.py --workers 32
    python scripts/hotword_bench/build_ar.py --smoke 50 --out <scratch dir>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_es
from build import cjk_join
from common import normalize

HERE = Path(__file__).resolve().parent
DESCRIPTIONS = {
    "cv_ar": "Common Voice 24.0 ar 测试集（众包朗读，句子以标准阿拉伯语为主，部分带元音符号），阿拉伯语热词标注（Qwen3.8-27B 抽取 + 复核），按 sha256(id) 取前 N 条正例",
    "fleurs_ar": "FLEURS ar_eg 测试集（朗读维基句子，同一句话有多个说话人），阿拉伯语热词标注，全部正例",
    "mgb2_ar": "MGB-2 测试集（半岛电视台节目分段，以标准阿拉伯语为主、夹杂方言，真实广播），阿拉伯语热词标注，全部正例",
    "quarantine": "不参与打分：时长越界的条目，保留原因",
}

DIACRITICS = re.compile("[ً-ْٰـ]")  # harakat, superscript alef, tatweel
FOLD = str.maketrans({"پ": "ب", "ڤ": "ف", "آ": "ا", "أ": "ا", "إ": "ا", "ؤ": "و", "ئ": "ي", "ء": None,
                      **{chr(0x0660 + i): str(i) for i in range(10)}})
# Consonant classes by ear, applied to the folded word: emphatic / plain pairs and the pairs dialects merge.
READING = str.maketrans({
    "ص": "s", "س": "s", "ث": "s", "ز": "z", "ذ": "z", "ظ": "z", "ت": "t", "ط": "t", "ة": "h", "د": "d", "ض": "d",
    "ه": "h", "ح": "h", "ا": "a", "ع": "a", "ى": "a", "ٱ": "a", "ق": "k", "ك": "k", "غ": "x", "خ": "x",
    "ي": "y", "و": "w", "ج": "j", "ش": "S", "ف": "f", "ب": "b", "م": "m", "ن": "n", "ل": "l", "ر": "r",
})


def strip_accents(text):
    """Arabic text as AmphionEval compares it: no diacritics or tatweel, alef / hamza seats unified, Western digits."""
    return " ".join(DIACRITICS.sub("", text).translate(FOLD).split())


def reading_key(word):
    """Approximate Arabic reading of a word or phrase (consonant classes, words joined by one space)."""
    words = []
    for token in strip_accents(normalize(word)).split():
        token = "".join(c for c in token if c.isalpha()).translate(READING)
        collapsed = "".join(c for i, c in enumerate(token) if i == 0 or c != token[i - 1])
        if collapsed:
            words.append(collapsed)
    return " ".join(words)


def declaration(recipe, by_split, index, version_dir, source, vocabulary_size, report):
    spec = ORIGINAL_DECLARATION(recipe, by_split, index, version_dir, source, vocabulary_size, report)
    version = recipe["version"]
    spec["provenance"]["description"] = cjk_join(f"""阿拉伯语热词评测集，与西语 es-v1-20261111、葡语 pt-v1-20261117 同一做法（对应中英 v3-20261020 的 cv_zh / cv_en），只用于评测，不进训练。
        三个阿拉伯语测试集（Common Voice 24.0 ar、FLEURS ar_eg、MGB-2 广播）里含热词的句子，热词由 Qwen3.8-27B 抽取 + 复核
        （label_hotwords.py，与西语、葡语同设置；原始标注 {recipe['labels']['path']}）。
        每条记录存好固定的热词列表（metadata.bias_lists，已打乱顺序），评测器另跑不给列表的 none 条件：gold；k50 = 正确词 + 每个正确词最多
        {recipe['confusables_per_word']} 个近音词 + 同 split 正确词池随机词，补到 {recipe['list_size']} 个；
        k50_no_gold 为同一批干扰词去掉正确词再补满。近音词是在 {vocabulary_size:,} 个阿拉伯语热词（测试集正确词 +
        MGB-2 train 与 CV 24.0 ar train 转写的热词标注）里按阿拉伯语读音键（强调音与普通音、ث/س、ذ/ز、ح/ه、ق/ك、غ/خ、ع/ا 等归为一类）
        的编辑距离检索出的真实词（检索只用 CPU）；只差元音符号或 hamza 写法的词算同一个词，不当近音词。
        原始候选见 source/{version}/mined/confusables.jsonl。生成脚本 scripts/hotword_bench/build_ar.py，配方 recipe-ar-v1.yaml。""")
    spec["provenance"]["sources"] = [*(s["dataset"] for s in recipe["sources"].values()),
                                     f"{recipe['labels']['path']} (Qwen3.8-27B hotword labels)",
                                     "common_voice_ar@legacy:train, mgb2@legacy:train (overlap check)",
                                     ("mgb2@legacy:train, common_voice_ar@legacy:train transcripts (confusable vocabulary only: "
                                      f"Qwen3.8-27B hotword labels, source/{version}-vocabulary)")]
    spec["provenance"]["limitations"] = cjk_join("""热词来自 LLM 抽取与复核，未经人工核对；没有中文 v3 的 hotword_types（需要 LLM 标注）；
        没有阿拉伯语现网词库，不做中文 v2 的 pool50 检索列表；近音词按拼写推出的读音键检索，不是声学相似度，也不覆盖方言读法与外来专名的原语读法；少数近音词只是同一专名带不带冠词 ال 的写法（如 رجب طيب أردوغان / رجب الطيب أردوغان）；
        CV 原文部分带元音符号，热词保留原文写法（打分时 AmphionEval 去掉元音符号、统一 hamza 写法）；FLEURS 同一句话有多个说话人。""")
    return spec


ORIGINAL_DECLARATION = build_es.declaration
build_es.LANGUAGE = "ar"
build_es.DESCRIPTIONS = DESCRIPTIONS
build_es.reading_key = reading_key
build_es.strip_accents = strip_accents
build_es.declaration = declaration
build_es.HERE = HERE


if __name__ == "__main__":
    if not any(a.startswith("--recipe") for a in sys.argv[1:]):
        sys.argv[1:1] = ["--recipe", str(HERE / "recipe-ar-v1.yaml")]
    build_es.main()
