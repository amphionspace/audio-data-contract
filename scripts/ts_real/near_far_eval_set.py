#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for ts_asr_nearfar.

    python scripts/ts_real/near_far_eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name ts-asr-nearfar --version v1-20261014
"""

import sys

import yaml

VERSION = "v1-20261014"
BUCKETS = {"1spk": "窗口里只有 1 人说话", "2spk": "窗口里 2 人说话", "3plus": "窗口里 3 人及以上说话"}
KINDS = {"pos": "目标在场", "neg": "目标缺席"}
CELLS = {
    "ef-mf": ("注册远场、混合远场", "登记的样本本身：注册语句取远场，混合是远场通道 0"),
    "en-mf": ("注册近场、混合远场", "同一条注册语句取说话人的头戴麦（像在手机上贴近嘴巴注册），混合是远场通道 0"),
    "ef-mn": ("注册远场、混合近场", "注册取远场，混合是该录音所有头戴麦之和（电平对齐远场混合）"),
    "en-mn": ("注册近场、混合近场", "注册取说话人的头戴麦，混合是所有头戴麦之和"),
}


def main():
    entries, groups = [], []
    for kind, kind_label in KINDS.items():
        labels = []
        for cell, (cell_label, description) in CELLS.items():
            for bucket, bucket_label in BUCKETS.items():
                name = f"nearfar-{bucket}-{cell}-{kind}"
                labels.append(name)
                entries.append({
                    "dataset_id": "ts_asr_nearfar", "version": VERSION, "split": name, "task": "ts_asr", "label": name,
                    "tags": ["zh", "target-speaker"], "display": f"{cell_label} · {bucket_label} · {kind_label}",
                    "description": f"AliMeeting 测试集窗口。{description}。" + ("目标说话人在窗口里说话。" if kind == "pos" else "注册人没有在窗口里说话，期望输出为空。"),
                })
        groups.append({"name": f"AliMeeting 近远场对照（{kind_label}）", "section": "真实对话 · 近远场", "labels": labels,
                       "description": "同一批窗口，注册和混合分别取近场（头戴麦）或远场；ef-mf 是基线"})
    yaml.safe_dump({"sampling_rate": 16000, "tags": ["zh", "target-speaker"], "groups": groups, "evaluation": entries},
                   sys.stdout, allow_unicode=True, sort_keys=False, width=200)


if __name__ == "__main__":
    main()
