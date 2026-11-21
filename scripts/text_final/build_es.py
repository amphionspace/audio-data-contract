#!/usr/bin/env python3
"""Build the Spanish final training-text versions (text-final-v1, rules es-v1 of docs/reference/training-text.md) for
the Spanish train sources of the given recipes.

Rules, applied to every text field of a row (target / text, metadata.scene.*.text, custom.hotword_labeling.text and
the hotword lists, so a sentence reads the same everywhere in its row):

- es-1: Common Voice 27.0 sentences (common_voice_es@cv27-train-v1-20261111) get back the original sentence of the
  27.0 release tsv (validated / other, by clip id) when it has the same letters once punctuation, spaces and case
  are ignored, with _ between words read as a space, then the es-v1 written form of common_voice_es@es-train-v1-20261108 (tidy_cv: no space before , ; : . ? ! or after
  ¿ ¡, first letter capitalized, a final . when none of . ? ! ends the sentence).
- es-2: the old spelling of the one-letter words á / é / ó (preposition a, conjunctions e / o; MLS audiobooks) is
  written a / e / o.

Only sources the rules change get a ``<version>-final-v1-20261120`` version; for the rest the recipe version is the
final one. Changed text files go to ``<final version>/text/<artifact>.jsonl.gz``; recordings, audio and unchanged
files are referenced in place. Record indexes are built afterwards with
``audio-data-contract build-record-index --register``.

    python -I scripts/text_final/build_es.py --recipe <train-data.yaml> [--recipe ...] --catalog catalog \
        --out-yaml catalog/text_final_v1_es.yaml --review-dir <run_dir>/es/review [--scan | --placeholder]
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

_spec = importlib.util.spec_from_file_location(
    "text_final_build", Path(__file__).resolve().parent / "build.py"
)
text_final = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(text_final)
SUFFIX, RUN_DIR = text_final.SUFFIX, text_final.RUN_DIR
SPEC = "docs/reference/training-text.md（v1，西语 es-v1）"
RULES = "es-v1"

CV27 = ("common_voice_es", "cv27-train-v1-20261111")
CV27_TSV = "datasets/common_voice_es/versions/mdc-27.0/cv-corpus-27.0-2026-09-11/es"
TEXT_FIELDS = {"audio-records": "target", "lhotse-supervisions": "text"}
EVAL_SPLITS = text_final.EVAL_SPLITS
ARCHAIC = re.compile(r"(?<![^\W\d_])[áéóÁÉÓ](?![^\W\d_])")
MODERN = str.maketrans("áéóÁÉÓ", "aeoAEO")
REVIEW = 40


def tidy_cv(text: str) -> str:
    """es-v1 written form of a Common Voice sentence, as for common_voice_es@es-train-v1-20261108 (es-data-20261108
    scripts/finalize.py tidy_cv): no space before , ; : . ? ! or after ¿ ¡, first letter capitalized, a final .
    when the sentence has no final . ? !"""
    out = re.sub(r"\s+([,;:.?!])", r"\1", " ".join(text.split()))
    out = re.sub(r"([¿¡])\s+", r"\1", out)
    if out[:1].islower() or (out[:1] in "¿¡" and out[1:2].islower()):
        i = 1 if out[:1] in "¿¡" else 0
        out = out[:i] + out[i].upper() + out[i + 1 :]
    if out and not re.search(r"[.?!]$", out):
        out += "."
    return out


def letters(text: str) -> str:
    """The letters of a sentence: the 27.0 text lost marks and some spaces (Reino Unido-Nueva -> Reino UnidoNueva)."""
    return re.sub(r"[\W_]", "", text.casefold())


def modern(text: str) -> str:
    return ARCHAIC.sub(lambda m: m.group(0).translate(MODERN), text)


def cv27_sentences(root: Path) -> dict:
    csv.field_size_limit(sys.maxsize)
    out = {}
    for name in ("validated.tsv", "other.tsv"):
        with (root / CV27_TSV / name).open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                out.setdefault(r["path"].rsplit(".", 1)[0], r["sentence"])
    return out


def recipe_sources(paths: list[Path], entries: dict) -> dict:
    """(dataset_id, version) -> train splits, for the Spanish top-level train entries of the recipes."""
    out: dict = {}
    for path in paths:
        for x in YAML(typ="safe").load(path.read_text())["train"]:
            key = (x["dataset_id"], str(x["version"]))
            split = str(x.get("split") or "")
            if split and not split.startswith(EVAL_SPLITS) and "es" in (entries[key].get("languages") or []):
                out.setdefault(key, set()).add(split)
    return out


def text_artifacts(entry: dict, splits: set) -> list[str]:
    arts = {a["name"]: a for a in entry["artifacts"]}
    names = []
    for split in sorted(splits):
        for group in ((entry.get("splits") or {}).get(split, {}).get("artifacts") or {}).values():
            names += [n for n in group if arts.get(n, {}).get("kind") in TEXT_FIELDS and n not in names]
    return names


def fix_row(row: dict, field: str, restore: dict | None, n: Counter) -> list[tuple[str, str, str]]:
    """Apply es-1 / es-2 in place; returns (rule, from, to) for the main text field."""
    edits = []
    old = row.get(field)
    if not isinstance(old, str):
        return edits
    new = old
    if restore is not None and old:
        orig = restore.get(row["id"])
        if orig is None:
            n["es1_no_source_sentence"] += 1
        elif letters(orig) != letters(old):
            n["es1_words_differ"] += 1
        else:
            new = tidy_cv(orig.replace("_", " "))  # a few sentences join words with _ (a_quemarropa)
    if new != old:
        n["es1_restored"] += 1
        edits.append(("es-1", old, new))
    m = modern(new)
    if m != new:
        n["es2_modern_spelling"] += 1
        edits.append(("es-2", new, m))
        new = m
    if new == old:
        return edits
    row[field] = new
    # the same sentence elsewhere in the row
    meta = row.get("metadata") or {}
    for t in (meta.get("scene") or {}).get("targets") or []:
        if isinstance(t.get("text"), str):
            t["text"] = new if t["text"] == old else modern(t["text"])
    custom = row.get("custom") or {}
    if isinstance((custom.get("hotword_labeling") or {}).get("text"), str):
        custom["hotword_labeling"]["text"] = new if custom["hotword_labeling"]["text"] == old else modern(custom["hotword_labeling"]["text"])
    for holder, key in ((row, "hotwords"), (meta, "interferer_hotwords"), (custom, "hotwords")):
        if isinstance(holder.get(key), list):
            holder[key] = [modern(w) if isinstance(w, str) else w for w in holder[key]]
    key = "metadata" if field == "target" else "custom"
    row[key] = {**(row.get(key) or {}), "text_final": {"original_text": old, "rules": RULES}}
    return edits


def process(src: Path, dst: Path | None, field: str, restore: dict | None) -> dict:
    """Scan (dst None) or rewrite one text file; dst is kept only when a row changed."""
    n, review = Counter(), []
    tmp = None
    if dst is not None:
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
    raw = tmp.open("wb") if tmp else None
    gz = gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) if raw else None
    with gzip.open(src, "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            n["records"] += 1
            edits = fix_row(row, field, restore, n)
            if edits:
                n["changed_records"] += 1
                line = json.dumps(row, ensure_ascii=False) + "\n"
                if len(review) < REVIEW:
                    review.append({"id": row["id"], "edits": edits})
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


def describe(totals: Counter) -> str:
    parts = []
    if totals["es1_restored"]:
        parts.append(f"恢复 Common Voice 27.0 原句的标点并按 es-v1 书面写法规整（es-1）{totals['es1_restored']:,} 条")
    if totals["es2_modern_spelling"]:
        parts.append(f"单字母词旧写法 á/é/ó 改为 a/e/o（es-2）{totals['es2_modern_spelling']:,} 条")
    return "；".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", type=Path, action="append", required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument("--roots", type=Path, default=Path("/workspace/data/registry/roots.json"))
    ap.add_argument("--out-yaml", type=Path, required=True)
    ap.add_argument("--review-dir", type=Path, required=True)
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
    sources = recipe_sources(args.recipe, entries)
    args.review_dir.mkdir(parents=True, exist_ok=True)
    scan_path = args.review_dir / "scan.json"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.placeholder:
        changed = [tuple(k.split("@", 1)) for k, v in json.loads(scan_path.read_text()).items() if v["changed_records"]]
        out = []
        for ds, version in changed:
            final = f"{version}-{SUFFIX}"
            rel = Path("datasets") / ds / "versions" / final / "state.json"
            (args.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (args.root / rel).write_text(json.dumps({
                "schema_version": "dataset-state/1.0", "dataset_id": ds, "version": final, "state": "planned",
                "updated_at": now, "error": None,
                "metadata": {"stage": "building", "owner": "mingdong", "source": f"{ds}@{version}", "spec": SPEC,
                             "run_dir": RUN_DIR},
            }, ensure_ascii=False, indent=2) + "\n")
            base = entries[(ds, version)]
            out.append({
                "schema_version": "dataset-catalog/2.0", "dataset_id": ds, "version": final,
                "languages": base.get("languages"), "tasks": base.get("tasks"), "aliases": [],
                "derived_from": f"{ds}@{version}",
                "artifacts": [{"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                               "relative_path": str(rel)}],
                "splits": {"train": {"artifacts": {"preparation_state": ["preparation_state"]},
                                     "provenance": {"preparation_status": "building"}}},
                "provenance": {
                    "preparation_status": "building", "owner": "mingdong",
                    "description": f"{ds}@{version} 的西语训练文本终版，按 audio-data-contract {SPEC} 规整。构建中。",
                    "source": f"{ds}@{version}", "method": "text-final-v1-es", "run_dir": RUN_DIR,
                },
            })
        dump(args.out_yaml, out, f"# 训练文本终版（text-final-v1）的西语来源，规则 es-v1，规范见 {SPEC}。占位，构建中。\n")
        print(f"reserved {len(out)} versions", flush=True)
        return

    restore = cv27_sentences(args.root) if CV27 in sources else None
    out, summary = [], {}
    for (ds, version), splits in sorted(sources.items()):
        e = copy.deepcopy(entries[(ds, version)])
        final = f"{version}-{SUFFIX}"
        vdir = Path("datasets") / ds / "versions" / final
        arts = {a["name"]: a for a in e["artifacts"]}
        totals, files, review = Counter(), {}, []
        for name in text_artifacts(e, splits):
            a = arts[name]
            src = Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]
            dst = None if args.scan else args.root / vdir / "text" / f"{name}.jsonl.gz"
            res = process(src, dst, TEXT_FIELDS[a["kind"]], restore if (ds, version) == CV27 else None)
            files[name] = res["counts"]
            totals.update({k: v for k, v in res["counts"].items() if k != "records"})
            review += res["review"]
            print(ds, version, name, res["counts"], flush=True)
            if "sha256" in res:
                a["root_alias"], a["relative_path"] = "aidc_data", str(vdir / "text" / f"{name}.jsonl.gz")
                a["expected_bytes"], a["sha256"] = res["expected_bytes"], res["sha256"]
        summary[f"{ds}@{version}"] = {"changed_records": totals["changed_records"], "totals": dict(totals), "files": files}
        (args.review_dir / f"{ds}@{version}.json").write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n")
        if args.scan or not totals["changed_records"]:
            continue
        e["artifacts"] = [a for a in e["artifacts"] if a.get("kind") not in ("lance-record-index", "dataset-state")]
        for split, s in (e.get("splits") or {}).items():
            for role in ("records_lance", "preparation_state"):
                (s.get("artifacts") or {}).pop(role, None)
            (s.get("provenance") or {}).pop("preparation_status", None)
            names = {n for g in (s.get("artifacts") or {}).values() for n in g}
            hit = sum(files[n]["changed_records"] for n in names if n in files and files[n].get("changed_records"))
            if split in splits and hit:
                s.setdefault("statistics", {})["final_es_changed_records"] = hit
        what = describe(totals)
        rel = vdir / "state.json"
        (args.root / vdir).mkdir(parents=True, exist_ok=True)
        (args.root / rel).write_text(json.dumps({
            "schema_version": "dataset-state/1.0", "dataset_id": ds, "version": final, "state": "prepared",
            "updated_at": now, "error": None,
            "metadata": {"stage": "built", "owner": "mingdong", "source": f"{ds}@{version}", "rules": what,
                         "files": files, "spec": SPEC, "run_dir": RUN_DIR},
        }, ensure_ascii=False, indent=2) + "\n")
        e["artifacts"].insert(0, {"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                                  "relative_path": str(rel)})
        e["version"] = final
        e["derived_from"] = f"{ds}@{version}"
        e["recipe_parameters"] = {
            "spec": SPEC,
            "start": f"{ds}@{version}",
            "rounds": what,
            "unchanged": "规则没有改动的文本文件、录音清单、音频和非 train 划分，引用原版本的产物",
        }
        prov = {k: v for k, v in (e.get("provenance") or {}).items() if k not in text_final.DROP_PROVENANCE}
        prov.update({
            "snapshot_date": now[:10],
            "description": (
                f"{ds}@{version} 的西语训练文本终版，按 audio-data-contract {SPEC} 规整，替代原版本：{what}。"
                "同一行里的场景文本、热词标注文本和热词列表一起改；其余字段、录音清单和音频照旧，引用原版本的产物。"
            ),
            "source": f"{ds}@{version}",
            "method": "text-final-v1-es",
            "owner": "mingdong",
            "run_dir": RUN_DIR,
            "build_script": "scripts/text_final/build_es.py",
        })
        e["provenance"] = prov
        out.append(e)
    (args.review_dir / ("scan.json" if args.scan else "build-summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    if not args.scan:
        dump(args.out_yaml, out, f"# 训练文本终版（text-final-v1）的西语来源，规则 es-v1，规范见 {SPEC}。\n"
             "# 生成脚本 scripts/text_final/build_es.py；只有规则改动了文本的来源才有终版，其余来源的原版本即终版。\n")


def dump(path: Path, entries: list, head: str) -> None:
    yaml = YAML()
    yaml.width = 4096
    with path.open("w") as w:
        w.write(head)
        yaml.dump(entries, w)


if __name__ == "__main__":
    main()
