#!/usr/bin/env python3
"""Write the TTS evaluation texts of police_scene_bench (sheet row 75: on-device TTS, MOS >= 4.3).

The sheet asks the listening test to cover simple and complex sentences, hard cases (polyphones,
digit strings, proper nouns, mixed Chinese-English, dialogue), paragraphs of 300+ characters and
four speaking contexts (neutral, happy, serious, soothing). There is no such text set, so this asks
the online LLM AmphionData uses (doubao-seed-2-0-pro) for police-device prompts of each kind, checks
every item mechanically and keeps ``PER_CATEGORY`` unique ones. MOS itself still needs listeners.

Run with AmphionData on the path and the ARK key mapped to AmphionData's variable names:

    ~/amphionkeys/load.sh volcengine-ark -- env DOUBAO_API_KEY=... DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \\
        PYTHONPATH=/path/to/amphiondata/src python scripts/police_scene_bench/generate_tts_texts.py
"""

from __future__ import annotations

import argparse
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import amphiondata
from amphiondata.llm import LLMRequest
from amphiondata.llm.request import request_llm

OUT = Path("/workspace/data/datasets/police_scene_bench/tts/texts-20261028/tts_eval_texts.jsonl")
MODEL = "doubao-seed-2-0-pro"
SEED = 20261028
PER_CATEGORY = 100
PER_REQUEST = 20
TOPICS = ["接处警", "道路交通执法", "户籍窗口业务", "反诈宣传", "巡逻防控", "执法记录仪操作提示", "案件办理与讯问",
          "社区警务与入户走访", "出入境业务", "治安调解", "大型活动安保", "警情查询结果播报"]
SCENE = "公安一线民警佩戴的执法记录仪/AR 终端上的离线语音播报（设备提示、查询结果、告知用语、对群众说的话）"
CATEGORIES = {
    "simple": ("简单句", "4–20 个字的短句或常用口语，例如设备状态提示、简短告知", {}),
    "complex": ("复杂句", "30–80 个字、带从句或书面语结构的长句，例如法律告知、流程说明", {}),
    "polyphone": ("多音字", "每句至少含 2 个在本句里容易读错的多音字（如 行、长、重、还、得、着、调、处、传、供、给、种、相、模、率、强、扎、恶、量、差）",
                  {"polyphones": "本句中的多音字及其在本句的正确读音，如 [{\"char\": \"调\", \"pinyin\": \"diao4\"}]"}),
    "digits": ("数字串", "含阿拉伯数字串：电话号码、身份证号、车牌、警情编号、时间日期、金额、门牌号等，每句至少一个 3 位以上的数字串", {}),
    "proper_noun": ("专有名词", "含地名、机构名、法律法规名称、系统或应用名称等专有名词",
                    {"nouns": "本句中的专有名词列表"}),
    "code_mix": ("中英混", "中文句子里夹英文单词或缩写，如 App、GPS、WiFi、PDT、AI、OK、ID", {}),
    "dialogue": ("对话文本", "民警与群众的两到四轮简短对话，每轮一行，格式为“民警：……”或“群众：……”", {}),
    "long": ("长段落", "300–500 个汉字的连续段落，如普法宣传、安全提示、流程说明，内容连贯，不要分点", {}),
}
EMOTIONS = {"neutral": "中性（平稳客观的播报）", "happy": "开心（表扬、好消息、祝贺）", "serious": "严肃（警告、法律告知、制止违法）",
            "soothing": "安抚（安慰受害群众、让对方别着急）"}


def prompt(category, topic, count, emotion=None):
    if emotion:
        kind, rule, fields = "情绪", f"语气为{EMOTIONS[emotion]}，读出来能听出这种情绪的一两句话，15–60 个字", {}
    else:
        kind, rule, fields = CATEGORIES[category]
    keys = {"text": "文本", **fields}
    return (f"为语音合成听测写 {count} 条测试文本。使用场景：{SCENE}。本批主题：{topic}。类别：{kind}——{rule}。\n"
            "要求：内容真实自然、彼此不重复；不要编号；不要使用引号包裹整句；数字按书面写法。\n"
            f"只输出 JSON 数组，每个元素是对象，字段：{json.dumps(keys, ensure_ascii=False)}。")


def hanzi(text):
    return len(re.findall(r"[一-鿿]", text))


def valid(category, item, emotion=None):
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return False
    text = text.strip()
    if emotion:
        return 10 <= len(text) <= 80
    if category == "simple":
        return 4 <= len(text) <= 22
    if category == "complex":
        return 28 <= len(text) <= 90
    if category == "polyphone":
        marks = item.get("polyphones")
        return isinstance(marks, list) and len(marks) >= 2 and all(
            isinstance(m, dict) and m.get("char") in text and m.get("pinyin") for m in marks)
    if category == "digits":
        return re.search(r"\d{3,}", text) is not None
    if category == "proper_noun":
        nouns = item.get("nouns")
        return isinstance(nouns, list) and nouns and all(isinstance(n, str) and n in text for n in nouns)
    if category == "code_mix":
        return re.search(r"[A-Za-z]{2,}", text) is not None and hanzi(text) >= 4
    if category == "dialogue":
        return len(re.findall(r"(民警|群众)：", text)) >= 2
    if category == "long":
        return 300 <= hanzi(text) <= 520
    return False


def ask(job):
    category, emotion, topic, count, config = job
    request = LLMRequest(messages=[{"role": "user", "content": prompt(category, topic, count, emotion)}],
                         stream=False, temperature=0.9, max_output_tokens=8192)
    try:
        items = request_llm(config, MODEL, request, is_json=True)
    except Exception as exc:  # noqa: BLE001 - a failed batch is retried by the next round
        print(json.dumps({"category": category, "emotion": emotion, "error": repr(exc)[:200]}), flush=True)
        return job, []
    return job, items if isinstance(items, list) else []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(Path(amphiondata.__file__).parent / "default.toml"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=4)
    args = parser.parse_args()
    rng = random.Random(SEED)
    wanted = {(c, None): PER_CATEGORY for c in CATEGORIES}
    wanted.update({("emotion", e): PER_CATEGORY // len(EMOTIONS) for e in EMOTIONS})
    kept = {key: {} for key in wanted}  # text -> item
    for _ in range(args.rounds):
        jobs = []
        for (category, emotion), need in wanted.items():
            missing = need - len(kept[(category, emotion)])
            per = 5 if category == "long" else PER_REQUEST
            for _ in range(-(-max(missing, 0) * 3 // 2 // per) if missing > 0 else 0):  # ask 1.5x what is missing
                jobs.append((category, emotion, rng.choice(TOPICS), per, args.config))
        if not jobs:
            break
        with ThreadPoolExecutor(args.workers) as pool:
            for (category, emotion, topic, _, _), items in pool.map(ask, jobs):
                bucket = kept[(category, emotion)]
                for item in items:
                    if isinstance(item, dict) and valid(category, item, emotion) and item["text"].strip() not in bucket:
                        bucket[item["text"].strip()] = {**item, "text": item["text"].strip(), "topic": topic}
        print(json.dumps({f"{c}:{e}" if e else c: len(v) for (c, e), v in kept.items()}, ensure_ascii=False), flush=True)
    rows = []
    for (category, emotion), bucket in kept.items():
        items = sorted(bucket.values(), key=lambda i: i["text"])
        random.Random(f"{SEED}:{category}:{emotion}").shuffle(items)
        for index, item in enumerate(items[:wanted[(category, emotion)]]):
            name = f"emotion-{emotion}" if emotion else category
            row = {"id": f"tts-{name}-{index:03d}", "category": "emotion" if emotion else category,
                   "category_zh": "情绪" if emotion else CATEGORIES[category][0], "text": item["text"],
                   "chars": len(item["text"]), "topic": item["topic"]}
            if emotion:
                row["emotion"] = emotion
            for key in ("polyphones", "nouns"):
                if key in item:
                    row[key] = item[key]
            rows.append(row)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(json.dumps({"written": len(rows), "path": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
