#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for ts_asr_nearfar@firstother-v1 (``first_speaker.py``).

    python scripts/ts_real/first_speaker_eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name ts-asr-first-other --version v1-20261104

Splits are read from the registered catalog version, so the ``-enrollmix`` splits appear only where records exist.
"""

import argparse
import sys
from pathlib import Path

import yaml

from audio_data_contract import load_catalog

VERSION = "firstother-v1-20261104"
SUFFIX = "-enrollmix"
BADCASE = ("复现一条内部返回的 TS-ASR badcase：45 秒三人同屋交替说话，注册是另一次单独录的声纹，会话开头是非目标说话人清晰发言，"
           "模型整段转写了先开口的人；两个因素叠加：注册与会话不同录音（匹配信号弱），混合开头先是非目标说话人。")
KINDS = {"firstother": ("非目标先开口", "窗口第一个开口的不是目标，目标第一句之前已有非目标一整句清晰语句（≥1.2 秒）"),
         "firsttarget": ("目标先开口（对照）", "同一批会议、同样长度与人数的窗口，目标第一个开口")}
CELLS = {"ef-mf": ("注册远场", "注册取远场通道 0（与混合同通道）"),
         "en-mf": ("注册近场", "注册取本人头戴麦（跨通道，接近单独录的声纹）"),
         "ed-mf": ("注册近场劣化", "注册取本人头戴麦，再限带（3.5–5 kHz 低通或 4 kHz 以上 −6 dB）并加稳态噪声（SNR 15–25 dB）")}
PRESENCE = {"pos": ("目标在场", "目标说话人在窗口里说话。"), "neg": ("目标缺席", "注册人没有在窗口里说话，期望输出为空。")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[2] / "catalog")
    args = parser.parse_args()
    spec = next(s for s in load_catalog(args.catalog) if s.dataset_id == "ts_asr_nearfar" and s.version == VERSION)
    entries, groups = [], []
    for mixed in (False, True):
        for presence, (presence_label, presence_text) in PRESENCE.items():
            labels = []
            for kind, (kind_label, kind_text) in KINDS.items():
                for cell, (cell_label, cell_text) in CELLS.items():
                    name = f"{kind}-{cell}-{presence}" + (SUFFIX if mixed else "")
                    if name not in spec.splits:
                        continue
                    labels.append(name)
                    entries.append({
                        "dataset_id": "ts_asr_nearfar", "version": VERSION, "split": name, "task": "ts_asr", "label": name,
                        "tags": ["zh", "target-speaker"],
                        "display": f"{kind_label} · {cell_label} · {presence_label}" + (" · 注册含他人声" if mixed else ""),
                        "description": (f"AliMeeting 测试集 25–45 秒窗口（≥3 人，目标说话 ≥5 秒），混合是远场通道 0。{kind_text}；"
                                        f"{cell_text}。{presence_text}"
                                        + ("注册前 5 秒里他人说话不少于 0.3 秒。" if mixed else "")),
                    })
            if labels:
                groups.append({"name": f"谁先开口 · {presence_label}" + ("（注册含他人声）" if mixed else ""),
                               "section": "真实对话 · 谁先开口", "labels": labels,
                               "description": BADCASE + "firstother 与 firsttarget 对比“谁先开口”，ef/en/ed 对比注册与会话的匹配程度。"})
    config = {"sampling_rate": 16000, "enroll_seconds": 5, "tags": ["zh", "target-speaker"], "groups": groups,
              "evaluation": entries}
    yaml.safe_dump(config, sys.stdout, allow_unicode=True, sort_keys=False, width=200)


if __name__ == "__main__":
    main()
