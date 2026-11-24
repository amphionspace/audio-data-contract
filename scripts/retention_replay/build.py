#!/usr/bin/env python3
"""Build ``retention_replay``: training audio in languages AmphionASR has forgotten, labelled by the
model it started from.

AmphionASR is trained on Chinese, English and Spanish only. On the Open ASR Leaderboard sets it lost
2-3x in German, French, Italian, Portuguese and Dutch against Qwen3-ASR-1.7B
(open-audio-llm docs/experiments/2026-11-24-open-asr-leaderboard). These splits feed a
retention objective: the frozen Qwen3-ASR-1.7B teaches its own output, so the target is that model's
transcript (language forced, as the Open ASR Leaderboard calls it), not the corpus text, whose style
differs per corpus (MLS has no case or punctuation). The corpus text is kept in metadata.

Audio comes from train splits only:
- Common Voice train (de, fr, ja, ko, ru, ar; pt from pt-train-v1-20261117) and MLS train (de, fr
  train_punc; pt-train-v1-20261117), referenced in place through the audio index;
- MLS it / nl from mls_sidon (DATA-TTS-UNIFIED), rows whose original MLS split is train, written out
  as 16 kHz FLAC under versions/<version>/audio/<lang>/ because the release stores audio in Lance.

Per language, PER_LANGUAGE clips of 2-20 s are drawn evenly over its sources, lowest SHA-256 of the
clip ID first, so a rerun picks the same clips. A clip is kept when the label is not empty and its
error rate against the corpus text is at most MAX_LABEL_ERROR: a larger gap means unusable audio or
a wrong corpus text. Labels come from a vLLM server of Qwen3-ASR-1.7B started with amphion-eval's
qwen3-asr-force-language.jinja.

    python scripts/retention_replay/build.py select
    python scripts/retention_replay/build.py label --server http://127.0.0.1:18821 --model Qwen/Qwen3-ASR-1.7B
    python scripts/retention_replay/build.py build --workers 32

Run with an environment that has Lhotse, lance, soundfile, scipy and open-audio-llm (for the catalog
resolver), e.g. oal-train with PYTHONPATH=<open-audio-llm>/src.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import gzip
import hashlib
import io
import json
import re
import threading
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np
import yaml

DATASET_ID = "retention_replay"
VERSION = "qwen3-base-v1-20261124"
ROOT = Path("/workspace/data/datasets") / DATASET_ID
VERSION_DIR = ROOT / "versions" / VERSION
REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPOSITORY / "catalog" / f"{DATASET_ID}.yaml"
REGISTRY = Path("/workspace/data/registry")
SIDON = Path("/workspace/data/DATA-TTS-UNIFIED/datasets/mls_sidon/v0.1/samples.lance")
PER_LANGUAGE = 6000
MIN_SECONDS, MAX_SECONDS = 2.0, 20.0
MAX_LABEL_ERROR = 0.5
SAMPLE_RATE = 16000
# Qwen3-ASR language names, as amphion-eval force_language sends them.
NAMES = {"de": "German", "fr": "French", "pt": "Portuguese", "it": "Italian", "nl": "Dutch",
         "ja": "Japanese", "ko": "Korean", "ru": "Russian", "ar": "Arabic"}
LHOTSE = {
    "de": [("common_voice_de", "legacy", "train"), ("mls_de", "legacy", "train_punc")],
    "fr": [("common_voice_fr", "legacy", "train"), ("mls_fr", "legacy", "train_punc")],
    "pt": [("common_voice_pt", "pt-train-v1-20261117", "train"), ("mls_pt", "pt-train-v1-20261117", "train")],
    "ja": [("common_voice_ja", "legacy", "train")],
    "ko": [("common_voice_ko", "legacy", "train")],
    "ru": [("common_voice_ru", "legacy", "train")],
    "ar": [("common_voice_ar", "legacy", "train")],
}
SIDON_LANGUAGES = ("it", "nl")
# Scored by character: Japanese has no spaces; Korean spacing varies ("투표해 주시기" / "투표해주시기").
BY_CHARACTER = {"ja", "ko"}
KEEP_MARKS = {"ja"}
# Files of this dataset are addressed through the shared data root, as AGENTS.md writes them.
ROOT_ALIAS = "aidc_data"
ROOT_PREFIX = f"datasets/{DATASET_ID}"
_NON_WORD = re.compile(r"[\W_]+")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


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


def root_of(path, roots):
    """(root alias, relative path) of an absolute audio path: the longest root that holds it."""
    best = None
    for alias, root in roots.items():
        root = str(Path(root)) + "/"
        if path.startswith(root) and (best is None or len(root) > len(best[1])):
            best = (alias, root)
    if best is None:
        raise ValueError(f"no root holds {path}")
    return best[0], path[len(best[1]):]


# --- select ---------------------------------------------------------------------------------------

def lhotse_candidates(dataset_id, version, split, roots):
    from open_audio_llm.data.catalog_resolver import LhotseCatalogAudioResolver

    resolver = LhotseCatalogAudioResolver(str(REGISTRY / "catalog"), str(REGISTRY / "roots.json"))
    for cut in resolver.iter_cuts(dataset_id, version, split):
        if not MIN_SECONDS <= cut.duration <= MAX_SECONDS or len(cut.supervisions) != 1:
            continue
        recording = cut.recording
        # Whole single-file recordings only, so the audio index can point at the file itself.
        if cut.start or abs(cut.duration - recording.duration) > 0.01 or len(recording.sources) != 1:
            continue
        source = recording.sources[0]
        if source.type != "file":
            continue
        yield {"key": f"{dataset_id}@{version}:{split}:{cut.id}", "origin": f"{dataset_id}@{version}:{split}",
               "upstream_id": cut.id, "text": cut.supervisions[0].text or "", "duration": round(cut.duration, 6),
               "path": source.source}


def sidon_candidates(language):
    import lance

    table = lance.dataset(str(SIDON))
    columns = ["sample_id", "source_key", "text", "language", "duration_seconds", "metadata_json"]
    for batch in table.to_batches(columns=columns, filter=f"language = '{language}' AND source_split = 'train'"):
        for row in batch.to_pylist():
            original = json.loads(row["metadata_json"] or "{}").get("original_split")
            if original != "train" or not MIN_SECONDS <= row["duration_seconds"] <= MAX_SECONDS:
                continue
            yield {"key": f"mls_sidon@v0.1:{row['source_key']}", "origin": "mls_sidon@v0.1:train",
                   "upstream_id": row["source_key"], "sample_id": row["sample_id"], "text": row["text"] or "",
                   "duration": round(row["duration_seconds"], 6)}


def lowest(items, count):
    return sorted(items, key=lambda item: sha(item["key"]))[:count]


def select(args):
    roots = json.loads((REGISTRY / "roots.json").read_text())
    plan = {}
    for language in NAMES:
        if language in SIDON_LANGUAGES:
            chosen = lowest(sidon_candidates(language), PER_LANGUAGE)
        else:
            sources = LHOTSE[language]
            chosen = []
            for number, (dataset_id, version, split) in enumerate(sources):
                share = PER_LANGUAGE // len(sources) + (number < PER_LANGUAGE % len(sources))
                for item in lowest(lhotse_candidates(dataset_id, version, split, roots), share):
                    # Only the chosen clips: a root lookup per candidate is slow over 10^6 cuts.
                    item["root_alias"], item["relative_path"] = root_of(item.pop("path"), roots)
                    chosen.append(item)
        plan[language] = chosen
        print(json.dumps({"language": language, "selected": len(chosen)}), flush=True)
    VERSION_DIR.mkdir(parents=True, exist_ok=True)
    (VERSION_DIR / "selection.json").write_text(json.dumps(plan, ensure_ascii=False))


# --- label ----------------------------------------------------------------------------------------

def sidon_relative(language, item):
    return f"versions/{VERSION}/audio/{language}/{item['upstream_id'].replace(':', '_')}.flac"


def extract_sidon(language, items, chunk=400):
    """Write the mls_sidon clips as 16 kHz mono FLAC under this version (their audio lives in Lance)."""
    import lance
    import soundfile as sf
    from scipy.signal import resample_poly

    table = lance.dataset(str(SIDON))
    wanted = {i["sample_id"]: i for i in items if not (ROOT / sidon_relative(language, i)).exists()}
    ids = sorted(wanted)
    for start in range(0, len(ids), chunk):
        quoted = ", ".join(f"'{s}'" for s in ids[start:start + chunk])
        for batch in table.to_batches(columns=["sample_id", "audio"], filter=f"sample_id IN ({quoted})"):
            for row in batch.to_pylist():
                # The release stores audio as a {bytes, path} struct.
                audio, rate = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32", always_2d=True)
                audio = audio.mean(axis=1)
                if rate != SAMPLE_RATE:
                    audio = resample_poly(audio, SAMPLE_RATE, rate).astype("float32")
                target = ROOT / sidon_relative(language, wanted[row["sample_id"]])
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + ".partial")
                sf.write(partial, audio, SAMPLE_RATE, format="FLAC")
                partial.rename(target)


def file_audio(path):
    import soundfile as sf
    from scipy.signal import resample_poly

    try:
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception:  # noqa: BLE001 - mp3 needs a decoder soundfile may lack
        from lhotse import Recording

        recording = Recording.from_file(path)
        audio, rate = recording.load_audio().T, recording.sampling_rate
    audio = audio.mean(axis=1)
    if rate != SAMPLE_RATE:
        audio = resample_poly(audio, SAMPLE_RATE, rate).astype("float32")
    return audio


def wav_bytes(audio):
    import soundfile as sf

    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 1.0:
        audio = audio / peak
    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def transcribe(server, model, audio, language):
    body = {"model": model, "max_tokens": 256, "temperature": 0.0,
            "chat_template_kwargs": {"force_language": NAMES[language]},
            "messages": [{"role": "system", "content": ""},
                         {"role": "user", "content": [{"type": "input_audio", "input_audio": {
                             "data": base64.b64encode(wav_bytes(audio)).decode(), "format": "wav"}}]}]}
    request = urllib.request.Request(f"{server}/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=300) as response:
        text = json.load(response)["choices"][0]["message"]["content"]
    if "<asr_text>" in text:
        raise RuntimeError("server did not apply force_language; start it with the force-language template")
    return text.strip()


def label(args):
    roots = json.loads((REGISTRY / "roots.json").read_text())
    plan = json.loads((VERSION_DIR / "selection.json").read_text())
    path = VERSION_DIR / "labels.jsonl"
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            done[row["key"]] = row
    lock = threading.Lock()
    with path.open("a", encoding="utf-8") as output:
        for language, items in plan.items():
            todo = [item for item in items if item["key"] not in done]
            if not todo:
                continue
            sidon = language in SIDON_LANGUAGES
            if sidon:
                extract_sidon(language, todo)

            def one(item, language=language, sidon=sidon):
                if sidon:
                    relative = sidon_relative(language, item)
                    audio = file_audio(str(ROOT / relative))
                    location = {"root_alias": DATASET_ID, "relative_path": relative}
                else:
                    audio = file_audio(str(Path(roots[item["root_alias"]]) / item["relative_path"]))
                    location = {}
                text = transcribe(args.server, args.model, audio, language)
                return {"key": item["key"], "language": language, "label": text, **location}

            with cf.ThreadPoolExecutor(args.concurrency) as pool:
                for result in pool.map(one, todo):
                    with lock:
                        output.write(json.dumps(result, ensure_ascii=False) + "\n")
                        output.flush()
            print(json.dumps({"language": language, "labelled": len(todo)}), flush=True)


# --- build ----------------------------------------------------------------------------------------

def norm(text, language):
    """Words of a text for the label check, combining marks removed on both sides.

    Arabic harakat (category Mn) are not \\w: left in, they split one word into pieces, and Common
    Voice ar writes them where Qwen3-ASR does not, so voweled sentences were rejected. NFC after the
    removal keeps Hangul syllables whole. Japanese keeps its marks: NFKD splits off the dakuten.
    """
    text = unicodedata.normalize("NFKC", text or "")
    if language not in KEEP_MARKS:
        text = unicodedata.normalize("NFKD", text)
        text = unicodedata.normalize("NFC", "".join(c for c in text if unicodedata.category(c) != "Mn"))
    return _NON_WORD.sub(" ", text.lower()).split()


def label_error(reference, hypothesis, language):
    from rapidfuzz.distance import Levenshtein

    ref, hyp = norm(reference, language), norm(hypothesis, language)
    if language in BY_CHARACTER:
        ref, hyp = list("".join(ref)), list("".join(hyp))
    return Levenshtein.distance(ref, hyp) / max(len(ref), 1)


def audio_facts(location):
    from lhotse import Recording

    alias, relative = location
    roots = json.loads((REGISTRY / "roots.json").read_text())
    path = Path(roots[alias]) / relative
    recording = Recording.from_file(str(path))
    return {"root_alias": alias, "relative_path": relative, "channels": len(recording.channel_ids),
            "sample_rate": recording.sampling_rate, "num_frames": recording.num_samples,
            "duration": round(recording.duration, 6), "sha256": sha256_file(path)}


def artifact(name, kind, path, count):
    return {"name": name, "kind": kind, "root_alias": ROOT_ALIAS,
            "relative_path": f"{ROOT_PREFIX}/{path.relative_to(ROOT).as_posix()}",
            "expected_bytes": path.stat().st_size, "sha256": sha256_file(path),
            "metadata": {"record_count": count}}


def build(args):
    plan = json.loads((VERSION_DIR / "selection.json").read_text())
    labels = {}
    for line in (VERSION_DIR / "labels.jsonl").read_text().splitlines():
        row = json.loads(line)
        labels[row["key"]] = row
    kept, rejected = {}, []
    for language, items in plan.items():
        rows = []
        for item in items:
            labelled = labels.get(item["key"])
            if labelled is None:
                raise SystemExit(f"not labelled yet: {item['key']}; run label first")
            error = label_error(item["text"], labelled["label"], language) if labelled["label"] else None
            if error is None or error > MAX_LABEL_ERROR:
                rejected.append({"language": language, "key": item["key"], "corpus_text": item["text"],
                                 "label": labelled["label"], "label_error": None if error is None else round(error, 4)})
                continue
            if labelled.get("root_alias") == DATASET_ID:
                # Written by label as this dataset's own file; addressed through the shared data root.
                location = (ROOT_ALIAS, f"{ROOT_PREFIX}/{labelled['relative_path']}")
            else:
                location = (item["root_alias"], item["relative_path"])
            rows.append((item, labelled["label"], round(error, 4), location))
        kept[language] = rows
    write_jsonl_gz(ROOT / "rejected.jsonl.gz", rejected)
    locations = sorted({row[3] for rows in kept.values() for row in rows})
    with cf.ProcessPoolExecutor(args.workers) as pool:
        facts = dict(zip(locations, pool.map(audio_facts, locations, chunksize=64)))

    index, artifacts, splits = [], [], {}
    for language, rows in kept.items():
        records = []
        for item, text, error, location in rows:
            fact = facts[location]
            cut_id = f"{language}/{sha(item['key'])[:20]}"
            index.append({"cut_id": cut_id, **fact})
            records.append({
                "schema_version": "audio-record/1.0", "id": f"{language}:{sha(item['key'])[:20]}",
                "task": "asr", "language": language, "target": text,
                "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                    "dataset_id": DATASET_ID, "version": VERSION, "split": language,
                    "cut_id": cut_id, "duration": fact["duration"]}}],
                "hotwords": [], "labels": {"label_source": "Qwen3-ASR-1.7B", "origin": item["origin"]},
                "metadata": {"upstream_id": item["upstream_id"], "corpus_text": item["text"],
                             "label_error_vs_corpus": error},
            })
        path = VERSION_DIR / "records" / f"{language}.jsonl.gz"
        write_jsonl_gz(path, records)
        artifacts.append(artifact(f"{language}-records", "audio-records", path, len(records)))
        hours = sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600
        origins = sorted({item["origin"] for item, *_ in rows})
        splits[language] = {
            "artifacts": {"records": [f"{language}-records"], "audio_index": ["audio-index"]},
            "group": "train", "task": "asr",
            "statistics": {"records": len(records), "selected": len(plan[language]),
                           "duration_hours": round(hours, 4), "duration_basis": "sum of Lhotse recording durations"},
            "provenance": {"description": f"{NAMES[language]}：{', '.join(origins)} 训练划分抽样，"
                                          f"目标是 Qwen3-ASR-1.7B 强制 {NAMES[language]} 的转写。"},
        }
        print(json.dumps({"split": language, "records": len(records), "selected": len(plan[language]),
                          "hours": round(hours, 3)}), flush=True)
    index.sort(key=lambda row: row["cut_id"])
    index_path = VERSION_DIR / "audio-index.jsonl.gz"
    write_jsonl_gz(index_path, index)
    artifacts.insert(0, artifact("audio-index", "audio-index", index_path, len(index)))
    sources = sorted({f"{d}@{v}:{s}" for language in LHOTSE for d, v, s in LHOTSE[language]}
                     | {"mls_sidon@v0.1:train (original MLS split train; it, nl)"})
    entry = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION,
        "languages": sorted(NAMES), "tasks": ["asr"], "aliases": [], "artifacts": artifacts, "splits": splits,
        "provenance": {
            "summary": "原版 Qwen3-ASR 标注的多语种保持数据",
            "description": (
                "9 种语言（德、法、葡、意、荷、日、韩、俄、阿）的训练音频，每种抽 6,000 条 2–20 秒，"
                "目标为冻结的 Qwen3-ASR-1.7B 强制语言后的转写，用于训练时保持原版在这些语言上的能力（KL 保持）。"
                "Common Voice、MLS 引用原文件；mls_sidon 的意、荷只取原始 MLS train 划分，转成 16 kHz FLAC 存在本版本 audio/。"
                f"与语料原文的错误率超过 {MAX_LABEL_ERROR} 的条目丢弃，原文保留在 metadata.corpus_text。"
            ),
            "owner": "mingdong",
            "snapshot_date": "2026-11-24",
            "run_dir": str(ROOT),
            "source": sources,
            "method": "原版模型强制语言转写作为目标（自蒸馏），按与语料原文的错误率筛选",
            "recipe_parameters": {
                "label_model": "Qwen3-ASR-1.7B（/workspace/model/Qwen3-ASR-1.7B），vLLM 0.18.0",
                "chat_template": "amphion-eval defaults/chat-templates/qwen3-asr-force-language.jinja，chat_template_kwargs.force_language",
                "temperature": 0.0, "max_tokens": 256,
                "per_language": PER_LANGUAGE, "duration_seconds": [MIN_SECONDS, MAX_SECONDS],
                "selection": "每个来源按片段 ID 的 SHA-256 取最小的若干条",
                "max_label_error": MAX_LABEL_ERROR,
                "label_error": "两边 NFKC、去组合符号（日语除外）、小写、去非文字字符；日、韩按字，其余按词",
            },
            "known_issues": [
                "未按文本排除与公开测试集相同的句子：留到训练配置里统一做（open-audio-llm #175 decontaminate_training_data.py），直接拿来训练前要先做这一步。",
                "韩语 Common Voice 训练集只有 657 条可用，训练权重应按条数缩小。",
                "目标是原版模型的输出，包含原版自己的错误；只适合作保持目标，不适合当真值评测。",
            ],
            "license": "Common Voice CC0；MLS CC BY 4.0",
            "build_script": "scripts/retention_replay/build.py",
        },
    }
    CATALOG_FILE.write_text(
        "# 多语种保持数据（scripts/retention_replay/build.py 生成）。\n"
        + yaml.safe_dump([entry], allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    print(json.dumps({"index": len(index), "catalog": str(CATALOG_FILE)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("select")
    labelling = sub.add_parser("label")
    labelling.add_argument("--server", required=True)
    labelling.add_argument("--model", required=True)
    labelling.add_argument("--concurrency", type=int, default=96)
    building = sub.add_parser("build")
    building.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    {"select": select, "label": label, "build": build}[args.command](args)


if __name__ == "__main__":
    main()
