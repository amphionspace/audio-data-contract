#!/usr/bin/env python3
"""Build ``multilingual_asr_bench``: one evaluation-only dataset of public ASR test sets in twelve languages.

The test audio is copied out of pinned upstream snapshots (registered as their own datasets, see
``sources.py``) into ``source/`` of this dataset, so the dataset directory alone is a complete copy for
``ab`` mirroring. Audio keeps its upstream encoding. Every split is AudioRecord JSONL plus one shared
audio index; durations and frame counts come from Lhotse, as the evaluator reads the files.

    python scripts/multilingual_asr_bench/build.py extract
    python scripts/multilingual_asr_bench/build.py build --workers 32 \
        --eval-set /workspace/data/datasets/multilingual_asr_bench/eval-sets/multilingual-asr-benchmark.yaml

Run with the amphion-eval environment (Lhotse 1.33). ``build`` writes the records, the audio index and
``catalog/multilingual_asr_bench.yaml`` (and with ``--eval-set`` the amphion-eval data config); a rerun
with unchanged inputs writes identical files.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (
    CASABLANCA_DIALECTS,
    DATASET_ID,
    NAMES,
    ROOT,
    SPLITS,
    VERSION,
)

REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPOSITORY / "catalog" / f"{DATASET_ID}.yaml"
csv.field_size_limit(1 << 24)


def read_tsv(path, header=True):
    with open(path, newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        rows = list(reader)
    if not header:
        return rows
    names = rows[0]
    return [dict(zip(names, row)) for row in rows[1:]]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- Upstream rows -------------------------------------------------------------------------------
# Each reader returns [(upstream_id, member_or_None, relative_audio_path, text, metadata)].


def fleurs_rows(split):
    rows = []
    for row in read_tsv(split["transcripts"], header=False):
        upstream_id, file, raw, _normalized, _chars, num_samples, gender = row
        rows.append((
            Path(file).stem,
            f"test/{file}",
            f"source/fleurs/{split['locale']}/{file}",
            raw.strip(),
            {"sentence_id": upstream_id, "gender": gender, "upstream_num_samples": int(num_samples)},
        ))
    return rows


def common_voice_rows(split):
    rows = []
    for row in read_tsv(split["transcripts"]):
        rows.append((
            Path(row["path"]).stem,
            row["path"],
            f"source/common_voice_17_0/{split['locale']}/{row['path']}",
            row["sentence"].strip(),
            {
                "speaker": row["client_id"],
                "sentence_id": row["sentence_id"],
                "gender": row["gender"],
                "age": row["age"],
                "accents": row["accents"],
            },
        ))
    return rows


def gigaspeech2_rows(split):
    rows = []
    for segment, text in read_tsv(split["transcripts"], header=False):
        group = segment.split("-")[0]
        rows.append((
            segment,
            f"./test/{group}/{segment}.wav",
            f"source/gigaspeech2/id/test/{group}/{segment}.wav",
            text.strip(),
            {},
        ))
    return rows


def casablanca_rows(split):
    import pyarrow.parquet as pq

    rows = []
    for path in sorted(Path(split["parquet_dir"]).glob("test-*.parquet")):
        table = pq.read_table(path, columns=["seg_id", "transcription", "gender", "duration"])
        for seg_id, text, gender, duration in zip(*(table[c].to_pylist() for c in table.column_names)):
            rows.append((
                seg_id,
                (path.name, seg_id),
                f"source/casablanca/{split['dialect']}/{seg_id}.wav",
                (text or "").strip(),
                {"gender": gender, "upstream_duration": duration},
            ))
    return rows


READERS = {
    "fleurs": fleurs_rows,
    "common_voice": common_voice_rows,
    "gigaspeech2": gigaspeech2_rows,
    "casablanca": casablanca_rows,
}


def upstream_rows(split):
    rows = READERS[split["kind"]](split)
    ids = [row[0] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{split['name']}: duplicate upstream IDs")
    return rows


# --- extract -------------------------------------------------------------------------------------


def extract_tar(split, rows):
    """Copy the listed members of the split's archives; members already in place are kept."""
    wanted = {member: ROOT / relative for _, member, relative, _, _ in rows}
    todo = {m: dest for m, dest in wanted.items() if not dest.exists()}
    found = set()
    for archive in split["archives"]:
        if not todo:
            break
        with tarfile.open(archive, "r|*") as stream:
            for info in stream:
                # Common Voice shards put clips under a per-shard folder; the TSV names the clip only.
                key = Path(info.name).name if split["kind"] == "common_voice" else info.name
                dest = todo.get(key)
                if dest is None or not info.isfile():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                partial = dest.with_name(dest.name + ".partial")
                with stream.extractfile(info) as source, open(partial, "wb") as target:
                    shutil.copyfileobj(source, target, 1 << 20)
                if partial.stat().st_size != info.size:
                    raise ValueError(f"{info.name}: size differs from the archive")
                partial.rename(dest)
                found.add(key)
    missing = sorted(set(todo) - found)
    if missing:
        raise ValueError(f"{split['name']}: {len(missing)} members not in the archives, e.g. {missing[:3]}")
    return len(found)


def extract_parquet(split, rows):
    import pyarrow.parquet as pq

    todo = {member: ROOT / relative for _, member, relative, _, _ in rows if not (ROOT / relative).exists()}
    written = 0
    for path in sorted(Path(split["parquet_dir"]).glob("test-*.parquet")):
        if not any(name == path.name for name, _ in todo):
            continue
        table = pq.read_table(path, columns=["seg_id", "audio"])
        for seg_id, audio in zip(table["seg_id"].to_pylist(), table["audio"].to_pylist()):
            dest = todo.get((path.name, seg_id))
            if dest is None:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            partial = dest.with_name(dest.name + ".partial")
            partial.write_bytes(audio["bytes"])
            partial.rename(dest)
            written += 1
    return written


def extract(args):
    for split in SPLITS:
        if args.kind and split["kind"] not in args.kind:
            continue
        rows = upstream_rows(split)
        count = (extract_parquet if split["kind"] == "casablanca" else extract_tar)(split, rows)
        print(json.dumps({"split": split["name"], "rows": len(rows), "extracted": count}), flush=True)


# --- build ---------------------------------------------------------------------------------------


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


def write_jsonl_gz(path, rows):
    """Write deterministic gzip JSONL (no file name or time stamp in the gzip header)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
        for row in rows:
            stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    path.write_bytes(buffer.getvalue())


def build(args):
    version_dir = ROOT / "versions" / VERSION
    plan = []
    for split in SPLITS:
        rows = upstream_rows(split)
        kept = [row for row in rows if row[3]]
        plan.append((split, kept, len(rows) - len(kept)))
    relatives = sorted({row[2] for _, kept, _ in plan for row in kept})
    with cf.ProcessPoolExecutor(args.workers) as pool:
        facts = dict(zip(relatives, pool.map(audio_facts, relatives, chunksize=64)))

    index, artifacts, splits = [], [], {}
    for split, kept, dropped in plan:
        name = split["name"]
        records = []
        for upstream_id, _member, relative, text, metadata in kept:
            fact = facts[relative]
            cut_id = f"{name}/{upstream_id}"
            index.append({"cut_id": cut_id, "root_alias": DATASET_ID, **fact})
            records.append({
                "schema_version": "audio-record/1.0",
                "id": f"{name}:{upstream_id}",
                "task": "asr",
                "language": split["language"],
                "target": text,
                "audio_slots": [{
                    "name": "primary",
                    "purpose": "primary",
                    "ref": {
                        "dataset_id": DATASET_ID,
                        "version": VERSION,
                        "split": name,
                        "cut_id": cut_id,
                        "duration": fact["duration"],
                    },
                }],
                "hotwords": [],
                "labels": {"source": split["source"], "locale": split["locale"]},
                "metadata": {"upstream_id": upstream_id, **{k: v for k, v in metadata.items() if v not in ("", None)}},
            })
        path = version_dir / "records" / f"{name}.jsonl.gz"
        write_jsonl_gz(path, records)
        artifacts.append({
            "name": f"{name}-records",
            "kind": "audio-records",
            "root_alias": DATASET_ID,
            "relative_path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(path),
            "metadata": {"record_count": len(records)},
        })
        hours = sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600
        statistics = {
            "records": len(records),
            "duration_hours": round(hours, 4),
            "duration_basis": "sum of Lhotse recording durations",
        }
        if dropped:
            statistics["dropped_empty_transcripts"] = dropped
        splits[name] = {
            "artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
            "group": "test",
            "task": "asr",
            "statistics": statistics,
            "provenance": {"description": split["description"]},
        }
        print(json.dumps({"split": name, "records": len(records), "hours": round(hours, 3), "dropped": dropped}), flush=True)

    index.sort(key=lambda row: row["cut_id"])
    index_path = version_dir / "audio-index.jsonl.gz"
    write_jsonl_gz(index_path, index)
    artifacts.insert(0, {
        "name": "audio-index",
        "kind": "audio-index",
        "root_alias": DATASET_ID,
        "relative_path": index_path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(index_path),
        "metadata": {"record_count": len(index)},
    })
    entry = {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "languages": sorted({split["language"] for split in SPLITS}),
        "tasks": ["asr"],
        "aliases": [],
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "summary": "十二种语言公开 ASR 测试集（只用于评测）",
            "description": (
                "FLEURS 与 Common Voice 17.0 的 test 划分覆盖中、英、阿、西、法、德、葡、日、韩、印地、俄、印尼十二种语言，"
                "另有 GigaSpeech 2 印尼语 test（YouTube）与 Casablanca 八种阿拉伯语方言 test（电视剧）。"
                "音频从各自登记的上游快照原样取出，不重编码；转写取上游原文（FLEURS 用 raw transcription）。只用于评测，不进训练。"
            ),
            "derived_from": sorted({split["derived_from"] for split in SPLITS}),
            "license": (
                "继承各上游：FLEURS CC BY 4.0；Common Voice CC0；GigaSpeech 2 Apache 2.0；"
                "Casablanca CC BY-NC-ND 4.0（仅限非商业用途，不得改编再分发）"
            ),
            "known_issues": [
                "Common Voice 17.0 来自非官方 HF 镜像 fsicoli/common_voice_17_0（官方 Mozilla 仓库需要授权），与 common_voice_pt@hf-8262c16bf297 相同。",
                "日语通常按字计分（CER）；当前 ts-asr 评测器（打分口径 v3）对中英文以外的语言按空格分词，日语里汉字一字一个单位、连续假名合成一个单位，日语错误率不能直接比较，需先改评测器。",
                "Casablanca 音频多为 44.1/48 kHz 双声道（电视音轨），保持原样；评测器读取时取声道平均并重采样到 16 kHz。",
            ],
            "build_script": "scripts/multilingual_asr_bench/build.py",
        },
    }
    CATALOG_FILE.write_text(
        yaml.safe_dump([entry], allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8"
    )
    print(json.dumps({"index": len(index), "catalog": str(CATALOG_FILE)}), flush=True)
    if args.eval_set:
        write_eval_set(args.eval_set)


def write_eval_set(path):
    """The amphion-eval data config of the benchmark (publish with ae eval-sets publish)."""
    by_name = {split["name"]: split for split in SPLITS}
    tags = {"zh": ["zh"], "en": ["en"]}
    evaluation = []
    for split in SPLITS:
        if split["kind"] == "casablanca":
            display = f"阿拉伯语方言 · {CASABLANCA_DIALECTS[split['dialect']]}（Casablanca）"
        elif split["kind"] == "gigaspeech2":
            display = "印尼语 · YouTube（GigaSpeech 2）"
        else:
            source = "FLEURS" if split["kind"] == "fleurs" else "Common Voice"
            display = f"{NAMES[split['language']]} · {source} 朗读"
        item = {
            "dataset_id": DATASET_ID, "version": VERSION, "split": split["name"], "task": "asr",
            "label": split["name"], "display": display, "description": split["description"],
        }
        item_tags = ["dialect"] if split["kind"] == "casablanca" else tags.get(split["language"])
        if item_tags:
            item["tags"] = list(item_tags)  # a fresh list each, so the YAML has no anchors
        evaluation.append(item)
    groups = []
    for lang, name in NAMES.items():
        labels = [f"fleurs-{lang}", f"cv-{lang}"]
        assert all(label in by_name for label in labels)
        description = f"{name} FLEURS 与 Common Voice 17.0 两个朗读测试集的平均"
        if lang == "ja":
            description += "；当前评测器没有对日语按字计分（汉字一字一个单位，连续假名合成一个），错误率暂不可比"
        groups.append({"name": name, "section": "朗读（FLEURS + Common Voice 17.0）", "description": description,
                       "labels": labels, "aggregate": "macro"})
    groups.append({"name": "印尼语 · YouTube", "section": "真实场景", "description": "GigaSpeech 2 印尼语真实视频",
                   "labels": ["gigaspeech2-id"], "aggregate": "macro"})
    groups.append({"name": "阿拉伯语方言", "section": "真实场景", "description": "Casablanca 八种阿拉伯语方言电视剧片段的平均",
                   "labels": [s["name"] for s in SPLITS if s["kind"] == "casablanca"], "aggregate": "macro"})
    config = {"task": "asr", "groups": groups, "evaluation": evaluation}
    header = (
        f"# {DATASET_ID}@{VERSION}：十二种语言公开 ASR 测试集（scripts/multilingual_asr_bench/build.py 生成）。\n"
        "# 发布：ae eval-sets publish <本文件> --project open-audio-llm --name multilingual-asr-benchmark --version <版本>\n"
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    print(json.dumps({"eval_set": str(path), "sources": len(evaluation), "groups": len(groups)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("--kind", action="append", choices=sorted(READERS), help="only these upstream kinds")
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--workers", type=int, default=16)
    build_parser.add_argument("--eval-set", type=Path, help="also write the amphion-eval data config here")
    args = parser.parse_args()
    {"extract": extract, "build": build}[args.command](args)


if __name__ == "__main__":
    main()
