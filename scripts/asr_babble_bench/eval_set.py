#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for the plain-ASR babble benchmark.

    python scripts/asr_babble_bench/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name asr-babble-bench --version v3-20261023

With ``--blank-recipe recipe-blank.yaml`` the config also lists the blank / non-speech splits of that recipe's
version (v4-20261104 onwards); the babble splits keep pointing at ``recipe.yaml``'s version, so their results
compare with earlier runs record by record.

The native evaluator scores ``noise`` splits (empty references) by
``false_alarm_rate`` and ``speech`` splits by CER/WER, insertions included.
"""

import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--blank-recipe", type=Path, help="also list the blank / non-speech splits (recipe-blank.yaml)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    splits = recipe["splits"]

    def names(kind, prefix=""):
        return [s["name"] for s in splits if s["kind"] == kind and s["name"].startswith(prefix)]

    def tags(split):
        """Language and ``synthetic`` where they apply (not on the recorded crowds); ``noise`` unless a clean control."""
        noise = ["noise"] if split.get("noise") else []
        if split.get("language"):
            return [split["language"], "synthetic", *noise]
        if split["noise"].startswith("babble_"):
            return [split["noise"].split("_")[1], "synthetic", *noise]
        return noise

    config = {
        "task": "asr",
        "sampling_rate": recipe["sample_rate"],
        "tags": ["zh", "en", "synthetic", "noise"],
        "groups": [
            {"name": "只有背景人声", "section": "背景人声", "labels": names("noise"),
             "description": "没有人对着设备说话，只有背景人声或人群嘈杂声；期望输出为空，指标为误输出率"},
            {"name": "中文 · 一句话前后有背景人声", "section": "背景人声", "labels": names("speech", "zh-"),
             "description": "同一批句子，只改背景人声的信噪比和前后是否留空；与对照之差是背景人声带来的错误"},
            {"name": "英文 · 一句话前后有背景人声", "section": "背景人声", "labels": names("speech", "en-"),
             "description": "同上，英文"},
        ],
        "evaluation": [
            {"dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": s["name"], "task": "asr",
             "label": s["name"], "tags": tags(s),
             "display": s["display"], "description": s["description"]}
            for s in splits
        ],
    }
    if args.blank_recipe:
        blank = yaml.safe_load(args.blank_recipe.read_text())
        real = [s["name"] for s in blank["splits"] if s["source"] == "tdtech"]
        other = [s["name"] for s in blank["splits"] if s["source"] != "tdtech"]
        config["groups"][1:1] = [
            {"name": "鼎桥真实空白", "section": "空白与非人声", "labels": real,
             "description": "鼎桥设备真实录音里无人说话的区间（三个说话人老师一致、FSMN-VAD 未检出语音），按时长分档；期望输出为空，指标为误输出率"},
            {"name": "空白、底噪与环境声", "section": "空白与非人声", "labels": other,
             "description": "近静音、底噪、电流嗡声与 FSD50K 评测划分的环境声（不含人声和音乐），以及 0.3–1.5 秒短片段；期望输出为空"},
        ]
        config["evaluation"] += [
            {"dataset_id": blank["dataset_id"], "version": blank["version"], "split": s["name"], "task": "asr",
             "label": s["name"], "tags": [blank["language"], "noise", *(["synthetic"] if s["source"] in ("floor", "hum", "mixed") else [])],
             "display": s["display"], "description": s["description"]}
            for s in blank["splits"]
        ]
    print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), end="")


if __name__ == "__main__":
    main()
