#!/usr/bin/env python3
"""Declare the upstream snapshots ``multilingual_asr_bench`` is copied from.

Reads the pinned download plans and their verification journals under ``--staging`` (see
``download_language_expansion.py``), copies each dataset's download state next to its data as
``versions/<version>/download_state/``, and writes ``catalog/multilingual_asr_sources.yaml``: one
version per snapshot with every downloaded file, split statistics and provenance.

    python scripts/multilingual_asr_bench/register_sources.py \
        --staging /workspace/data/staging/multilingual-asr-eval-20261110
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CASABLANCA_DIALECTS, DATA, LANGUAGES, NAMES

REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPOSITORY / "catalog" / "multilingual_asr_sources.yaml"
PLANS = ("hf-plan.json", "hf-plan-base.json", "http-plan.json")
csv.field_size_limit(1 << 24)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tsv(path, header=True):
    with open(path, newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE))
    return [dict(zip(rows[0], row)) for row in rows[1:]] if header else rows


def file_facts(destination, plan):
    """{relative path: (bytes, sha256)}; LFS files keep the pinned sha256, small files are hashed here."""
    facts = {}
    for row in plan["files"]:
        path = destination / row["path"]
        size = path.stat().st_size
        if size != row["size"]:
            raise ValueError(f"{path}: size differs from the plan")
        digest = row["digest"] if row["algorithm"] == "sha256" and row["digest"] else sha256_file(path)
        facts[row["path"]] = (size, digest)
    on_disk = sorted(p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file())
    if on_disk != sorted(facts):
        raise ValueError(f"{destination}: files differ from the plan: {sorted(set(on_disk) ^ set(facts))[:5]}")
    return facts


def tree_sha256(facts):
    digest = hashlib.sha256()
    for relative in sorted(facts):
        size, sha = facts[relative]
        digest.update(f"{relative}\0{size}\0{sha}\n".encode())
    return digest.hexdigest()


# --- split statistics per family ------------------------------------------------------------------


def fleurs_splits(destination, locale, names):
    splits = {}
    for split in names:
        rows = tsv(destination / "data" / locale / f"{split}.tsv", header=False)
        splits[split] = {
            "files": [f"data/{locale}/audio/{split}.tar.gz", f"data/{locale}/{split}.tsv"],
            "roles": {"audio_archive": f"data/{locale}/audio/{split}.tar.gz", "transcripts": f"data/{locale}/{split}.tsv"},
            "statistics": {
                "count": len(rows),
                "duration_hours": round(sum(int(r[5]) for r in rows) / 16000 / 3600, 4),
                "duration_basis": "sum of TSV num_samples / 16000; pinned upstream file hashes verified",
            },
        }
    return splits


def common_voice_splits(destination, locale, names):
    durations = {r["clip"]: int(r["duration[ms]"]) for r in tsv(destination / "transcript" / locale / "clip_durations.tsv")}
    splits = {}
    for split in names:
        rows = tsv(destination / "transcript" / locale / f"{split}.tsv")
        archives = sorted(p.relative_to(destination).as_posix() for p in (destination / "audio" / locale / split).glob("*.tar"))
        members = set()
        for archive in archives:
            with tarfile.open(destination / archive) as stream:
                members |= {Path(m).name for m in stream.getnames()}
        if any(r["path"] not in members for r in rows):
            raise ValueError(f"{destination} {split}: TSV rows without a clip in the split tar")
        splits[split] = {
            "files": archives + [f"transcript/{locale}/{split}.tsv", f"transcript/{locale}/clip_durations.tsv"],
            "roles": {"audio_archive": archives, "transcripts": f"transcript/{locale}/{split}.tsv",
                      "clip_durations": f"transcript/{locale}/clip_durations.tsv"},
            "statistics": {
                "count": len(rows),
                "speakers": len({r["client_id"] for r in rows}),
                "duration_hours": round(sum(durations[r["path"]] for r in rows) / 1000 / 3600, 4),
                "duration_basis": "sum of clip_durations.tsv for the split TSV rows; every row has its clip in the split tar",
            },
        }
    return splits


def gigaspeech2_splits(destination):
    splits = {}
    for split in ("dev", "test"):
        rows = tsv(destination / "data" / "id" / f"{split}.tsv", header=False)
        splits[split] = {
            "files": [f"data/id/{split}.tar.gz", f"data/id/{split}.tsv"],
            "roles": {"audio_archive": f"data/id/{split}.tar.gz", "transcripts": f"data/id/{split}.tsv"},
            "statistics": {"count": len(rows), "empty_transcripts": sum(1 for r in rows if not r[1].strip())},
        }
    return splits


def casablanca_splits(destination):
    import pyarrow.parquet as pq

    splits = {}
    for dialect in CASABLANCA_DIALECTS:
        files = sorted(p.relative_to(destination).as_posix() for p in (destination / dialect).glob("test-*.parquet"))
        tables = [pq.read_table(destination / f, columns=["duration"]) for f in files]
        splits[f"test_{dialect.lower()}"] = {
            "files": files,
            "roles": {"parquet_dir": dialect},
            "statistics": {
                "count": sum(t.num_rows for t in tables),
                "duration_hours": round(sum(sum(t["duration"].to_pylist()) for t in tables) / 3600, 4),
                "duration_basis": "sum of the parquet duration column",
            },
        }
    return splits


# --- catalog entries ------------------------------------------------------------------------------


def entry(dataset_id, plan, splits, language, provenance, staging):
    version = plan["version"]
    destination = Path(plan["destination"])
    root = DATA / dataset_id
    facts = file_facts(destination, plan)
    relative_source = destination.relative_to(root).as_posix()
    artifacts = [{
        "name": "source",
        "kind": "hf-dataset-snapshot",
        "root_alias": dataset_id,
        "relative_path": relative_source,
        "metadata": {"file_count": len(facts), "expected_bytes": sum(s for s, _ in facts.values()), "tree_sha256": tree_sha256(facts)},
    }]
    names = {}

    def artifact(path, kind):
        if path not in names:
            names[path] = path.replace("/", "_").replace(".", "_").replace("-", "_")
            size, sha = facts[path]
            artifacts.append({
                "name": names[path], "kind": kind, "root_alias": dataset_id,
                "relative_path": f"{relative_source}/{path}", "expected_bytes": size, "sha256": sha,
            })
        return names[path]

    def directory(path):
        # A folder of parquet shards, declared like mtedx's per-language folders.
        inside = {k: v for k, v in facts.items() if k.startswith(path + "/")}
        name = f"{path.lower()}_parquet"
        artifacts.append({
            "name": name, "kind": "parquet-directory", "root_alias": dataset_id,
            "relative_path": f"{relative_source}/{path}",
            "metadata": {"file_count": len(inside), "expected_bytes": sum(s for s, _ in inside.values()),
                         "tree_sha256": tree_sha256({k[len(path) + 1:]: v for k, v in inside.items()})},
        })
        return name

    kinds = {"audio_archive": "source-archive", "transcripts": "transcript-table", "clip_durations": "transcript-table"}
    declared = {}
    for split, info in splits.items():
        roles = {"source": ["source"]}
        for role, paths in info["roles"].items():
            if role == "parquet_dir":
                roles["source"] = [directory(paths)]
                continue
            roles[role] = [artifact(p, kinds[role]) for p in ([paths] if isinstance(paths, str) else paths)]
        declared[split] = {"artifacts": roles, "statistics": info["statistics"]}
        if split.startswith("test_"):
            declared[split]["group"] = "test"

    # Download state lives with the data; the staging journal stays where the downloader wrote it.
    work = Path(staging) / dataset_id
    state_dir = root / "versions" / version / "download_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    for name in ("state.json", "verified.jsonl"):
        shutil.copyfile(work / name, state_dir / name)
    state = json.loads((state_dir / "state.json").read_text())
    if state["state"] != "verified":
        raise ValueError(f"{dataset_id}: download state is {state['state']}")
    artifacts.append({
        "name": "download_state", "kind": "dataset-state", "root_alias": dataset_id,
        "relative_path": f"versions/{version}/download_state/state.json",
        "expected_bytes": (state_dir / "state.json").stat().st_size, "sha256": sha256_file(state_dir / "state.json"),
    })
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": dataset_id,
        "version": version,
        "languages": [language],
        "tasks": ["asr"],
        "aliases": [],
        "artifacts": artifacts,
        "splits": declared,
        "provenance": {
            **provenance,
            **({"source": "Hugging Face", "source_id": plan["repo"], "revision": plan["revision"],
                "url": f"https://huggingface.co/datasets/{plan['repo']}", "download_mirror": "https://hf-mirror.com"} if plan.get("repo") else {}),
            "license": plan["license"],
            "download_scope": plan["scope"],
            "expected_download_files": len(plan["files"]),
            "expected_download_bytes": sum(r["size"] for r in plan["files"]),
            "integrity": "verified",
            "used_by": "multilingual_asr_bench@v1-20261110",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--staging", required=True, type=Path)
    args = parser.parse_args()
    plans = {}
    for name in PLANS:
        plans.update(json.loads((args.staging / name).read_text()))
    entries = []
    for lang, (fleurs_locale, cv_locale) in LANGUAGES.items():
        if lang == "pt":
            continue  # fleurs_pt and common_voice_pt are already registered at these revisions.
        dev = ["dev", "test"] if lang in ("hi", "id") else ["test"]
        plan = plans[f"fleurs_{lang}"]
        entries.append(entry(
            f"fleurs_{lang}", plan, fleurs_splits(Path(plan["destination"]), fleurs_locale, dev), lang,
            {"summary": f"FLEURS {NAMES[lang]}朗读", "locale": fleurs_locale, "dataset_family": f"fleurs_{lang}",
             "description": f"Google FLEURS 的 {fleurs_locale} 子集（音频归档和 TSV 转写），只下载了 {'/'.join(dev)}，与 fleurs_pt 同一修订。"},
            args.staging,
        ))
        plan = plans[f"common_voice_{lang}"]
        entries.append(entry(
            f"common_voice_{lang}", plan, common_voice_splits(Path(plan["destination"]), cv_locale, dev), lang,
            {"summary": f"Common Voice 17 {NAMES[lang]}朗读", "locale": cv_locale, "release": "Common Voice 17.0",
             "dataset_family": f"common_voice_{lang}",
             "description": f"Common Voice 17.0 {cv_locale} 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 {'/'.join(dev)}，与 common_voice_pt@hf-8262c16bf297 同一修订。"},
            args.staging,
        ))
    plan = plans["gigaspeech2_id"]
    entries.append(entry(
        "gigaspeech2_id", plan, gigaspeech2_splits(Path(plan["destination"])), "id",
        {"summary": "GigaSpeech 2 印尼语评测划分", "dataset_family": "gigaspeech2_id",
         "description": "GigaSpeech 2 印尼语 dev/test（YouTube 音频，人工标注，大写无标点）。HF 仓库需同意条款，用团队已获授权的令牌下载；train 见 gigaspeech2_id@local-20260805。"},
        args.staging,
    ))
    plan = plans["casablanca"]
    entries.append(entry(
        "casablanca", plan, casablanca_splits(Path(plan["destination"])), "ar",
        {"summary": "Casablanca 八种阿拉伯语方言", "dataset_family": "casablanca",
         "description": "UBC-NLP Casablanca 的 test 划分（阿尔及利亚、埃及、约旦、毛里塔尼亚、摩洛哥、巴勒斯坦、阿联酋、也门），音频以 wav 字节存在 parquet 内；validation 未下载。仅限非商业用途。"},
        args.staging,
    ))
    # The overview shows one summary per dataset; keep the one already registered for existing datasets.
    summarized = {
        name
        for path in sorted((REPOSITORY / "catalog").glob("*.yaml"))
        if path != CATALOG_FILE
        for spec in yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if isinstance(spec, dict) and (spec.get("provenance") or {}).get("summary")
        for name in (spec["dataset_id"], spec.get("derived_from"), spec["provenance"].get("dataset_family"))
    }
    for spec in entries:
        if spec["dataset_id"] in summarized:
            del spec["provenance"]["summary"]
    CATALOG_FILE.write_text(yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    print(json.dumps({"entries": len(entries), "catalog": str(CATALOG_FILE)}))


if __name__ == "__main__":
    main()
