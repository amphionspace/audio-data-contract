#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for ts_asr_real.

    python scripts/ts_real/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name ts-asr-real --version v1-20261013

``--recipe overlap`` / ``dev`` write the target-anchored versions, grouped by overlap bucket.
"""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

BUCKETS = {"1spk": "窗口里只有 1 人说话", "2spk": "窗口里 2 人说话", "3plus": "窗口里 3 人及以上说话"}
KINDS = {"pos": "目标在场", "neg": "目标缺席"}
OVERLAP = {"o0": "目标几乎没被别人重叠（<5%）", "o20": "目标 5–20% 的语音被别人重叠",
           "o50": "目标 20–50% 的语音被别人重叠", "o100": "目标一半以上的语音被别人重叠"}


def overlap_config(recipe):
    entries, groups = [], []
    for corpus, spec in recipe["corpora"].items():
        for kind, kind_label in KINDS.items():
            labels = []
            for bucket in spec["windows"]:
                name = f"{recipe['prefix']}-{corpus}-{bucket}-{kind}"
                labels.append(name)
                entries.append({
                    "dataset_id": "ts_asr_real", "version": recipe["version"], "split": name, "task": "ts_asr",
                    "label": name, "tags": ["zh", "target-speaker"],
                    "display": f"{spec['label']} · {OVERLAP[bucket]} · {kind_label}",
                    "description": ("真实对话窗口，人工标注，以目标说话人为锚切出（目标的语句完整，别人的语句截到窗口边界）；"
                                   "注册取窗外的另一条语句。" + ("目标说话人在窗口里说话。" if kind == "pos"
                                                         else "注册人没有在窗口里说话，期望输出为空。")),
                })
            groups.append({"name": f"{spec['label']} · 按重叠分档（{kind_label}）", "section": "真实对话重叠", "labels": labels,
                           "description": f"{spec['label']}的人工标注 {spec['split']} 划分，按目标被重叠的比例分档"})
    return {"sampling_rate": 16000, "tags": ["zh", "target-speaker"], "groups": groups, "evaluation": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", choices=sorted(build.RECIPES), default="v2")
    args = parser.parse_args()
    if args.recipe != "v2":
        config = overlap_config(build.RECIPES[args.recipe])
        yaml.safe_dump(config, sys.stdout, allow_unicode=True, sort_keys=False, width=200)
        return
    recipe = build.RECIPE
    entries, groups = [], []
    for corpus, spec in recipe["corpora"].items():
        for kind, kind_label in KINDS.items():
            labels = []
            for bucket, bucket_label in BUCKETS.items():
                if corpus == "ramc" and bucket == "3plus":
                    continue  # phone calls have two speakers
                name = f"real-{corpus}-{bucket}-{kind}"
                labels.append(name)
                entries.append({
                    "dataset_id": "ts_asr_real", "version": recipe["version"], "split": name, "task": "ts_asr",
                    "label": name, "tags": ["zh", "target-speaker"],
                    "display": f"{spec['label']} · {bucket_label} · {kind_label}",
                    "description": ("真实对话窗口，人工标注；注册取窗外的另一条语句。"
                                   + ("目标说话人在窗口里说话。" if kind == "pos" else "注册人没有在窗口里说话，期望输出为空。")),
                })
            groups.append({"name": f"{spec['label']}（{kind_label}）", "section": "真实对话", "labels": labels,
                           "description": f"{spec['label']}的人工标注测试集，不做任何混合"})
    config = {"sampling_rate": 16000, "tags": ["zh", "target-speaker"], "groups": groups, "evaluation": entries}
    yaml.safe_dump(config, sys.stdout, allow_unicode=True, sort_keys=False, width=200)


if __name__ == "__main__":
    main()
