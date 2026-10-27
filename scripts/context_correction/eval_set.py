#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for the context-correction benchmark.

    python scripts/context_correction/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name context-correction-zh --version <date>

Run it with ``ae open-audio-llm after-training`` (evaluator ``ts-asr``): the
``context_correction`` block of the summary holds correction, keep, evidence,
conditional-correction and pair metrics; the per-source CER is the usual guard.
"""

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

SOURCES = [
    ("synthetic", "asr", "合成 · 普通 ASR", "LLM 生成的成对题目，Qwen3-TTS 用测试划分说话人的声音合成；显式说字、同名一致性、隐式语义"),
    ("synthetic_ts", "ts_asr", "合成 · TS 模式", "同一批题目中不超过 26.5 秒的部分，配同一说话人的真实注册音频（客户实际使用的模式）"),
    ("mined_real", "asr", "真实录音 · 普通 ASR", "从 WenetSpeech 播客挖掘、两个 LLM 一致标注的真实录音"),
]


def main():
    recipe = yaml.safe_load((HERE / "recipe.yaml").read_text())
    config = {
        "tags": ["zh", "context-correction"],
        "groups": [
            {"name": "上下文纠偏 · 合成", "section": "上下文纠偏", "labels": ["synthetic"],
             "description": "看 summary 的 context_correction：纠正成功率、保持率（误改率）、说明识别率、条件纠正率、成对正确率"},
            {"name": "上下文纠偏 · TS 模式", "section": "上下文纠偏", "labels": ["synthetic_ts"],
             "description": "同上，TS-ASR 请求（注册音频 + 识别片段）"},
            {"name": "上下文纠偏 · 真实录音", "section": "上下文纠偏", "labels": ["mined_real"],
             "description": "真实播客录音；每条单独成题（没有成对的确认题），看 mined_accuracy"},
        ],
        "sampling_rate": recipe["sample_rate"],
        "evaluation": [
            {"dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": split, "task": task,
             "label": split, "tags": ["zh", "context-correction"], "display": display, "description": description}
            for split, task, display, description in SOURCES
        ],
    }
    print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), end="")


if __name__ == "__main__":
    main()
