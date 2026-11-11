#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for the hotword benchmark.

    python scripts/hotword_bench/eval_set.py > data.yaml                                  # v1
    python scripts/hotword_bench/eval_set.py --recipe scripts/hotword_bench/recipe-v2.yaml > data.yaml  # v2
    python scripts/hotword_bench/eval_set.py --recipe scripts/hotword_bench/recipe-v3.yaml > data.yaml  # v3
    python scripts/hotword_bench/eval_set.py --recipe scripts/hotword_bench/recipe-es-v1.yaml > data.yaml  # es-v1
    ae eval-sets publish data.yaml --project open-audio-llm --name hotword-bench --version <version>

Run it with ``ae open-audio-llm after-training`` (evaluator ``hotwords``,
``samples_per_source: 0``): every record is sent once with no list and once per
stored list; the summary's ``hotword_bench`` block has CER/WER, B-/U-error
rate, recall / precision / F1 and false alarms per source and condition (v3:
also per gold-word type, ``breakdowns.<source>/<condition>.hotword_type``).
``validation`` (Dev-AISHELL1-NE) is for checkpoint selection and is not scored
by the hotword evaluator.
"""

import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# split, label, tags, display, description
SOURCES = [
    ("aishell1_ne_test", "aishell1-ne", ["zh"], "AISHELL1-NE",
     "SeACo-Paraformer Test-AISHELL1-NE（808 句，官方热词表 400 词）；可与论文对照（official 条件、R1 召回）"),
    ("contextasr_speech_zh", "contextasr-speech-zh", ["zh", "synthetic"], "ContextASR Speech-ZH",
     "ContextASR-Bench Speech-Mandarin 全量（TTS 合成、多领域实体）；gold 条件即论文的 fine context"),
    ("real_zh", "real-zh", ["zh"], "真实口语",
     "SpeechIO 27 个子集 + WenetSpeech test_net/test_meeting，热词由 LLM 抽取并复核"),
    ("cv_zh", "cv-zh", ["zh"], "Common Voice 中文", "Common Voice zh-CN 测试集已有热词标注，2,000 条正例"),
    ("aishell2", "aishell2", ["zh"], "AISHELL-2", "AISHELL-2 测试集已有热词标注，全部正例"),
    ("aishell3", "aishell3", ["zh"], "AISHELL-3", "AISHELL-3 测试集已有热词标注，2,000 条正例"),
    ("kespeech", "kespeech", ["zh", "dialect"], "KeSpeech", "KeSpeech 测试集（方言口音普通话）已有热词标注，2,000 条正例"),
    ("gigaspeech_test", "gigaspeech", ["en"], "GigaSpeech",
     "GigaSpeech 测试集全量，按 SALMONN-2 协议重建的 L=20/50/100 列表"),
    ("librispeech_test_clean", "librispeech-clean", ["en"], "LibriSpeech clean", "Le et al. 官方 N=100/1000 列表"),
    ("librispeech_test_other", "librispeech-other", ["en"], "LibriSpeech other", "Le et al. 官方 N=100/1000 列表"),
    ("cv_en", "cv-en", ["en"], "Common Voice 英文", "Common Voice en 测试集已有热词标注，2,000 条正例"),
]


# v2 (recipe-v2.yaml) replaces the Chinese k50 / k50_no_gold with lists retrieved from hotword pools;
# v3 (recipe-v3.yaml) keeps v2's lists and adds gold-word types
GROUP_NOTES = {
    "v1": ("主条件 k50（正确词 + 易混词 + 随机词共 50 个）看 B-CER 与 F1；k50_no_gold 看误触发率与 CER 变化",
           "GigaSpeech l20/l50/l100、LibriSpeech n100/n1000 可与论文对照；cv-en 同中文的 k50 条件"),
    "v2": (("主条件 pool50（正确词 + 从约 1 万词的热词池检索出的干扰词共 50 个）看 B-CER 与 F1；"
            "pool50_no_gold 看误触发率与 CER 变化"),
           "GigaSpeech l20/l50/l100、LibriSpeech n100/n1000 可与论文对照；cv-en 为 k50（正确词 + 随机词）"),
}
GROUP_NOTES["v3"] = tuple(f"{note}；hotword_type 分项看各类热词的召回与误触发" for note in GROUP_NOTES["v2"])


# es-v1 (recipe-es-v1.yaml): the Spanish splits; AmphionEval has no es tag, so sources carry only the shared ones
ES_SOURCES = [
    ("cv_es", "cv-es", "Common Voice 西语", "Common Voice es 测试集已有热词标注，2,000 条正例"),
    ("fleurs_es", "fleurs-es", "FLEURS 西语", "FLEURS es 测试集已有热词标注，全部 362 条正例（约 145 句话，多个说话人）"),
    ("mls_es", "mls-es", "MLS 西语", "MLS es 测试集（有声书，转写全小写无标点）已有热词标注，全部 907 条正例"),
]
ES_NOTE = ("主条件 k50（正确词 + 按西语读音键检索出的近音词 + 随机词共 50 个）看 B-WER 与 F1；"
           "k50_no_gold 看误触发率与 WER 变化")


def es_config(recipe):
    return {
        "task": "asr",
        "tags": ["hotwords"],
        "groups": [{"name": "热词 · 西语", "section": "西班牙语", "labels": [s[1] for s in ES_SOURCES],
                    "aggregate": "macro", "description": ES_NOTE}],
        "sampling_rate": recipe["sample_rate"],
        "evaluation": [{"dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": split,
                        "task": "asr_hotwords", "label": label, "display": display, "description": description}
                       for split, label, display, description in ES_SOURCES],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    recipe = yaml.safe_load(parser.parse_args().recipe.read_text())
    if recipe["version"].startswith("es-"):
        print(yaml.safe_dump(es_config(recipe), allow_unicode=True, sort_keys=False, width=200), end="")
        return
    zh_note, en_note = GROUP_NOTES[recipe["version"].split("-", 1)[0]]

    def source(split, label, tags, display, description):
        return {"dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": split,
                "task": "asr_hotwords", "label": label, "tags": tags, "display": display,
                "description": description}

    zh = [s[1] for s in SOURCES if "zh" in s[2]]
    en = [s[1] for s in SOURCES if "en" in s[2]]
    config = {
        "task": "asr",
        "tags": ["hotwords"],
        "groups": [
            {"name": "热词 · 中文", "section": "中文", "labels": zh, "aggregate": "macro",
             "description": zh_note},
            {"name": "热词 · 英文", "section": "英文", "labels": en, "aggregate": "macro",
             "description": en_note},
        ],
        "sampling_rate": recipe["sample_rate"],
        "validation": [source("aishell1_ne_dev", "aishell1-ne-dev", ["zh"], "AISHELL1-NE dev",
                              "SeACo-Paraformer Dev-AISHELL1-NE（1,334 句，官方热词表 600 词），用于挑选")],
        "evaluation": [source(*row) for row in SOURCES],
    }
    print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), end="")


if __name__ == "__main__":
    main()
