#!/usr/bin/env python3
"""voxpopuli_en@hf-42f01879c780 train as a text-final v3 training version.

extract: write each parquet row's wav bytes unchanged to <version>/audio/<year>/<id>.wav (":" in ids becomes "-") and
         stage the row fields to <run_dir>/voxpopuli/stage/*.jsonl.gz; rows with an empty raw_text also go to
         <run_dir>/voxpopuli/punc-input.jsonl for the en-v1 student (label = normalized_text).
finalize: target = raw_text with the rule-2 fixes below; empty raw_text rows take the student output on
          normalized_text (amphiondata written_punctuation_en.written_text). Keeps 0.5-30 s.

raw_text fixes (no word changes): an em dash after a letter or digit is a hyphen ("trust—building"), other em dashes
become a comma; a ' with no letter on either side is a quote mark and is removed; a word-final ' after a letter other
than s is a closing quote whose opening quote the source already lost ("the word dignity'") and is removed, also in the
normalized_text label and the student output; the first letter is capitalized; a trailing , ; : becomes . and a missing
final mark becomes . (rule 2: every utterance ends in . ? !).

    python -I scripts/text_final/en_board/voxpopuli.py extract --workers 8 --amphiondata <repo>
    python -I scripts/text_final/en_board/voxpopuli.py finalize --punc <student output jsonl> --amphiondata <repo>
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    DATA,
    FINAL,
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

DS, SRC = "voxpopuli_en", "hf-42f01879c780"
VER = f"{SRC}-{FINAL}"
VDIR = version_dir(DS, VER)
PARQUET = DATA / "datasets" / DS / "source" / SRC / "en"
STAGE = Path(RUN_DIR) / "voxpopuli"
# a word-final ' after s may be a plural possessive ("workers' rights") and is kept
CLOSING_QUOTE = re.compile(r"(?<=[^\W\d_sS])'(?![^\W\d_])")
COLS = ["audio_id", "audio", "raw_text", "normalized_text", "gender", "speaker_id", "is_gold_transcript", "accent"]


def extract_one(path: str) -> dict:
    import pyarrow.parquet as pq
    import soundfile as sf

    out = STAGE / "stage" / (Path(path).stem + ".jsonl.gz")
    n = 0
    with gzip.open(out.with_suffix(".tmp"), "wt") as w:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=256, columns=COLS):
            for r in batch.to_pylist():
                cut = r["audio_id"].replace(":", "-")
                rel = VDIR / "audio" / cut[:4] / f"{cut}.wav"
                data = r["audio"]["bytes"]
                dst = DATA / rel
                if not dst.exists() or dst.stat().st_size != len(data):
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.with_suffix(".tmp").write_bytes(data)
                    dst.with_suffix(".tmp").replace(dst)
                info = sf.info(io.BytesIO(data))
                sr, ch, frames = info.samplerate, info.channels, info.frames
                del r["audio"]
                r.update(cut_id=cut, rel=str(rel), sample_rate=sr, channels=ch, num_frames=frames)
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    out.with_suffix(".tmp").replace(out)
    return {"file": Path(path).name, "rows": n}


def fix_raw(text: str, n: Counter) -> str:
    s = " ".join(text.split())
    t = re.sub(r"(?<=[^\W_])—", "-", s)
    n["em dash after a word -> hyphen"] += t.count("-") - s.count("-")
    s, t = t, re.sub(r"\s*—\s*", ", ", t)
    n["other em dash -> comma"] += s != t
    s, t = t, re.sub(r"(?<![^\W\d_])'(?![^\W\d_])", "", t)
    n["quote mark ' removed"] += s != t
    s, t = t, CLOSING_QUOTE.sub("", t)
    n["closing quote ' after a word (not s) removed"] += s != t
    s = re.sub(r"\s+([,.?!;:])", r"\1", " ".join(t.split()))
    s = re.sub(r",\s*([.?!;:])", r"\1", s)
    if s[:1].islower():
        s = s[0].upper() + s[1:]
        n["first letter capitalized"] += 1
    if s[-1:] in ",;:":
        s = s[:-1] + "."
        n["final , ; : -> ."] += 1
    elif s[-1:] not in ".?!":
        s += "."
        n["final . added"] += 1
    return s


def extract(args):
    sys.path.insert(0, str(Path(args.amphiondata) / "src"))
    from amphiondata.enrichment.written_punctuation_en import normalize_label

    (STAGE / "stage").mkdir(parents=True, exist_ok=True)
    files = sorted(str(p) for p in PARQUET.glob("train-*.parquet"))
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(extract_one, files):
            print(res, flush=True)
    with (STAGE / "punc-input.jsonl").open("w") as w:
        for p in sorted((STAGE / "stage").glob("*.jsonl.gz")):
            for r in read_jsonl(p):
                if not r["raw_text"].strip() and r["normalized_text"].strip():
                    label = normalize_label(r["normalized_text"])
                    w.write(json.dumps({"id": r["cut_id"], "source": DS, "label": label}, ensure_ascii=False) + "\n")


def finalize(args):
    sys.path.insert(0, str(Path(args.amphiondata) / "src"))
    from amphiondata.enrichment.written_punctuation_en import (
        normalize_label,
        written_text,
    )

    punc = {r["id"]: r["text"] for r in read_jsonl(args.punc)}
    n, records, index, durs = Counter(), [], [], []
    for p in sorted((STAGE / "stage").glob("*.jsonl.gz")):
        for r in read_jsonl(p):
            n["source rows"] += 1
            dur = r["num_frames"] / r["sample_rate"]
            index.append(index_row(r["cut_id"], r["rel"], r["sample_rate"], r["channels"], r["num_frames"]))
            if not (MIN_S <= dur <= MAX_S):
                n[f"dropped: duration outside {MIN_S}-{MAX_S} s"] += 1
                continue
            raw = r["raw_text"].strip()
            if raw:
                target, src = fix_raw(raw, n), "raw_text"
            else:
                label = CLOSING_QUOTE.sub("", normalize_label(r["normalized_text"]))
                if not re.search(r"[a-z]", label):
                    n["dropped: raw_text and normalized_text empty"] += 1
                    continue
                out = punc.get(r["cut_id"])
                target, src = written_text(label, out and CLOSING_QUOTE.sub("", out), n), "normalized_text+en-v1"
                n["empty raw_text: normalized_text punctuated by the en-v1 student"] += 1
            meta = {"source_record_id": r["audio_id"], "speaker_id": r["speaker_id"], "gender": r["gender"],
                    "accent": r["accent"], "text_source": src}
            records.append(record(DS, VER, "train", r["cut_id"], 0.0, dur, target, meta))
            durs.append(dur)
    rec_rel, idx_rel = VDIR / "records" / "train.jsonl.gz", VDIR / "audio_index" / "audio-index.jsonl.gz"
    write_jsonl_gz(DATA / rec_rel, records)
    write_jsonl_gz(DATA / idx_rel, sorted(index, key=lambda x: x["cut_id"]))
    dist = {"train": distribution(durs)}
    (DATA / VDIR / "duration_distribution.json").write_text(json.dumps(dist, indent=2) + "\n")
    counts = dict(sorted(n.items()))
    print(json.dumps(counts, ensure_ascii=False, indent=1))
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (DATA / VDIR / "state.json").write_text(json.dumps({
        "schema_version": "dataset-state/1.0", "dataset_id": DS, "version": VER, "state": "prepared", "updated_at": now,
        "error": None, "metadata": {"stage": "built", "owner": "mingdong", "source": f"{DS}@{SRC}", "spec": SPEC,
                                    "counts": counts, "run_dir": RUN_DIR}}, ensure_ascii=False, indent=2) + "\n")
    arts = [artifact("preparation_state", "dataset-state", VDIR / "state.json"),
            artifact("train", "audio-records", rec_rel, len(records)),
            artifact("audio_index", "audio-index", idx_rel, len(index)),
            artifact("duration_distribution", "statistics", VDIR / "duration_distribution.json")]
    (STAGE / "artifacts.json").write_text(json.dumps({"artifacts": arts, "counts": counts, "distribution": dist},
                                                     ensure_ascii=False, indent=1) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--workers", type=int, default=8)
    e.add_argument("--amphiondata", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--punc", required=True)
    f.add_argument("--amphiondata", required=True)
    args = ap.parse_args()
    {"extract": extract, "finalize": finalize}[args.cmd](args)


if __name__ == "__main__":
    main()
