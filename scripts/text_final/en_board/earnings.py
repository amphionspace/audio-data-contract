#!/usr/bin/env python3
"""Earnings-22 (train/dev) and Earnings-21 (test) cut into <= 30 s utterances as text-final v3 versions.

transcode: each media file -> <version>/audio/<file id>.flac, 16 kHz mono PCM16 (ffmpeg); records point into it.
segment:   words, speakers, case and punctuation come from transcripts/nlp_references (the written reference); times
           come from an aligned .nlp table: Earnings-22's transcripts/force_aligned_nlp_references, or --aligned <dir>
           for Earnings-21 (its references have no times). The force-aligned table replaces each tagged entity (a run
           of tokens with one tag id, e.g. MTN, 2019, 31st) by its spoken form (M T N, twenty nineteen, thirty first)
           and <inaudible> by "inaudible", so the two tables are matched unit by unit (difflib, tagged units keyed by
           class) and a reference unit takes the times of its aligned unit when every aligned word has one; unmatched
           units count as unaligned. The target is the reference tokens with their punctuation (rule 2).

Cutting rules (a segment is one speaker's consecutive words):
- a segment starts and ends on a word with a timestamp; up to MAX_GAP_WORDS unaligned words in a row may sit
  inside it, a longer unaligned run is dropped together with the segment around it ending there;
- tags such as <inaudible>, <unk>, <crosstalk>, <affirmative>, <foreign> end the segment and are dropped; <laugh>
  and <silence> are dropped from the text only;
- a pause of PAUSE_S or more ends the segment; otherwise the segment ends at a sentence end once it is longer than
  a per-segment target drawn from TARGET_S (seeded by file), and before it would pass MAX_S at the last sentence
  end, else comma, else word;
- a segment whose padded window overlaps an aligned word of any other segment or speaker is dropped (cross-talk);
- meetings with FILE_MAX_UNALIGNED or more words without times are skipped, and segments whose whisper-large-v3
  transcript is far from the text (--reject from whisper_qc.py) are dropped: misplaced times of the few aligned
  words in badly aligned stretches give short texts on long audio (Earnings-22). Earnings-21 is aligned by
  earnings21_align.py instead and its test segments are all kept, with their whisper WER in metadata (--wer): about
  a third to a half of its WER > 0.5 segments are whisper's errors, and a test set must not be chosen by one ASR;
- the text gets a capital first letter and ends in . ? or ! (a trailing , … - becomes .); … - – inside become ,;
  fillers (uh, um) and repetitions stay as transcribed.

    python -I scripts/text_final/en_board/earnings.py transcode --ds earnings22 --workers 8
    python -I scripts/text_final/en_board/earnings.py segment --ds earnings22 [--reject <whisper_qc.py output>]
    python -I scripts/text_final/en_board/earnings.py segment --ds earnings21 --aligned <dir> [--wer <all WERs>]
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import random
import re
import subprocess
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
    record,
    version_dir,
    write_jsonl_gz,
)

SRC = "github-c05ab6fd8b4b"
# Open ASR Leaderboard Earnings-22 test meetings: never in this version
BOARD_TEST = {"4468919", "4471586", "4474955", "4475604", "4482968", "4483046"}
# one well-aligned, short meeting per accent group: Spanish/Portuguese, Asian, English, Other Romance
E22_DEV = {"4469528", "4481221", "4483668", "4482110"}
SKIP = {"<laugh>", "<silence>"}  # every other <...> tag ends the segment
MAX_GAP_WORDS = 2
PAUSE_S = 2.0
TARGET_S = (4.0, 25.0)
PAD_S = 0.15
# a meeting where this share of reference words has no time is skipped: its few aligned words are often misplaced
FILE_MAX_UNALIGNED = 0.4


def src_dir(ds):
    return DATA / "datasets" / ds / "source" / SRC / ds


def ver(ds):
    return f"{SRC}-{FINAL}"


def media(ds) -> dict[str, Path]:
    return {p.stem: p for p in sorted((src_dir(ds) / "media").iterdir()) if p.suffix in {".mp3", ".wav", ".flac"}}


def flac_rel(ds, fid) -> Path:
    return version_dir(ds, ver(ds)) / "audio" / f"{fid}.flac"


def transcode_one(job):
    ds, fid, path = job
    dst = DATA / flac_rel(ds, fid)
    if dst.exists():
        return fid, "exists"
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".tmp.flac")
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-ac", "1",
                    "-ar", "16000", "-sample_fmt", "s16", str(tmp)], check=True)
    tmp.replace(dst)
    return fid, "done"


def transcode(args):
    ids = sorted(set(media(args.ds)) - BOARD_TEST) if args.ds == "earnings22" else sorted(media(args.ds))
    jobs = [(args.ds, fid, media(args.ds)[fid]) for fid in ids]
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(transcode_one, jobs):
            print(*res, flush=True)


def read_nlp(path: Path) -> list[dict]:
    rows = list(csv.reader(path.open(encoding="utf-8"), delimiter="|", quoting=csv.QUOTE_NONE))
    return [dict(zip(rows[0], r, strict=False)) for r in rows[1:]]


def nlp_units(rows: list[dict]) -> list[tuple[str | None, list[dict]]]:
    """Single untagged tokens, or runs of consecutive tokens with the same tags (one entity)."""
    out = []
    for r in rows:
        tag = r["tags"] if r["tags"] not in ("", "[]") else None
        if tag and out and out[-1][0] == tag:
            out[-1][1].append(r)
        else:
            out.append((tag, [r]))
    return out


def unit_key(u) -> str:
    return re.sub(r"\d+:", "", u[0]) if u[0] else u[1][0]["token"].lower()


def read_tokens(ref: Path, aligned: Path, n: Counter) -> list[dict]:
    """One token per reference unit: written words + final punctuation, speaker, and aligned times (or None)."""
    O, A = nlp_units(read_nlp(ref)), nlp_units(read_nlp(aligned))
    times: dict[int, tuple[float, float]] = {}
    sm = difflib.SequenceMatcher(None, [unit_key(u) for u in O], [unit_key(u) for u in A], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            n["reference units without an aligned match"] += i2 - i1
            continue
        for i, j in zip(range(i1, i2), range(j1, j2), strict=True):
            ts = [r.get("ts", "") for r in A[j][1]]
            te = [r.get("endTs", "") for r in A[j][1]]
            if all(ts) and all(te):
                times[i] = (float(ts[0]), float(te[-1]))
    out = []
    for i, (_, rows) in enumerate(O):
        words = " ".join(r["token"] + (r["punctuation"] if k < len(rows) - 1 else "") for k, r in enumerate(rows))
        ts, te = times.get(i, (None, None))
        out.append({"w": words, "spk": rows[0]["speaker"], "p": rows[-1]["punctuation"], "ts": ts, "te": te})
    return out


def units(tokens, n: Counter):
    """Runs of one speaker's tokens that start and end aligned, with short unaligned gaps only."""
    cur: list[int] = []
    gap: list[int] = []

    def close():
        if cur:
            yield cur[:]
        cur.clear()
        gap.clear()

    for i, t in enumerate(tokens):
        if t["w"] in SKIP:
            continue
        if t["w"].startswith("<") and t["w"].endswith(">"):
            n[f"break token {t['w']}"] += 1
            yield from close()
            continue
        if cur and t["spk"] != tokens[cur[0]]["spk"]:
            yield from close()
        if t["ts"] is None:
            if cur:
                gap.append(i)
                if len(gap) > MAX_GAP_WORDS:
                    n["unaligned run longer than 2 words: cut"] += 1
                    yield from close()
            n["unaligned words"] += 1
            continue
        if cur and tokens[cur[-1]]["te"] is not None and t["ts"] - tokens[cur[-1]]["te"] >= PAUSE_S:
            yield from close()
        cur.extend(gap)
        gap.clear()
        cur.append(i)
    yield from close()


def split_unit(tokens, idx, rng, n: Counter):
    """Cut one unit into segments of at most MAX_S that start and end on aligned words."""
    aligned = [k for k, i in enumerate(idx) if tokens[i]["ts"] is not None]
    out, a = [], 0
    while a < len(aligned):
        t0, target = tokens[idx[aligned[a]]]["ts"], rng.uniform(*TARGET_S)
        best = end = None  # best: (rank, b), rank 3 sentence end, 2 comma, 1 any aligned word
        b = a
        while b < len(aligned):
            t = tokens[idx[aligned[b]]]
            if t["te"] - t0 > MAX_S:
                break
            rank = 3 if t["p"] in {".", "?", "!"} else 2 if t["p"] in {",", ";", ":", "…", "-", "–"} else 1
            if best is None or rank >= best[0]:
                best = (rank, b)
            if rank == 3 and t["te"] - t0 >= target:
                end = b
                break
            b += 1
        if end is None:
            if b == len(aligned):
                end = b - 1  # the rest of the unit fits
            elif best is not None:
                end = best[1]
            else:
                n["first word ends past 30 s"] += 1
                end = a
        out.append(idx[aligned[a] : aligned[end] + 1])
        a = end + 1
    return out


def render(words: list[dict]) -> str:
    parts = []
    for j, t in enumerate(words):
        p = t["p"]
        if p in {"…", "-", "–"}:
            p = ","
        if j == len(words) - 1:
            p = p if p in {".", "?", "!"} else "."
        parts.append(t["w"] + p)
    s = " ".join(parts)
    return s[0].upper() + s[1:] if s[:1].islower() else s


def segment(args):
    ds = args.ds
    V = ver(ds)
    vdir = version_dir(ds, V)
    aligned_dir = Path(args.aligned) if args.aligned else src_dir(ds) / "transcripts" / "force_aligned_nlp_references"
    meta = {}
    mfile = src_dir(ds) / ("metadata.csv" if ds == "earnings22" else "earnings21-file-metadata.csv")
    for r in csv.DictReader(mfile.open(encoding="utf-8")):
        meta[str(r.get("File ID") or r.get("file_id") or next(iter(r.values())))] = r
    import soundfile as sf

    n, recs, index, durs, skipped = Counter(), {}, [], {}, []
    reject = json.loads(Path(args.reject).read_text()) if args.reject else {}
    wer = json.loads(Path(args.wer).read_text()) if args.wer else {}
    for path in sorted(aligned_dir.glob("*.nlp")):
        fid = path.name.split(".")[0]
        if ds == "earnings22" and fid in BOARD_TEST:
            n["board test meetings excluded"] += 1
            continue
        split = ("dev" if fid in E22_DEV else "train") if ds == "earnings22" else "test"
        info = sf.info(str(DATA / flac_rel(ds, fid)))
        index.append(index_row(fid, flac_rel(ds, fid), info.samplerate, info.channels, info.frames))
        total = info.frames / info.samplerate
        tokens = read_tokens(src_dir(ds) / "transcripts" / "nlp_references" / f"{fid}.nlp", path, n)
        share = sum(t["ts"] is None for t in tokens) / len(tokens)
        if share >= FILE_MAX_UNALIGNED:
            n[f"meetings skipped: >= {FILE_MAX_UNALIGNED:.0%} of words without times"] += 1
            skipped.append(fid)
            continue
        rng = random.Random(f"{ds}:{fid}")
        segs = [s for u in units(tokens, n) for s in split_unit(tokens, u, rng, n)]
        spans = sorted((t["ts"], t["te"], i) for i, t in enumerate(tokens) if t["ts"] is not None)
        for k, seg in enumerate(segs):
            words = [tokens[i] for i in seg if tokens[i]["w"] not in SKIP]
            first, last = tokens[seg[0]], tokens[seg[-1]]
            prev_end = max((te for ts, te, i in spans if i < seg[0] and te <= first["ts"]), default=0.0)
            next_start = min((ts for ts, te, i in spans if i > seg[-1] and ts >= last["te"]), default=total)
            start = max(0.0, first["ts"] - min(PAD_S, (first["ts"] - prev_end) / 2))
            end = min(total, last["te"] + min(PAD_S, (next_start - last["te"]) / 2))
            inside = set(seg)
            if any(ts < end and te > start and i not in inside for ts, te, i in spans):
                n["dropped: window overlaps other words (cross-talk)"] += 1
                continue
            dur = end - start
            if not (MIN_S <= dur <= MAX_S):
                n[f"dropped: duration outside {MIN_S}-{MAX_S} s"] += 1
                continue
            if f"{split}:{fid}-{k:05d}" in reject:
                n["dropped: whisper-large-v3 WER > 0.5 (whisper_qc.py)"] += 1
                continue
            m = meta.get(fid, {})
            md = {"meeting_id": fid, "speaker": first["spk"], "start": round(start, 3), "end": round(end, 3),
                  "unaligned_words": sum(tokens[i]["ts"] is None for i in seg)}
            if wer:
                md["whisper_wer"] = wer[f"{split}:{fid}-{k:05d}"]
            if ds == "earnings22":
                md.update(country=m.get("Country by Ticker"), language_family=m.get("Language Family + Area Based"))
            recs.setdefault(split, []).append(record(ds, V, split, fid, start, dur, render(words), md,
                                                     rid=f"{fid}-{k:05d}"))
            durs.setdefault(split, []).append(dur)
            n[f"{split} segments"] += 1
    arts = [artifact("preparation_state", "dataset-state", vdir / "state.json")]
    idx_rel = vdir / "audio_index" / "audio-index.jsonl.gz"
    write_jsonl_gz(DATA / idx_rel, sorted(index, key=lambda x: x["cut_id"]))
    for split in sorted(recs):
        rel = vdir / "records" / f"{split}.jsonl.gz"
        write_jsonl_gz(DATA / rel, recs[split])
        arts.append(artifact(split, "audio-records", rel, len(recs[split])))
    arts.append(artifact("audio_index", "audio-index", idx_rel, len(index)))
    dist = {s: distribution(d) for s, d in sorted(durs.items())}
    (DATA / vdir / "duration_distribution.json").write_text(json.dumps(dist, indent=2) + "\n")
    arts.append(artifact("duration_distribution", "statistics", vdir / "duration_distribution.json"))
    counts = dict(sorted(n.items()))
    print(json.dumps(counts, ensure_ascii=False, indent=1), json.dumps(dist, indent=1))
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (DATA / vdir / "state.json").write_text(json.dumps({
        "schema_version": "dataset-state/1.0", "dataset_id": ds, "version": V, "state": "prepared", "updated_at": now,
        "error": None, "metadata": {"stage": "built", "owner": "mingdong", "source": f"{ds}@{SRC}", "spec": SPEC,
                                    "counts": counts, "run_dir": RUN_DIR}}, ensure_ascii=False, indent=2) + "\n")
    arts[0] = artifact("preparation_state", "dataset-state", vdir / "state.json")
    out = Path(RUN_DIR) / ds
    out.mkdir(parents=True, exist_ok=True)
    (out / "artifacts.json").write_text(json.dumps({"artifacts": arts, "counts": counts, "distribution": dist,
                                                    "skipped_meetings": skipped},
                                                   ensure_ascii=False, indent=1) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transcode")
    t.add_argument("--ds", required=True, choices=["earnings22", "earnings21"])
    t.add_argument("--workers", type=int, default=8)
    s = sub.add_parser("segment")
    s.add_argument("--ds", required=True, choices=["earnings22", "earnings21"])
    s.add_argument("--aligned", help="aligned .nlp directory (Earnings-21)")
    s.add_argument("--reject", help="whisper_qc.py output: record ids to drop")
    s.add_argument("--wer", help="whisper_qc.py output with --max-wer -1: every record's WER, kept as metadata.whisper_wer")
    args = ap.parse_args()
    {"transcode": transcode, "segment": segment}[args.cmd](args)


if __name__ == "__main__":
    main()
