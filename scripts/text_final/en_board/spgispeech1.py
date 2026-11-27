#!/usr/bin/env python3
"""spgispeech@hf-14e69dd3b80e-s train (SPGISpeech 1.0, configuration S) as a text-final v3 training version.

open-audio-llm A line asked for it on 2026-11-27: the board's SPGISpeech test is the 1.0 test, and Musci writes the
clean (non-verbatim) style only on audio of that distribution (on SPGISpeech 2.0 audio it writes verbatim, see the
quality_status of spgispeech2@...-musci-kd-v1-20261127). The A line labels a subset with Musci for sequence KD.

build:    each parquet row (5-15 s, 16 kHz PCM16 WAV) -> <version>/audio/<call>/<n>.flac, an audio index row and one
          audio-record/1.0 record. The target is the S&P Global transcript (written form: case, punctuation and
          non-standard words already written out), with rule 2's minimal fixes only: a first lower-case letter is
          capitalised and a missing final . ? ! is added. metadata.raw_transcript keeps the transcript as given.
          Records outside 0.5-30 s are dropped (none expected).
match:    the Open ASR Leaderboard copy of the 1.0 test. Train and test calls are checked for shared call ids (the
          first part of wav_filename); records whose text contains a test utterance (shared 10-word runs, then at
          least 80% of the test utterance's words in order) carry metadata.spgispeech1_test_ids. Nothing is dropped:
          training recipes exclude marked records.
register: replaces the two placeholders in catalog/spgispeech.yaml (source snapshot and training version).

    python -I scripts/text_final/en_board/spgispeech1.py build --workers 16
    python -I scripts/text_final/en_board/spgispeech1.py match
    python -I scripts/text_final/en_board/spgispeech1.py register --catalog catalog
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    DATA,
    MAX_S,
    MIN_S,
    RUN_DIR,
    SPEC,
    artifact,
    distribution,
    index_row,
    read_jsonl,
    record,
    version_dir,
    write_jsonl_gz,
)

DS, SRC = "spgispeech", "hf-14e69dd3b80e-s"
REVISION = "14e69dd3b80e968282ca55d3eb2b39cc9db2b62e"
FINAL = "final-v3-20261127"
VER = f"{SRC}-{FINAL}"
VDIR = version_dir(DS, VER)
SOURCE = DATA / "datasets" / DS / "source" / SRC
STAGE = Path(RUN_DIR) / "spgispeech1"
TEST = (
    DATA
    / "datasets"
    / "open_asr_leaderboard"
    / "source"
    / "hf-audio__open-asr-leaderboard-de79e57adf99"
    / "spgispeech"
)
SHINGLE = 10
MARK = 0.8
SCRIPT = "scripts/text_final/en_board/spgispeech1.py"


def parts(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def written(text: str) -> str:
    t = " ".join(text.split())
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    if t and t[-1] not in ".?!":
        t += "."
    return t


def build_one(path: str) -> dict:
    import pyarrow.parquet as pq
    import soundfile as sf

    out = STAGE / "stage" / (Path(path).stem + ".jsonl.gz")
    if out.exists():
        return {"file": Path(path).name, "rows": "exists"}
    rows = []
    for batch in pq.ParquetFile(path).iter_batches(batch_size=64):
        for r in batch.to_pylist():
            name = r["wav_filename"]
            call, utt = name.split("/", 1) if "/" in name else ("", name)
            cut = name.removesuffix(".wav").replace("/", "-")
            rel = VDIR / "audio" / call / (Path(utt).stem + ".flac")
            audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="int16")
            dst = DATA / rel
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(dst.stem + ".tmp.flac")
                sf.write(tmp, audio, sr, format="FLAC", subtype="PCM_16")
                tmp.replace(dst)
            rows.append(
                {
                    "cut_id": cut,
                    "call_id": call,
                    "wav_filename": name,
                    "rel": str(rel),
                    "sample_rate": sr,
                    "channels": 1 if audio.ndim == 1 else audio.shape[1],
                    "num_frames": len(audio),
                    "transcript": r["transcript"],
                }
            )
    write_jsonl_gz(out, rows)
    return {"file": Path(path).name, "rows": len(rows)}


def build(args):
    (STAGE / "stage").mkdir(parents=True, exist_ok=True)
    files = sorted(str(p) for p in (SOURCE / "S").glob("train-*.parquet"))
    assert len(files) == 6, files
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(build_one, files):
            print(res, flush=True)


def staged():
    for p in sorted((STAGE / "stage").glob("*.jsonl.gz")):
        yield from read_jsonl(p)


def match(args):
    import pyarrow.parquet as pq

    test = []
    for p in sorted(TEST.glob("*.parquet")):
        test += pq.read_table(p, columns=["id", "text"]).to_pylist()
    test_calls = {t["id"].split("/", 1)[0] for t in test}
    words = [parts(t["text"]) for t in test]
    grams = defaultdict(set)
    for i, ws in enumerate(words):
        for k in range(len(ws) - SHINGLE + 1):
            grams[tuple(ws[k : k + SHINGLE])].add(i)
    n, out = Counter(), {}
    for r in staged():
        n["train records"] += 1
        n["train records in a test call"] += r["call_id"] in test_calls
        ws = parts(r["transcript"])
        hits = {
            i
            for k in range(len(ws) - SHINGLE + 1)
            for i in grams.get(tuple(ws[k : k + SHINGLE]), ())
        }
        for i in hits:
            sm = difflib.SequenceMatcher(None, words[i], ws, autojunk=False)
            matched = sum(b.size for b in sm.get_matching_blocks())
            if matched >= MARK * len(words[i]):
                out.setdefault(r["cut_id"], []).append(test[i]["id"])
    n["test utterances"] = len(test)
    n["test calls"] = len(test_calls)
    n["train records marked"] = len(out)
    n["test utterances matched"] = len({t for ts in out.values() for t in ts})
    (STAGE / "test-matches.json").write_text(
        json.dumps({"counts": dict(n), "matches": out}, indent=1) + "\n"
    )
    print(json.dumps(dict(n), indent=1))
    write_version(out)


def write_version(marks: dict):
    n, recs, idx, durs = Counter(), [], [], []
    for r in staged():
        dur = r["num_frames"] / r["sample_rate"]
        if not MIN_S <= dur <= MAX_S:
            n[f"dropped: duration outside {MIN_S}-{MAX_S} s"] += 1
            continue
        target = written(r["transcript"])
        n["target differs from the transcript (rule 2 fixes)"] += target != " ".join(
            r["transcript"].split()
        )
        md = {
            "call_id": r["call_id"],
            "wav_filename": r["wav_filename"],
            "raw_transcript": r["transcript"],
        }
        if r["cut_id"] in marks:
            md["spgispeech1_test_ids"] = sorted(marks[r["cut_id"]])
            n["marked: text of a board test utterance"] += 1
        recs.append(record(DS, VER, "train", r["cut_id"], 0.0, dur, target, md))
        idx.append(
            index_row(
                r["cut_id"], r["rel"], r["sample_rate"], r["channels"], r["num_frames"]
            )
        )
        durs.append(dur)
    n["records"] = len(recs)
    write_jsonl_gz(DATA / VDIR / "records" / "train.jsonl.gz", recs)
    write_jsonl_gz(DATA / VDIR / "audio_index" / "audio-index.jsonl.gz", idx)
    dist = {"train": distribution(durs)}
    (DATA / VDIR / "duration_distribution.json").write_text(
        json.dumps(dist, indent=1) + "\n"
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (DATA / VDIR / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "dataset-state/1.0",
                "dataset_id": DS,
                "version": VER,
                "state": "prepared",
                "updated_at": now,
                "error": None,
                "metadata": {
                    "stage": "built",
                    "owner": "mingdong",
                    "source": f"{DS}@{SRC}",
                    "spec": SPEC,
                    "counts": dict(n),
                    "run_dir": RUN_DIR,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    arts = [
        artifact("preparation_state", "dataset-state", VDIR / "state.json"),
        artifact(
            "train", "audio-records", VDIR / "records" / "train.jsonl.gz", len(recs)
        ),
        artifact(
            "audio_index",
            "audio-index",
            VDIR / "audio_index" / "audio-index.jsonl.gz",
            len(idx),
        ),
        artifact(
            "duration_distribution",
            "json-metadata",
            VDIR / "duration_distribution.json",
        ),
    ]
    (STAGE / "artifacts.json").write_text(
        json.dumps(
            {"artifacts": arts, "distribution": dist, "counts": dict(n)},
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(json.dumps(dict(n), indent=1))


def tree_sha256(root: Path) -> tuple[str, int, int]:
    """metadata.tree_sha256 as check-registration computes it (catalog._verify_artifact_directory): sha256 over
    "<relative path>\0<size>\0<sha256>\n" of every file, sorted by relative path. The hub's .cache must be gone."""
    assert not (root / ".cache").exists(), (
        "remove the huggingface_hub .cache directory first"
    )
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    h, total = hashlib.sha256(), 0
    for p in files:
        d = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                d.update(chunk)
        size = p.stat().st_size
        h.update(
            f"{p.relative_to(root).as_posix()}\0{size}\0{d.hexdigest()}\n".encode()
        )
        total += size
    return h.hexdigest(), len(files), total


def register(args):
    from ruamel.yaml import YAML

    built = json.loads((STAGE / "artifacts.json").read_text())
    digest, count, total = tree_sha256(SOURCE)
    state = DATA / "datasets" / DS / "versions" / SRC / "state.json"
    state.write_text(
        json.dumps(
            {
                "schema_version": "dataset-state/1.0",
                "dataset_id": DS,
                "version": SRC,
                "state": "verified",
                "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "error": None,
                "metadata": {
                    "repo": "kensho/spgispeech",
                    "revision": REVISION,
                    "files": count,
                    "bytes": total,
                    "verification_journal": "/workspace/data/staging/open-speech-20261113/spgispeech/verified.jsonl",
                },
            },
            indent=2,
        )
        + "\n"
    )
    dist = built["distribution"]["train"]
    lic = ["other (Kensho SPGISpeech terms; gated)"]
    source = {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DS,
        "version": SRC,
        "languages": ["en"],
        "tasks": ["asr"],
        "aliases": [],
        "artifacts": [
            {
                "name": "source",
                "kind": "hf-dataset-snapshot",
                "root_alias": "aidc_data",
                "relative_path": f"datasets/{DS}/source/{SRC}",
                "metadata": {
                    "file_count": count,
                    "expected_bytes": total,
                    "tree_sha256": digest,
                },
            },
            artifact(
                "download_state",
                "dataset-state",
                Path("datasets") / DS / "versions" / SRC / "state.json",
            ),
        ],
        "splits": {
            "train": {
                "artifacts": {"source": ["source"]},
                "statistics": {
                    "count": built["counts"]["records"],
                    "duration_basis": "sum of WAV durations",
                },
            }
        },
        "provenance": {
            "owner": "mingdong",
            "summary": "SPGISpeech 1.0 S train 原始下载",
            "source": "Hugging Face",
            "source_id": "kensho/spgispeech",
            "revision": REVISION,
            "url": "https://huggingface.co/datasets/kensho/spgispeech",
            "paper": "https://arxiv.org/abs/2104.02014",
            "license": lic,
            "description": (
                "Kensho（S&P Global）SPGISpeech 1.0 的 S 配置 train：2007–2020 年上市公司财报电话会议切成 5–15 秒的单人片段，"
                f"{dist['count']:,} 段、{dist['hours']:.1f} 小时，16 kHz 单声道。转写是 S&P Global 的专业转写，按编辑规范写成书面形式"
                "（大小写、标点、非标准词书面化），口吃和语气词大多删掉。数据有访问门控，用户 2026-11-27 用 HF 账号接受了条款："
                "仅限非商业研究，不得再分发。只下载了 S 的 train（6 个 parquet）；validation、test 没下（榜单 test 在 open_asr_leaderboard 副本里）。"
            ),
            "download_scope": "SPGISpeech 1.0 configuration S, train split (S/train-0000[0-5]-of-00006.parquet), README, .gitattributes",
            "integrity": "verified",
            "local_scan_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        },
    }
    c = built["counts"]
    training = {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DS,
        "version": VER,
        "languages": ["en"],
        "tasks": ["asr"],
        "aliases": [],
        "derived_from": f"{DS}@{SRC}",
        "artifacts": built["artifacts"],
        "splits": {
            "train": {
                "group": "train",
                "artifacts": {
                    "records": ["train"],
                    "audio_index": ["audio_index"],
                    "preparation_state": ["preparation_state"],
                },
                "statistics": {
                    "records": dist["count"],
                    "duration_hours": dist["hours"],
                    "duration_basis": "sum of record durations",
                    "languages": {"en": dist["count"]},
                    "spgispeech1_test_marked": c.get(
                        "marked: text of a board test utterance", 0
                    ),
                },
            }
        },
        "recipe_parameters": {
            "spec": SPEC,
            "duration_seconds": [MIN_S, MAX_S],
            "text": "transcript 原样，按规则 2 只补句首大写和句末标点；原文在 metadata.raw_transcript",
            "board_test": f"与 Open ASR 榜单 SPGISpeech test 比：同一会议编号，以及按 {SHINGLE} 词片段比文本、test 句子 {int(MARK * 100)}% 以上的词按序出现时记入 metadata.spgispeech1_test_ids（不删）",
            "audio_policy": "parquet 里的 WAV 转成 <version>/audio/<call>/<n>.flac（16 kHz 单声道 PCM16），整段引用",
            "counts": c,
            "duration_distribution": built["distribution"],
        },
        "provenance": {
            "owner": "mingdong",
            "summary": "SPGISpeech 1.0 S train 训练文本终版",
            "snapshot_date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "description": (
                f"{DS}@{SRC} 的 train 按训练文本规范 v3 建的训练版本，供 open-audio-llm A 线（英文榜单版）用 Musci 做序列级蒸馏，"
                "学榜单 SPGISpeech test 的整理稿写法（Musci 在 SPGISpeech 2.0 音频上按逐字写，只在与 test 同分布的 1.0 音频上按整理稿写）。"
                "目标是 S&P Global 转写原文（规则 2 只补句首大写和句末标点）。与榜单 test 句子文本近乎相同的记录在 metadata.spgispeech1_test_ids 标出，"
                "训练配方按它排除。Kensho 条款：仅限非商业研究。"
            ),
            "source": f"{DS}@{SRC}",
            "license": lic,
            "method": "text-final-v3",
            "requested_by": "open-audio-llm A 线（open-audio-llm-45 会话，2026-11-27）",
            "record_correction": (
                "2026-11-27 登记（PR #315）后修正：记录时长原来四舍五入到毫秒，553 条比音频长不到 1 个采样点，"
                "其中 95 条在 Musci 打标时报 Audio slice exceeds duration；改为向下取整到毫秒，只改了 records 和 "
                "state.json（Lance 记录索引随之重建），文本、音频、音频清单和时长统计不变。原 records sha256 "
                "f61c18b1d6d7d4b07e04649c4b7a32cb5453206c1bddbd75003d11cc36d7e294（8,469,161 字节）。"
            ),
            "run_dir": RUN_DIR,
            "build_script": SCRIPT,
        },
    }
    path = args.catalog / "spgispeech.yaml"
    head = "".join(
        line for line in path.read_text().splitlines(True) if line.startswith("#")
    ).replace("占位登记：", "")
    head = head.replace("构建中，进度见状态文件。", f"生成脚本 {SCRIPT}。")
    yaml = YAML()
    yaml.width = 4096
    with path.open("w") as w:
        w.write(head)
        yaml.dump([source, training], w)
    print("registered", f"{DS}@{SRC}", f"{DS}@{VER}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--workers", type=int, default=16)
    sub.add_parser("match")
    r = sub.add_parser("register")
    r.add_argument("--catalog", type=Path, required=True)
    args = ap.parse_args()
    {"build": build, "match": match, "register": register}[args.cmd](args)


if __name__ == "__main__":
    main()
