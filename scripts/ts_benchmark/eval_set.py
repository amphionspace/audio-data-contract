#!/usr/bin/env python3
"""Write the AmphionEval eval-set data config for the target-speaker benchmark.

The output is the file ``ae eval-sets publish`` takes: one evaluation source per
recipe split, with display names, descriptions and report groups.

    python scripts/ts_benchmark/eval_set.py > data.yaml
    ae eval-sets publish data.yaml --project open-audio-llm --name ts-asr-benchmark --version <日期>
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

CONDITIONS = {
    "clean": ("干净注册", "注册音频是同一说话人的另一条完整干净语句，客户端取前 3 秒"),
    "short1": ("注册仅 1 秒语音", "注册音频只有 1 秒语音，其余补零"),
    "lead_silence": ("注册开头静音", "注册音频前 1.5 秒静音，后 1.5 秒语音"),
    "lp4k": ("注册窄带", "注册音频经 4 kHz 低通（电话或远场带宽）"),
    "noise10": ("注册带噪声", "注册音频叠加 MUSAN 噪声，信噪比 10 dB"),
    "reverb": ("注册带混响", "注册音频经房间脉冲响应（DNS5）"),
    "contam10": ("注册被他人声音污染 10 dB", "注册音频叠加另一个说话人，信干比 10 dB"),
    "contam0": ("注册被他人声音污染 0 dB（压力）", "注册音频叠加另一个说话人，信干比 0 dB，标签含糊，只作压力测试"),
    "quiet": ("注册低电平（对照）", "注册音频降低 25 dB；此前的实测表明模型对电平不敏感，作为对照"),
}
KINDS = {
    "pos": ("目标在场", "目标说话人在场，指标为转写字错率与漏识率"),
    "neg": ("目标缺席", "注册人不在场、只有别人说话，期望输出为空，指标为误输出率"),
}
NAMED = {
    "dyn-solo": ("目标单独说话", "只有目标说话人，没有干扰人（对照）"),
    "dyn-full-k1": ("持续对话 · 1 个干扰人", "目标连续说话，另有 1 人说话，重叠程度随机"),
    "dyn-full-k4": ("持续对话 · 4 个干扰人", "目标连续说话，另有 4 人说话（共 5 人）"),
    "dyn-burst-k1": ("目标插话 · 1 个干扰人", "另 1 人持续说话，目标只在中间插 1–2 句"),
    "dyn-burst-k2": ("目标插话 · 2 个干扰人", "另 2 人持续说话，目标只在中间插 1–2 句"),
    "dyn-burst-k4": ("目标插话 · 4 个干扰人", "另 4 人持续说话，目标只在中间插 1–2 句"),
    "dyn-enter-k2": ("目标中途进场 · 2 个干扰人", "前半段只有别人，目标在后半段加入"),
    "dyn-leave-k2": ("目标中途离场 · 2 个干扰人", "目标先说话，前半段结束后离场，别人继续"),
    "dyn-alternate-k2": ("轮流对话 · 2 个干扰人", "多人轮流说话，几乎不重叠，目标说 1–2 轮"),
    "dyn-alternate-k4": ("轮流对话 · 4 个干扰人", "5 人轮流说话，几乎不重叠，目标只说 1–2 轮"),
    "dyn-overlap-k1": ("目标被抢话 · 1 个干扰人", "目标语句与干扰人语句几乎同时开始"),
    "dyn-overlap-k3": ("目标被抢话 · 3 个干扰人", "目标语句与干扰人语句几乎同时开始，另有 2 人说话"),
    "dyn-short-k1": ("目标只说一两个字 · 1 个干扰人", "目标只说约 1 秒的短语，别人持续说话"),
    "dyn-short-k3": ("目标只说一两个字 · 3 个干扰人", "目标只说约 1 秒的短语，别人持续说话"),
    "dyn-target-quiet": ("目标比干扰人轻 6–12 dB", "目标离麦克风远或声音小，干扰人更响"),
    "dyn-target-loud": ("目标比干扰人响 6–12 dB（对照）", "目标声音明显更大，应当最容易"),
    "abs-k1": ("缺席 · 1 个干扰人", "只有 1 个别人说话，没有目标，且没有混合"),
    "abs-k2": ("缺席 · 2 个干扰人", "2 个别人说话"),
    "abs-k4": ("缺席 · 4 个干扰人", "4 个别人同时说话"),
    "abs-hard": ("缺席 · 注册人与干扰人声音相近", "注册人是与某个干扰人最相近的说话人（ECAPA 余弦前 5）"),
    "abs-long": ("缺席 · 长片段（22–26.5 秒）", "长时间只有别人说话，检验复读和循环"),
    "abs-short": ("缺席 · 极短片段（0.4–1.2 秒）", "VAD 切出的极短别人语音，检验短片段幻觉"),
    "nonspeech-noise": ("纯噪声", "MUSAN 噪声，没有人声"),
    "nonspeech-music": ("纯音乐", "MUSAN 音乐，没有人声"),
    "nonspeech-traffic": ("道路交通噪声", "AudioSet 道路交通，没有人声"),
    "nonspeech-quiet": ("近乎静音", "极低电平的高斯噪声"),
    "nonspeech-short": ("纯噪声 · 极短（0.3–1 秒）", "极短的噪声片段"),
    "nonspeech-long": ("纯噪声 · 长片段（22–26.5 秒）", "长噪声片段，检验复读和循环"),
    "realreg1-neg": ("真实注册 1 · 缺席", "测试人员 2026-10-10 批的注册录音，配上 1–2 个没有他的说话人"),
    "realreg2-neg": ("真实注册 2 · 缺席", "测试人员 2026-10-12 批的注册录音，配上 1–2 个没有他的说话人"),
    "realreg1-music": ("真实注册 1 · 纯音乐", "同一段注册录音，片段是纯音乐"),
    "realreg2-music": ("真实注册 2 · 纯音乐", "同一段注册录音，片段是纯音乐"),
    "dom-clean-pos": ("无背景 · 目标在场（配对对照）", "与下面三种背景完全相同的场景，没有混响和背景声"),
    "dom-clean-neg": ("无背景 · 目标缺席（配对对照）", "同上，注册人不在场"),
    "dom-reverb-noise-pos": ("混响加噪声 · 目标在场", "混合音频经各说话人不同的房间响应并叠加噪声（5–15 dB），注册音频保持干净"),
    "dom-reverb-noise-neg": ("混响加噪声 · 目标缺席", "同上，注册人不在场"),
    "dom-music-pos": ("背景音乐 · 目标在场", "MUSAN 音乐背景（3–10 dB），近似旁边在放歌"),
    "dom-music-neg": ("背景音乐 · 目标缺席", "同上，注册人不在场"),
    "dom-traffic-pos": ("道路交通 · 目标在场", "道路交通噪声（0–10 dB），近似户外"),
    "dom-traffic-neg": ("道路交通 · 目标缺席", "同上，注册人不在场"),
    "dom-solo-music": ("目标单独说话 · 背景音乐", "只有目标说话人，叠加背景音乐"),
    "dom-solo-traffic": ("目标单独说话 · 道路交通", "只有目标说话人，叠加道路交通噪声"),
    "dom-phone-pos": ("手机录音 · 目标在场", "KeSpeech、MagicData、AISHELL-2 的手机录音说话人（含方言口音）"),
    "dom-phone-neg": ("手机录音 · 目标缺席", "同上，注册人不在场"),
    "dom-studio-pos": ("棚内录音 · 目标在场", "AISHELL-3 棚内高质量录音说话人"),
    "dom-studio-neg": ("棚内录音 · 目标缺席", "同上，注册人不在场"),
}


def entry(split, recipe):
    name, params = split["name"], split["params"]
    if name.startswith("enroll-"):
        cond = params["enroll"]
        label, description = CONDITIONS[cond]
        kind_label, _ = KINDS[params["kind"]]
        display = f"{label} · {kind_label}"
    else:
        display, description = NAMED[name]
    return {
        "dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": name, "task": "ts_asr",
        "label": name, "tags": ["zh", "target-speaker"], "display": display, "description": description,
    }


def main():
    recipe = yaml.safe_load(Path(build.__file__).with_name("recipe.yaml").read_text())
    splits = build.expand_splits(recipe)
    names = [s["name"] for s in splits]

    def pick(prefix, kinds):
        return [s["name"] for s in splits if s["name"].startswith(prefix) and s["params"]["kind"] in kinds]

    groups = [
        {"name": "目标在场（注册音频劣化）", "section": "注册音频劣化", "labels": pick("enroll-", {"pos"}),
         "description": "同一批基础场景（1–2 个干扰人），只改注册音频；指标为转写字错率与漏识率"},
        {"name": "目标缺席（注册音频劣化）", "section": "注册音频劣化", "labels": pick("enroll-", {"neg"}),
         "description": "注册音频劣化时，注册人不在场的误输出率"},
        {"name": "目标在场（进场离场与干扰人数）", "section": "进场、离场与缺席", "labels": pick("dyn-", {"pos"}),
         "description": "目标说话人的发言时机、被抢话、说话很短、声音很轻"},
        {"name": "目标缺席（别人在说话）", "section": "进场、离场与缺席", "labels": pick("abs-", {"neg"}),
         "description": "注册人不在场，含干扰人数、声音相近的人、长片段、极短片段"},
        {"name": "没有说话声", "section": "纯噪声", "labels": pick("nonspeech-", {"nonspeech"}),
         "description": "噪声、音乐、交通、近乎静音；期望输出为空"},
        {"name": "目标在场（环境与设备）", "section": "环境与设备", "labels": pick("dom-", {"pos"}),
         "description": "混响、背景音乐、交通、手机与棚内录音，目标在场"},
        {"name": "真实注册录音（缺席）", "section": "真实注册音频", "labels": pick("realreg", {"neg", "nonspeech"}),
         "description": "业务反馈里测试人员的真实注册录音，目标不在场；误输出率"},
        {"name": "目标缺席（环境与设备）", "section": "环境与设备", "labels": pick("dom-", {"neg"}),
         "description": "同上，注册人不在场"},
    ]
    covered = {label for g in groups for label in g["labels"]}
    missing = sorted(set(names) - covered)
    if missing:
        raise SystemExit(f"splits not in any group: {missing}")
    config = {
        "sampling_rate": recipe["sample_rate"],
        "tags": ["zh", "target-speaker"],
        "groups": groups,
        "evaluation": [entry(s, recipe) for s in splits],
    }
    yaml.safe_dump(config, sys.stdout, allow_unicode=True, sort_keys=False, width=200)


if __name__ == "__main__":
    main()
