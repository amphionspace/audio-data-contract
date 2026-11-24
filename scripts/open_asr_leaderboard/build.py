#!/usr/bin/env python3
"""Build ``open_asr_leaderboard``: the public test sets of the Hugging Face Open ASR Leaderboard.

The leaderboard (https://huggingface.co/spaces/hf-audio/open_asr_leaderboard, v1.16.2 of 2026-11-20)
scores English on seven public sets plus private ones, and eight languages on FLEURS, Common Voice,
MLS and AISHELL-1. This dataset mirrors the public sets from the pinned Hugging Face snapshots under
``source/`` (see ``SOURCES``), so a model can be scored here the way the leaderboard scores it:

- ``hf-snapshots-20261124``: the downloaded files as they are (Parquet, the Earnings22 chunk WAVs and
  transcripts), one artifact per upstream repository.
- ``v1-20261124``: AudioRecord JSONL per split plus one shared audio index. Audio is written out of the
  Parquet bytes unchanged under ``versions/<version>/audio/<split>/``; ``target`` is the upstream
  ``text`` (or ``transcript``), raw, because the leaderboard normalizes at scoring time.

Earnings22-Cleaned-AA-chunked has no per-chunk transcript: every chunk record carries the transcript of
its whole session as ``target`` and ``parent_id`` / ``chunk_index`` in ``metadata``. The leaderboard
joins the chunk predictions of a session in order and scores them against that transcript, so the
per-record error rate of this split is meaningless; score it with the leaderboard scorer.

Records with an empty upstream text are dropped (the leaderboard drops them too). The leaderboard also
drops a reference whose normalized text is empty, which needs its normalizer: that filter is left to the
scorer.

    python scripts/open_asr_leaderboard/build.py --workers 32 \
        --eval-set /workspace/data/datasets/open_asr_leaderboard/eval-sets/open-asr-leaderboard-v1-20261124.yaml

Run with an environment that has Lhotse 1.33, pyarrow and PyYAML (``adc-dev``). Writes
``catalog/open_asr_leaderboard.yaml`` and, with ``--eval-set``, the amphion-eval data config; a rerun
with unchanged inputs writes identical files.
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

DATASET_ID = "open_asr_leaderboard"
SOURCE_VERSION = "hf-snapshots-20261124"
VERSION = "v1-20261124"
ROOT = Path("/workspace/data/datasets") / DATASET_ID
REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPOSITORY / "catalog" / f"{DATASET_ID}.yaml"
LEADERBOARD = "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard"
LEADERBOARD_CODE = "https://github.com/huggingface/open_asr_leaderboard (commit c4696193a333)"

# Upstream repository -> pinned revision; files are under source/<org>__<name>-<revision[:12]>/.
SOURCES = {
    "hf-audio/open-asr-leaderboard": "de79e57adf9983993bcc72586d7313460825f5eb",
    "ArtificialAnalysis/Earnings22-Cleaned-AA-chunked": "27f7d0056d593231974a752ce03c1e965da69b3f",
    "ArtificialAnalysis/Earnings22-Cleaned-AA": "5999936ee3d8d3cde160e3c65a8cc6ff5b7c5276",
    "VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN": "bc1da7b42ef6e2853123c97bf6d22067e4802d11",
    "hf-audio/open-asr-leaderboard-multilingual-datasets": "2a6022fd57eea78ca23a54ec4325644fe248edd6",
}
LICENSES = {
    "hf-audio/open-asr-leaderboard": "各子集沿用原始许可：AMI CC BY 4.0；GigaSpeech 需同意使用条款（非商业研究）；"
    "SPGISpeech 仅限非商业用途；VoxPopuli CC0；URGENT 2024 加噪版含 CC BY-NC 4.0 与仅限研究的噪声",
    "ArtificialAnalysis/Earnings22-Cleaned-AA-chunked": "CC BY-SA 4.0（Earnings-22）",
    "ArtificialAnalysis/Earnings22-Cleaned-AA": "CC BY-SA 4.0（Earnings-22）",
    "VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN": "CC BY 4.0（Voice Arena）",
    "hf-audio/open-asr-leaderboard-multilingual-datasets": "FLEURS CC BY 4.0；Common Voice CC0；MLS CC BY 4.0；"
    "AISHELL-1 Apache 2.0",
}
MAIN, CHUNKED, PARENTS, MONSOON, MULTI = SOURCES


def source_dir(repo):
    org, name = repo.split("/")
    return ROOT / "source" / f"{org}__{name}-{SOURCES[repo][:12]}"


LANGUAGE_NAMES = {"zh": "中文", "de": "德语", "fr": "法语", "it": "意大利语", "es": "西班牙语",
                  "pt": "葡萄牙语", "nl": "荷兰语"}


def english(name, config, display, description):
    return {"name": name, "language": "en", "repo": MAIN, "glob": f"{config}/test-*.parquet",
            "leaderboard": config, "display": display, "description": description}


SPLITS = [
    english("ami-cleaned", "ami_cleaned", "AMI 会议（清洗版）",
            "AMI 会议录音 test，Hugging Face 清洗过参考文本的版本（榜单默认集 AMI-Cleaned）。"),
    {"name": "earnings22-cleaned-aa-chunked", "language": "en", "repo": CHUNKED, "leaderboard": "Earnings22-Cleaned-AA-chunked",
     "display": "Earnings22 财报电话会（分段）",
     "description": "Artificial Analysis 清洗的 Earnings-22 六场财报电话会，切成不超过 30 秒的段；"
                    "target 是整场转写，按场拼接后打分（榜单默认集 Earnings22-Cleaned-AA-chunked）。"},
    english("gigaspeech-cleaned", "gigaspeech_cleaned", "GigaSpeech（清洗版）",
            "GigaSpeech test，清洗过参考文本的版本（榜单默认集 Gigaspeech-Cleaned）。"),
    english("spgispeech", "spgispeech", "SPGISpeech 财经",
            "SPGISpeech test：财报电话会片段（榜单默认集 SPGISpeech）。"),
    english("urgent24", "urgent2024", "URGENT 2024（加噪）",
            "URGENT 2024 挑战赛 1,000 条，叠加噪声和混响（榜单默认集 URGENT24）。"),
    english("urgent24-clean", "urgent2024_clean", "URGENT 2024（干净）",
            "与 urgent24 同一批语音的干净版（榜单可选集 URGENT24 Clean，不在默认平均里）。"),
    {"name": "monsoon-en-in", "language": "en", "repo": MONSOON, "glob": "data/test-*.parquet", "leaderboard": "Voice Arena Monsoon",
     "display": "印度口音英语对话（Monsoon）",
     "description": "Voice Arena 为榜单提供的印度口音英语双人对话，按声道切成单人片段（榜单默认集 Voice Arena Monsoon）。"},
    english("voxpopuli-cleaned-aa", "voxpopuli_cleaned_aa", "VoxPopuli 欧洲议会（清洗版）",
            "Artificial Analysis 清洗参考文本后的 VoxPopuli 英语子集，628 条（榜单默认集 Voxpopuli-AA-Cleaned）。"),
]
for lang in ("zh", "de", "fr", "it", "es", "pt", "nl"):
    SPLITS.append({"name": f"fleurs-{lang}", "language": lang, "repo": MULTI, "glob": f"data/fleurs/{lang}_test.parquet",
                   "leaderboard": f"fleurs_{lang}", "display": f"{LANGUAGE_NAMES[lang]} · FLEURS",
                   "description": f"FLEURS {lang} test（榜单多语种 {lang} 的 FLEURS 部分）。"})
SPLITS.append({"name": "aishell1-zh", "language": "zh", "repo": MULTI, "glob": "data/aishell1/zh_test.parquet",
               "leaderboard": "aishell1_zh", "display": "中文 · AISHELL-1",
               "description": "AISHELL-1 test（榜单多语种中文的另一部分，按字计分）。"})
for lang in ("de", "es", "fr", "it", "nl"):
    SPLITS.append({"name": f"mcv-{lang}", "language": lang, "repo": MULTI, "glob": f"data/mcv/{lang}_test.parquet",
                   "leaderboard": f"mcv_{lang}", "display": f"{LANGUAGE_NAMES[lang]} · Common Voice",
                   "description": f"Common Voice {lang} test（榜单多语种 {lang} 的 MCV 部分）。"})
for lang in ("es", "fr", "it", "pt", "nl"):
    SPLITS.append({"name": f"mls-{lang}", "language": lang, "repo": MULTI, "glob": f"data/mls/{lang}_test.parquet",
                   "leaderboard": f"mls_{lang}", "display": f"{LANGUAGE_NAMES[lang]} · MLS",
                   "description": f"Multilingual LibriSpeech {lang} test（榜单多语种 {lang} 的 MLS 部分）。"})


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


def audio_suffix(data, path):
    """File suffix of the audio bytes: the upstream file name's when it has one, else sniffed."""
    suffix = Path(path or "").suffix.lower()
    if suffix in (".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a"):
        return suffix
    if data[:4] == b"RIFF":
        return ".wav"
    if data[:4] == b"fLaC":
        return ".flac"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    raise ValueError(f"unknown audio format for {path!r}")


def text_of(row):
    """The reference column, in the order the leaderboard's data_utils.get_text looks for it."""
    for key in ("text", "sentence", "normalized_text", "transcript", "transcription"):
        if key in row and row[key] is not None:
            return row[key]
    raise KeyError(f"no transcript column in {sorted(row)}")


def write_audio(relative, data):
    dest = ROOT / relative
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".partial")
        partial.write_bytes(data)
        partial.rename(dest)


def extract_parquet(job):
    """Write one Parquet file's audio; return its rows as (upstream_id, relative, text, metadata)."""
    import pyarrow.parquet as pq

    split, path = job
    rows = []
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=256):
        for row in batch.to_pylist():
            text = text_of(row)
            upstream_id = str(row.get("id") or Path(row.get("file_name") or "").stem)
            if not upstream_id:
                raise ValueError(f"row without id or file_name in {path}")
            metadata = {k: row[k] for k in ("dataset", "audio_length_s", "duration", "snr_db", "speaker_id",
                                            "source_lang", "file_name") if row.get(k) is not None}
            audio = row["audio"]
            if not text.strip():
                rows.append((upstream_id, None, text, metadata))
                continue
            name = upstream_id.replace("/", "_")
            relative = f"versions/{VERSION}/audio/{split['name']}/{name}{audio_suffix(audio['bytes'], audio.get('path'))}"
            write_audio(relative, audio["bytes"])
            rows.append((upstream_id, relative, text, metadata))
    return split["name"], path.name, rows


def earnings_rows(split):
    parents = {}
    with open(source_dir(PARENTS) / "earnings22_cleaned_aa_v1.jsonl", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            parents[row["id"]] = text_of(row)
    rows = []
    with open(source_dir(CHUNKED) / "earnings22_cleaned_aa_chunked_v1.jsonl", encoding="utf-8") as stream:
        for line in stream:
            chunk = json.loads(line)
            source = source_dir(CHUNKED) / "audio" / chunk["file_name"]
            relative = f"versions/{VERSION}/audio/{split['name']}/{chunk['file_name']}"
            write_audio(relative, source.read_bytes())
            upstream_id = f"{chunk['parent_id']}:{chunk['chunk_index']:04d}"
            metadata = {"parent_id": chunk["parent_id"], "chunk_index": chunk["chunk_index"],
                        "chunk_start_seconds": chunk["chunk_start_seconds"],
                        "chunk_end_seconds": chunk["chunk_end_seconds"], "upstream_chunk_id": chunk["id"]}
            rows.append((upstream_id, relative, parents[chunk["parent_id"]], metadata))
    return rows


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


def tree_facts(directory):
    """file_count, expected_bytes and tree_sha256 exactly as audio-data-contract verifies a directory."""
    files = sorted((p for p in directory.rglob("*") if p.is_file()), key=lambda p: p.relative_to(directory).as_posix())
    tree, total = hashlib.sha256(), 0
    for path in files:
        size = path.stat().st_size
        tree.update(f"{path.relative_to(directory).as_posix()}\0{size}\0{sha256_file(path)}\n".encode())
        total += size
    return {"file_count": len(files), "expected_bytes": total, "tree_sha256": tree.hexdigest()}


def source_entry():
    artifacts = []
    for repo, revision in SOURCES.items():
        directory = source_dir(repo)
        artifacts.append({
            "name": directory.name, "kind": "hf-snapshot", "root_alias": DATASET_ID,
            "relative_path": directory.relative_to(ROOT).as_posix(),
            "metadata": {"repository": f"https://huggingface.co/datasets/{repo}", "revision": revision,
                         "license": LICENSES[repo], **tree_facts(directory)},
        })
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": SOURCE_VERSION,
        "languages": sorted({"en", *LANGUAGE_NAMES}),
        "tasks": ["asr"],
        "aliases": [],
        "artifacts": artifacts,
        "splits": {},
        "provenance": {
            "summary": "Open ASR 榜公开测试集的 HF 快照",
            "description": (
                f"{LEADERBOARD}（v1.16.2，2026-11-20）评分用到的公开数据，按 {LEADERBOARD_CODE} 的评测脚本"
                "（qwen/submit_jobs.sh、submit_jobs_ml.sh）列出的仓库和配置下载，每个仓库固定一个 revision，"
                "文件原样保存。印地语（Voice Arena 私有集与 lattice 打分）和英文私有集不在其中。"
            ),
            "license": "见各 artifact 的 metadata.license；整体只用于评测，多数子集限非商业使用",
            "build_script": "scripts/open_asr_leaderboard/build.py",
        },
    }


def build(args):
    version_dir = ROOT / "versions" / VERSION
    jobs = []
    for split in SPLITS:
        if split["repo"] == CHUNKED:
            continue
        files = sorted(source_dir(split["repo"]).glob(split["glob"]))
        if not files:
            raise FileNotFoundError(f"{split['name']}: no files match {split['glob']}")
        jobs.extend((split, path) for path in files)

    plan = {split["name"]: {} for split in SPLITS}
    with cf.ProcessPoolExecutor(args.workers) as pool:
        for name, file_name, rows in pool.map(extract_parquet, jobs):
            plan[name][file_name] = rows
            print(json.dumps({"extracted": name, "file": file_name, "rows": len(rows)}), flush=True)
    by_split = {}
    for split in SPLITS:
        if split["repo"] == CHUNKED:
            by_split[split["name"]] = earnings_rows(split)
        else:
            by_split[split["name"]] = [r for file_name in sorted(plan[split["name"]]) for r in plan[split["name"]][file_name]]

    relatives = sorted(r[1] for rows in by_split.values() for r in rows if r[1])
    with cf.ProcessPoolExecutor(args.workers) as pool:
        facts = dict(zip(relatives, pool.map(audio_facts, relatives, chunksize=64)))

    index, artifacts, splits = [], [], {}
    for split in SPLITS:
        name = split["name"]
        records, dropped, seen = [], 0, {}
        for upstream_id, relative, text, metadata in by_split[name]:
            if relative is None:
                dropped += 1
                continue
            # Upstream ids repeat in a few sets; the n-th repeat gets "#n" so ids stay unique.
            count = seen.get(upstream_id, 0)
            seen[upstream_id] = count + 1
            record_key = upstream_id if count == 0 else f"{upstream_id}#{count}"
            fact = facts[relative]
            cut_id = f"{name}/{record_key}"
            index.append({"cut_id": cut_id, "root_alias": DATASET_ID, **fact})
            records.append({
                "schema_version": "audio-record/1.0",
                "id": f"{name}:{record_key}",
                "task": "asr",
                "language": split["language"],
                "target": text,
                "audio_slots": [{
                    "name": "primary",
                    "purpose": "primary",
                    "ref": {"dataset_id": DATASET_ID, "version": VERSION, "split": name,
                            "cut_id": cut_id, "duration": fact["duration"]},
                }],
                "hotwords": [],
                "labels": {"source": "Open ASR Leaderboard", "leaderboard_dataset": split["leaderboard"]},
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
            "provenance": {"description": split["description"]},
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
        "languages": sorted({"en", *LANGUAGE_NAMES}),
        "tasks": ["asr"],
        "aliases": [],
        "derived_from": f"{DATASET_ID}@{SOURCE_VERSION}",
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "summary": "Open ASR 榜公开测试集的评测记录",
            "description": (
                f"{DATASET_ID}@{SOURCE_VERSION} 转成的 AudioRecord：英文 7 个默认公开集加 URGENT24 Clean，"
                "多语种 7 种语言的 FLEURS、Common Voice、MLS 和 AISHELL-1。音频取自 Parquet 原样写出；"
                "target 是上游原始文本，不做规范化。只用于评测，不进训练。"
            ),
            "license": "见 hf-snapshots-20261124 各 artifact；多数子集限非商业使用",
            "known_issues": [
                "earnings22-cleaned-aa-chunked 每条的 target 是整场转写，逐条错误率没有意义，要按场拼接打分。",
                "榜单会去掉规范化后为空的参考文本，这一步需要榜单规范化器，留给打分器。",
            ],
            "build_script": "scripts/open_asr_leaderboard/build.py",
        },
    }
    CATALOG_FILE.write_text(
        "# Open ASR Leaderboard 公开测试集（scripts/open_asr_leaderboard/build.py 生成）。\n"
        + yaml.safe_dump([source_entry(), entry], allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(json.dumps({"index": len(index), "catalog": str(CATALOG_FILE)}), flush=True)
    if args.eval_set:
        write_eval_set(args.eval_set)


def write_eval_set(path):
    """The amphion-eval data config (publish with ae eval-sets publish)."""
    evaluation = [{
        "dataset_id": DATASET_ID, "version": VERSION, "split": split["name"], "task": "asr",
        "label": split["name"], "display": split["display"], "description": split["description"],
    } for split in SPLITS]
    english_default = [s["name"] for s in SPLITS if s["language"] == "en" and s["name"] != "urgent24-clean"
                       and s["repo"] != CHUNKED]
    groups = [
        {"name": "英文 · 默认公开集（不含 Earnings22）", "section": "英文",
         "description": "榜单英文默认集中能逐条打分的 6 个公开集；完整的榜单口径（含 Earnings22，不含私有集）"
                        "用 ae open-asr-leaderboard score",
         "labels": english_default, "aggregate": "macro"},
        {"name": "英文 · Earnings22 分段", "section": "英文",
         "description": "每段的参考文本是整场转写，逐条错误率没有意义；按场拼接的榜单口径见 ae open-asr-leaderboard score",
         "labels": ["earnings22-cleaned-aa-chunked"], "aggregate": "macro"},
        {"name": "英文 · URGENT24 干净版", "section": "英文",
         "description": "与 urgent24 同一批语音的干净版，榜单可选集，不在默认平均里",
         "labels": ["urgent24-clean"], "aggregate": "macro"},
    ]
    for lang, name in LANGUAGE_NAMES.items():
        groups.append({"name": name, "section": "多语种", "description": f"榜单多语种 {lang} 用到的公开集",
                       "labels": [s["name"] for s in SPLITS if s["language"] == lang], "aggregate": "macro"})
    config = {"task": "asr", "groups": groups, "evaluation": evaluation}
    header = (
        f"# {DATASET_ID}@{VERSION}：Open ASR Leaderboard 公开测试集（scripts/open_asr_leaderboard/build.py 生成）。\n"
        "# 发布：ae eval-sets publish <本文件> --namespace asr --name open-asr-leaderboard --version <版本>\n"
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--eval-set", help="also write the amphion-eval data config to this path")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
