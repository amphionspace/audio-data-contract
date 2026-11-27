#!/usr/bin/env python3
"""Build the final training-text versions v4 (text-final-v4): rule 9 of docs/reference/training-text.md, Chinese
numerals written as Arabic digits (zh-num-v1, scripts/text_final/zh_numbers.py; user decision 2026-11-27).

Starts from the newest Chinese final of every source (the ends of the superseded_by chains in catalog/text_final_v*.yaml)
and from Chinese sources whose original version is the final (EXTRA). Every train-like split (not dev / test / eval /
validation) is converted. Only finals the rule changes get ``<recipe version>-final-v4-20261127``; the previous final is
marked superseded_by it. The same sentence elsewhere in a row (metadata.scene.targets[].text, hotword lists) changes with
it. Changed text files go to ``<final version>/text/<artifact>.jsonl.gz``; recordings, audio and unchanged files are
referenced in place. Record indexes are built afterwards with ``audio-data-contract build-record-index --register``.

Needs cn2an (``uv pip install cn2an==0.5.24``).

    python -I scripts/text_final/build_v4.py --catalog catalog --out-yaml catalog/text_final_v4.yaml \
        --review-dir <run_dir>/v4/review [--scan | --placeholder]
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


text_final = _load("text_final_build", "text_final/build.py")
zh_numbers = _load("zh_numbers", "text_final/zh_numbers.py")
SUFFIX = "final-v4-20261127"
SPEC = "docs/reference/training-text.md（v4）"
FINAL_SUFFIX = re.compile(r"-final-v\d+-\d{8}$")
# Chinese training sources whose original version is the final (training-text.md "原版本即终版"), plus later sets.
EXTRA = [
    "context_correction_synth_zh@train-v1-20261114", "context_correction_synth_zh@implicit-v1-20261117",
    "context_correction_synth_zh@ts-twins-v1-20261121", "police_text_gaps_train@v2-20261123",
    "police_v6_test_instr_train@v1-20261123",
]
RUN_DIR = text_final.RUN_DIR
EVAL = ("eval", "dev", "validation", "test")
FIELDS = {"audio-records": "target", "lhotse-supervisions": "text"}
HAN = re.compile(r"[㐀-鿿]")
WIDE = r"[⺀-鿿　-〿＀-￯]"
REVIEW = 40


def fix(text: str) -> str:
    return zh_numbers.convert(text)[0] if isinstance(text, str) else text


def letters(text: str) -> str:
    return re.sub(r"[\W_]", "", text.casefold())


def fix_row(row: dict, field: str, punc, n: Counter) -> tuple[str, str] | None:
    old = row.get(field)
    if not isinstance(old, str):
        return None
    new, changes = zh_numbers.convert(old)
    if not changes:
        return None
    for cat, _, _ in changes:
        n[f"rule9_{cat}"] += 1
    row[field] = new
    meta = row.get("metadata") or {}
    for t in (meta.get("scene") or {}).get("targets") or []:
        if isinstance(t.get("text"), str):
            t["text"] = fix(t["text"])
    for holder in (row, meta, row.get("custom") or {}):
        for key in ("hotwords", "interferer_hotwords"):
            if isinstance(holder.get(key), list):
                # two spellings of one word (大明王朝一五六六, 大明王朝1566) become one: keep the first
                words, seen = [], set()
                for w in holder[key]:
                    if isinstance(w, str):
                        w = fix(w)
                        if w in seen:
                            continue
                        seen.add(w)
                    words.append(w)
                holder[key] = words
    key = "metadata" if field == "target" else "custom"
    row[key] = {**(row.get(key) or {}), "text_final": {"original_text": old, "rules": "text-final-v4"}}
    return old, new


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
    # (dataset, recipe version) -> (base entry, None): the newest Chinese final of every chain, plus EXTRA
    sources = {}
    finals = {}
    for path in sorted(args.catalog.glob("text_final_v*.yaml")):
        if path.resolve() == args.out_yaml.resolve():
            continue
        for e in YAML(typ="safe").load(path.read_text()) or []:
            finals[(e["dataset_id"], str(e["version"]))] = e
    for key, e in finals.items():
        prov = e.get("provenance") or {}
        if prov.get("superseded_by") or prov.get("retired") or "zh" not in (e.get("languages") or []):
            continue
        relocate(entries[key], deployed.get(key), roots)
        sources[(key[0], FINAL_SUFFIX.sub("", key[1]))] = (entries[key], None)
    for spec in EXTRA:
        key = tuple(spec.split("@", 1))
        relocate(entries[key], deployed.get(key), roots)
        sources[key] = (entries[key], None)
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
                    "description": f"{ds}@{version} 的训练文本终版 v4，按 audio-data-contract {SPEC} 把数字写成阿拉伯数字。构建中。",
                    "source": f"{ds}@{base['version']}", "method": "text-final-v4", "run_dir": RUN_DIR,
                },
            })
        dump(args.out_yaml, out, f"# 训练文本终版 v4（text-final-v4）：规则 9，数字写成阿拉伯数字，规范见 {SPEC}。占位，构建中。\n")
        print(f"reserved {len(out)} versions", flush=True)
        return

    jobs, plan = {}, {}
    with ProcessPoolExecutor(args.workers) as pool:
        for (ds, version), (base, punc) in sources.items():
            e = copy.deepcopy(base)
            final = f"{version}-{SUFFIX}"
            vdir = Path("datasets") / ds / "versions" / final
            arts = {a["name"]: a for a in e["artifacts"]}
            names = text_artifacts(e)
            plan[(ds, version)] = (e, final, vdir, names, punc)
            for name in names:
                a = arts[name]
                src = Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]
                dst = None if args.scan else args.root / vdir / "text" / f"{name}.jsonl.gz"
                jobs[(ds, version, name)] = pool.submit(
                    process, (src, dst, FIELDS[a["kind"]], None)
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
                s.setdefault("statistics", {})["final_v4_changed_records"] = sum(hit.values())
        cats = {k[len("rule9_"):]: v for k, v in totals.items() if k.startswith("rule9_")}
        parts = [f"数字写成阿拉伯数字（规则 9，zh-num-v1）{totals['changed_records']:,} 条，" +
                 "、".join(f"{c} {v:,} 处" for c, v in sorted(cats.items(), key=lambda x: -x[1]))]
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
        lead = f"{ds}@{version} 的训练文本终版 v4：在 {ds}@{start} 上补做"
        prov.update({
            "snapshot_date": now[:10],
            "description": (
                f"{lead}{what}，按 audio-data-contract {SPEC}。同一行里的场景文本和热词列表一起改；"
                "其余字段、录音清单和音频照旧，引用起点版本的产物。"
            ),
            "source": f"{ds}@{start}",
            "method": "text-final-v4",
            "owner": "mingdong",
            "run_dir": RUN_DIR,
            "build_script": "scripts/text_final/build_v4.py",
        })
        e["provenance"] = prov
        out.append(e)
    (args.review_dir / ("scan.json" if args.scan else "build-summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    if not args.scan:
        dump(args.out_yaml, out, f"# 训练文本终版 v4（text-final-v4）：规则 9，数字写成阿拉伯数字，规范见 {SPEC}。\n"
             "# 生成脚本 scripts/text_final/build_v4.py；只有规则改动了文本的来源才有 v4，其余来源的上一版终版仍是终版。\n")


if __name__ == "__main__":
    main()
