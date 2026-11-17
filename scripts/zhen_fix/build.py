#!/usr/bin/env python3
"""Build the zhen-fix-v1 derived versions: space-separated single uppercase letters in Chinese texts are joined
(K T V -> KTV), per rule 2 of docs/reference/zh-en-transcription.md.

Only the train splits' text files are rewritten (AudioRecord ``target``, Lhotse supervision ``text``); the original
text goes to ``metadata.zhen_fix`` / ``custom.zhen_fix``. Everything else (recordings, audio indexes, eval/test splits)
is referenced at the base version's paths. Lowercase and mixed-case letter runs (mostly math variables, "d y 比 d x")
and Chinese numerals in letter+digit tokens ("五G") are left unchanged.

Writes <root>/datasets/<id>/versions/<base>-zhenfix-20261117/..., the catalog entries to --out-yaml (copied from the
base entries in --catalog) and per-version samples of changed texts to --review-dir. Record indexes are built
afterwards with ``audio-data-contract build-record-index --register``.

    python -I scripts/zhen_fix/build.py --catalog catalog --out-yaml catalog/zhen_fix.yaml --review-dir <run_dir>/review
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML

SUFFIX = "zhenfix-20261117"
RULES = "zhen-fix-v1"
RUN_DIR = "/workspace/workspace/mingdong/data/amphiondata/zhen-fix-20261117"
TARGETS = [
    ("emilia2_mix", "mix-20261013-utts-ctxclean-20261110"),
    ("emilia2_short", "short-lance-20261023-ctxclean-20261110"),
    ("emilia2_dialog", "dialog-turn-taking-20261013-enroll-ctxclean-20261110"),
    ("police_asr_unified", "train-punc-v1-20261102"),
    ("magicdata_ramc", "train-punc-v1-20261102-ctxclean-20261110"),
    ("magicdata_ramc", "turn-taking-20261014-utts-punc-20261102-ctxclean-20261110"),
    ("magicdata_ramc", "allspk-asr-v1-20261103"),
    ("magicdata_ramc", "allspk-ts-v1-20261104"),
    ("aishell4", "asr-20261014-punc-20261102-ctxclean-20261110"),
    ("aishell4", "turn-taking-20261014-utts-punc-20261102-ctxclean-20261110"),
]
# dataset-level summaries, reused so the dataset's overview row keeps its description
SUMMARY = {"emilia2_mix": "Emilia2 长音频合成的 2/3 人目标说话人混合", "emilia2_short": "Emilia2 中英短音频普通转写",
           "emilia2_dialog": "Emilia2 中英对话的轮流说话目标说话人数据", "police_asr_unified": "警务合成语音统合版（V1–V6 合并）",
           "magicdata_ramc": "中文手机通话自然对话（MagicData-RAMC）", "aishell4": "中文多人会议（AISHELL-4）；含轮流说话混合版"}
KEEP_STATS = {"records", "duration_hours", "duration_basis", "languages", "negative_records", "unique_mixture_count",
              "unique_mixture_duration_hours", "recordings", "recordings_with_supervisions", "records_punctuated"}
DROP_PROVENANCE = {"preparation_status", "quality_status", "status", "superseded_by"}
CJK = re.compile(r"[一-鿿]")
SPACED_UPPER = re.compile(r"(?<![A-Za-z'])[A-Z](?: [A-Z])+(?![A-Za-z'])")
TEXT_KINDS = {"audio-records": "target", "lhotse-supervisions": "text"}


def fix(text: str) -> str:
    """Join space-separated single uppercase letters in a text that has Chinese characters."""
    if not isinstance(text, str) or not CJK.search(text):
        return text
    return SPACED_UPPER.sub(lambda m: m.group(0).replace(" ", ""), text)


def rewrite(src: Path, dst: Path, field: str, review: list, rnd: random.Random) -> dict:
    """Rewrite one JSONL.gz file deterministically; returns counts, bytes and sha256."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    rows = changed = seen = 0
    with gzip.open(src, "rt", encoding="utf-8") as f, gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for line in f:
            row = json.loads(line)
            rows += 1
            old = row.get(field)
            new = fix(old)
            if new != old:
                changed += 1
                row[field] = new
                key = "metadata" if field == "target" else "custom"
                row[key] = {**(row.get(key) or {}), "zhen_fix": {
                    ("original_target" if field == "target" else "original_text"): old, "rules": RULES}}
                seen += 1
                item = {"id": row["id"], "from": old, "to": new}
                if len(review) < 60:
                    review.append(item)
                elif (j := rnd.randrange(seen)) < 60:
                    review[j] = item
                line = json.dumps(row, ensure_ascii=False) + "\n"
            gz.write(line.encode("utf-8"))
    data = buf.getvalue()
    dst.write_bytes(data)
    return {"records": rows, "changed": changed, "expected_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument("--out-yaml", type=Path, required=True)
    ap.add_argument("--review-dir", type=Path, required=True)
    args = ap.parse_args()

    yaml = YAML()
    yaml.width = 4096
    entries = {}
    for path in sorted(args.catalog.glob("*.yaml")):
        if path.resolve() == args.out_yaml.resolve():
            continue
        for e in YAML(typ="safe").load(path.read_text()) or []:
            if isinstance(e, dict) and (e.get("dataset_id"), e.get("version")) in TARGETS:
                entries[(e["dataset_id"], e["version"])] = e
    missing = [t for t in TARGETS if t not in entries]
    if missing:
        raise SystemExit(f"base versions not in the catalog: {missing}")

    args.review_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_entries, summary = [], {}
    for ds, base in TARGETS:
        e = copy.deepcopy(entries[(ds, base)])
        version = f"{base}-{SUFFIX}"
        vdir = Path("datasets") / ds / "versions" / version
        base_dir = Path("datasets") / ds / "versions" / base
        arts = {a["name"]: a for a in e["artifacts"]}
        train_arts = {n for split, s in (e.get("splits") or {}).items() if split.startswith("train")
                      for names in (s.get("artifacts") or {}).values() for n in names}
        rnd, review, stats = random.Random(20261117), [], {}
        for name in sorted(train_arts):
            a = arts.get(name)
            if not a or a.get("kind") not in TEXT_KINDS:
                continue
            rel = Path(a["relative_path"])
            try:
                inner = rel.relative_to(base_dir)
            except ValueError:
                raise SystemExit(f"{ds}@{base}: {name} lives outside its version directory: {rel}")
            res = rewrite(args.root / rel, args.root / vdir / inner, TEXT_KINDS[a["kind"]], review, rnd)
            a["relative_path"] = str(vdir / inner)
            a["expected_bytes"], a["sha256"] = res["expected_bytes"], res["sha256"]
            stats[name] = {"records": res["records"], "changed": res["changed"]}
            print(ds, version, name, stats[name], flush=True)
        # the record index is rebuilt for the new version (build-record-index --register)
        e["artifacts"] = [a for a in e["artifacts"] if a.get("kind") not in ("lance-record-index", "dataset-state")]
        for split, s in (e.get("splits") or {}).items():
            for role in ("records_lance", "preparation_state"):
                (s.get("artifacts") or {}).pop(role, None)
            (s.get("provenance") or {}).pop("preparation_status", None)
            if "statistics" in s:
                s["statistics"] = {k: v for k, v in s["statistics"].items() if k in KEEP_STATS}
                if split.startswith("train"):
                    names = {n for names in (s.get("artifacts") or {}).values() for n in names}
                    s["statistics"]["zhen_fix_changed_records"] = sum(v["changed"] for n, v in stats.items() if n in names)
        state_rel = vdir / "state.json"
        changed = sum(v["changed"] for v in stats.values())
        state = {"schema_version": "dataset-state/1.0", "dataset_id": ds, "version": version, "state": "complete",
                 "updated_at": now, "error": None,
                 "metadata": {"owner": "mingdong", "source": f"{ds}@{base}", "rules": RULES, "changed_records": changed,
                              "files": stats, "run_dir": RUN_DIR}}
        (args.root / state_rel).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        e["artifacts"].insert(0, {"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                                  "relative_path": str(state_rel)})
        e["version"] = version
        e["derived_from"] = f"{ds}@{base}"
        e["recipe_parameters"] = {
            "rules": f"{RULES}: Chinese texts only; space-separated single uppercase letters joined (K T V -> KTV)",
            "changed": "train 划分 target / text 里命中规则的记录；原文本在 metadata.zhen_fix.original_target 或 custom.zhen_fix.original_text",
            "unchanged": "其余记录、字段、音频引用、音频索引和非 train 划分，引用底版本的产物",
        }
        prov = {k: v for k, v in (e.get("provenance") or {}).items() if k not in DROP_PROVENANCE}
        e["provenance"] = prov
        prov.update({
            "summary": SUMMARY[ds], "snapshot_date": now[:10],
            "description": (f"{ds}@{base} 的中文文本按 audio-data-contract docs/reference/zh-en-transcription.md 规则 2 修正："
                            "用空格隔开的单个大写字母连写（K T V→KTV、A P P→APP、N F C→NFC），原文本存进 "
                            "metadata.zhen_fix / custom.zhen_fix。小写或大小写混合的字母串（多是数学变量）和字母数字词里的汉字数字不改。"
                            f"只改 train 划分的文本，共 {changed:,} 条；其余字段、音频引用和其他划分照旧，引用底版本的产物。"),
            "source": f"{ds}@{base}", "method": RULES, "rules": RULES, "changed_records": changed,
            "owner": "mingdong", "run_dir": RUN_DIR, "build_script": "scripts/zhen_fix/build.py",
        })
        out_entries.append(e)
        summary[f"{ds}@{version}"] = stats
        (args.review_dir / f"{ds}@{version}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in review))
    with args.out_yaml.open("w") as w:
        w.write("# zh-en 写法规则修正（zhen-fix-v1，2026-11-17）：拆开的大写字母连写（K T V→KTV），只改 train 划分的 target / text。\n"
                "# 底版本是交付配方 v7set34 的来源，有 ctxclean-20261110 派生版的从派生版接着改。生成脚本 scripts/zhen_fix/build.py。\n")
        yaml.dump(out_entries, w)
    (args.review_dir / "build-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
