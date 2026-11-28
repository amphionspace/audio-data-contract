#!/usr/bin/env python3
"""ami_ihm@hf-edinburghcstr-20261023 train as a text-final v3 training version.

extract: write each train parquet row's wav bytes unchanged to <version>/audio/<meeting>/<audio_id>.wav and stage the
         row fields to <run_dir>/ami_ihm/stage/*.jsonl.gz; every row's label (the Kaldi upper-case text lowercased,
         marks stripped: written_punctuation_en.normalize_label) goes to <run_dir>/ami_ihm/punc-input.jsonl.
finalize: target = the en-v1 student's punctuation and casing on the label (rule 2; written_text keeps every word, so
          repetitions and fillers stay); keeps 0.5-30 s. dev and test meetings are not in train (Kaldi split).

    python -I scripts/text_final/en_board/ami_ihm.py extract --workers 8 --amphiondata <repo>
    python -I scripts/text_final/en_board/ami_ihm.py finalize --punc <student output jsonl> --amphiondata <repo>
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

DS, SRC = "ami_ihm", "hf-edinburghcstr-20261023"
VER = f"{SRC}-{FINAL}"
VDIR = version_dir(DS, VER)
PARQUET = DATA / "datasets" / DS / "source" / SRC / "ihm"
STAGE = Path(RUN_DIR) / "ami_ihm"
COLS = ["meeting_id", "audio_id", "text", "audio", "begin_time", "end_time", "microphone_id", "speaker_id"]


def extract_one(path: str) -> dict:
    import pyarrow.parquet as pq
    import soundfile as sf

    out = STAGE / "stage" / (Path(path).stem + ".jsonl.gz")
    n = 0
    with gzip.open(out.with_suffix(".tmp"), "wt") as w:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=256, columns=COLS):
            for r in batch.to_pylist():
                cut = r["audio_id"]
                rel = VDIR / "audio" / r["meeting_id"] / f"{cut}.wav"
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
                label = normalize_label(r["text"])
                if re.search(r"[a-z]", label):
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
            label = normalize_label(r["text"])
            if not re.search(r"[a-z]", label):
                n["dropped: no word in the label"] += 1
                continue
            target = written_text(label, punc.get(r["cut_id"]), n)
            meta = {"source_record_id": r["audio_id"], "meeting_id": r["meeting_id"], "speaker_id": r["speaker_id"],
                    "microphone_id": r["microphone_id"], "begin_time": r["begin_time"], "end_time": r["end_time"],
                    "source_text": r["text"]}
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
