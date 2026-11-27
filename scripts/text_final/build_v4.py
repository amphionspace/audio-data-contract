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
    "context_correction_synth_zh@asr-dialog-v1-20261122",
]
# Records moved to a quarantine split instead of training (context-correction line, 2026-11-27): a protected word
# expanded with its alternative ("必须|必需") was read twice by the TTS, so audio and target disagree.
PIPE_QUARANTINE = {"context_correction_synth_zh"}
QUARANTINE_WHY = "受保护词展开时没去掉备选，TTS 两种写法都念了；纠偏线 2026-11-27 确认"
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
    cc = (row.get("labels") or {}).get("context_correction")
    if isinstance(cc, dict):
        fix_context_labels(cc, old, new, n)
    turns = meta.get("turns")
    if isinstance(turns, list) and all(isinstance(t, dict) and isinstance(t.get("text"), str) for t in turns):
        cut = cut_like([t["text"] for t in turns], old, new)
        if cut is None:
            n["turns_not_target"] += 1
        else:
            for t, text in zip(turns, cut, strict=True):
                t["text"] = text
            n["turns_records"] += 1
    key = "metadata" if field == "target" else "custom"
    row[key] = {**(row.get(key) or {}), "text_final": {"original_text": old, "rules": "text-final-v4"}}
    return old, new


def cut_like(pieces: list, old: str, new: str) -> list | None:
    """Cut new (old converted) into pieces at the old pieces' boundaries moved through the replacements, so they
    still join to it; None when the pieces do not join to old or a boundary falls inside a converted number."""
    if "".join(pieces) != old:
        return None
    spans = zh_numbers.edits(old)

    def moved(b):
        shift = 0
        for s, e, _, rep in spans:
            if e <= b:
                shift += len(rep) - (e - s)
            elif s < b:
                return None
        return b + shift

    ends, pos = [], 0
    for piece in pieces:
        pos += len(piece)
        ends.append(moved(pos))
    if None in ends:
        return None
    return [new[a:b] for a, b in zip([0, *ends[:-1]], ends, strict=True)]


MARK = {"target": "[[T:{text}|{alt}]]", "evidence": "[[D:{text}]]", "protected": "[[P:{text}]]"}


def fix_context_labels(cc: dict, old: str, new: str, n: Counter) -> None:
    """labels.context_correction follows the converted target: segments are cut from the new target at the old
    boundaries moved through the replacements (so they still join to the target), marked_text and the draft are
    rebuilt from them, and the free-text fields (alt, edits, reasons) get the rule on their own."""
    segs = cc.get("segments") or []
    before = [dict(s) for s in segs]
    if segs:
        cut = cut_like([s["text"] for s in segs], old, new)
        if cut is None:
            n["cc_segments_not_cut"] += 1
            cut = [fix(s["text"]) for s in segs]
        for s, text in zip(segs, cut, strict=True):
            s["text"] = text
    for s in segs:
        if isinstance(s.get("alt"), str):
            s["alt"] = fix(s["alt"])

    def marked(ss):
        return "".join(MARK[s["role"]].format(**s) if s.get("role") in MARK else s["text"] for s in ss)

    def misheard(ss):
        return "".join(s.get("alt", s["text"]) if s.get("role") == "target" else s["text"] for s in ss)

    if isinstance(cc.get("marked_text"), str):
        if cc["marked_text"] == marked(before):
            cc["marked_text"] = marked(segs)
        else:
            n["cc_marked_text_fixed_alone"] += 1
            cc["marked_text"] = fix(cc["marked_text"])
    cot = cc.get("cot") if isinstance(cc.get("cot"), dict) else {}
    if isinstance(cot.get("final"), str):
        cot["final"] = new if cot["final"] == old else fix(cot["final"])
    if isinstance(cot.get("draft"), str):
        if cot["draft"] == old:
            cot["draft"] = new
        elif cot["draft"] == misheard(before):
            cot["draft"] = misheard(segs)
        else:
            n["cc_draft_fixed_alone"] += 1
            cot["draft"] = fix(cot["draft"])
    same = {}
    for b, s in zip(before, segs, strict=True):
        same[b["text"]] = s["text"]
        if "alt" in b:
            same[b["alt"]] = s["alt"]
    for e in cot.get("edits") or []:
        for k in ("evidence", "from", "to"):
            if isinstance(e.get(k), str):
                e[k] = same.get(e[k], fix(e[k]))
        if isinstance(e.get("reason"), str):
            e["reason"] = fix(e["reason"])
    if isinstance(cc.get("reason"), str):
        cc["reason"] = fix(cc["reason"])
    n["cc_records"] += 1


def process(job: tuple) -> dict:
    """Scan (dst None) or rewrite one text file; dst is kept only when a row changed. With ``quarantine``, rows whose
    text holds a "|" go to <dst>-quarantine instead (PIPE_QUARANTINE)."""
    src, dst, field, punc_path, quarantine = job
    held = []
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
            if quarantine and "|" in (row.get(field) or ""):
                n["quarantined"] += 1
                n["quarantined_ms"] += round(1000 * sum(s["ref"]["duration"] for s in row["audio_slots"][:1]))
                held.append(line)
                continue
            if gz:
                gz.write(line.encode("utf-8"))
    out = {"counts": dict(n), "review": review}
    if not gz:
        return out
    gz.close()
    raw.close()
    if not n["changed_records"] and not held:
        tmp.unlink()
        return out
    os.replace(tmp, dst)
    out.update(expected_bytes=dst.stat().st_size, sha256=_sha256(dst))
    if held:
        q = quarantine_path(dst)
        with q.open("wb") as raw_q, gzip.GzipFile(fileobj=raw_q, mode="wb", mtime=0) as gz_q:
            for line in held:
                gz_q.write(line.encode("utf-8"))
        out["quarantine"] = {"expected_bytes": q.stat().st_size, "sha256": _sha256(q)}
    return out


def held_already(entry: dict) -> set:
    """Record artifacts of an existing quarantine split (nothing to move there)."""
    return set(((entry.get("splits") or {}).get("quarantine") or {}).get("artifacts", {}).get("records") or [])


def quarantine_path(path: Path) -> Path:
    return path.with_name(path.name.removesuffix(".jsonl.gz") + "-quarantine.jsonl.gz")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


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
                    process, (src, dst, FIELDS[a["kind"]], None, ds in PIPE_QUARANTINE and name not in held_already(e))
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
        for name in names:
            res = results[(ds, version, name)]
            if "quarantine" not in res:
                continue
            a, k, ms = arts[name], res["counts"]["quarantined"], res["counts"]["quarantined_ms"]
            q = {**a, "name": f"{name}-quarantine", **res["quarantine"],
                 "relative_path": str(quarantine_path(vdir / "text" / f"{name}.jsonl.gz")),
                 "metadata": {**(a.get("metadata") or {}), "record_count": k}}
            if isinstance((a.get("metadata") or {}).get("record_count"), int):
                a["metadata"] = {**a["metadata"], "record_count": a["metadata"]["record_count"] - k}
            e["artifacts"].append(q)
            if "quarantine" not in e["splits"]:
                first = next(sp for sp in e["splits"].values() if name in (sp.get("artifacts") or {}).get("records", []))
                e["splits"]["quarantine"] = {"artifacts": {"records": []}, "statistics": {
                    "records": 0, "duration_hours": 0.0,
                    **{x: v for x, v in (first.get("statistics") or {}).items() if x == "duration_basis"}}}
            qs = e["splits"]["quarantine"]
            qs["artifacts"].setdefault("records", []).append(q["name"])
            qst = qs.setdefault("statistics", {})
            if isinstance(qst.get("records"), int):
                qst["records"] += k
            if isinstance(qst.get("duration_hours"), (int, float)):
                qst["duration_hours"] = round(qst["duration_hours"] + ms / 3.6e6, 4)
            qst["pipe_records"] = qst.get("pipe_records", 0) + k
            for split, sp in e["splits"].items():
                if split == "quarantine" or name not in ((sp.get("artifacts") or {}).get("records") or []):
                    continue
                for x in sp["artifacts"].get("audio_index") or []:
                    if x not in qs["artifacts"].setdefault("audio_index", []):
                        qs["artifacts"]["audio_index"].append(x)
                st = sp.setdefault("statistics", {})
                if isinstance(st.get("records"), int):
                    st["records"] -= k
                if isinstance(st.get("duration_hours"), (int, float)):
                    st["duration_hours"] = round(st["duration_hours"] - ms / 3.6e6, 4)
                st["quarantined_pipe_records"] = st.get("quarantined_pipe_records", 0) + k
        cats = {k[len("rule9_"):]: v for k, v in totals.items() if k.startswith("rule9_")}
        parts = [f"数字写成阿拉伯数字（规则 9，zh-num-v1）{totals['changed_records']:,} 条，" +
                 "、".join(f"{c} {v:,} 处" for c, v in sorted(cats.items(), key=lambda x: -x[1]))]
        if totals["quarantined"]:
            parts.append(f"target 含竖线的 {totals['quarantined']:,} 条移到 quarantine 划分（{QUARANTINE_WHY}；记录内容不变）")
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
                f"{lead}{what}，按 audio-data-contract {SPEC}。同一行里的场景文本"
                f"{'、热词列表和上下文纠偏标签' if totals['cc_records'] else '和热词列表'}一起改；"
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
