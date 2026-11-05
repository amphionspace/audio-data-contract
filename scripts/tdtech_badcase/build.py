#!/usr/bin/env python3
"""Build and register tdtech_badcase: recognition regressions TD-Tech reported, kept as a fixed gate.

v1-20261104 holds the ``e警保`` regression (dingqiao-ejingbao-20261102.zip): five recordings of TD-Tech's
customer (also in tdtech_customer_bench police-cmd, same sha256) and one macOS TTS clip, all reading the police
command ``e警保``. The 10.26 release (048 avg3, in use by the customer) got 6/6, the 10.28 release (054 avg3) 3/6.
Two ``asr_hotwords`` splits send the same audio with different bias lists; the hotword evaluator also scores each
record without a list, so every split reports the no-list and the with-list condition:

* ``ejingbao-builtin``: the whole shipped pool of audiollm-go main-td (builtin-hotwords-20261102.txt, 1296 terms,
  file order; ``e警保`` is line 330), as tdtech_customer_bench police-cmd-builtin;
* ``ejingbao-single``: only ``e警保``, as in TD-Tech's own check that the term reached the model;
* ``ejingbao-yijing`` (from v2-20261104): ``e警保`` and ``义警`` (lines 330 and 386 of the pool, in that order). The
  regression is known to appear when the list holds ``义警``; this is the smallest list that triggers it.
* ``ejingbao-cluster`` (from v3-20261104): ``e警保`` and every pool term of at most 3 characters holding ``警``
  (交警、协警、义警…, 44 terms, file order). Same shape as a deployed request (<= 50 terms, <= 300 characters,
  audiollm-go main.go:411-412) but dense with near-homophones; the model must still write ``e警保``.
* ``ejingbao-cluster-noterm`` (from v3-20261104): the same cluster without ``e警保``; with-list accuracy should not
  fall below the no-list condition (the confusers must not drag the output to 义警保 / 义警总).

The audio stays under ``source/v1-20261104``; later versions only add splits and point their index there.

    python scripts/tdtech_badcase/build.py --zip /home/mingdong/dingqiao-ejingbao-20261102.zip --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import soundfile as sf
import yaml

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

REPO = Path(__file__).resolve().parents[2]
DATASET_ID, VERSION, SAMPLE_RATE = "tdtech_badcase", "v3-20261104", 16000
AUDIO_VERSION = "v1-20261104"  # where the archive was unpacked
CONFUSER = "义警"  # a pool term that pulls e警保 towards 义警保 / 义警总
TERM = "e警保"
POOL = Path("/workspace/data/datasets/tdtech_customer_bench/source/audiollm-go/builtin-hotwords-20261102.txt")
POOL_SHA256 = "5ad6238e2677dfd128d2e5e3f3e8b529b0e1e12dd0d2c8dd9b86305d180ba0c1"  # SOURCE.json of that copy
# TD-Tech's README in the archive: final transcripts of the two releases they compared
REPORTED = {
    "human-dq-107bb7c75dfd0a23": ("客户 10-23 真人采集", "e警保。", "义警总。"),
    "human-dq-2a6babe0ef8bce06": ("客户 10-23 真人采集", "e警保。", "义警保。"),
    "human-dq-13603ebe8661290c": ("客户 10-23 真人采集", "e警保。", "e警保。"),
    "human-dq-59303f5ab80a9c0d": ("客户 10-23 真人采集", "e警保。", "e警保。"),
    "human-dq-776f0d8a05f1dea3": ("客户 10-23 真人采集", "e警保。", "e警保。"),
    "tts-p53": ("macOS Tingting 合成（10-14）", "e警保。", "呃警保。"),
}
SPLITS = {"ejingbao-builtin": "builtin", "ejingbao-single": "single", "ejingbao-yijing": "yijing",
          "ejingbao-cluster": "cluster", "ejingbao-cluster-noterm": "cluster-noterm"}
CLUSTER_CHAR, CLUSTER_MAX_LEN = "警", 3  # short 警 terms: the near-homophones of e警保 in the pool


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl_gz(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def builtin_pool():
    if sha256_file(POOL) != POOL_SHA256:
        raise ValueError(f"{POOL}: not the shipped pool this version is built from")
    words = [line.strip() for line in POOL.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(set(words)) != len(words) or TERM not in words or CONFUSER not in words:
        raise ValueError(f"{POOL}: duplicate terms, or {TERM} / {CONFUSER} missing")
    return words


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[DATASET_ID])
    source = data_root / "source" / AUDIO_VERSION
    if (data_root / "versions" / VERSION).exists():
        raise FileExistsError(f"refusing to replace {DATASET_ID}@{VERSION}")
    archive_sha = sha256_file(args.zip)
    if source.exists():
        recorded = json.loads((source / "SOURCE.json").read_text())["sha256"]
        if recorded != archive_sha:
            raise ValueError(f"{args.zip}: not the archive unpacked into {source}")
    else:
        source.mkdir(parents=True)
        unpack(args.zip, source, archive_sha)
    pool = builtin_pool()
    cluster = [w for w in pool if CLUSTER_CHAR in w and len(w) <= CLUSTER_MAX_LEN]
    if len(cluster) > 50 or len(",".join(cluster)) > 300:
        raise ValueError("cluster list exceeds the deployed request bound (50 terms, 300 characters)")
    lists = {"builtin": pool, "single": [TERM], "yijing": [w for w in pool if w in (TERM, CONFUSER)],
             "cluster": cluster, "cluster-noterm": [w for w in cluster if w != TERM]}
    build(args, data_root, source, archive_sha, lists)


def unpack(zip_path, source, archive_sha):
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = Path(info.filename)
            if name.parts[0] == "__MACOSX" or info.is_dir() or name.suffix not in (".wav", ".md"):
                continue
            with archive.open(info) as src, (source / name.name).open("wb") as dst:
                shutil.copyfileobj(src, dst)
    (source / "SOURCE.json").write_text(json.dumps(
        {"archive": zip_path.name, "sha256": archive_sha, "received": "2026-11-04"}, ensure_ascii=False, indent=1) + "\n")


def build(args, data_root, source, archive_sha, lists):
    index, records = [], {split: [] for split in SPLITS}
    for stem, (origin, release_1026, release_1028) in REPORTED.items():
        path = source / f"{stem}.wav"
        info = sf.info(path)
        if info.samplerate != SAMPLE_RATE or info.channels != 1:
            raise ValueError(f"{path}: expected 16 kHz mono")
        digest = sha256_file(path)
        if stem.startswith("human-dq-") and not digest.startswith(stem.removeprefix("human-dq-")):
            raise ValueError(f"{path}: name is not its sha256 prefix")
        index.append({"cut_id": stem, "root_alias": DATASET_ID, "relative_path": f"source/{AUDIO_VERSION}/{stem}.wav",
                      "sample_rate": SAMPLE_RATE, "channels": 1, "num_frames": info.frames,
                      "duration": round(info.frames / SAMPLE_RATE, 4), "sha256": digest})
        for split, list_name in SPLITS.items():
            words = lists[list_name]
            records[split].append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{split}:{stem}", "task": "asr_hotwords",
                "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                    "dataset_id": DATASET_ID, "version": VERSION, "split": split, "cut_id": stem,
                    "duration": index[-1]["duration"]}}],
                "target": TERM, "language": "zh", "hotwords": [TERM],
                "labels": {"scenario": split, "term": TERM, "origin": "tts" if stem.startswith("tts-") else "customer",
                           "hotword_list_size": len(words), "term_in_pool": TERM in words},
                "metadata": {"bias_lists": {list_name: words},
                             "distractor_kinds": {w: list_name for w in words if w != TERM},
                             "reported": {"origin": origin, "20261026 (048 avg3)": release_1026,
                                          "20261028 (054 avg3)": release_1028},
                             "source_audio_sha256": digest},
            }).to_dict())
    artifacts = []
    write_jsonl_gz(data_root / "versions" / VERSION / "audio-index.jsonl.gz", index)
    artifacts.append({"name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
                      "relative_path": f"versions/{VERSION}/audio-index.jsonl.gz",
                      "sha256": sha256_file(data_root / "versions" / VERSION / "audio-index.jsonl.gz"),
                      "metadata": {"record_count": len(index)}})
    splits = {}
    for split, rows in records.items():
        rel = f"versions/{VERSION}/records/{split}.jsonl.gz"
        write_jsonl_gz(data_root / rel, rows)
        artifacts.append({"name": f"{split}-records", "kind": "audio-records", "root_alias": DATASET_ID,
                          "relative_path": rel, "sha256": sha256_file(data_root / rel), "metadata": {"record_count": len(rows)}})
        splits[split] = {"artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]}, "task": "asr_hotwords",
                         "statistics": {"records": len(rows), "duration_hours": round(sum(e["duration"] for e in index) / 3600, 5),
                                        "duration_basis": "clip duration"},
                         "provenance": {"description": f"{TERM} 回退样本，热词表 {SPLITS[split]}（{len(lists[SPLITS[split]])} 条）"}}
    declaration = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
        "tasks": ["asr_hotwords"], "artifacts": artifacts, "splits": splits,
        "provenance": {
            "status": "complete", "synthetic": "partial",
            "summary": "鼎桥反馈的识别回退样本（e警保 × 多种热词表），仅评测",
            "description": f"鼎桥反馈的识别回退样本，作为固定守门。v1：{TERM} 6 条（5 条客户真人采集，与 tdtech_customer_bench "
                           "police-cmd 同 sha256；1 条 macOS 合成），参考一律为 e警保；客户在用的 10.26 版本（048 avg3）6/6，10.28 版本"
                           "（054 avg3）3/6。五个切分音频相同（在 source/v1-20261104），分别下发 audiollm-go 出厂内置热词表整表（1296 条）、只含 e警保 的表、"
                           "只含 e警保 与 义警 的表（v2 新增）；e警保 加词表里 44 条 3 字以内含“警”的近音词（v3 新增，规模同线上单次请求）、同一批近音词去掉 e警保（v3 新增）。只用于评测。",
            "sources": [f"{args.zip.name} (sha256 {archive_sha})",
                        "audiollm-go main-td providers/common/rag/vocabulary/builtin-hotwords-20261102.txt"],
        },
    }
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == VERSION for r in rows):
        raise FileExistsError(f"{DATASET_ID}@{VERSION} already registered")
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", DATASET_ID, VERSION, {k: len(v) for k, v in records.items()})


if __name__ == "__main__":
    main()
