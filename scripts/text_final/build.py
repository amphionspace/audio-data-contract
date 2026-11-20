#!/usr/bin/env python3
"""Build the final training-text versions (text-final-v1): one version per text source of a training recipe, with every
text fix of docs/reference/training-text.md applied.

For each (dataset, version) the recipe trains on, the fix rounds already registered as derived versions are followed
down the chain (``<version>-ctxclean-20261110`` 说字写法, ``-zhenfix-20261117`` 字母连写, ``-zhenfix-20261119`` WenetSpeech
英文写回); the deepest one is the starting point. Rule zhen-fix-v1 (space-separated capitals joined, K T V -> KTV) is then
applied to every train text file, since its derived versions were only built for the ten sources with the most hits.
A text file the rule leaves unchanged is referenced at its current path (no copy); a changed one is written to
``<version>-final-v1-20261120/text/<artifact>.jsonl.gz``. Recordings, audio and non-train splits are referenced as
they are. Record indexes are built afterwards with ``audio-data-contract build-record-index --register``.

    python -I scripts/text_final/build.py --recipe <train-data.yaml> --catalog catalog \
        --out-yaml catalog/text_final_v1.yaml --review-dir <run_dir>/review
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import random
import re
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

_spec = importlib.util.spec_from_file_location(
    "zhen_fix_build", Path(__file__).resolve().parents[1] / "zhen_fix" / "build.py"
)
zhen_fix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zhen_fix)
DROP_PROVENANCE, KEEP_STATS, TEXT_KINDS, rewrite = (
    zhen_fix.DROP_PROVENANCE,
    zhen_fix.KEEP_STATS,
    zhen_fix.TEXT_KINDS,
    zhen_fix.rewrite,
)

SUFFIX = "final-v1-20261120"
SPEC = "docs/reference/training-text.md（v1）"
RUN_DIR = "/workspace/workspace/mingdong/data/amphiondata/text-final-20261120"
# fix rounds registered as derived versions, in the order they are chained
ROUNDS = [
    (
        "-ctxclean-20261110",
        "说字写法（ctxclean，context_correction_clean_zh@v1-20261110）",
    ),
    ("-zhenfix-20261117", "拆开的大写字母连写（zhen-fix-v1）"),
    ("-zhenfix-20261119", "写成汉字的英文换回英文（zhen-fix-en-v1）"),
]
EVAL_SPLITS = ("eval", "dev", "validation", "test")


def recipe_sources(path: Path) -> dict[tuple[str, str], set[str]]:
    """(dataset_id, version) -> splits the recipe trains on (top-level ``train`` entries only; noise and interferer
    sources nested in online_mix are not training text)."""
    out: dict[tuple[str, str], set[str]] = {}
    for x in YAML(typ="safe").load(path.read_text())["train"]:
        split = str(x.get("split") or "")
        if split and not split.startswith(EVAL_SPLITS):
            out.setdefault((x["dataset_id"], str(x["version"])), set()).add(split)
    return out


def head_of(entries: dict, ds: str, version: str) -> str:
    """The deepest registered fix round below version."""
    head = version
    for suffix, _ in ROUNDS:
        nxt = [
            v
            for (d, v) in entries
            if d == ds and v.startswith(head) and v[len(head) :] == suffix
        ]
        if nxt:
            head = nxt[0]
    return head


def rounds_in(version: str, head: str) -> list[str]:
    tail = head[len(version) :]
    return [label for suffix, label in ROUNDS if suffix in tail]


def train_text_artifacts(entry: dict, splits: set[str]) -> list[str]:
    """Text artifacts (AudioRecord target, Lhotse supervision text) of the splits the recipe trains on."""
    arts = {a["name"]: a for a in entry["artifacts"]}
    names = []
    for split, s in (entry.get("splits") or {}).items():
        if split not in splits:
            continue
        for group in (s.get("artifacts") or {}).values():
            for n in group:
                if n in arts and arts[n].get("kind") in TEXT_KINDS and n not in names:
                    names.append(n)
    return names


CJK_LATIN_SPACE = re.compile(r"[一-鿿] +[A-Za-z]|[A-Za-z] +[一-鿿]")
NONSPEECH = re.compile(r"<[^<>]*>|\[UNK\]|\*\*")


def scan(path: Path, field: str) -> dict:
    """Read-only counts: rows rule zhen-fix-v1 would change, and rows breaking rules 5 and 7 of zh-en-transcription.md
    (a space between Chinese and English; non-speech tags), which the final version reports but does not fix."""
    n = {"r1": 0, "cjk_latin_space": 0, "nonspeech_tags": 0}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            text = json.loads(line).get(field)
            if not isinstance(text, str):
                continue
            n["r1"] += zhen_fix.fix(text) != text
            n["cjk_latin_space"] += bool(CJK_LATIN_SPACE.search(text))
            n["nonspeech_tags"] += bool(NONSPEECH.search(text))
    return n


def facts(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return path.stat().st_size, h.hexdigest()


def reserve(args, entries: dict, sources: dict, now: str) -> None:
    """Placeholder entries: one dataset-state artifact per final version, preparation_status building."""
    out = []
    for ds, version in sources:
        final = f"{version}-{SUFFIX}"
        head = head_of(entries, ds, version)
        state_rel = Path("datasets") / ds / "versions" / final / "state.json"
        (args.root / state_rel).parent.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": "dataset-state/1.0",
            "dataset_id": ds,
            "version": final,
            "state": "planned",
            "updated_at": now,
            "error": None,
            "metadata": {
                "stage": "building",
                "owner": "mingdong",
                "source": f"{ds}@{version}",
                "start": f"{ds}@{head}",
                "spec": SPEC,
                "run_dir": RUN_DIR,
            },
        }
        (args.root / state_rel).write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        )
        base = entries[(ds, version)]
        prov = base.get("provenance") or {}
        out.append(
            {
                "schema_version": "dataset-catalog/2.0",
                "dataset_id": ds,
                "version": final,
                "languages": base.get("languages"),
                "tasks": base.get("tasks"),
                "aliases": [],
                "derived_from": f"{ds}@{head}",
                "artifacts": [
                    {
                        "name": "preparation_state",
                        "kind": "dataset-state",
                        "root_alias": "aidc_data",
                        "relative_path": str(state_rel),
                    }
                ],
                "splits": {
                    "train": {
                        "artifacts": {"preparation_state": ["preparation_state"]},
                        "provenance": {"preparation_status": "building"},
                    }
                },
                "provenance": {
                    "preparation_status": "building",
                    "owner": "mingdong",
                    **({"summary": prov["summary"]} if prov.get("summary") else {}),
                    "description": (
                        f"{ds}@{version}（交付配方 v7set34 训练用的版本）的训练文本终版，按 {SPEC} "
                        f"应用全部已执行的文本修正，起点 {ds}@{head}。构建中。"
                    ),
                    "source": f"{ds}@{version}",
                    "method": "text-final-v1",
                    "run_dir": RUN_DIR,
                },
            }
        )
    yaml = YAML()
    yaml.width = 4096
    with args.out_yaml.open("w") as w:
        w.write(
            f"# 训练文本终版（text-final-v1，2026-11-20）：交付配方 v7set34 的每个文本来源一个终版，规范见 {SPEC}。占位，构建中。\n"
        )
        yaml.dump(out, w)
    print(f"reserved {len(out)} versions", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument(
        "--roots", type=Path, default=Path("/workspace/data/registry/roots.json")
    )
    ap.add_argument(
        "--registry-catalog",
        type=Path,
        default=Path("/workspace/data/registry/catalog"),
        help="deployed catalog; its relocated paths are used where a repo path does not resolve here",
    )
    ap.add_argument("--out-yaml", type=Path, required=True)
    ap.add_argument("--review-dir", type=Path, required=True)
    ap.add_argument(
        "--placeholder",
        action="store_true",
        help="only reserve the versions (state.json, building)",
    )
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
    sources = recipe_sources(args.recipe)
    missing = [s for s in sources if s not in entries]
    if missing:
        raise SystemExit(f"recipe versions not in the catalog: {missing}")

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.placeholder:
        reserve(args, entries, sources, now)
        return
    args.review_dir.mkdir(parents=True, exist_ok=True)
    out, summary = [], {}
    for (ds, version), splits in sources.items():
        head = head_of(entries, ds, version)
        base = entries[(ds, head)]
        texts = train_text_artifacts(base, splits)
        if not texts:
            summary[f"{ds}@{version}"] = {"skipped": "no train text"}
            continue
        e = copy.deepcopy(base)
        final = f"{version}-{SUFFIX}"
        vdir = Path("datasets") / ds / "versions" / final
        arts = {a["name"]: a for a in e["artifacts"]}
        # legacy sets (FLEURS under root multilingual) were relocated: the deployed catalog has paths that resolve here
        moved = {
            a["name"]: a for a in (deployed.get((ds, head)) or {}).get("artifacts", [])
        }
        for name, a in arts.items():
            here = Path(roots[a.get("root_alias", "aidc_data")]) / a.get(
                "relative_path", ""
            )
            m = moved.get(name)
            there = (
                Path(roots[m.get("root_alias", "aidc_data")]) / m["relative_path"]
                if m and "relative_path" in m
                else None
            )
            if "relative_path" in a and not here.exists() and there and there.exists():
                a["root_alias"], a["relative_path"] = (
                    m.get("root_alias", "aidc_data"),
                    m["relative_path"],
                )
                for k in ("expected_bytes", "sha256"):
                    a.pop(k, None)
                    if k in m:
                        a[k] = m[k]
                if (
                    not (a.get("expected_bytes") and a.get("sha256"))
                    and there.is_file()
                ):
                    a["expected_bytes"], a["sha256"] = facts(there)
        rnd, review, stats = random.Random(20261120), [], {}
        for name in texts:
            a = arts[name]
            src = Path(roots[a.get("root_alias", "aidc_data")]) / a["relative_path"]
            counts = scan(src, TEXT_KINDS[a["kind"]])
            if counts["r1"]:
                dst = args.root / vdir / "text" / f"{name}.jsonl.gz"
                res = rewrite(src, dst, TEXT_KINDS[a["kind"]], review, rnd)
                a["root_alias"], a["relative_path"] = (
                    "aidc_data",
                    str(vdir / "text" / f"{name}.jsonl.gz"),
                )
                a["expected_bytes"], a["sha256"] = res["expected_bytes"], res["sha256"]
                stats[name] = {"records": res["records"], "r1_changed": res["changed"]}
            else:
                if not (a.get("expected_bytes") and a.get("sha256")):
                    a["expected_bytes"], a["sha256"] = facts(src)
                stats[name] = {"r1_changed": 0}
            stats[name].update(
                cjk_latin_space=counts["cjk_latin_space"],
                nonspeech_tags=counts["nonspeech_tags"],
            )
            print(ds, final, name, stats[name], flush=True)
        e["artifacts"] = [
            a
            for a in e["artifacts"]
            if a.get("kind") not in ("lance-record-index", "dataset-state")
        ]
        r1 = sum(v["r1_changed"] for v in stats.values())
        for split, s in (e.get("splits") or {}).items():
            for role in ("records_lance", "preparation_state"):
                (s.get("artifacts") or {}).pop(role, None)
            (s.get("provenance") or {}).pop("preparation_status", None)
            if "statistics" in s:
                keep = KEEP_STATS | {
                    "zhen_fix_changed_records",
                    "corrected_records",
                    "removed_eval_recording_records",
                    "removed_quarantine_records",
                }
                s["statistics"] = {
                    k: v for k, v in s["statistics"].items() if k in keep
                }
                if split in splits and r1:
                    names = {n for g in (s.get("artifacts") or {}).values() for n in g}
                    changed = sum(
                        v["r1_changed"] for n, v in stats.items() if n in names
                    )
                    if changed:
                        s["statistics"]["final_r1_changed_records"] = changed
        done = rounds_in(version, head) + (
            [f"拆开的大写字母连写补齐（zhen-fix-v1，{r1:,} 条）"] if r1 else []
        )
        state_rel = vdir / "state.json"
        (args.root / vdir).mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": "dataset-state/1.0",
            "dataset_id": ds,
            "version": final,
            "state": "prepared",
            "updated_at": now,
            "error": None,
            "metadata": {
                "stage": "built",
                "owner": "mingdong",
                "source": f"{ds}@{version}",
                "start": f"{ds}@{head}",
                "rounds": done,
                "files": stats,
                "spec": SPEC,
                "run_dir": RUN_DIR,
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
        e["version"] = final
        e["derived_from"] = f"{ds}@{head}"
        e["recipe_parameters"] = {
            "spec": SPEC,
            "start": f"{ds}@{head}（{version} 之后已登记的修正版本里最深的一个）",
            "rounds": "；".join(["书面化标点（底版本自带）", *done])
            if done
            else "书面化标点（底版本自带）；其余修正对本数据没有改动",
            "unchanged": "规则没有改动的文本文件、录音清单、音频和非 train 划分，引用起点版本的产物",
        }
        prov = {
            k: v
            for k, v in (e.get("provenance") or {}).items()
            if k not in DROP_PROVENANCE
        }
        e["provenance"] = prov
        prov.update(
            {
                "snapshot_date": now[:10],
                "description": (
                    f"{ds}@{version}（交付配方 v7set34 训练用的版本）的训练文本终版，按 audio-data-contract {SPEC} "
                    "应用全部已执行的文本修正，替代配方原来的版本和中间修正版本。起点 "
                    f"{ds}@{head}；已含修正：{'、'.join(done) if done else '无（各轮修正对本数据都没有改动）'}。"
                    "其余字段、录音清单和音频照旧，引用起点版本的产物。"
                ),
                "source": f"{ds}@{version}",
                "method": "text-final-v1",
                "owner": "mingdong",
                "run_dir": RUN_DIR,
                "build_script": "scripts/text_final/build.py",
            }
        )
        out.append(e)
        summary[f"{ds}@{final}"] = {"start": head, "rounds": done, "files": stats}
        (args.review_dir / f"{ds}@{final}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in review)
        )
    yaml = YAML()
    yaml.width = 4096
    with args.out_yaml.open("w") as w:
        w.write(
            f"# 训练文本终版（text-final-v1，2026-11-20）：交付配方 v7set34 的每个文本来源一个终版，规范见 {SPEC}。\n"
            "# 生成脚本 scripts/text_final/build.py；起点是各来源已登记修正版本里最深的一个，再补齐 zhen-fix-v1。\n"
        )
        yaml.dump(out, w)
    (args.review_dir / "build-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
