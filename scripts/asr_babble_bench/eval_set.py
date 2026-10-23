#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for the plain-ASR babble benchmark.

    python scripts/asr_babble_bench/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name asr-babble-bench --version <version>

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
    recipe = yaml.safe_load(parser.parse_args().recipe.read_text())
    splits = recipe["splits"]

    def names(kind, prefix=""):
        return [s["name"] for s in splits if s["kind"] == kind and s["name"].startswith(prefix)]

    config = {
        "sampling_rate": recipe["sample_rate"],
        "tags": ["asr", "noise"],
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
             "label": s["name"], "tags": [s.get("language") or ("zh" if s["name"].startswith("zh-") else "en"), "noise"],
             "display": s["display"], "description": s["description"]}
            for s in splits
        ],
    }
    print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), end="")


if __name__ == "__main__":
    main()
