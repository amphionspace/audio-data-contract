#!/usr/bin/env python3
"""Build ``mtedx@test-v1-20261114``: the mTEDx Spanish and Portuguese test splits as evaluation records.

The audio (FLAC as shipped in the HF Parquet of ``mtedx@hf-0b97ef40298d``) is written under this
version's ``audio/<lang>/``; every split is AudioRecord JSONL plus one shared audio index, the same layout as
``multilingual_asr_bench``. Transcripts are the upstream ``transcript`` (case and punctuation kept).

    python scripts/mtedx_test/build.py --workers 16 --eval-set /workspace/data/datasets/mtedx/eval-sets/mtedx-test-v1-20261114.yaml

Run with an environment that has Lhotse 1.33, pyarrow and PyYAML. Writes ``catalog/mtedx_test.yaml`` and,
with ``--eval-set``, the amphion-eval data config; a rerun with unchanged inputs writes identical files.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import io
import json
from pathlib import Path

import yaml

DATASET_ID = "mtedx"
SOURCE_VERSION = "hf-0b97ef40298d"
VERSION = "test-v1-20261114"
ROOT = Path("/workspace/data/datasets") / DATASET_ID
REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPOSITORY / "catalog" / "mtedx_test.yaml"
NAMES = {"es": "西班牙语", "pt": "葡萄牙语"}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl_gz(path, rows):
    """Deterministic gzip JSONL (no file name or time stamp in the gzip header)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
        for row in rows:
            stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    path.write_bytes(buffer.getvalue())


def extract(lang):
    """Write the split's audio; return (rows kept, rows without transcript)."""
    import pyarrow.parquet as pq

    table = pq.read_table(ROOT / "source" / SOURCE_VERSION / lang / "test-00000-of-00001.parquet")
    rows, dropped = [], 0
    for row in table.to_pylist():
        text = (row["transcript"] or "").strip()
        if not text:
            dropped += 1
            continue
        relative = f"versions/{VERSION}/audio/{lang}/{row['id']}.flac"
        dest = ROOT / relative
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            partial = dest.with_name(dest.name + ".partial")
            partial.write_bytes(row["audio"]["bytes"])
            partial.rename(dest)
        metadata = {"talk_id": row["talk_id"], "segment_id": row["segment_id"],
                    "talk_start": float(row["start"]), "talk_end": float(row["end"])}
        rows.append((row["id"], relative, text, metadata))
    return rows, dropped


def audio_facts(relative):
    from lhotse import Recording

    path = ROOT / relative
    recording = Recording.from_file(str(path))
    return {
        "relative_path": relative,
        "channels": len(recording.channel_ids),
        "sample_rate": recording.sampling_rate,
        "num_frames": recording.num_samples,
        "duration": round(recording.duration, 6),
        "sha256": sha256_file(path),
    }


def build(args):
    version_dir = ROOT / "versions" / VERSION
    plan = {lang: extract(lang) for lang in NAMES}
    relatives = sorted(r[1] for rows, _ in plan.values() for r in rows)
    with cf.ProcessPoolExecutor(args.workers) as pool:
        facts = dict(zip(relatives, pool.map(audio_facts, relatives, chunksize=32)))

    index, artifacts, splits = [], [], {}
    for lang, (rows, dropped) in plan.items():
        name = f"mtedx-{lang}"
        records = []
        for upstream_id, relative, text, metadata in rows:
            fact = facts[relative]
            cut_id = f"{name}/{upstream_id}"
            index.append({"cut_id": cut_id, "root_alias": DATASET_ID, **fact})
            records.append({
                "schema_version": "audio-record/1.0",
                "id": f"{name}:{upstream_id}",
                "task": "asr",
                "language": lang,
                "target": text,
                "audio_slots": [{
                    "name": "primary",
                    "purpose": "primary",
                    "ref": {"dataset_id": DATASET_ID, "version": VERSION, "split": name,
                            "cut_id": cut_id, "duration": fact["duration"]},
                }],
                "hotwords": [],
                "labels": {"source": "mTEDx", "locale": lang},
                "metadata": {"upstream_id": upstream_id, **metadata},
            })
        path = version_dir / "records" / f"{name}.jsonl.gz"
        write_jsonl_gz(path, records)
        artifacts.append({
            "name": f"{name}-records", "kind": "audio-records", "root_alias": DATASET_ID,
            "relative_path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path),
            "metadata": {"record_count": len(records)},
        })
        hours = sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600
        statistics = {"records": len(records), "duration_hours": round(hours, 4),
                      "duration_basis": "sum of Lhotse recording durations"}
        if dropped:
            statistics["dropped_empty_transcripts"] = dropped
        splits[name] = {
            "artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
            "group": "test",
            "task": "asr",
            "statistics": statistics,
            "provenance": {"description": f"mTEDx {lang} test：{NAMES[lang]} TEDx 演讲（自发、半即兴），人工转写，带大小写和标点。"},
        }
        print(json.dumps({"split": name, "records": len(records), "hours": round(hours, 3), "dropped": dropped}), flush=True)

    index.sort(key=lambda row: row["cut_id"])
    index_path = version_dir / "audio-index.jsonl.gz"
    write_jsonl_gz(index_path, index)
    artifacts.insert(0, {
        "name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
        "relative_path": index_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(index_path),
        "metadata": {"record_count": len(index)},
    })
    entry = {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "languages": sorted(NAMES),
        "tasks": ["asr"],
        "aliases": [],
        "derived_from": f"{DATASET_ID}@{SOURCE_VERSION}",
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "summary": "mTEDx 西语、葡语 test（只用于评测）",
            "description": (
                f"mtedx@{SOURCE_VERSION} 的 es、pt test 划分，转成评测用的 AudioRecord：TEDx 演讲，自发、半即兴，"
                "补朗读测试集（FLEURS、Common Voice）之外的自发语音。音频为上游 Parquet 里的 FLAC，原样写出；转写取上游 transcript。只用于评测，不进训练。"
            ),
            "license": "CC BY-NC-ND 4.0（仅限非商业用途）",
            "known_issues": [
                "HF 快照比官方 test 少几条（es 1,003/1,012，pt 1,006/1,013），与 mtedx@hf-0b97ef40298d 的统计一致。",
            ],
            "build_script": "scripts/mtedx_test/build.py",
        },
    }
    CATALOG_FILE.write_text(
        "# mTEDx 西语、葡语 test 评测记录（scripts/mtedx_test/build.py 生成）。\n"
        + yaml.safe_dump([entry], allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(json.dumps({"index": len(index), "catalog": str(CATALOG_FILE)}), flush=True)
    if args.eval_set:
        write_eval_set(args.eval_set)


def write_eval_set(path):
    """The amphion-eval data config (publish with ae eval-sets publish)."""
    evaluation = [{
        "dataset_id": DATASET_ID, "version": VERSION, "split": f"mtedx-{lang}", "task": "asr",
        "label": f"mtedx-{lang}", "display": f"{name} · TEDx 演讲（mTEDx）",
        "description": f"mTEDx {lang} test：{name} TEDx 演讲，自发语音。",
    } for lang, name in NAMES.items()]
    groups = [{"name": f"{name} · TEDx", "section": "自发语音（mTEDx）", "description": f"mTEDx {name} test",
               "labels": [f"mtedx-{lang}"], "aggregate": "macro"} for lang, name in NAMES.items()]
    config = {"task": "asr", "groups": groups, "evaluation": evaluation}
    header = (
        f"# {DATASET_ID}@{VERSION}：mTEDx 西语、葡语 test（scripts/mtedx_test/build.py 生成）。\n"
        "# 发布：ae eval-sets publish <本文件> --namespace asr --name mtedx-test --version <版本>\n"
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    print(json.dumps({"eval_set": str(path), "sources": len(evaluation)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--eval-set", type=Path, help="also write the amphion-eval data config here")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
