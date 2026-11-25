#!/usr/bin/env python3
"""spgispeech2@hf-f4ce91de393c train/dev/test cut into <= 30 s utterances as text-final v3 versions.

extract:  each parquet row's WAV (16 kHz PCM16) -> <version>/audio/<call_id>/<snippet_id>.flac; row fields and the
          snippet's word alignment (supplemental_data/alignment_files, extracted to <run_dir>/spgispeech2) are staged
          to <run_dir>/spgispeech2/stage/*.jsonl.gz.
match-v1: SPGISpeech 1.0 test utterances (the Open ASR Leaderboard copy) whose text appears in a 2.0 snippet: shared
          10-word runs, then a difflib check that at least half of the 1.0 utterance's words match in order.
segment:  words, case and punctuation come from raw_transcript (S&P Global's professional transcript: written form,
          not verbatim, fillers and stutters mostly removed); times come from the alignment file, whose words split
          tokens at punctuation (U.S. -> U S, long-term -> long term, 1.5 -> 1 5) and drop dashes, so both sides are
          split into letter/digit parts and matched with difflib; a token is timed when all its parts match.
          Cutting follows earnings.py (one speaker, "|" turns, 2 s pause, random 4-25 s target ending at a sentence
          end, at most 30 s, padded windows), except that windows may overlap neighbouring words' alignment times and
          a segment with more than MAX_WPS words per second is dropped (see MAX_WPS). Snippets are cut out of longer calls, so a
          first word starting within EDGE_S of the audio start, or a last word of an unfinished sentence ending within
          EDGE_S of the audio end, may be clipped: it keeps its time (to bound the neighbouring window) but ends the
          segment and is left out. Records that overlap a 1.0 test utterance matched at V1_MARK or more
          carry metadata.spgispeech1_test_ids. No 2.0 call is a 1.0 test recording (at most 4 utterances of a 1.0
          call match one 2.0 call, all scripted safe-harbor or operator lines that recur across quarters); the marks
          are text overlap: the same script read in another call.

    python -I scripts/text_final/en_board/spgispeech2.py extract --workers 32
    python -I scripts/text_final/en_board/spgispeech2.py match-v1
    python -I scripts/text_final/en_board/spgispeech2.py segment
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import io
import json
import random
import re
import sys
from collections import Counter, defaultdict
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
from earnings import PAD_S, render, split_unit, units

DS, SRC = "spgispeech2", "hf-f4ce91de393c"
VER = f"{SRC}-{FINAL}"
VDIR = version_dir(DS, VER)
PARQUET = DATA / "datasets" / DS / "source" / SRC / "data"
STAGE = Path(RUN_DIR) / "spgispeech2"
V1_TEST = (DATA / "datasets" / "open_asr_leaderboard" / "source" / "hf-audio__open-asr-leaderboard-de79e57adf99"
           / "spgispeech")
EDGE_S = 0.1
SHINGLE = 10
# The alignment often gives neighbouring words overlapping or shared times, so the earnings.py rule that drops a
# window overlapping another word dropped mostly good segments here (49 of 60 sampled had whisper WER <= 0.2); it is
# not used. Where the alignment collapses, many words share a short span: more than MAX_WPS words per second marks
# such a segment (39 of 40 sampled had whisper WER > 0.5).
MAX_WPS = 8.0
V1_MARK = 0.8  # a record is marked when this share of a 1.0 test utterance's words match in order
MARKS = ".,;:?!…"
DASHES = {"-", "--", "---", "—", "–"}


def split_of(path: str) -> str:
    name = Path(path).name
    return "train" if name.startswith("train") else name.split("-")[0]


def parts(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def extract_one(path: str) -> dict:
    import pyarrow.parquet as pq
    import soundfile as sf

    out = STAGE / "stage" / (Path(path).stem + ".jsonl.gz")
    if out.exists():
        return {"file": Path(path).name, "rows": "exists"}
    n = 0
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as w:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=64):
            for r in batch.to_pylist():
                cut = f"{r['call_id']}-{r['snippet_id']}"
                rel = VDIR / "audio" / str(r["call_id"]) / f"{r['snippet_id']}.flac"
                audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="int16")
                dst = DATA / rel
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    part = dst.with_name(dst.stem + ".tmp.flac")
                    sf.write(part, audio, sr, format="FLAC", subtype="PCM_16")
                    part.replace(dst)
                al = json.loads((STAGE / r["alignment"]).read_text())
                words = [[a["word"], a["start_time"], a["end_time"], a["speaker"]]
                         for a in (al[k] for k in sorted(al, key=int))]
                w.write(json.dumps({
                    "split": split_of(path), "call_id": r["call_id"], "snippet_id": r["snippet_id"], "cut_id": cut,
                    "rel": str(rel), "sample_rate": sr, "channels": 1 if audio.ndim == 1 else audio.shape[1],
                    "num_frames": len(audio), "raw_transcript": r["raw_transcript"], "speakers": r["speakers"],
                    "words": words}, ensure_ascii=False) + "\n")
                n += 1
    tmp.replace(out)
    return {"file": Path(path).name, "rows": n}


def extract(args):
    (STAGE / "stage").mkdir(parents=True, exist_ok=True)
    files = sorted(str(p) for p in PARQUET.glob("*.parquet"))
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(extract_one, files):
            print(res, flush=True)


def staged():
    for p in sorted((STAGE / "stage").glob("*.jsonl.gz")):
        yield from read_jsonl(p)


def match_v1(args):
    import pyarrow.parquet as pq

    v1 = []
    for p in sorted(V1_TEST.glob("*.parquet")):
        v1 += pq.read_table(p, columns=["id", "text"]).to_pylist()
    v1_words = [parts(r["text"]) for r in v1]
    grams = defaultdict(set)
    for i, ws in enumerate(v1_words):
        for k in range(len(ws) - SHINGLE + 1):
            grams[tuple(ws[k:k + SHINGLE])].add(i)
    n, out = Counter(), {}
    for r in staged():
        ws = parts(" ".join(t for t in r["raw_transcript"].split() if t != "|"))
        hits = Counter()
        for k in range(len(ws) - SHINGLE + 1):
            for i in grams.get(tuple(ws[k:k + SHINGLE]), ()):
                hits[i] += 1
        n["2.0 snippets"] += 1
        for i in hits:
            sm = difflib.SequenceMatcher(None, v1_words[i], ws, autojunk=False)
            blocks = [b for b in sm.get_matching_blocks() if b.size]
            if sum(b.size for b in blocks) < 0.5 * len(v1_words[i]):
                n["candidate pairs rejected (< half of the 1.0 words)"] += 1
                continue
            out.setdefault(r["cut_id"], []).append({
                "v1_id": v1[i]["id"], "v1_words": len(v1_words[i]), "matched_words": sum(b.size for b in blocks),
                "part_span": [blocks[0].b, blocks[-1].b + blocks[-1].size], "split": r["split"]})
            n[f"matched pairs ({r['split']})"] += 1
    n["1.0 test utterances"] = len(v1)
    n["1.0 test utterances matched"] = len({m["v1_id"] for ms in out.values() for m in ms})
    (STAGE / "v1-test-matches.json").write_text(json.dumps({"counts": dict(n), "matches": out}, indent=1) + "\n")
    print(json.dumps(dict(n), indent=1))


def tokens_of(r, n: Counter) -> list[dict]:
    """Transcript tokens {w, p, spk, ts, te, parts: (first, last) part index} with alignment times."""
    toks, turn = [], 0
    raw = r["raw_transcript"].split()
    for j, tok in enumerate(raw):
        if tok == "|":
            turn += 1
            continue
        if not re.search(r"[A-Za-z0-9]", tok):
            if tok in DASHES and toks and not toks[-1]["p"]:
                toks[-1]["p"] = "-"
            elif tok not in DASHES:
                toks.append({"w": tok, "p": "", "spk": turn})
            continue
        m = re.match(rf"^(.*?)([{MARKS}]*)$", tok)
        w, marks = m.group(1), m.group(2)
        nxt = next((t for t in raw[j + 1:] if t != "|"), "")
        if marks == "." and "." in w and not nxt[:1].isupper():  # U.S. inside a sentence: the dot is the word's
            w, marks = tok, ""
        toks.append({"w": w, "p": marks[-1:] if marks else "", "spk": turn})
    ref_parts, owner = [], []
    for i, t in enumerate(toks):
        ps = parts(t["w"])
        ref_parts += ps
        owner += [i] * len(ps)
    al = r["words"]
    al_parts, al_owner = [], []
    for k, a in enumerate(al):
        ps = parts(a[0])
        al_parts += ps
        al_owner += [k] * len(ps)
    got = defaultdict(list)
    sm = difflib.SequenceMatcher(None, ref_parts, al_parts, autojunk=False)
    for b in sm.get_matching_blocks():
        for x in range(b.size):
            got[owner[b.a + x]].append(al_owner[b.b + x])
    for i, t in enumerate(toks):
        need = t["np"] = len(parts(t["w"]))
        ks = got.get(i, [])
        if need and len(ks) == need:
            t["ts"], t["te"] = float(al[ks[0]][1]), float(al[ks[-1]][2])
            if t["te"] < t["ts"]:
                t["ts"], t["te"] = None, None
        else:
            t["ts"] = t["te"] = None
            n["tokens without a time"] += bool(need)
        n["tokens"] += bool(need)
    return toks


def segment(args):
    matches = json.loads((STAGE / "v1-test-matches.json").read_text())["matches"] if args.v1 else {}
    n, recs, index, durs = Counter(), defaultdict(list), [], defaultdict(list)
    for r in staged():
        split, cut = r["split"], r["cut_id"]
        total = r["num_frames"] / r["sample_rate"]
        index.append(index_row(cut, r["rel"], r["sample_rate"], r["channels"], r["num_frames"]))
        n[f"{split} snippets"] += 1
        toks = tokens_of(r, n)
        timed = [i for i, t in enumerate(toks) if t["ts"] is not None]
        if not timed:
            n["snippets without timed words"] += 1
            continue
        offs = [0]  # letter/digit part offset of each token, to find records overlapping a matched 1.0 utterance
        for t in toks:
            offs.append(offs[-1] + t["np"])
        first, last = timed[0], timed[-1]
        if toks[first]["ts"] < EDGE_S:
            toks[first]["w"] = "<edge>"
            n["clipped first word left out"] += 1
        if toks[last]["p"] not in {".", "?", "!"} and total - toks[last]["te"] < EDGE_S:
            toks[last]["w"] = "<edge>"
            n["clipped last word left out"] += 1
        rng = random.Random(f"{DS}:{cut}")
        segs = [s for u in units(toks, n) for s in split_unit(toks, u, rng, n)]
        spans = sorted((t["ts"], t["te"], i) for i, t in enumerate(toks) if t["ts"] is not None)
        for k, seg in enumerate(segs):
            words = [toks[i] for i in seg]
            a, b = toks[seg[0]], toks[seg[-1]]
            prev_end = max((te for ts, te, i in spans if i < seg[0] and te <= a["ts"]), default=0.0)
            next_start = min((ts for ts, te, i in spans if i > seg[-1] and ts >= b["te"]), default=total)
            start = max(0.0, a["ts"] - min(PAD_S, (a["ts"] - prev_end) / 2))
            end = min(total, b["te"] + min(PAD_S, (next_start - b["te"]) / 2))
            dur = end - start
            if not (MIN_S <= dur <= MAX_S):
                n[f"dropped: duration outside {MIN_S}-{MAX_S} s"] += 1
                continue
            if sum(toks[i]["np"] > 0 for i in seg) / dur > MAX_WPS:
                n[f"dropped: more than {MAX_WPS:g} words per second (collapsed alignment)"] += 1
                continue
            rid = f"{cut}-{k:03d}"
            md = {"call_id": r["call_id"], "snippet_id": r["snippet_id"], "turn": a["spk"],
                  "start": round(start, 3), "end": round(end, 3),
                  "untimed_tokens": sum(toks[i]["ts"] is None for i in seg)}
            lo, hi = offs[seg[0]], offs[seg[-1] + 1]
            v1 = [m["v1_id"] for m in matches.get(cut, [])
                  if m["matched_words"] >= V1_MARK * m["v1_words"] and m["part_span"][0] < hi and m["part_span"][1] > lo]
            if v1:
                md["spgispeech1_test_ids"] = v1
                n[f"{split} records overlapping SPGISpeech 1.0 test"] += 1
            recs[split].append(record(DS, VER, split, cut, start, dur, render(words), md, rid=rid))
            durs[split].append(dur)
            n[f"{split} segments"] += 1
    arts = [artifact("preparation_state", "dataset-state", VDIR / "state.json")]
    idx_rel = VDIR / "audio_index" / "audio-index.jsonl.gz"
    write_jsonl_gz(DATA / idx_rel, sorted(index, key=lambda x: x["cut_id"]))
    for split in sorted(recs):
        rel = VDIR / "records" / f"{split}.jsonl.gz"
        write_jsonl_gz(DATA / rel, recs[split])
        arts.append(artifact(split, "audio-records", rel, len(recs[split])))
    arts.append(artifact("audio_index", "audio-index", idx_rel, len(index)))
    dist = {s: distribution(d) for s, d in sorted(durs.items())}
    (DATA / VDIR / "duration_distribution.json").write_text(json.dumps(dist, indent=2) + "\n")
    arts.append(artifact("duration_distribution", "statistics", VDIR / "duration_distribution.json", 1))
    counts = dict(sorted(n.items()))
    print(json.dumps(counts, ensure_ascii=False, indent=1), json.dumps(dist, indent=1))
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (DATA / VDIR / "state.json").write_text(json.dumps({
        "schema_version": "dataset-state/1.0", "dataset_id": DS, "version": VER, "state": "prepared", "updated_at": now,
        "error": None, "metadata": {"stage": "built", "owner": "mingdong", "source": f"{DS}@{SRC}", "spec": SPEC,
                                    "counts": counts, "run_dir": RUN_DIR}}, ensure_ascii=False, indent=2) + "\n")
    arts[0] = artifact("preparation_state", "dataset-state", VDIR / "state.json")
    (STAGE / "artifacts.json").write_text(json.dumps({"artifacts": arts, "counts": counts, "distribution": dist},
                                                     ensure_ascii=False, indent=1) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--workers", type=int, default=8)
    sub.add_parser("match-v1")
    s = sub.add_parser("segment")
    s.add_argument("--no-v1", dest="v1", action="store_false", help="skip the SPGISpeech 1.0 test marks")
    args = ap.parse_args()
    {"extract": extract, "match-v1": match_v1, "segment": segment}[args.cmd](args)


if __name__ == "__main__":
    main()
