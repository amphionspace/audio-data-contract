#!/usr/bin/env python3
"""Build the final training-text version v3 (text-final-v3): v2 plus rule 8 of docs/reference/training-text.md
(Latin parentheticals the speaker did not read are dropped; issue #299). Only fleurs_zh has them in large numbers.

A parenthetical counts when its content has Latin letters and no Chinese characters, e.g. 孙德尔本斯（Sundarbans）.
Whether it was read is decided per recording from ASR evidence (``--decisions``, written by decide.py in the run
directory from whisper-large-v3 and Qwen3-ASR-1.7B transcripts): not read, the parenthetical and the space before it
go; read, only the brackets go. Then rule 7 (spaces) runs again on the changed text. Nothing else in a row changes;
the train supervisions are written to ``<final version>/text/<artifact>.jsonl.gz`` and the v2 final is marked
superseded_by the v3 one in catalog/text_final_v2.yaml by hand.

    python -I scripts/text_final/build_v3.py --catalog catalog --decisions <run_dir>/v3/decisions.json \
        --out-yaml catalog/text_final_v3.yaml --review <run_dir>/v3/build-review.json
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_v2 = _load("text_final_build_v2", "text_final/build_v2.py")
SOURCE = ("fleurs_zh", "legacy-20260804-final-v2-20261123")
FINAL = "legacy-20260804-final-v3-20261124"
ARTIFACT = "train_sup_0"
SPEC = "docs/reference/training-text.md（v3）"
SPAN = re.compile(r"\s*[（(]([^（）()㐀-鿿]*[A-Za-z][^（）()㐀-鿿]*)[）)]")
HAN = re.compile(r"[㐀-鿿]")


def apply(text: str, spans: list[dict]) -> str:
    """Apply the per-recording decisions; the spans must be exactly the ones SPAN finds in text."""
    found = [(m.start(), m.group(0)) for m in SPAN.finditer(text)]
    assert found == [(s["start"], s["span"]) for s in spans], (text, spans)
    out, last = [], 0
    for m, s in zip(SPAN.finditer(text), spans, strict=True):
        out.append(text[last : m.start()])
        if s["read"]:
            out.append(m.group(0)[: len(m.group(0)) - len(m.group(0).lstrip())] + m.group(1).strip())
        last = m.end()
    out.append(text[last:])
    return build_v2.rule5("".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument("--roots", type=Path, default=Path("/workspace/data/registry/roots.json"))
    ap.add_argument("--decisions", type=Path, required=True)
    ap.add_argument("--out-yaml", type=Path, required=True)
    ap.add_argument("--review", type=Path, required=True)
    args = ap.parse_args()
    roots = json.loads(args.roots.read_text())
    entry = next(e for e in YAML(typ="safe").load((args.catalog / "text_final_v2.yaml").read_text())
                 if (e["dataset_id"], e["version"]) == SOURCE)
    decisions = json.loads(args.decisions.read_text())
    e = copy.deepcopy(entry)
    ds = e["dataset_id"]
    arts = {a["name"]: a for a in e["artifacts"]}
    a = arts[ARTIFACT]
    src = Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]
    vdir = Path("datasets") / ds / "versions" / FINAL
    dst = args.root / vdir / "text" / f"{ARTIFACT}.jsonl.gz"
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = changed = dropped = kept = 0
    review = []
    with gzip.open(src, "rt") as f, gzip.open(dst, "wt") as w:
        for line in f:
            row = json.loads(line)
            n += 1
            spans = decisions.get(row["id"], [])
            if spans:
                new = apply(row["text"], spans)
                # only brackets, their Latin content and spaces may change
                assert HAN.findall(new) == HAN.findall(row["text"]), (row["text"], new)
                if new != row["text"]:
                    changed += 1
                    dropped += sum(not s["read"] for s in spans)
                    kept += sum(s["read"] for s in spans)
                    review.append({"id": row["id"], "old": row["text"], "new": new,
                                   "spans": [(s["span"].strip(), s["read"], s["reason"]) for s in spans]})
                    row["text"] = new
            else:
                assert not SPAN.search(row["text"]), row["text"]
            w.write(json.dumps(row, ensure_ascii=False) + "\n")
    assert changed == len(decisions)
    data = dst.read_bytes()
    a["root_alias"], a["relative_path"] = "aidc_data", str(vdir / "text" / f"{ARTIFACT}.jsonl.gz")
    a["expected_bytes"], a["sha256"] = len(data), hashlib.sha256(data).hexdigest()
    args.review.write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n")

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    what = (f"拉丁文括注（规则 8）{changed:,} 条：没读的 {dropped:,} 处整段删掉，读了的 {kept:,} 处只去括号")
    counts = {"records": n, "changed_records": changed, "parentheticals_dropped": dropped, "parentheticals_unbracketed": kept}
    rel = vdir / "state.json"
    (args.root / rel).write_text(json.dumps({
        "schema_version": "dataset-state/1.0", "dataset_id": ds, "version": FINAL, "state": "prepared",
        "updated_at": now, "error": None,
        "metadata": {"stage": "built", "owner": "mingdong", "source": f"{ds}@{e['version']}", "rules": what,
                     "files": {ARTIFACT: counts}, "decisions": str(args.decisions), "spec": SPEC,
                     "issue": "amphionspace/audio-data-contract#299", "run_dir": build_v2.RUN_DIR},
    }, ensure_ascii=False, indent=2) + "\n")
    start = e["version"]
    e["artifacts"] = [x for x in e["artifacts"] if x.get("kind") != "dataset-state"]
    e["artifacts"].insert(0, {"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                              "relative_path": str(rel)})
    e["version"] = FINAL
    e["derived_from"] = f"{ds}@{start}"
    e["splits"]["train"].setdefault("statistics", {})["final_v3_changed_records"] = changed
    e["recipe_parameters"] = {
        "spec": SPEC,
        "start": f"{ds}@{start}",
        "rounds": what,
        "evidence": "每条录音逐处判断：whisper-large-v3（语种 zh）写出括注里的字母，或 whisper 与 Qwen3-ASR-1.7B 都在括注处多出音译汉字，算读了；"
                    "两个 ASR 写出的括注逐处人工复核，改判 13 处。Qwen3-ASR 单独写出括注不算证据（它会复现 FLEURS 的括注写法）。",
        "unchanged": "括号里有汉字的括注、录音清单、音频和 dev/test 划分，引用起点版本的产物",
    }
    prov = dict(e.get("provenance") or {})
    prov.update({
        "snapshot_date": now[:10],
        "description": (
            f"{ds}@legacy-20260804 的训练文本终版 v3：在 v2 终版 {ds}@{start} 上处理{what}，按 audio-data-contract {SPEC}"
            "（issue #299：训练文本里的“孙德尔本斯（Sundarbans）”这类括注朗读人多数没读，模型学会了凭空输出括注）。"
            "其余字段、录音清单和音频照旧，引用起点版本的产物。"
        ),
        "source": f"{ds}@{start}",
        "method": "text-final-v3",
        "owner": "mingdong",
        "run_dir": build_v2.RUN_DIR,
        "build_script": "scripts/text_final/build_v3.py",
    })
    e["provenance"] = prov
    build_v2.dump(args.out_yaml, [e], f"# 训练文本终版 v3（text-final-v3，2026-11-24）：v2 加规则 8（删掉没读的拉丁文括注，issue #299），规范见 {SPEC}。\n"
                  "# 生成脚本 scripts/text_final/build_v3.py；只有 fleurs_zh 有 v3，其余来源的 v2 或 v1 终版仍是终版。\n")
    print(ds, FINAL, counts, flush=True)


if __name__ == "__main__":
    main()
