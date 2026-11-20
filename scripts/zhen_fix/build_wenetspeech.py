#!/usr/bin/env python3
"""Build the zhen-fix-en-v1 derived version of wenetspeech_clean: English the speaker said, written as Chinese in the
label, goes back to English (rule 1 of docs/reference/zh-en-transcription.md).

The edits are planned in the run dir (``wenet/scripts/plan.py``): candidates are rows where Qwen3-ASR-1.7B heard an
English word the label lacks; whisper-large-v3 and Qwen3-ASR with Chinese forced must both hear it too, and a replaced
label span must be a paraphrase or a made-up transliteration (established names, places and loanwords keep the
label). This script only applies the planned edits (``action == "apply"`` rows of ``--patches``) to the base
version's train supervisions, checking that each row still has the planned original text. The original text goes to
``custom.zhen_fix``; ``custom.clean`` and every other field stay. Recordings and the audio stay at the base paths.

Writes <root>/datasets/wenetspeech_clean/versions/<VERSION>/{supervisions/train.jsonl.gz, evidence/patches.jsonl,
state.json} and the catalog entry to --out-yaml. The record index is built afterwards with
``audio-data-contract build-record-index --register``.

    python -I scripts/zhen_fix/build_wenetspeech.py --catalog catalog --patches <run_dir>/plan/patches.jsonl \
        --out-yaml catalog/zhen_fix_wenetspeech.yaml --review-dir <run_dir>/review
"""

from __future__ import annotations

import argparse
import collections
import copy
import gzip
import hashlib
import io
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import DROP_PROVENANCE, KEEP_STATS

DATASET = "wenetspeech_clean"
BASE = "train-punc-v1-20261102-ctxclean-20261110"
VERSION = f"{BASE}-zhenfix-20261119"
RULES = "zhen-fix-en-v1"
RUN_DIR = "/workspace/workspace/mingdong/data/amphiondata/zhen-fix-20261117/wenet"
SUMMARY = "WenetSpeech 训练文本英文写法修正"
EVIDENCE_FIELDS = (
    "id",
    "label",
    "kind",
    "op",
    "ref_span",
    "english",
    "from",
    "to",
    "qwen",
    "qwen_zh",
    "whisper",
    "firered",
    "action",
    "reason",
)


def rewrite(
    src: Path, dst: Path, patches: dict, review: list, rnd: random.Random
) -> dict:
    """Apply the patches to one Lhotse supervisions JSONL.gz deterministically."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    rows = changed = 0
    stale = []
    with (
        gzip.open(src, "rt", encoding="utf-8") as f,
        gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz,
    ):
        for line in f:
            rows += 1
            at = line.find(
                '"id": "'
            )  # fast path; "recording_id" does not match (no quote before id)
            sid = (
                line[at + 7 : line.index('"', at + 7)]
                if at >= 0
                else json.loads(line)["id"]
            )
            p = patches.get(sid)
            if p is not None:
                row = json.loads(line)
                if row.get("text") != p["from"]:
                    stale.append(sid)
                else:
                    row["text"] = p["to"]
                    row["custom"] = {
                        **(row.get("custom") or {}),
                        "zhen_fix": {
                            "original_text": p["from"],
                            "rules": RULES,
                            "op": p["op"],
                            "english": p["english"],
                        },
                    }
                    changed += 1
                    item = {
                        "id": sid,
                        "label": p["label"],
                        "kind": p.get("kind"),
                        "op": p["op"],
                        "from": p["from"],
                        "to": p["to"],
                    }
                    if len(review) < 100:
                        review.append(item)
                    elif (j := rnd.randrange(changed)) < 100:
                        review[j] = item
                    line = json.dumps(row, ensure_ascii=False) + "\n"
            gz.write(line.encode("utf-8"))
    if stale:
        raise SystemExit(
            f"{len(stale)} planned rows no longer have their planned text, e.g. {stale[:3]}"
        )
    missing = len(patches) - changed
    if missing:
        raise SystemExit(f"{missing} planned rows are not in {src}")
    data = buf.getvalue()
    dst.write_bytes(data)
    return {
        "records": rows,
        "changed": changed,
        "expected_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument("--patches", type=Path, required=True)
    ap.add_argument("--out-yaml", type=Path, required=True)
    ap.add_argument("--review-dir", type=Path, required=True)
    args = ap.parse_args()

    base = None
    for path in sorted(args.catalog.glob("*.yaml")):
        for e in YAML(typ="safe").load(path.read_text()) or []:
            if isinstance(e, dict) and (e.get("dataset_id"), e.get("version")) == (
                DATASET,
                BASE,
            ):
                base = e
    if base is None:
        raise SystemExit(f"{DATASET}@{BASE} is not in the catalog")

    planned = [json.loads(line) for line in args.patches.read_text().splitlines()]
    patches = {r["id"]: r for r in planned if r["action"] == "apply"}
    e = copy.deepcopy(base)
    vdir = Path("datasets") / DATASET / "versions" / VERSION
    arts = {a["name"]: a for a in e["artifacts"]}
    sup = arts["train_supervisions_punc_0"]
    rnd, review = random.Random(20261119), []
    res = rewrite(
        args.root / sup["relative_path"],
        args.root / vdir / "supervisions" / "train.jsonl.gz",
        patches,
        review,
        rnd,
    )
    print(res, flush=True)
    sup["relative_path"] = str(vdir / "supervisions" / "train.jsonl.gz")
    sup["expected_bytes"], sup["sha256"] = res["expected_bytes"], res["sha256"]

    evidence = args.root / vdir / "evidence" / "patches.jsonl"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        "".join(
            json.dumps({k: r.get(k) for k in EVIDENCE_FIELDS}, ensure_ascii=False)
            + "\n"
            for r in planned
        )
    )
    data = evidence.read_bytes()
    actions = collections.Counter((r["label"], r["action"]) for r in planned)
    e["artifacts"] = [
        a
        for a in e["artifacts"]
        if a.get("kind") not in ("lance-record-index", "dataset-state")
    ]
    e["artifacts"].append(
        {
            "name": "zhen_fix_patches",
            "kind": "jsonl-metadata",
            "root_alias": "aidc_data",
            "relative_path": str(vdir / "evidence" / "patches.jsonl"),
            "expected_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "metadata": {
                "record_count": len(planned),
                "description": (
                    "全部候选（LLM 判为音译 A / 意译 B / 识别错 C）的逐条处理：标注原文、改后文本、替换或插入、标注片段和英文、"
                    "Qwen3-ASR（自动语种、强制中文）、whisper-large-v3、FireRedASR2-AED 的转写、LLM 片段类别、是否改和不改的原因"
                ),
            },
        }
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    state_rel = vdir / "state.json"
    state = {
        "schema_version": "dataset-state/1.0",
        "dataset_id": DATASET,
        "version": VERSION,
        "state": "prepared",
        "updated_at": now,
        "error": None,
        "metadata": {
            "stage": "built",
            "owner": "mingdong",
            "source": f"{DATASET}@{BASE}",
            "rules": RULES,
            "changed_records": res["changed"],
            "records": res["records"],
            "run_dir": RUN_DIR,
            "candidates": len(planned),
            "by_label": {
                f"{lab}_{act}": n for (lab, act), n in sorted(actions.items())
            },
        },
    }
    (args.root / state_rel).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    )
    e["artifacts"].insert(
        0,
        {
            "name": "preparation_state",
            "kind": "dataset-state",
            "root_alias": "aidc_data",
            "relative_path": str(state_rel),
        },
    )
    for s in (e.get("splits") or {}).values():
        for role in ("records_lance", "preparation_state"):
            (s.get("artifacts") or {}).pop(role, None)
        (s.get("provenance") or {}).pop("preparation_status", None)
        if "statistics" in s:
            s["statistics"] = {
                k: v for k, v in s["statistics"].items() if k in KEEP_STATS
            }
            s["statistics"]["zhen_fix_changed_records"] = res["changed"]
    e["version"] = VERSION
    e["derived_from"] = f"{DATASET}@{BASE}"
    e["recipe_parameters"] = {
        "rules": (
            f"{RULES}: 候选是 Qwen3-ASR-1.7B 听出英文、标注缺这个英文的句子；whisper-large-v3 和强制中文的 Qwen3-ASR "
            "都听出同一个英文才改；替换的标注片段要是意译或生造的音译，通行的人名、地名译名和外来词不改；标注漏写的英文补进去"
        ),
        "changed": "train 划分 text 里改动的记录；原文本在 custom.zhen_fix.original_text，custom.clean 不变",
        "unchanged": "其余记录、字段、录音清单和音频，引用底版本的产物",
        "evidence": "zhen_fix_patches",
    }
    prov = {
        k: v for k, v in (e.get("provenance") or {}).items() if k not in DROP_PROVENANCE
    }
    e["provenance"] = prov
    prov.update(
        {
            "summary": SUMMARY,
            "snapshot_date": now[:10],
            "description": (
                f"{DATASET}@{BASE} 的训练文本里，说话人说英文、标注写成汉字的句子按 audio-data-contract "
                "docs/reference/zh-en-transcription.md 规则 1 换回英文（例：艾特斯→iTunes、五本儿→Uber、对抗→PK，标注漏写的补上："
                "那边的办公室→那边的office办公室）。候选是 Qwen3-ASR-1.7B 听出英文、标注缺这个英文的 24,336 句；whisper-large-v3 和"
                "强制中文的 Qwen3-ASR-1.7B 都听出同一个英文才改。通行的人名、地名译名和外来词（大卫、弗洛格、纽约、派对）照中文念和英文"
                "发音相近，识别模型分不出来，不改。FireRedASR2-AED 的转写大多照抄标注里的汉字（品牌名只有约 8% 写成英文），听不出这类错误，不作依据。"
                f"共改 {res['changed']:,} 条，原文本存进 custom.zhen_fix；其余字段、录音清单和音频照旧，引用底版本的产物。"
            ),
            "source": f"{DATASET}@{BASE}",
            "method": RULES,
            "rules": RULES,
            "changed_records": res["changed"],
            "owner": "mingdong",
            "run_dir": RUN_DIR,
            "build_script": "scripts/zhen_fix/build_wenetspeech.py",
        }
    )
    yaml = YAML()
    yaml.width = 4096
    with args.out_yaml.open("w") as w:
        w.write(
            "# WenetSpeech 训练文本里写成汉字的英文换回英文（zhen-fix-en-v1，2026-11-19）。底版本是 ctxclean 派生版，"
            "交付配方 v7set34 用的是 train-punc-v1-20261102。\n"
            "# 生成脚本 scripts/zhen_fix/build_wenetspeech.py，改动清单在 zhen_fix_patches。\n"
        )
        yaml.dump([e], w)
    args.review_dir.mkdir(parents=True, exist_ok=True)
    (args.review_dir / f"{DATASET}@{VERSION}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in review)
    )


if __name__ == "__main__":
    main()
