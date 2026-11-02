#!/usr/bin/env python3
"""Write the AmphionEval eval-set data configs of the police scene benchmark (td-tech acceptance).

One config per scoring family, every group one row (capability x noise level) of the acceptance sheet:

    python scripts/police_scene_bench/eval_set.py asr > asr.yaml          # recognition, terms, 300 hotwords, numbers, context
    python scripts/police_scene_bench/eval_set.py ts > ts.yaml            # device owner (target speaker)
    python scripts/police_scene_bench/eval_set.py meeting > meeting.yaml  # role separation (speaker-attributed ASR)
    ae eval-sets publish asr.yaml --project tdtech --name scene-asr --version v1-20261028

Channel variants (``dev-``, ``far-``) sit in a group with the split they pair with.
"""

import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CAPABILITIES = {  # split-name prefix -> (section, family)
    "asr-": ("通用识别", "asr"),
    "term-": ("行业术语", "asr"),
    "num-": ("号码", "asr"),
    "ctx-": ("上下文矫正", "asr"),
    "owner-": ("机主识别", "ts"),
    "diar8-": ("角色分离 5–8 人", "meeting"),
    "diar-": ("角色分离 ≤4 人", "meeting"),
}
TASKS = {"short": "asr", "long": "asr", "context": "asr", "owner": "ts_asr", "meeting": "speaker_attributed_asr"}


def capability(name):
    return next((section, family) for prefix, (section, family) in CAPABILITIES.items() if name.startswith(prefix))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("family", choices=["asr", "ts", "meeting"])
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    by_name = {s["name"]: s for s in recipe["splits"]}
    splits = []
    for s in recipe["splits"]:
        if "variant_of" in s:  # the variant has the scene of its base
            s = {**{k: v for k, v in by_name[s["variant_of"]].items() if k not in ("name", "rows", "display", "description",
                                                                                  "hotwords")}, **s}
        splits.append(s)

    def family(s):
        return capability(s.get("variant_of") or s["name"])[1]

    def tags(s):
        out = ["zh", "police", "synthetic"]
        if s["level"] != "quiet":
            out.append("noise")
        if s.get("far_field"):
            out.append("far-field")
        if s["form"] == "context":
            out.append("context-correction")
        return out

    def entry(s, hotwords=False):
        level = recipe["levels"][s["level"]]
        rows = "、".join(str(r) for r in s["rows"])
        label = f"{s['name']}-hw{recipe['hotword_list_size']}" if hotwords else s["name"]
        return {"dataset_id": recipe["dataset_id"], "version": recipe["version"], "split": label,
                "task": "asr_hotwords" if hotwords else TASKS[s["form"]], "label": label, "tags": tags(s),
                "display": f"{s['display']}（{recipe['hotword_list_size']} 词热词表）" if hotwords else s["display"],
                "description": f"{s['description']}。表格第 {rows} 行，{level['display']}，信噪比 "
                               f"{level['snr_db'][0]}～{level['snr_db'][1]} dB"}

    mine = [s for s in splits if family(s) == args.family]
    evaluation, groups = [], {}
    for s in mine:
        evaluation.append(entry(s))
        if s.get("hotwords"):
            evaluation.append(entry(s, hotwords=True))
    for s in mine:
        if "variant_of" in s:
            continue
        section, _ = capability(s["name"])
        level = recipe["levels"][s["level"]]["display"]
        kind = "（分开讲话）" if s.get("mode") == "separate" else "（重叠讲话）" if s.get("mode") == "overlap" else ""
        key = (section + kind, level)
        groups.setdefault(key, {"name": f"{section}{kind} · {level}", "section": section, "labels": [], "rows": set()})
        groups[key]["labels"].append(s["name"])
        groups[key]["rows"].update(r for r in s["rows"] if not (s.get("hotwords") and r == s["rows"][-1]))
        if s.get("hotwords"):
            hot = ("热词 300 个", level)
            groups.setdefault(hot, {"name": f"热词 300 个 · {level}", "section": "热词", "labels": [], "rows": set()})
            groups[hot]["labels"].append(f"{s['name']}-hw{recipe['hotword_list_size']}")
            groups[hot]["rows"].add(s["rows"][-1])
    variants = [s for s in mine if "variant_of" in s]
    if variants:
        groups[("channel", "")] = {
            "name": "通道对比", "section": "通道", "labels": [x for s in variants for x in (s["variant_of"], s["name"])],
            "rows": set(), "description": "每对逐条同一批语音和噪声：dev- 经执法记录仪通道（过载削波、高通、自动增益），"
                                          "far- 设备离民警 1–3 米；与原场景之差就是通道带来的错误"}
    config = {
        **({"task": "diarization"} if args.family == "meeting" else {"task": "asr"}),
        "tags": ["zh", "police", "synthetic", "noise"],
        "groups": [{"name": g["name"], "section": g["section"], "labels": g["labels"], "aggregate": "macro",
                    "description": g.get("description") or "对应验收表第 " + "、".join(str(r) for r in sorted(g["rows"]))
                    + " 行；各场景等权平均"} for g in groups.values()],
        "sampling_rate": recipe["sample_rate"],
        "evaluation": evaluation,
    }
    print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), end="")


if __name__ == "__main__":
    main()
