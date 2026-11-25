#!/usr/bin/env python3
"""Word times for Earnings-21 references (its nlp_references have none), written as aligned .nlp tables for
``earnings.py segment --ds earnings21 --aligned <dir>``.

asr:   whisper-large-v3 (vLLM server) text for each 30 s window of a meeting, timed by Qwen3-ForcedAligner on that
       window -> <out>/whisper/<fid>.json (words cut by a window edge just fail to match below).
align: the reference words are matched to the whisper words (difflib on lowercase alphanumerics, e.g. COVID-19 ->
       covid19, 50% -> 50). Matches inside runs of at least ANCHOR_RUN consecutive equal words are anchors. The
       meeting is cut at anchor gaps (the middle of the silence between two anchored words) into chunks of at most
       CHUNK_MAX_S, or up to CHUNK_LONG_S where no gap is in reach, and each chunk's reference words are force-aligned
       to its audio with Qwen3-ForcedAligner, which gives every word a time. Whisper only places the chunk borders, so
       which words get times does not depend on whether whisper recognised them. Tags (<inaudible>, <crosstalk>, ...)
       and tokens without letters or digits get no time; a longer stretch with no anchor gap is left without times.

    python -I scripts/text_final/en_board/earnings21_align.py asr --out <run_dir>/earnings21 --port <whisper port>
    python -I scripts/text_final/en_board/earnings21_align.py align --out <run_dir>/earnings21
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA
from earnings import flac_rel, read_nlp, src_dir

DS = "earnings21"
WINDOW_S = 30.0
ALIGNER = "/workspace/model/Qwen3-ForcedAligner-0.6B"
ANCHOR_RUN = 3
MIN_GAP_S = 0.15  # cut only where whisper has at least this much silence between the two anchored words
CHUNK_MAX_S = 60.0
CHUNK_LONG_S = 180.0  # a stretch with no anchor gap within CHUNK_MAX_S is still aligned up to this length


def key(word: str) -> str:
    return re.sub(r"[^0-9a-z]", "", word.lower())


def asr(args):
    """Whisper text per WINDOW_S window (vLLM server on --port), timed by force-aligning that text to the window."""
    import io
    from concurrent.futures import ThreadPoolExecutor

    import soundfile as sf
    import torch
    from openai import OpenAI
    from qwen_asr import Qwen3ForcedAligner

    client = OpenAI(base_url=f"http://127.0.0.1:{args.port}/v1", api_key="x", timeout=300)
    model = Qwen3ForcedAligner.from_pretrained(ALIGNER, dtype=torch.bfloat16, device_map="cuda:0",
                                               attn_implementation="sdpa")
    out = Path(args.out) / "whisper"
    out.mkdir(parents=True, exist_ok=True)

    def transcribe(w):
        buf = io.BytesIO()
        sf.write(buf, w, 16000, format="WAV")
        buf.seek(0)
        return client.audio.transcriptions.create(model="whisper-large-v3", file=("a.wav", buf), language="en",
                                                  temperature=0).text.strip()

    for ref in sorted((src_dir(DS) / "transcripts" / "nlp_references").glob("*.nlp")):
        fid = ref.stem
        dst = out / f"{fid}.json"
        if dst.exists():
            continue
        audio, sr = sf.read(str(DATA / flac_rel(DS, fid)), dtype="float32")
        step = int(WINDOW_S * sr)
        wins = [audio[k:k + step] for k in range(0, len(audio), step)]
        with ThreadPoolExecutor(32) as pool:
            texts = list(pool.map(transcribe, wins))
        words = []
        todo = [k for k, t in enumerate(texts) if any(c.isalnum() for c in t) and len(wins[k]) >= sr]
        for b0 in range(0, len(todo), 16):
            ks = todo[b0:b0 + 16]
            res = model.align(audio=[(wins[k], sr) for k in ks], text=[texts[k] for k in ks],
                              language=["English"] * len(ks))
            for k, items in zip(ks, res, strict=True):
                words += [{"w": it.text, "s": k * WINDOW_S + float(it.start_time),
                           "e": k * WINDOW_S + float(it.end_time)} for it in items]
        tmp = dst.with_suffix(".tmp")
        tmp.write_text(json.dumps({"duration": len(audio) / sr, "texts": texts, "words": words},
                                  ensure_ascii=False) + "\n")
        tmp.replace(dst)
        print(fid, len(wins), len(words), flush=True)


def anchors(ref_keys, hyp, n: Counter) -> dict[int, tuple[float, float]]:
    """Reference index -> whisper (start, end) for words inside long enough equal runs."""
    hyp_keys = [key(w["w"]) for w in hyp]
    sm = difflib.SequenceMatcher(None, ref_keys, hyp_keys, autojunk=False)
    out = {}
    for b in sm.get_matching_blocks():
        n["reference words matched by whisper"] += b.size
        if b.size < ANCHOR_RUN:
            continue
        for k in range(b.size):
            w = hyp[b.b + k]
            if w["s"] is not None and w["e"] is not None:
                out[b.a + k] = (float(w["s"]), float(w["e"]))
    return out


def cut_points(anc: dict[int, tuple[float, float]]) -> list[tuple[int, float]]:
    """(first reference index after the cut, cut time) at silences between two consecutive anchored words."""
    pts = []
    for i in sorted(anc):
        if i + 1 in anc:
            gap = anc[i + 1][0] - anc[i][1]
            if gap >= MIN_GAP_S:
                pts.append((i + 1, (anc[i][1] + anc[i + 1][0]) / 2))
    return pts


def align(args):
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ForcedAligner

    model = Qwen3ForcedAligner.from_pretrained(ALIGNER, dtype=torch.bfloat16, device_map="cuda:0",
                                               attn_implementation="sdpa")
    out = Path(args.out)
    (out / "aligned").mkdir(parents=True, exist_ok=True)
    total = Counter()
    report = {}
    for ref in sorted((src_dir(DS) / "transcripts" / "nlp_references").glob("*.nlp")):
        fid = ref.stem
        n = Counter()
        rows = read_nlp(ref)
        hyp = json.loads((out / "whisper" / f"{fid}.json").read_text())
        audio, sr = sf.read(str(DATA / flac_rel(DS, fid)), dtype="float32")
        dur = len(audio) / sr
        # words the aligner can take: not a tag, has a letter or digit
        idx = [i for i, r in enumerate(rows) if not r["token"].startswith("<") and key(r["token"])]
        ref_keys = [key(rows[i]["token"]) for i in idx]
        anc = anchors(ref_keys, hyp["words"], n)
        pts = cut_points(anc)
        # greedy chunks: from the current cut, take the farthest cut point within CHUNK_MAX_S; the meeting end closes
        # the last chunk
        chunks, a, t0 = [], 0, 0.0
        j = 0
        while a < len(idx):
            best = None
            while j < len(pts) and pts[j][1] - t0 <= CHUNK_MAX_S:
                if pts[j][0] > a and pts[j][1] > t0 + 1.0:
                    best = pts[j]
                j += 1
            if dur - t0 <= CHUNK_MAX_S:
                chunks.append((a, len(idx), t0, dur, True))
                break
            if best is None:  # no anchor gap within CHUNK_MAX_S: take the next one if within CHUNK_LONG_S
                if j >= len(pts):
                    chunks.append((a, len(idx), t0, dur, dur - t0 <= CHUNK_LONG_S))
                    break
                b, t1 = pts[j]
                chunks.append((a, b, t0, t1, t1 - t0 <= CHUNK_LONG_S))
                a, t0 = b, t1
                j += 1
                continue
            b, t1 = best
            chunks.append((a, b, t0, t1, True))
            a, t0 = b, t1
        times: dict[int, tuple[float, float]] = {}
        for a, b, t0, t1, ok in chunks:
            if b <= a:
                continue
            if not ok:
                n["words in chunks without an anchor gap (no time)"] += b - a
                n["chunks without an anchor gap"] += 1
                continue
            words = [rows[i]["token"] for i in idx[a:b]]
            res = model.align(audio=[(audio[int(t0 * sr):int(t1 * sr)], sr)], text=[" ".join(words)],
                              language=["English"])[0]
            if len(res) != len(words):
                n["words in chunks where the aligner returned another word count (no time)"] += b - a
                continue
            for k, it in enumerate(res):
                times[idx[a + k]] = (t0 + float(it.start_time), t0 + float(it.end_time))
            n["chunks aligned"] += 1
            n["chunk seconds aligned"] += round(t1 - t0)
        n["reference rows"] += len(rows)
        n["alignable words"] += len(idx)
        n["words with times"] += len(times)
        header = list(rows[0].keys())
        for col in ("ts", "endTs"):
            if col not in header:
                header.insert(2, col)
        dst = out / "aligned" / f"{fid}.nlp"
        with dst.with_suffix(".tmp").open("w", encoding="utf-8") as w:
            w.write("|".join(header) + "\n")
            for i, r in enumerate(rows):
                ts, te = times.get(i, ("", ""))
                r = {**r, "ts": f"{ts:.3f}" if ts != "" else "", "endTs": f"{te:.3f}" if te != "" else ""}
                w.write("|".join(r.get(c, "") for c in header) + "\n")
        dst.with_suffix(".tmp").replace(dst)
        report[fid] = dict(n)
        total.update(n)
        print(fid, json.dumps(dict(n)), flush=True)
    (out / "align-report.json").write_text(json.dumps({"total": dict(total), "meetings": report}, indent=1) + "\n")
    print(json.dumps(dict(total), indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("asr")
    a.add_argument("--out", required=True)
    a.add_argument("--port", required=True, help="vLLM whisper-large-v3 server")
    b = sub.add_parser("align")
    b.add_argument("--out", required=True)
    args = ap.parse_args()
    {"asr": asr, "align": align}[args.cmd](args)


if __name__ == "__main__":
    main()
