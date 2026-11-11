#!/usr/bin/env python3
"""Build ``multilingual_asr_bench``: one evaluation-only dataset of public ASR test sets in twelve languages.

The test audio is copied out of pinned upstream snapshots (registered as their own datasets, see
``sources.py``) into ``source/`` of this dataset, so the dataset directory alone is a complete copy for
``ab`` mirroring. Audio keeps its upstream encoding, except Kathbath's m4a (AAC), which Lhotse does not
read reliably and is decoded to FLAC with ffmpeg. Every split is AudioRecord JSONL plus one shared
audio index; durations and frame counts come from Lhotse, as the evaluator reads the files.

    python scripts/multilingual_asr_bench/build.py extract
    python scripts/multilingual_asr_bench/build.py build --workers 32 \
        --eval-set /workspace/data/datasets/multilingual_asr_bench/eval-sets/multilingual-asr-benchmark-v2-20261110.yaml

Run with the amphion-eval environment (Lhotse 1.33) and ffmpeg on PATH. ``build`` writes the records and
the audio index of ``VERSION``, replaces that version's entry in ``catalog/multilingual_asr_bench.yaml``
(earlier versions stay as they are) and with ``--eval-set`` writes the amphion-eval data config; a rerun
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
import subprocess
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
    V1,
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


def tar_member(archive, member):
    with tarfile.open(archive) as stream:
        return stream.extractfile(member).read().decode("utf-8")


def kathbath_rows(split):
    rows = []
    for line in tar_member(*split["transcripts"]).splitlines():
        if not line.strip():
            continue
        file, text = line.split("\t")
        stem = Path(file).stem
        # Files are <utterance>-<speaker>-<gender>.m4a.
        _, speaker, gender = stem.rsplit("-", 2)
        rows.append((
            stem,
            f"kb_data_clean_m4a/hindi/{split['folder']}/audio/{file}",
            f"source/kathbath/hindi/{split['folder']}/{stem}.flac",
            text.strip(),
            {"speaker": speaker, "gender": gender, "upstream_file": file},
        ))
    return rows


def voxpopuli_rows(split):
    import pyarrow.parquet as pq

    rows = []
    columns = ["audio_id", "raw_text", "normalized_text", "gender", "speaker_id", "is_gold_transcript", "accent"]
    for path in split["parquet_files"]:
        table = pq.read_table(path, columns=columns)
        for audio_id, raw, normalized, gender, speaker, gold, accent in zip(*(table[c].to_pylist() for c in columns)):
            # IDs carry the clock time (10:24:36); file names and record IDs use "-" instead of ":".
            local_id = audio_id.replace(":", "-")
            # Unknown fields are the string "None" upstream.
            known = {k: v for k, v in {"speaker": speaker, "gender": gender, "accent": accent}.items() if v != "None"}
            rows.append((
                local_id,
                (path.name, audio_id),
                f"source/voxpopuli/{split['language']}/{local_id}.wav",
                (raw or "").strip(),
                {"audio_id": audio_id, **known, "normalized_text": normalized, "is_gold_transcript": gold},
            ))
    return rows


def golos_rows(split):
    rows = []
    for line in tar_member(*split["transcripts"]).splitlines():
        row = json.loads(line)
        rows.append((
            row["id"],
            f"test/{split['part']}/{row['audio_filepath']}",
            f"source/golos/{split['part']}/{row['audio_filepath']}",
            row["text"].strip(),
            {"upstream_duration": row["duration"]},
        ))
    return rows


READERS = {
    "fleurs": fleurs_rows,
    "common_voice": common_voice_rows,
    "gigaspeech2": gigaspeech2_rows,
    "casablanca": casablanca_rows,
    "kathbath": kathbath_rows,
    "voxpopuli": voxpopuli_rows,
    "golos": golos_rows,
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
    if split["kind"] == "casablanca":
        files, key = sorted(Path(split["parquet_dir"]).glob("test-*.parquet")), "seg_id"
    else:
        files, key = split["parquet_files"], "audio_id"
    written = 0
    for path in files:
        if not any(name == path.name for name, _ in todo):
            continue
        table = pq.read_table(path, columns=[key, "audio"])
        for seg_id, audio in zip(table[key].to_pylist(), table["audio"].to_pylist()):
            dest = todo.get((path.name, seg_id))
            if dest is None:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            partial = dest.with_name(dest.name + ".partial")
            partial.write_bytes(audio["bytes"])
            partial.rename(dest)
            written += 1
    return written


def decode_to_flac(source, dest):
    """Decode one compressed file to 16-bit FLAC; bitexact output, so a rerun writes the same bytes."""
    partial = dest.with_name(dest.name + ".partial")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source), "-map_metadata", "-1",
         "-fflags", "+bitexact", "-flags:a", "+bitexact", "-c:a", "flac", "-sample_fmt", "s16", "-f", "flac", str(partial)],
        check=True,
    )
    partial.rename(dest)
    source.unlink()


def extract_kathbath(split, rows):
    """Copy the listed m4a members next to their destination, then decode each to FLAC."""
    todo = {member: ROOT / relative for _, member, relative, _, _ in rows if not (ROOT / relative).exists()}
    found = set()
    with cf.ThreadPoolExecutor(16) as pool:
        futures = []
        for archive in split["archives"]:
            with tarfile.open(archive, "r|*") as stream:
                for info in stream:
                    dest = todo.get(info.name)
                    if dest is None or not info.isfile():
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    compressed = dest.with_suffix(".m4a")
                    with stream.extractfile(info) as source, open(compressed, "wb") as target:
                        shutil.copyfileobj(source, target, 1 << 20)
                    futures.append(pool.submit(decode_to_flac, compressed, dest))
                    found.add(info.name)
        for future in futures:
            future.result()
    missing = sorted(set(todo) - found)
    if missing:
        raise ValueError(f"{split['name']}: {len(missing)} members not in the archives, e.g. {missing[:3]}")
    return len(found)


EXTRACTORS = {"casablanca": extract_parquet, "voxpopuli": extract_parquet, "kathbath": extract_kathbath}


def extract(args):
    for split in SPLITS:
        if args.kind and split["kind"] not in args.kind:
            continue
        rows = upstream_rows(split)
        # Rows without a transcript are not built, so their audio is not copied.
        count = EXTRACTORS.get(split["kind"], extract_tar)(split, [row for row in rows if row[3]])
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
                "另有 GigaSpeech 2 印尼语 test（YouTube）、Casablanca 八种阿拉伯语方言 test（电视剧）、"
                "Kathbath 印地语 test（手机朗读，已知/未知说话人）、VoxPopuli 法语和德语 test（欧洲议会发言）"
                "与 Golos 俄语 test（语音助手指令，众包/远场）。"
                "音频从各自登记的上游快照原样取出，只有 Kathbath 的 m4a 解码为 FLAC；转写取上游原文（FLEURS 用 raw transcription，VoxPopuli 用 raw_text）。"
                f"{V1} 是不含 Kathbath、VoxPopuli、Golos 的前一版，两版共用 source/ 下的音频。只用于评测，不进训练。"
            ),
            "derived_from": sorted({split["derived_from"] for split in SPLITS}),
            "license": (
                "继承各上游：FLEURS CC BY 4.0；Common Voice CC0；GigaSpeech 2 Apache 2.0；"
                "Casablanca CC BY-NC-ND 4.0（仅限非商业用途，不得改编再分发）；Kathbath CC0；VoxPopuli CC0；"
                "Golos 为 SberDevices 署名-相同方式共享公共许可（允许商用，再分发须署名并沿用同类许可）"
            ),
            "known_issues": [
                "Common Voice 17.0 来自非官方 HF 镜像 fsicoli/common_voice_17_0（官方 Mozilla 仓库需要授权），与 common_voice_pt@hf-8262c16bf297 相同。",
                "日语按字计分（CER）需要 ts-asr 打分口径版本 4 及以上；版本 3 对日语按空格分词（汉字一字一个单位、连续假名合成一个单位），日语错误率不可比。",
                "Casablanca 音频多为 44.1/48 kHz 双声道（电视音轨），保持原样；评测器读取时取声道平均并重采样到 16 kHz。",
                "Kathbath 音频原为 44.1 kHz 单声道 m4a（AAC），用 ffmpeg 解码为 16 位 FLAC（采样率不变）；test-known 的说话人也出现在 Kathbath 训练集。",
                "Golos 转写为小写、无标点（与上游 manifest.jsonl 一致）；GigaSpeech 2 转写为大写、无标点。打分时会统一大小写和标点，但带标点的识别结果在其他评测器下可能吃亏。",
            ],
            "build_script": "scripts/multilingual_asr_bench/build.py",
        },
    }
    # Earlier versions keep their entries unchanged; this version's entry is replaced.
    entries = [e for e in yaml.safe_load(CATALOG_FILE.read_text(encoding="utf-8")) or [] if e["version"] != VERSION]
    CATALOG_FILE.write_text(
        yaml.safe_dump(entries + [entry], allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8"
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
        elif split["kind"] == "kathbath":
            part = "已知说话人" if split["folder"] == "test_known" else "未知说话人"
            display = f"印地语 · 手机朗读 {part}（Kathbath）"
        elif split["kind"] == "voxpopuli":
            display = f"{NAMES[split['language']]} · 欧洲议会（VoxPopuli）"
        elif split["kind"] == "golos":
            display = "俄语 · 语音助手 " + ("众包" if split["part"] == "crowd" else "远场") + "（Golos）"
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
            description += "；日语按字计分（CER）需要 ts-asr 打分口径版本 4 及以上，版本 3 的日语错误率不可比"
        groups.append({"name": name, "section": "朗读（FLEURS + Common Voice 17.0）", "description": description,
                       "labels": labels, "aggregate": "macro"})
    groups.append({"name": "印尼语 · YouTube", "section": "真实场景", "description": "GigaSpeech 2 印尼语真实视频",
                   "labels": ["gigaspeech2-id"], "aggregate": "macro"})
    groups.append({"name": "阿拉伯语方言", "section": "真实场景", "description": "Casablanca 八种阿拉伯语方言电视剧片段的平均",
                   "labels": [s["name"] for s in SPLITS if s["kind"] == "casablanca"], "aggregate": "macro"})
    for lang in ("fr", "de"):
        groups.append({"name": f"{NAMES[lang]} · 欧洲议会", "section": "真实场景",
                       "description": f"VoxPopuli 欧洲议会{NAMES[lang]}发言", "labels": [f"voxpopuli-{lang}"], "aggregate": "macro"})
    groups.append({"name": "印地语 · Kathbath", "section": "手机与远场录音",
                   "description": "Kathbath 印地语手机朗读，已知说话人与未知说话人两部分的平均",
                   "labels": ["kathbath-hi-known", "kathbath-hi-unknown"], "aggregate": "macro"})
    groups.append({"name": "俄语 · Golos", "section": "手机与远场录音",
                   "description": "Golos 俄语语音助手指令，众包手机录音与远场录音两部分的平均",
                   "labels": ["golos-crowd", "golos-farfield"], "aggregate": "macro"})
    assert sorted(label for g in groups for label in g["labels"]) == sorted(by_name)
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
