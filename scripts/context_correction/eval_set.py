#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for the context-correction benchmark (v2: the v1 splits
unchanged, plus the v2 splits built from recipe_v2_indep.yaml).

    python scripts/context_correction/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name context-correction-zh --version <version>

Run it with ``ae open-audio-llm after-training`` (evaluator ``ts-asr``): the
``context_correction`` block of the summary holds correction, keep, evidence,
conditional-correction and pair metrics, also by source and by ``train_overlap``
(seen / unseen in the training data, v2 splits only); the per-source CER is the usual guard.
"""

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# (recipe, split, task, label, display, description)
SOURCES = [
    ("recipe.yaml", "synthetic", "asr", "synthetic", "合成 · 同源 · 普通 ASR",
     "LLM 生成的成对题目，Qwen3-TTS 用测试划分说话人的声音合成；显式说字、同名一致性、隐式语义。与训练数据同一生成器，只当同分布参考"),
    ("recipe.yaml", "synthetic_ts", "ts_asr", "synthetic_ts", "合成 · 同源 · TS 模式",
     "同一批题目中不超过 26.5 秒的部分，配同一说话人的真实注册音频（客户实际使用的模式）"),
    ("recipe.yaml", "mined_real", "asr", "mined_real", "真实录音 · 播客 · 普通 ASR",
     "从 WenetSpeech 播客挖掘、两个 LLM 一致标注的真实录音"),
    ("recipe_v2_indep.yaml", "synthetic_indep", "asr", "synthetic_indep", "合成 · 独立 · 普通 ASR",
     "另一套生成器出题、两家复核，CosyVoice3 用训练没用过的说话人合成；含训练没有的题型（专名指代、字义说明、逐字说明、对话问答）"),
    ("recipe_v2_indep.yaml", "synthetic_indep_ts", "ts_asr", "synthetic_indep_ts", "合成 · 独立 · TS 模式",
     "同一批独立题中不超过 26.5 秒的单人题，配同一说话人的真实注册音频"),
    ("recipe_v2_indep.yaml", "mined_real", "asr", "mined_real_emilia", "真实录音 · Emilia · 普通 ASR",
     "从原版 Emilia-ZH 挖掘、两个 LLM 一致标注的真实录音（该语料不在训练配方里）"),
]
GROUPS = [
    ("上下文纠偏 · 合成 · 同源", ["synthetic"],
     "看 summary 的 context_correction：纠正成功率、保持率（误改率）、说明识别率、条件纠正率、成对正确率"),
    ("上下文纠偏 · TS 模式 · 同源", ["synthetic_ts"], "同上，TS-ASR 请求（注册音频 + 识别片段）"),
    ("上下文纠偏 · 合成 · 独立", ["synthetic_indep"], "同上；与同源组的差距就是只学会训练模板的程度"),
    ("上下文纠偏 · TS 模式 · 独立", ["synthetic_indep_ts"], "同上，TS-ASR 请求"),
    ("上下文纠偏 · 真实录音", ["mined_real", "mined_real_emilia"],
     "真实录音；每条单独成题（没有成对的确认题），看 mined_accuracy，按 source 和 train_overlap 分开看"),
]


def main():
    recipes = {name: yaml.safe_load((HERE / name).read_text()) for name in {s[0] for s in SOURCES}}
    rates = {r["sample_rate"] for r in recipes.values()}
    if len(rates) != 1:
        raise ValueError(f"recipes disagree on the sample rate: {rates}")
    config = {
        "tags": ["zh", "context-correction"],
        "groups": [{"name": name, "section": "上下文纠偏", "labels": labels, "description": description}
                   for name, labels, description in GROUPS],
        "sampling_rate": rates.pop(),
        "evaluation": [
            {"dataset_id": recipes[recipe]["dataset_id"], "version": recipes[recipe]["version"], "split": split,
             "task": task, "label": label, "tags": ["zh", "context-correction"], "display": display,
             "description": description}
            for recipe, split, task, label, display, description in SOURCES
        ],
    }
    print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), end="")


if __name__ == "__main__":
    main()
