#!/usr/bin/env python3
"""Build the Mandarin-English code-switch evaluation versions (eval-zhen-v1).

Five public test sets become lhotse recordings + supervisions under
<root>/datasets/<dataset_id>/versions/<version>/.  Every supervision is
labelled ``language: zh`` (scored as characters, like TALCS in asr-benchmark)
and carries ``custom.target_terms``: the English spans of its reference, which
AmphionEval scores as term hit rate.

Reference cleaning follows docs/reference/zh-en-transcription.md:
  talcs            test as is (lowercase English, no punctuation)
  cs_dialogue_mix  test: drop <FIL/> <SPK/> <NON/>; drop "**" (unintelligible)
                   and supervisions longer than 30 s (model limit)
  ascend           test, language == mixed; drop [UNK]
  wenetspeech      test_net / test_meeting supervisions with an English span
  ntuml2021        test: traditional -> simplified, drop spaces between
                   characters; audio downmixed to 16 kHz mono PCM_16

TALCS, CS-Dialogue and WenetSpeech manifests point at the registered audio;
ASCEND and ntuml2021 audio is decoded from the Parquet snapshots.

Run with an interpreter that has pyarrow, soundfile and opencc (the
amphion-eval venv does):

    python -I scripts/zh_en_codeswitch_eval/build.py --root /workspace/data \
        --summary-out /workspace/data/staging/zh-en-codeswitch-eval-20261117/build-summary.json
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import io
import json
import re
from pathlib import Path

VERSION = "eval-zhen-v1-20261117"
MAX_SECONDS = 30.0
FILLERS = {"uh", "um", "umm", "uhm", "ah", "er", "err", "erm", "hmm", "mm", "mhm", "oh", "eh"}
CJK = r"㐀-䶿一-鿿豈-﫿"
LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*(?: +[A-Za-z0-9][A-Za-z0-9'’.\-]*)*")
TAGS = re.compile(r"<(?:FIL|SPK|NON)/>")
SPACE_NEAR_CJK = re.compile(rf"(?<=[{CJK}]) +| +(?=[{CJK}])")


def target_terms(text: str, max_words: int = 3) -> list[str]:
    """English spans embedded in a Chinese sentence (1-3 words, >= 2 letters)."""
    terms = []
    for run in LATIN_RUN.findall(text):
        words = [w.strip(".-'’") for w in run.split()]
        while words and words[0].lower() in FILLERS:
            words.pop(0)
        while words and words[-1].lower() in FILLERS:
            words.pop()
        span = " ".join(w for w in words if w)
        if span and len(words) <= max_words and len(re.findall("[A-Za-z]", span)) >= 2:
            terms.append(span)
    return terms


def read_jsonl(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def write_jsonl(path: Path, rows) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for row in rows:
            gz.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
    data = buf.getvalue()
    path.write_bytes(data)
    return {"expected_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def supervision(sid, rec_id, start, duration, text, speaker=None, **custom):
    row = {"id": sid, "recording_id": rec_id, "start": start, "duration": duration,
           "channel": 0, "text": text, "language": "zh"}
    if speaker is not None:
        row["speaker"] = str(speaker)
    terms = target_terms(text)
    row["custom"] = {**custom, **({"target_terms": terms} if terms else {})}
    return row


def recording(rec_id, path, num_samples, sr=16000):
    return {"id": rec_id, "sources": [{"type": "file", "channels": [0], "source": str(path)}],
            "sampling_rate": sr, "num_samples": num_samples,
            "duration": round(num_samples / sr, 6), "channel_ids": [0]}


def lhotse_subset(rec_path, sups):
    keep = {s["recording_id"] for s in sups}
    return [r for r in read_jsonl(rec_path) if r["id"] in keep]


def build_talcs(root):
    base = root / "datasets/talcs/versions/legacy-20260804"
    sups = [supervision(s["id"], s["recording_id"], s["start"], s["duration"], s["text"],
                        s.get("speaker"))
            for s in read_jsonl(base / "test_sup_0/talcs_supervisions_test_cleaned.jsonl.gz")]
    recs = lhotse_subset(base / "test_rec_0/talcs_recordings_test.jsonl.gz", sups)
    return {"test": (recs, sups, {})}


def build_cs_dialogue_mix(root):
    base = root / "datasets/cs_dialogue_mix/versions/legacy-20260804"
    raw = read_jsonl(base / "test_sup_0/cs_dialogue_supervisions_test.mix.jsonl.gz")
    dropped = {"unintelligible": 0, "over_30s": 0}
    sups = []
    for s in raw:
        if "**" in s["text"]:
            dropped["unintelligible"] += 1
            continue
        if s["duration"] > MAX_SECONDS:
            dropped["over_30s"] += 1
            continue
        text = re.sub(r"\s+", " ", TAGS.sub(" ", s["text"])).strip()
        sups.append(supervision(s["id"], s["recording_id"], s["start"], s["duration"], text,
                                s.get("speaker"), dialog_id=s["custom"]["dialog_id"],
                                topic=s["custom"].get("topic")))
    recs = lhotse_subset(base / "test_rec_0/cs_dialogue_recordings_test.mix.jsonl.gz", sups)
    return {"test": (recs, sups, {"source_records": len(raw), "dropped": dropped})}


def decode_parquet_audio(files, out_dir, select, make_id, downmix=False):
    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        table = pq.read_table(path)
        for row in table.to_pylist():
            if not select(row):
                continue
            audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
            if audio.ndim == 2:
                if not downmix:
                    raise ValueError(f"unexpected multichannel audio in {path}")
                audio = audio.mean(axis=1)
            if sr != 16000:
                raise ValueError(f"{path}: sample rate {sr}")
            rec_id = make_id(row)
            wav = out_dir / f"{rec_id}.wav"
            sf.write(wav, np.clip(audio, -1, 1), sr, subtype="PCM_16")
            yield row, rec_id, wav, len(audio)


def build_ascend(root, out):
    files = sorted(glob.glob(str(root / "datasets/ascend/source/hf-737e9800ae31/main/test-*.parquet")))
    unk = 0
    recs, sups = [], []

    def select(row):
        nonlocal unk
        if row["language"] != "mixed":
            return False
        if "[UNK]" in row["transcription"]:
            unk += 1
            return False
        return True

    for row, rec_id, wav, n in decode_parquet_audio(
            files, out / "audio/test_mixed", select, lambda r: f"ascend_{r['id']}"):
        recs.append(recording(rec_id, wav, n))
        sups.append(supervision(rec_id, rec_id, 0.0, round(n / 16000, 6),
                                row["transcription"].strip(), row["original_speaker_id"],
                                session_id=row["session_id"], topic=row["topic"]))
    return {"test_mixed": (recs, sups, {"dropped": {"unk": unk}})}


def build_wenetspeech(root):
    base = root / "datasets/wenetspeech/source/cos-backup-20261011"
    splits = {}
    for split, tag in (("test_net", "TEST_NET"), ("test_meeting", "TEST_MEETING")):
        raw = read_jsonl(base / f"legacy_asr/LHOTSE/WenetSpeech/data/manifests/wenetspeech_supervisions_{tag}.jsonl.gz")
        sups = [supervision(s["id"], s["recording_id"], s["start"], s["duration"], s["text"])
                for s in raw if re.search(f"[{CJK}]", s["text"])]
        sups = [s for s in sups if s["custom"].get("target_terms")]
        recs = lhotse_subset(base / f"relocated/LHOTSE/WenetSpeech/data/manifests/wenetspeech_recordings_{tag}.jsonl.gz", sups)
        splits[split] = (recs, sups, {"source_records": len(raw)})
    return splits


def build_ntuml2021(root, out):
    from opencc import OpenCC

    t2s = OpenCC("t2s")
    files = sorted(glob.glob(str(root / "datasets/ntuml2021/source/hf-1e121cc419e8/data/test-*.parquet")))
    recs, sups = [], []

    def make_id(row):
        lecture, clip = Path(row["file"]).parent.name.removesuffix("-clips"), Path(row["file"]).stem
        return f"ntuml2021_{lecture}_{clip.split('-')[0]}"

    for row, rec_id, wav, n in decode_parquet_audio(
            files, out / "audio/test", lambda r: True, make_id, downmix=True):
        text = SPACE_NEAR_CJK.sub("", t2s.convert(row["transcription"]))
        text = re.sub(r" +", " ", text).strip()
        recs.append(recording(rec_id, wav, n))
        sups.append(supervision(rec_id, rec_id, 0.0, round(n / 16000, 6), text, "hylee",
                                lecture=Path(row["file"]).parent.name.removesuffix("-clips"),
                                source_file=row["file"]))
    return {"test": (recs, sups, {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("/workspace/data"))
    ap.add_argument("--summary-out", type=Path, required=True)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    builders = {
        "talcs": lambda out: build_talcs(args.root),
        "cs_dialogue_mix": lambda out: build_cs_dialogue_mix(args.root),
        "ascend": lambda out: build_ascend(args.root, out),
        "wenetspeech": lambda out: build_wenetspeech(args.root),
        "ntuml2021": lambda out: build_ntuml2021(args.root, out),
    }
    summary = {}
    for dataset_id, build in builders.items():
        if args.only and dataset_id not in args.only:
            continue
        out = args.root / "datasets" / dataset_id / "versions" / VERSION
        splits = {}
        for split, (recs, sups, notes) in build(out).items():
            recs.sort(key=lambda r: r["id"])
            sups.sort(key=lambda s: s["id"])
            rel = f"datasets/{dataset_id}/versions/{VERSION}"
            splits[split] = {
                "recordings": {"relative_path": f"{rel}/{split}_recordings.jsonl.gz",
                               **write_jsonl(out / f"{split}_recordings.jsonl.gz", recs)},
                "supervisions": {"relative_path": f"{rel}/{split}_supervisions.jsonl.gz",
                                 **write_jsonl(out / f"{split}_supervisions.jsonl.gz", sups)},
                "records": len(sups),
                "duration_hours": round(sum(s["duration"] for s in sups) / 3600, 4),
                "records_with_terms": sum(bool(s["custom"].get("target_terms")) for s in sups),
                "terms": sum(len(s["custom"].get("target_terms", [])) for s in sups),
                **notes,
            }
        summary[dataset_id] = splits
        (out / "build-summary.json").write_text(json.dumps(splits, ensure_ascii=False, indent=2) + "\n")
    args.summary_out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
