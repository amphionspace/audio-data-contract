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
FLOORS = {
    "none": ("无底噪（数字静音）", "发言间隙是精确的 0，v1 的做法；其他底噪条件都与它配对比较"),
    "white50": ("白噪声底 −50 dBFS", "合成白噪声底，说话约 −25 dBFS"),
    "pink50": ("粉红噪声底 −50 dBFS", "合成粉红噪声底"),
    "wham60": ("WHAM 真实环境底噪 −60 dBFS", "WHAM! 的咖啡馆、餐厅、街道、公园等真实环境噪声，几乎听不见"),
    "wham50": ("WHAM 真实环境底噪 −50 dBFS", "同上，信噪比约 25 dB"),
    "wham40": ("WHAM 真实环境底噪 −40 dBFS", "同上，信噪比约 15 dB"),
    "wham30": ("WHAM 真实环境底噪 −30 dBFS", "同上，信噪比约 5 dB，明显的环境声"),
    "dnsas50": ("DNS5 AudioSet 底噪 −50 dBFS", "DNS5 的 AudioSet 噪声（只取电平稳定的片段）"),
    "dnsfs50": ("DNS5 Freesound 底噪 −50 dBFS", "DNS5 的 Freesound 噪声（只取电平稳定的片段）"),
}
ROOMS = {
    "real": ("真实房间响应", "SLR28 的实测房间脉冲响应（178 个）"),
    "sim_small": ("模拟小房间", "SLR28 模拟小房间"),
    "sim_medium": ("模拟中房间", "SLR28 模拟中房间"),
    "sim_large": ("模拟大房间", "SLR28 模拟大房间"),
    "dns5_sim": ("DNS5 模拟房间", "DNS5 包里的 SLR26 模拟房间响应"),
}
LEVELS = {
    "q20": ("整体电平降 20 dB", "说话约 −45 dBFS，业务第一批包的实际电平（−41 到 −46 dB）"),
    "q10": ("整体电平降 10 dB", "说话约 −35 dBFS"),
    "loud10": ("整体电平升 10 dB", "说话约 −15 dBFS，业务第二批包的实际电平"),
    "clip": ("过载削波", "升 15 dB 后硬削波，近似麦克风过载"),
    "nb": ("窄带 3.4 kHz", "混合音频经 3.4 kHz 低通，近似电话带宽"),
    "mulaw": ("μ 律 8 位压缩", "电话编码的量化失真"),
}
# 不贴近业务现实、只用于诊断的极端条件：不进分组汇总（评测表里列在「其他」，不计平均）。
EXTREME = ("enroll-contam0-", "level-clip-", "level-nb-", "level-mulaw-", "stress-")


def is_extreme(name):
    return name.startswith(EXTREME)


NOISES = {
    "babble20": ("背景人声 20 dB", "合成背景人声（5–20 位中文说话人同时说话，测试划分的说话人），信噪比 20 dB，背景很远"),
    "babble10": ("背景人声 10 dB", "同上，信噪比 10 dB，像身边有一群人聊天"),
    "babble5": ("背景人声 5 dB", "同上，信噪比 5 dB，嘈杂的人群"),
    "events20": ("环境事件声 20 dB", "FSD50K 评测划分里的家居、车辆、门、水、发动机、警报等声音（不含人声和音乐），信噪比 20 dB"),
    "events10": ("环境事件声 10 dB", "同上，信噪比 10 dB"),
    "crowd10": ("人群嘈杂声 10 dB", "FSD50K 的 Crowd 和 Chatter 标注片段，信噪比 10 dB"),
}
# 目标和干扰人的房间响应（RIR）：同一批基础场景，只改谁过 RIR、是不是同一个 RIR（SLR28 实测房间响应）
ROLES = {
    "rirtgt": ("只有目标过 RIR", "目标说话人过实测房间响应（远），干扰人是干的（近）；每个场景一个响应"),
    "rirint": ("只有干扰人过 RIR", "干扰人过实测房间响应（远），目标是干的（近）"),
    "rirsame": ("目标和干扰人过同一个 RIR", "目标和干扰人都过同一个实测房间响应，像坐在房间里同一个位置"),
    "rirdiff": ("目标和干扰人各过不同 RIR", "目标和每个干扰人各过一个不同的实测房间响应，混合是远场、注册是近场（干的），也是下面近远场失配的「注册近场、混合远场」"),
}
# 注册和混合分别是近场（干）或远场（过实测 RIR）；近场注册 + 远场混合就是 rirdiff
MISMATCH = {
    "mmfarfar": ("注册远场、混合远场", "注册音频和混合都过实测房间响应（注册一个、混合里每人各一个）：匹配的远场"),
    "mmfarnear": ("注册远场、混合近场", "注册音频过实测房间响应，混合是干的：反向失配"),
}
NOISE_ONLY = {
    "nonspeech-babble": ("只有背景人声", "只有合成的背景人声（一群人聊天），没有目标，期望输出为空"),
    "nonspeech-crowd": ("只有人群嘈杂声", "只有 FSD50K 的 Crowd 和 Chatter 片段，期望输出为空"),
    "nonspeech-events": ("只有环境事件声", "只有 FSD50K 的环境事件声（不含人声和音乐），期望输出为空"),
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
    "stress-outdoor-pos": ("组合压力 · 户外电话 · 目标在场", "窄带 3.4 kHz、整体降 10 dB、道路交通 0–10 dB、WHAM 底噪 −45 到 −35 dBFS、2–4 个干扰人"),
    "stress-outdoor-neg": ("组合压力 · 户外电话 · 目标缺席", "同上，注册人不在场"),
    "stress-office-pos": ("组合压力 · 办公室 · 目标在场", "真实房间响应、WHAM 底噪 −45 到 −35 dBFS、注册开头静音、2–4 个干扰人"),
    "stress-office-neg": ("组合压力 · 办公室 · 目标缺席", "同上，注册人不在场"),
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
    if name.split("-")[0] in NOISES:
        label, description = NOISES[name.split("-")[0]]
        display = f"{label} · {KINDS[params['kind']][0]}"
    elif name in NOISE_ONLY:
        display, description = NOISE_ONLY[name]
    elif name.startswith(("floor-", "room-", "level-")):
        table = {"floor": FLOORS, "room": ROOMS, "level": LEVELS}[name.split("-")[0]]
        label, description = table[name.split("-")[1]]
        display = f"{label} · {KINDS[params['kind']][0]}"
    elif name.split("-")[0] in ROLES:
        label, description = ROLES[name.split("-")[0]]
        display = f"{label} · {KINDS[params['kind']][0]}"
    elif name.split("-")[0] in MISMATCH:
        label, description = MISMATCH[name.split("-")[0]]
        display = f"{label} · {KINDS[params['kind']][0]}"
    elif name.startswith("panel-base"):
        display = f"面板基线 · {KINDS[params['kind']][0]}"
        description = "面板的共同基线：同一批基础场景，默认底噪（真实与合成混合），干燥房间，正常电平"
    elif name.startswith("enroll-"):
        cond = params["enroll"]
        label, description = CONDITIONS[cond]
        kind_label, _ = KINDS[params["kind"]]
        display = f"{label} · {kind_label}"
    else:
        display, description = NAMED[name]
    if is_extreme(name):
        display, description = f"{display}（极端，诊断用）", f"{description}。不贴近业务现实，不计入分组平均"
    return {
        "dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": name, "task": "ts_asr",
        "label": name, "tags": ["zh", "target-speaker"], "display": display, "description": description,
    }


def main():
    recipe = yaml.safe_load(Path(sys.argv[1] if len(sys.argv) > 1 else Path(build.__file__).with_name("recipe.yaml")).read_text())
    splits = build.expand_splits(recipe)

    def pick(prefix, kinds):
        return [s["name"] for s in splits
                if s["name"].startswith(prefix) and s["params"]["kind"] in kinds and not is_extreme(s["name"])]

    if recipe["dataset_id"] == "ts_asr_farfield":
        groups = []
        for title, key, prefixes, text in (
            ("目标和干扰人各自的房间响应", "pos", ("rirtgt", "rirint", "rirsame", "rirdiff"), "同一批基础场景；只改谁过房间响应、是不是同一个"),
            ("注册与混合的近远场失配", "pos", ("rirdiff", "mmfarfar", "mmfarnear"), "注册和混合分别是近场（干）或远场（过房间响应）；基线是近场注册、近场混合"),
        ):
            for kind, kind_label in (("pos", "目标在场"), ("neg", "目标缺席")):
                labels = [f"panel-base-{kind}"] + [s["name"] for s in splits if s["name"].split("-")[0] in prefixes and s["params"]["kind"] == kind]
                groups.append({"name": f"{title}（{kind_label}）", "section": "远场与房间响应", "labels": labels, "description": text})
        return emit(recipe, splits, groups)
    if recipe["dataset_id"] == "ts_asr_noise":
        groups = [
            {"name": "背景噪声（目标在场）", "section": "新登记的噪声集", "labels": ["panel-base-pos", *pick("babble", {"pos"}), *pick("events", {"pos"}), *pick("crowd", {"pos"})],
             "description": "同一批基础场景，只加背景人声、环境事件声或人群嘈杂声；基线与 v3 的面板基线相同"},
            {"name": "背景噪声（目标缺席）", "section": "新登记的噪声集", "labels": ["panel-base-neg", *pick("babble", {"neg"}), *pick("events", {"neg"}), *pick("crowd", {"neg"})],
             "description": "同上，注册人不在场"},
            {"name": "只有噪声，没有目标", "section": "新登记的噪声集", "labels": pick("nonspeech-", {"nonspeech"}),
             "description": "背景人声、人群、环境事件声；期望输出为空"},
        ]
        return emit(recipe, splits, groups)
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
        {"name": "脆弱性面板 · 底噪类型与强度（目标在场）", "section": "脆弱性面板",
         "labels": ["panel-base-pos", *pick("floor-", {"pos"})],
         "description": "同一批基础场景，只改底噪的类型和强度；最坏的条件就是模型对底噪的脆弱点"},
        {"name": "脆弱性面板 · 底噪类型与强度（目标缺席）", "section": "脆弱性面板",
         "labels": ["panel-base-neg", *pick("floor-", {"neg"})], "description": "同上，注册人不在场"},
        {"name": "脆弱性面板 · 房间响应（目标在场）", "section": "脆弱性面板", "labels": pick("room-", {"pos"}),
         "description": "同一批基础场景，只改房间响应（实测与模拟，小中大房间）"},
        {"name": "脆弱性面板 · 房间响应（目标缺席）", "section": "脆弱性面板", "labels": pick("room-", {"neg"}),
         "description": "同上，注册人不在场"},
        {"name": "脆弱性面板 · 电平与录音链路（目标在场）", "section": "脆弱性面板", "labels": pick("level-", {"pos"}),
         "description": "同一批基础场景，只改整体电平、削波、窄带和电话编码"},
        {"name": "脆弱性面板 · 电平与录音链路（目标缺席）", "section": "脆弱性面板", "labels": pick("level-", {"neg"}),
         "description": "同上，注册人不在场"},
        {"name": "真实注册录音（缺席）", "section": "真实注册音频", "labels": pick("realreg", {"neg", "nonspeech"}),
         "description": "业务反馈里测试人员的真实注册录音，目标不在场；误输出率"},
        {"name": "目标缺席（环境与设备）", "section": "环境与设备", "labels": pick("dom-", {"neg"}),
         "description": "同上，注册人不在场"},
    ]
    return emit(recipe, splits, groups)


def emit(recipe, splits, groups):
    names = [s["name"] for s in splits]
    covered = {label for g in groups for label in g["labels"]}
    missing = sorted(n for n in set(names) - covered if not is_extreme(n))
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
