#!/usr/bin/env python3
"""Mine real recordings whose context decides how a word is written.

Stages (each resumable, outputs under ``<source>/mined/``):

- ``windows``: merge consecutive supervisions of each recording into windows of at
  most ``mining.window_seconds`` (the model sees one window per request).
- ``scan``: a local LLM (served by vLLM, OpenAI API) reads windows in batches and
  flags the ones that contain such context. No regex prefilter.
- ``label``: for each flagged window the generator LLM writes the context-correct
  transcript with markup, and the reviewer LLM independently writes its own
  context-correct transcript; only agreeing windows whose correction changes no
  sound (tone-exact pinyin) are kept. ``cot.draft`` is the corpus transcript.
- ``extract``: cut the kept windows' audio to 16 kHz wav.

    python mine.py windows --source <dir>
    python mine.py scan --source <dir> --server http://127.0.0.1:18301/v1 --served-model qwen3.6-27b
    load.sh aliyun-llm -- python mine.py label --source <dir>
    python mine.py extract --source <dir>
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts
from common import (
    LLM,
    JsonlAppender,
    MarkupError,
    alt_text,
    parse_json_reply,
    parse_markup,
    plain_text,
    read_jsonl,
    tone_pinyin,
    write_jsonl,
)

HERE = Path(__file__).resolve().parent


def gz_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def cmd_windows(recipe, source_dir, corpus):
    spec = recipe["mining"]["corpora"][corpus]
    by_recording = defaultdict(list)
    for row in gz_rows(Path(spec["supervisions"])):
        text = (row.get("text") or "").strip()
        if text:
            by_recording[row["recording_id"]].append((float(row["start"]), float(row["duration"]), row["id"], text))
    limit, gap = recipe["mining"]["window_seconds"], recipe["mining"]["max_gap_seconds"]
    windows = []
    for recording, segments in sorted(by_recording.items()):
        segments.sort()
        current = []
        for start, duration, sid, text in segments:
            if current and (start + duration - current[0][0] > limit or start - (current[-1][0] + current[-1][1]) > gap):
                windows.append((recording, current))
                current = []
            if duration <= limit:
                current.append((start, duration, sid, text))
        if current:
            windows.append((recording, current))
    out = source_dir / "mined" / corpus / "windows.jsonl.gz"
    write_jsonl(out, (
        {"window_id": f"{corpus}:{rec}:{segs[0][2].rsplit('_', 1)[-1]}", "corpus": corpus, "recording_id": rec,
         "start": round(segs[0][0], 3), "end": round(segs[-1][0] + segs[-1][1], 3),
         "segments": [s[2] for s in segs], "text": "，".join(s[3] for s in segs)}
        for rec, segs in windows))
    print(f"{corpus}: {len(by_recording)} recordings -> {len(windows)} windows -> {out}")


def cmd_scan(recipe, source_dir, corpus, server, served_model, limit, workers):
    from openai import OpenAI

    cfg = recipe["mining"]
    root = source_dir / "mined" / corpus
    windows = list(gz_rows(root / "windows.jsonl.gz"))
    hits_path = root / "scan.jsonl"
    if limit:  # hit-rate and throughput test: an evenly spaced sample across recordings, kept apart
        windows = windows[:: max(1, len(windows) // limit)][:limit]
        hits_path = root / f"scan-sample{limit}.jsonl"
    done = {row["batch"] for row in read_jsonl(hits_path)}
    batch_size = cfg["scan_batch"]
    batches = [(i // batch_size, windows[i:i + batch_size]) for i in range(0, len(windows), batch_size)]
    batches = [b for b in batches if b[0] not in done]
    client = OpenAI(base_url=server, api_key="EMPTY", timeout=600)
    sink = JsonlAppender(hits_path)

    def run(batch):
        index, rows = batch
        listing = "\n".join(f"{k + 1}. {w['text']}" for k, w in enumerate(rows))
        messages = [{"role": "system", "content": prompts.SCAN_SYSTEM},
                    {"role": "user", "content": listing}]
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=served_model, messages=messages, temperature=0.0, max_tokens=256,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}})
                reply = response.choices[0].message.content or ""
                flagged = parse_json_reply(reply)
                flagged = sorted({int(k) for k in flagged if isinstance(k, int) and 1 <= k <= len(rows)})
                return {"batch": index, "flagged": [rows[k - 1]["window_id"] for k in flagged], "reply": reply,
                        "model": served_model}
            except Exception as exc:  # noqa: BLE001 - recorded, batch retried on resume
                error = f"{type(exc).__name__}: {exc}"
        return {"batch": index, "flagged": [], "error": error, "model": served_model}

    with ThreadPoolExecutor(workers) as pool:
        for count, result in enumerate(pool.map(run, batches), 1):
            if "error" not in result:
                sink.append(result)
            if count % 200 == 0 or count == len(batches):
                print(f"[scan] {count}/{len(batches)} batches", flush=True)


def correction_issues(original: str, segments: list[dict]) -> list[str]:
    """The corrected transcript may only respell; every sound must stay the same."""
    issues = []
    corrected = plain_text(segments)
    if tone_pinyin(_han(corrected)) != tone_pinyin(_han(original)):
        issues.append("corrected transcript changes sounds, not only spellings")
    if alt_text(segments) != original:
        issues.append("markup alternatives do not reproduce the corpus transcript")
    if not any(s["role"] == "target" for s in segments):
        issues.append("no target")
    if not any(s["role"] == "evidence" for s in segments):
        issues.append("no evidence")
    return issues


def target_spans(segments: list[dict]) -> list[range]:
    """Character range of each target in the corrected transcript."""
    spans, offset = [], 0
    for segment in segments:
        if segment["role"] == "target":
            spans.append(range(offset, offset + len(segment["text"])))
        offset += len(segment["text"])
    return spans


def targets_agree(first: list[range], second: list[range]) -> bool:
    """Both labelers mark the same words: every target of each overlaps a target of the other
    (boundaries may differ, e.g. 小曹 / 图小曹; the generator's markup is kept)."""
    def covered(a, b):
        return all(any(set(x) & set(y) for y in b) for x in a)
    return bool(first) and covered(first, second) and covered(second, first)


def _han(text: str) -> str:
    return "".join(ch for ch in text if "一" <= ch <= "鿿")


def cmd_label(recipe, source_dir, corpus):
    llm_cfg = recipe["llm"]
    root = source_dir / "mined" / corpus
    flagged = {w for row in read_jsonl(root / "scan.jsonl") for w in row["flagged"]}
    windows = {w["window_id"]: w for w in gz_rows(root / "windows.jsonl.gz") if w["window_id"] in flagged}
    labels_path = root / "labels.jsonl"
    done = {row["window_id"] for row in read_jsonl(labels_path)}
    log = JsonlAppender(root / "llm-log" / "label.jsonl")
    generator = LLM(llm_cfg["generator"], log, llm_cfg["base_url"], llm_cfg["api_key_env"])
    reviewer = LLM(llm_cfg["reviewer"], log, llm_cfg["base_url"], llm_cfg["api_key_env"])
    sink = JsonlAppender(labels_path)

    def run(window):
        user = prompts.MINE_LABEL_USER.format(text=window["text"])
        messages = [{"role": "system", "content": prompts.MINE_LABEL_SYSTEM}, {"role": "user", "content": user}]
        answers = {}
        for role, client in (("generator", generator), ("reviewer", reviewer)):
            try:
                answers[role] = parse_json_reply(client.chat(messages, tag=f"{role}:{window['window_id']}"))
            except (ValueError, RuntimeError) as exc:
                answers[role] = {"error": str(exc)}
        issues, segments = [], None
        gen, rev = answers["generator"], answers["reviewer"]
        if not gen.get("keep") or not rev.get("keep"):
            issues.append(f"not kept: generator={gen.get('keep')} reviewer={rev.get('keep')}")
        else:
            try:
                segments = parse_markup(gen.get("marked") or "")
                review_segments = parse_markup(rev.get("marked") or "")
                issues += correction_issues(window["text"], segments)
                if plain_text(segments) != plain_text(review_segments):
                    issues.append("generator and reviewer corrected transcripts differ")
                elif not targets_agree(target_spans(segments), target_spans(review_segments)):
                    issues.append("generator and reviewer mark different targets")
                if gen.get("category") != rev.get("category"):
                    issues.append(f"category differs: {gen.get('category')} vs {rev.get('category')}")
            except MarkupError as exc:
                issues.append(f"markup: {exc}")
        return {"window_id": window["window_id"], "answers": answers, "issues": issues,
                "segments": segments if not issues else None}

    seen_texts = set()
    pending = []
    for window in windows.values():  # the same text (re-uploaded episodes) is labeled once
        if window["window_id"] not in done and window["text"] not in seen_texts:
            pending.append(window)
        seen_texts.add(window["text"])
    with ThreadPoolExecutor(llm_cfg["workers"]) as pool:
        for count, result in enumerate(pool.map(run, pending), 1):
            sink.append(result)
            if count % 20 == 0 or count == len(pending):
                print(f"[label] {count}/{len(pending)}", flush=True)


def cmd_extract(recipe, source_dir, corpus):
    import numpy as np
    import soundfile as sf
    import soxr

    spec = recipe["mining"]["corpora"][corpus]
    root = source_dir / "mined" / corpus
    kept = [row for row in read_jsonl(root / "labels.jsonl") if not row["issues"]]
    windows = {w["window_id"]: w for w in gz_rows(root / "windows.jsonl.gz")}
    paths = {r["id"]: r["sources"][0]["source"] for r in gz_rows(Path(spec["recordings"]))}
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    items, clips = [], []
    pad = recipe["mining"]["pad_seconds"]
    seen_spans = set()
    for row in kept:
        # a show repeating its sign-off ("我是小溪，春晓的晓") yields the same question many times: keep one
        spans = tuple((s["role"], s["text"]) for s in row["segments"] if s["role"] in ("target", "evidence"))
        if spans in seen_spans:
            continue
        seen_spans.add(spans)
        window = windows[row["window_id"]]
        gen = row["answers"]["generator"]
        with sf.SoundFile(paths[window["recording_id"]]) as stream:
            sr = stream.samplerate
            start = max(0.0, window["start"] - pad)
            stream.seek(int(start * sr))
            wav = stream.read(int((window["end"] + pad - start) * sr), dtype="float32", always_2d=True).mean(axis=1)
        if sr != 16000:
            wav = soxr.resample(wav, sr, 16000)
        item_id = "mined-" + window["window_id"].replace(":", "-")
        path = audio_dir / f"{item_id}.wav"
        sf.write(path, np.clip(wav, -1, 1), 16000, subtype="PCM_16")
        segments = row["segments"]
        evidence = "；".join(s["text"] for s in segments if s["role"] == "evidence")
        edits = [{"from": s["alt"], "to": s["text"], "evidence": evidence, "reason": gen.get("reason") or ""}
                 for s in segments if s["role"] == "target" and s["alt"] != s["text"]]
        text = plain_text(segments)
        items.append({
            "id": item_id, "pair_id": None, "category": gen.get("category"), "subtype": gen.get("subtype"),
            "kind": "mined", "position": gen.get("position"), "distance": None, "entity_type": gen.get("entity_type"),
            "scenario": corpus, "marked_text": gen["marked"], "text": text, "segments": segments,
            "reason": gen.get("reason") or "",
            "cot": {"draft": window["text"], "edits": edits, "final": text},
            "corpus_transcript": window["text"], "corpus_transcript_correct": not edits,
            "source_recording": window["recording_id"], "source_start": start,
            "source_segments": window["segments"],
        })
        clips.append({"id": item_id, "pair_id": None, "voice_id": None, "speaker": None, "path": str(path),
                      "duration": round(len(wav) / 16000, 4)})
    write_jsonl(root / "items.jsonl", items)
    write_jsonl(root / "clips.jsonl", clips)
    print(f"extracted {len(items)} windows")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["windows", "scan", "label", "extract"])
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--corpus", default="wenetspeech_podcast")
    parser.add_argument("--server", default="http://127.0.0.1:18301/v1")
    parser.add_argument("--served-model", default="qwen3.6-27b")
    parser.add_argument("--limit", type=int, default=0, help="scan an evenly spaced sample of N windows (hit-rate and throughput test)")
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    if args.stage == "windows":
        cmd_windows(recipe, args.source, args.corpus)
    elif args.stage == "scan":
        cmd_scan(recipe, args.source, args.corpus, args.server, args.served_model, args.limit, args.workers)
    elif args.stage == "label":
        cmd_label(recipe, args.source, args.corpus)
    else:
        cmd_extract(recipe, args.source, args.corpus)


if __name__ == "__main__":
    main()
