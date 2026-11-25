#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config of the whole-meeting TS benchmark (ts_asr_real meeting versions).

AISHELL-4 from meeting-v3-20261117; AliMeeting and MagicData-RAMC, with the controls of ``meeting_controls.py``,
from ``--version`` (meeting-v4-20261125 or a version derived from it).

    python scripts/ts_real/meeting_eval_set.py --version meeting-v4-20261125 > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name ts-asr-meeting --version v1-20261125
"""

import argparse
import sys

import yaml

AISHELL4 = "meeting-v3-20261117"
KINDS = {"pos": "目标在场", "neg": "目标缺席"}
CORPORA = {
    "aishell4": ("AISHELL-4", "AISHELL-4 test 20 场会议远场通道 0（5–7 人）"),
    "alimeeting": ("AliMeeting", "AliMeeting test 20 场会议远场通道 0（2–4 人）"),
    "ramc": ("RAMC", "MagicData-RAMC test 两人手机对话（去掉含训练划分说话人的录音）"),
}
SEND = ("按人工标注把同一人相邻语句并成段（同下游 MOSS 分段，落在别人话里的插话不单独成段），每段发给会上每个注册人"
        "（注册取本人会上最早的干净语句，客户端取前 5 秒）。")
KIND_TEXT = {"pos": "本人在段内说话 ≥0.5 秒且语句完整在段内，参考为这些语句。",
             "neg": ("本人在段前后 0.5 秒内都没说话，段里是同场其他人，期望输出为空；"
                     "labels.impostor_sim 为注册与段内最像的在场人的声纹相似度。")}
CONTROLS = {
    "xrec": ("别场注册", ("neg",), ("alimeeting", "ramc"),
             ("同一批段，注册换成同语料另一场录音里的人：与段内最像的在场人的声纹相似度最接近原注册（labels.base_impostor_sim、"
              "xrec_sim_gap）。与基础组逐条配对，检验同一录音的注册是否被当成目标的证据")),
    "enear": ("近讲注册", ("pos", "neg"), ("alimeeting",),
              "同一批注册语句改取本人头戴麦（按远场注册 RMS 缩放），段仍为远场：注册不再带会议室远场声学"),
    "near": ("全近讲", ("pos", "neg"), ("alimeeting",),
             "注册取本人头戴麦，段为全部头戴麦之和（按远场 RMS 缩放）：两边都是近讲"),
    "snr": ("低信噪比", ("pos", "neg"), ("alimeeting",),
            "段与注册都加同一条真实会议室底噪（按会议时间对齐），每场一个增益，段的中位信噪比 8 dB，注册不低于 6 dB（同下游服务挑注册的门槛）"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="ts_asr_real version of the AliMeeting / RAMC splits")
    args = ap.parse_args()
    entries, groups = [], []

    def add(split, version, display, description):
        entries.append({"dataset_id": "ts_asr_real", "version": version, "split": split, "task": "ts_asr", "label": split,
                        "tags": ["zh", "target-speaker"], "display": display, "description": description})
        return split

    for kind, kind_label in KINDS.items():
        labels = []
        for corpus, (name, source) in CORPORA.items():
            version = AISHELL4 if corpus == "aishell4" else args.version
            labels.append(add(f"meeting-{corpus}-{kind}", version, f"整场会议 · {name} · {kind_label}",
                              f"{source}，{SEND}{KIND_TEXT[kind]}"))
        groups.append({"name": f"整场会议逐段发送 · {kind_label}", "section": "真实对话 · 整场会议", "labels": labels,
                       "description": "复现下游 speaker-enroll 回放会议的发送方式：会上每人注册一次，每段话发给每个注册人的框。"
                                      + ("目标缺席时的误输出率（下游串人 badcase：AISHELL-4 3.8%，手机远场会议 47.9%）"
                                         if kind == "neg" else "目标在场时的字错率与漏识率")})
    for control, (label, kinds, corpora, description) in CONTROLS.items():
        for kind in kinds:
            labels = [add(f"meeting-{corpus}-{kind}-{control}", args.version,
                          f"整场会议 · {CORPORA[corpus][0]} · {KINDS[kind]} · {label}", f"{description}。{KIND_TEXT[kind]}")
                      for corpus in corpora]
            groups.append({"name": f"定位对照 · {label} · {KINDS[kind]}", "section": "真实对话 · 整场会议对照", "labels": labels,
                           "description": description + "；与同名基础组（不带后缀）逐条配对比较（metadata.base）"})
    yaml.safe_dump({"sampling_rate": 16000, "enroll_seconds": 5, "tags": ["zh", "target-speaker"], "groups": groups,
                    "evaluation": entries}, sys.stdout, allow_unicode=True, sort_keys=False, width=200)


if __name__ == "__main__":
    main()
