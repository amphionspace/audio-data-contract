#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for ts_asr_real.

    python scripts/ts_real/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name ts-asr-real --version v1-20261013
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

BUCKETS = {"1spk": "窗口里只有 1 人说话", "2spk": "窗口里 2 人说话", "3plus": "窗口里 3 人及以上说话"}
KINDS = {"pos": "目标在场", "neg": "目标缺席"}


def main():
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
