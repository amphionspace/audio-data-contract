#!/usr/bin/env python3
"""Turn the English board placeholders in catalog/text_final_v3.yaml into formal entries.

Reads <run_dir>/<name>/artifacts.json written by voxpopuli.py, ami_ihm.py and earnings.py, and replaces each
named placeholder (dataset-state only) by an entry with checksummed records, audio index, statistics and
provenance. Other entries are kept as they are.

    python -I scripts/text_final/en_board/register.py --catalog catalog voxpopuli earnings22 ami_ihm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FINAL, MAX_S, MIN_S, RUN_DIR, SPEC

AUDIO_POLICY = "records point at the audio index with start and duration; channel 0"
SOURCES = {
    "voxpopuli": {
        "dataset_id": "voxpopuli_en", "src": "hf-42f01879c780", "license": "CC0-1.0",
        "script": "scripts/text_final/en_board/voxpopuli.py",
        "description": (
            "VoxPopuli 英文 train（欧洲议会演讲）的训练文本终版，直接按训练文本规范 v3 建，供 open-audio-llm A 线（英文榜单版）"
            "训练。目标用 raw_text（带大小写和标点），按规则 2 只补句首大写和句末标点，词中的破折号改连字符、两侧没有字母的引号删掉，"
            "源文本丢了开引号后留在词尾的闭引号（s 以外字母后的 '，如 dignity'）删掉，不改词；raw_text 为空的行用 normalized_text 经 en-v1 学生模型补标点和大小写。wav 从 parquet 原样落盘（32 位浮点，16 kHz）。"
        ),
        "recipe": {
            "text": "raw_text；空的用 normalized_text + en-v1 学生模型（amphiondata written_punctuation_en.written_text）",
            "rule2_fixes": "词中 em dash→连字符，其余 em dash→逗号；两侧没有字母的 ' 删掉；s 以外字母后的词尾 ' 是闭引号，删掉（normalized_text 的标签和学生输出同样处理）；句首大写；句末 , ; : 改 .，没有句末标点补 .",
            "audio_policy": "parquet 里的 wav 字节原样写成 <version>/audio/<年份>/<audio_id>.wav（: 换成 -），不重新编码",
        },
    },
    "ami_ihm": {
        "dataset_id": "ami_ihm", "src": "hf-edinburghcstr-20261023", "license": "CC BY 4.0",
        "script": "scripts/text_final/en_board/ami_ihm.py",
        "description": (
            "AMI 会议近讲耳麦 train 的训练文本终版，直接按训练文本规范 v3 建，供 open-audio-llm A 线（英文榜单版）训练。"
            "Kaldi s5 的全大写无标点文本经 en-v1 学生模型补标点和大小写（规则 2），输出改了词的按原词只补句末标点；"
            "词、口语重复和语气词都保留。dev、test 会议不在 train 里（Kaldi 划分）。不足 0.5 秒的段（22,081 条、1.95 h，几乎都是 yeah、mm-hmm 这类单字附和）不收；0.5 秒以上的单字附和仍有 1.3 万条。wav 从 parquet 原样落盘（32 位浮点，16 kHz）。"
        ),
        "recipe": {
            "text": "normalize_label(Kaldi 文本) + en-v1 学生模型（amphiondata written_punctuation_en.written_text）",
            "audio_policy": "parquet 里的 wav 字节原样写成 <version>/audio/<meeting>/<audio_id>.wav，不重新编码",
        },
    },
    "earnings22": {
        "dataset_id": "earnings22", "src": "github-c05ab6fd8b4b", "license": "CC-BY-SA-4.0",
        "script": "scripts/text_final/en_board/earnings.py",
        "description": (
            "Earnings-22 财报电话会议切成不超过 30 秒的短句，直接按训练文本规范 v3 建，供 open-audio-llm A 线（英文榜单版）训练。"
            "文本用 nlp_references 的书面写法（大小写、标点、MTN/2019/31st 这类实体原样），时间取 force_aligned_nlp_references，"
            "两表按单元匹配；口语重复和 uh/um 保留。排除 Open ASR 榜单测试用的 6 场（4468919、4471586、4474955、4475604、"
            "4482968、4483046），另按口音组各取 1 场共 4 场作 dev。音频转成 16 kHz 单声道 FLAC。"
        ),
        "recipe": {
            "excluded_board_test_meetings": ["4468919", "4471586", "4474955", "4475604", "4482968", "4483046"],
            "dev_meetings": ["4469528", "4481221", "4483668", "4482110"],
            "cutting": "一段只含一个说话人；起止都落在有时间的词上，段内最多连续 2 个没对齐的词；<inaudible> 等标记处断开，"
                       "<laugh>/<silence> 只从文本删掉；停顿 2 秒断开；超过每段随机目标（4–25 秒）后在句末断开，最长 30 秒；"
                       "前后各留最多 0.15 秒（不超过到邻词间隔的一半）；窗口里混进其他词的段丢掉",
            "audio_policy": "ffmpeg 把 media 转成 <version>/audio/<file id>.flac（16 kHz 单声道 PCM16），记录按 start/duration 引用",
        },
    },
}


def entry(name: str, placeholder: dict) -> dict:
    s = SOURCES[name]
    ds, src = s["dataset_id"], s["src"]
    built = json.loads((Path(RUN_DIR) / name / "artifacts.json").read_text())
    arts = built["artifacts"]
    names = {a["name"] for a in arts}
    splits = {}
    for split, dist in built["distribution"].items():
        splits[split] = {
            "group": "train" if split == "train" else "eval",
            "artifacts": {"records": [split], "audio_index": ["audio_index"], "preparation_state": ["preparation_state"]},
            "statistics": {"records": dist["count"], "duration_hours": dist["hours"],
                           "duration_basis": "sum of record durations", "languages": {"en": dist["count"]}},
        }
        assert split in names, split
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": ds,
        "version": f"{src}-{FINAL}",
        "languages": ["en"],
        "tasks": ["asr"],
        "aliases": [],
        "derived_from": f"{ds}@{src}",
        "artifacts": arts,
        "splits": splits,
        "recipe_parameters": {"spec": SPEC, "duration_seconds": [MIN_S, MAX_S], **s["recipe"],
                              "counts": built["counts"], "duration_distribution": built["distribution"]},
        "provenance": {
            "snapshot_date": now,
            "description": s["description"],
            "source": f"{ds}@{src}",
            "license": s["license"],
            "method": "text-final-v3",
            "owner": placeholder["provenance"].get("owner", "mingdong"),
            "requested_by": "open-audio-llm A 线（open-audio-llm PR #174）",
            "run_dir": RUN_DIR,
            "build_script": s["script"],
            "quality_status": "whisper-large-v3 spot check in run_dir/verify",
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("names", nargs="+", choices=sorted(SOURCES))
    args = ap.parse_args()
    path = args.catalog / "text_final_v3.yaml"
    yaml = YAML()
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=2, offset=0)
    data = yaml.load(path.read_text())
    want = {(SOURCES[n]["dataset_id"], f"{SOURCES[n]['src']}-{FINAL}"): n for n in args.names}
    done = set()
    for i, e in enumerate(data):
        key = (e["dataset_id"], e["version"])
        if key in want:
            assert e["provenance"].get("preparation_status") == "building", key
            data[i] = entry(want[key], e)
            done.add(key)
    assert done == set(want), set(want) - done
    with path.open("w") as w:
        yaml.dump(data, w)
    print("registered", sorted(done))


if __name__ == "__main__":
    main()
