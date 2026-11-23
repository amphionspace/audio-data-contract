#!/usr/bin/env python3
"""Build the final training-text versions v2 (text-final-v2): v1 plus rule 5 of docs/reference/zh-en-transcription.md
(spaces: one between English words, none between Chinese characters or between Chinese and English), and v2 finals
for read-speech corpora that had no v1.

- From a v1 final (catalog/text_final_v1.yaml): every train-like split (not dev / test / eval / validation) gets rule 5
  and rule zhen-fix-v1 (letter runs; v1 applied it only to the splits recipe v7set34 trains on). Only finals the
  rules change get ``<recipe version>-final-v2-20261123``; the v1 final is marked superseded_by it.
- From a read-speech corpus (``--new dataset@version=punc_dataset@punc_version``): the train supervisions take the
  written punctuation of the punc version by id when it has the same letters once marks, spaces and case are
  ignored (rule 1, punc-student-v1), then rule 5 and zhen-fix-v1.

Rule 5 touches only texts with Chinese characters: whitespace runs become one space, and a space next to a Chinese
character, kana or a full-width mark is dropped; a space between two other characters (English words, digits) stays.
The same sentence elsewhere in a row (metadata.scene.targets[].text, hotword lists) changes with it. Changed text files
go to ``<final version>/text/<artifact>.jsonl.gz``; recordings, audio and unchanged files are referenced in place.
Record indexes are built afterwards with ``audio-data-contract build-record-index --register``.

    python -I scripts/text_final/build_v2.py --catalog catalog --out-yaml catalog/text_final_v2.yaml \
        --review-dir <run_dir>/v2/review [--new aishell@legacy-20260804=aishell@punc-written-v1-20261029 ...] \
        [--scan | --placeholder]
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


zhen_fix = _load("zhen_fix_build", "zhen_fix/build.py")
text_final = _load("text_final_build", "text_final/build.py")
V1 = text_final.SUFFIX
SUFFIX = "final-v2-20261123"
SPEC = "docs/reference/training-text.md（v2）"
RUN_DIR = text_final.RUN_DIR
EVAL = ("eval", "dev", "validation", "test")
FIELDS = {"audio-records": "target", "lhotse-supervisions": "text"}
HAN = re.compile(r"[㐀-鿿]")
WIDE = r"[⺀-鿿　-〿＀-￯]"
REVIEW = 40


def rule5(text: str) -> str:
    if not isinstance(text, str) or not HAN.search(text):
        return text
    out = re.sub(r"\s+", " ", text).strip()
    return re.sub(rf"(?<={WIDE}) | (?={WIDE})", "", out)


def fix(text: str) -> str:
    return zhen_fix.fix(rule5(text))


def letters(text: str) -> str:
    return re.sub(r"[\W_]", "", text.casefold())


def fix_row(row: dict, field: str, punc: dict | None, n: Counter) -> tuple[str, str] | None:
    old = row.get(field)
    if not isinstance(old, str):
        return None
    new = old
    if punc is not None and old:
        written = punc.get(row["id"])
        if written is None:
            n["punc_missing"] += 1
        elif letters(written) != letters(old):
            n["punc_letters_differ"] += 1
        elif written != old:
            new = written
            n["punc_applied"] += 1
    spaced = rule5(new)
    n["rule5_changed"] += spaced != new
    joined = zhen_fix.fix(spaced)
    n["r1_changed"] += joined != spaced
    if joined == old:
        return None
    row[field] = joined
    meta = row.get("metadata") or {}
    for t in (meta.get("scene") or {}).get("targets") or []:
        if isinstance(t.get("text"), str):
            t["text"] = fix(t["text"])
    for holder in (row, meta, row.get("custom") or {}):
        for key in ("hotwords", "interferer_hotwords"):
            if isinstance(holder.get(key), list):
                holder[key] = [fix(w) if isinstance(w, str) else w for w in holder[key]]
    key = "metadata" if field == "target" else "custom"
    row[key] = {**(row.get(key) or {}), "text_final": {"original_text": old, "rules": "text-final-v2"}}
    return old, joined


def process(job: tuple) -> dict:
    """Scan (dst None) or rewrite one text file; dst is kept only when a row changed."""
    src, dst, field, punc_path = job
    punc = None
    if punc_path:
        with gzip.open(punc_path, "rt", encoding="utf-8") as f:
            punc = {r["id"]: r["text"] for r in map(json.loads, f)}
    n, review = Counter(), []
    tmp = Path(str(dst) + ".tmp") if dst else None
    if tmp:
        tmp.parent.mkdir(parents=True, exist_ok=True)
    raw = tmp.open("wb") if tmp else None
    gz = gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) if raw else None
    with gzip.open(src, "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            n["records"] += 1
            edit = fix_row(row, field, punc, n)
            if edit:
                n["changed_records"] += 1
                line = json.dumps(row, ensure_ascii=False) + "\n"
                if len(review) < REVIEW:
                    review.append({"id": row.get("id"), "from": edit[0], "to": edit[1]})
            if gz:
                gz.write(line.encode("utf-8"))
    out = {"counts": dict(n), "review": review}
    if not gz:
        return out
    gz.close()
    raw.close()
    if not n["changed_records"]:
        tmp.unlink()
        return out
    os.replace(tmp, dst)
    h = hashlib.sha256()
    with dst.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return {**out, "expected_bytes": dst.stat().st_size, "sha256": h.hexdigest()}


def relocate(entry: dict, deployed: dict | None, roots: dict) -> None:
    """Point artifacts whose catalog path does not resolve here at the deployed catalog's relocated path (legacy sets
    moved under datasets/<dataset>/versions/<version>/)."""
    moved = {a["name"]: a for a in (deployed or {}).get("artifacts", [])}
    for a in entry["artifacts"]:
        m = moved.get(a["name"])
        if "relative_path" not in a or a.get("root_alias", "aidc_data") not in roots or not m or "relative_path" not in m:
            continue
        if (Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]).exists():
            continue
        if (Path(roots[m.get("root_alias", "aidc_data")]) / m["relative_path"]).exists():
            a["root_alias"], a["relative_path"] = m.get("root_alias", "aidc_data"), m["relative_path"]
            for k in ("expected_bytes", "sha256"):
                a.pop(k, None)
                if k in m:
                    a[k] = m[k]


def text_artifacts(entry: dict, only_train: bool = False) -> list[str]:
    arts = {a["name"]: a for a in entry["artifacts"]}
    names = []
    for split, s in (entry.get("splits") or {}).items():
        if split.startswith(EVAL) or (only_train and split != "train"):
            continue
        for group in (s.get("artifacts") or {}).values():
            names += [n for n in group if arts.get(n, {}).get("kind") in FIELDS and n not in names]
    return names


def punc_file(entry: dict, roots: dict) -> Path:
    arts = {a["name"]: a for a in entry["artifacts"]}
    names = [n for g in entry["splits"]["train"]["artifacts"].values() for n in g if arts[n]["kind"] == "lhotse-supervisions"]
    assert len(names) == 1, (entry["dataset_id"], entry["version"], names)
    a = arts[names[0]]
    return Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]


def dump(path: Path, entries: list, head: str) -> None:
    yaml = YAML()
    yaml.width = 4096
    with path.open("w") as w:
        w.write(head)
        yaml.dump(entries, w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument("--roots", type=Path, default=Path("/workspace/data/registry/roots.json"))
    ap.add_argument(
        "--registry-catalog",
        type=Path,
        default=Path("/workspace/data/registry/catalog"),
        help="deployed catalog; its relocated paths are used where a repo path does not resolve here",
    )
    ap.add_argument("--out-yaml", type=Path, required=True)
    ap.add_argument("--review-dir", type=Path, required=True)
    ap.add_argument("--new", action="append", default=[], help="dataset@version=punc_dataset@punc_version")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--reserve", action="append", default=[], help="with --placeholder: also reserve dataset@version (no scan yet)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--scan", action="store_true", help="count what the rules change; write nothing but the summary")
    mode.add_argument("--placeholder", action="store_true", help="reserve the versions the scan found changes for")
    args = ap.parse_args()
    roots = json.loads(args.roots.read_text())
    entries = {}
    for path in sorted(args.catalog.glob("*.yaml")):
        if path.resolve() == args.out_yaml.resolve():
            continue
        for e in YAML(typ="safe").load(path.read_text()) or []:
            if isinstance(e, dict) and "dataset_id" in e:
                entries[(e["dataset_id"], str(e["version"]))] = e
    deployed = {}
    for path in sorted(args.registry_catalog.glob("*.yaml")):
        for e in YAML(typ="safe").load(path.read_text()) or []:
            if isinstance(e, dict) and "dataset_id" in e:
                deployed[(e["dataset_id"], str(e["version"]))] = e
    # (dataset, recipe version) -> (base entry, punc file or None)
    sources = {}
    for e in YAML(typ="safe").load((args.catalog / "text_final_v1.yaml").read_text()):
        key = (e["dataset_id"], e["version"])
        relocate(entries[key], deployed.get(key), roots)
        sources[(e["dataset_id"], e["version"][: -len(V1) - 1])] = (entries[key], None)
    for spec in args.new:
        base, punc = (tuple(x.split("@", 1)) for x in spec.split("="))
        relocate(entries[base], deployed.get(base), roots)
        relocate(entries[punc], deployed.get(punc), roots)
        sources[base] = (entries[base], punc_file(entries[punc], roots))
    args.review_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.placeholder:
        scan = json.loads((args.review_dir / "scan.json").read_text())
        out = []
        keys = [k for k, v in scan.items() if v["changed_records"]] + [k for k in args.reserve if k not in scan]
        for key in keys:
            ds, version = key.split("@", 1)
            base = sources[(ds, version)][0] if (ds, version) in sources else entries[(ds, version)]
            final = f"{version}-{SUFFIX}"
            rel = Path("datasets") / ds / "versions" / final / "state.json"
            (args.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (args.root / rel).write_text(json.dumps({
                "schema_version": "dataset-state/1.0", "dataset_id": ds, "version": final, "state": "planned",
                "updated_at": now, "error": None,
                "metadata": {"stage": "building", "owner": "mingdong", "source": f"{ds}@{base['version']}",
                             "spec": SPEC, "run_dir": RUN_DIR},
            }, ensure_ascii=False, indent=2) + "\n")
            out.append({
                "schema_version": "dataset-catalog/2.0", "dataset_id": ds, "version": final,
                "languages": base.get("languages"), "tasks": base.get("tasks"), "aliases": [],
                "derived_from": f"{ds}@{base['version']}",
                "artifacts": [{"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                               "relative_path": str(rel)}],
                "splits": {"train": {"artifacts": {"preparation_state": ["preparation_state"]},
                                     "provenance": {"preparation_status": "building"}}},
                "provenance": {
                    "preparation_status": "building", "owner": "mingdong",
                    "description": f"{ds}@{version} 的训练文本终版 v2，按 audio-data-contract {SPEC} 统一空格等。构建中。",
                    "source": f"{ds}@{base['version']}", "method": "text-final-v2", "run_dir": RUN_DIR,
                },
            })
        dump(args.out_yaml, out, f"# 训练文本终版 v2（text-final-v2）：v1 加规则 5（空格），另含朗读语料的新终版，规范见 {SPEC}。占位，构建中。\n")
        print(f"reserved {len(out)} versions", flush=True)
        return

    jobs, plan = {}, {}
    with ProcessPoolExecutor(args.workers) as pool:
        for (ds, version), (base, punc) in sources.items():
            e = copy.deepcopy(base)
            final = f"{version}-{SUFFIX}"
            vdir = Path("datasets") / ds / "versions" / final
            arts = {a["name"]: a for a in e["artifacts"]}
            names = text_artifacts(e, only_train=punc is not None)
            plan[(ds, version)] = (e, final, vdir, names, punc)
            for name in names:
                a = arts[name]
                src = Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]
                dst = None if args.scan else args.root / vdir / "text" / f"{name}.jsonl.gz"
                jobs[(ds, version, name)] = pool.submit(
                    process, (src, dst, FIELDS[a["kind"]], str(punc) if punc and a["kind"] == "lhotse-supervisions" else None)
                )
        results = {k: f.result() for k, f in jobs.items()}

    out, summary = [], {}
    for (ds, version), (e, final, vdir, names, punc) in plan.items():
        arts = {a["name"]: a for a in e["artifacts"]}
        totals, files, review = Counter(), {}, []
        for name in names:
            res = results[(ds, version, name)]
            files[name] = res["counts"]
            totals.update({k: v for k, v in res["counts"].items() if k != "records"})
            review += res["review"]
            if "sha256" in res:
                a = arts[name]
                a["root_alias"], a["relative_path"] = "aidc_data", str(vdir / "text" / f"{name}.jsonl.gz")
                a["expected_bytes"], a["sha256"] = res["expected_bytes"], res["sha256"]
        summary[f"{ds}@{version}"] = {"changed_records": totals["changed_records"], "totals": dict(totals), "files": files}
        if totals["changed_records"]:
            print(ds, version, dict(totals), flush=True)
        (args.review_dir / f"{ds}@{version}.json").write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n")
        if args.scan or not totals["changed_records"]:
            continue
        e["artifacts"] = [a for a in e["artifacts"] if a.get("kind") not in ("lance-record-index", "dataset-state")]
        for s in (e.get("splits") or {}).values():
            for role in ("records_lance", "preparation_state"):
                (s.get("artifacts") or {}).pop(role, None)
            (s.get("provenance") or {}).pop("preparation_status", None)
            hit = {n: files[n]["changed_records"] for g in (s.get("artifacts") or {}).values() for n in g
                   if n in files and files[n].get("changed_records")}
            if hit:
                s.setdefault("statistics", {})["final_v2_changed_records"] = sum(hit.values())
        parts = []
        if totals["punc_applied"]:
            parts.append(f"书面化标点（规则 1，按 id 取自 {ds}@{punc.parent.name}）{totals['punc_applied']:,} 条")
        if totals["rule5_changed"]:
            parts.append(f"空格统一（中英规范规则 5）{totals['rule5_changed']:,} 条")
        if totals["r1_changed"]:
            parts.append(f"拆开的大写字母连写（zhen-fix-v1）{totals['r1_changed']:,} 条")
        what = "；".join(parts)
        rel = vdir / "state.json"
        (args.root / vdir).mkdir(parents=True, exist_ok=True)
        (args.root / rel).write_text(json.dumps({
            "schema_version": "dataset-state/1.0", "dataset_id": ds, "version": final, "state": "prepared",
            "updated_at": now, "error": None,
            "metadata": {"stage": "built", "owner": "mingdong", "source": f"{ds}@{e['version']}", "rules": what,
                         "files": files, "spec": SPEC, "run_dir": RUN_DIR},
        }, ensure_ascii=False, indent=2) + "\n")
        start = e["version"]
        e["artifacts"].insert(0, {"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                                  "relative_path": str(rel)})
        e["version"] = final
        e["derived_from"] = f"{ds}@{start}"
        e["recipe_parameters"] = {
            "spec": SPEC,
            "start": f"{ds}@{start}",
            "rounds": what,
            "unchanged": "规则没有改动的文本文件、录音清单、音频和 dev/test 划分，引用起点版本的产物",
        }
        prov = {k: v for k, v in (e.get("provenance") or {}).items() if k not in text_final.DROP_PROVENANCE}
        lead = (f"{ds}@{version} 的训练文本终版 v2：在 v1 终版 {ds}@{start} 上补做" if punc is None else
                f"{ds}@{version} 训练集的训练文本终版（v2 起新建，没有 v1）：")
        prov.update({
            "snapshot_date": now[:10],
            "description": (
                f"{lead}{what}，按 audio-data-contract {SPEC}。同一行里的场景文本和热词列表一起改；"
                "其余字段、录音清单和音频照旧，引用起点版本的产物。"
            ),
            "source": f"{ds}@{start}",
            "method": "text-final-v2",
            "owner": "mingdong",
            "run_dir": RUN_DIR,
            "build_script": "scripts/text_final/build_v2.py",
        })
        e["provenance"] = prov
        out.append(e)
    (args.review_dir / ("scan.json" if args.scan else "build-summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    if not args.scan:
        dump(args.out_yaml, out, f"# 训练文本终版 v2（text-final-v2）：v1 加规则 5（空格），另含朗读语料的新终版，规范见 {SPEC}。\n"
             "# 生成脚本 scripts/text_final/build_v2.py；只有规则改动了文本的来源才有 v2，其余 v1 终版仍是终版。\n")


if __name__ == "__main__":
    main()
