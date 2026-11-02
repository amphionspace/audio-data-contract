#!/usr/bin/env python3
"""Ask a served base Qwen3-ASR what it hears on rendered distant-talk clips; also writes FireRed worker requests.

Labels must not come from the model being trained (that would be circular), so the two judges are the unmodified
Qwen3-ASR-1.7B and FireRedASR2-AED. FireRed runs through its AmphionEval worker on the requests written here.

    python scripts/ts_robust/label_distant_talk_pool.py --version V --ports 18391 18392 [--workers 16]

Writes source/V/labels/firered-N/requests.jsonl (one directory per FireRed worker, which keeps its files beside its
output) and source/V/labels/qwen3.jsonl (appends; skips ids already answered). With --requests-only, stops after the
requests, so FireRed can start while the base model answers.
"""

import argparse
import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import soundfile as sf

DATA = Path("/workspace/data")
SOURCE = DATA / "datasets/asr_distant_talk_pool/source"
MODEL = "Qwen/Qwen3-ASR-1.7B"
MAX_TOKENS = 512


def ask(port, audio):
    wav = io.BytesIO()  # the server's input_audio takes wav, not flac
    sf.write(wav, *sf.read(audio, dtype="float32"), format="WAV", subtype="PCM_16")
    body = {"model": MODEL, "temperature": 0, "max_tokens": MAX_TOKENS, "messages": [
        {"role": "system", "content": ""},
        {"role": "user", "content": [{"type": "input_audio", "input_audio": {
            "data": base64.b64encode(wav.getvalue()).decode(), "format": "wav"}}]}]}
    response = requests.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=body, timeout=600)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"] or ""
    return content.partition("<asr_text>")[2] if "<asr_text>" in content else content


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--ports", type=int, nargs="*", default=[])
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--firered-shards", type=int, default=1)
    parser.add_argument("--requests-only", action="store_true")
    args = parser.parse_args()
    root = SOURCE / args.version
    rows = [json.loads(line) for line in (root / "manifest.jsonl").read_text().splitlines()]
    labels = root / "labels"
    labels.mkdir(exist_ok=True)
    for shard in range(args.firered_shards):
        directory = labels / f"firered-{shard}"
        directory.mkdir(exist_ok=True)
        with (directory / "requests.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows[shard::args.firered_shards]:
                stream.write(json.dumps({"id": row["id"], "task": "asr", "audio": str(DATA / row["path"]),
                                         "context": {}}, ensure_ascii=False) + "\n")
    if args.requests_only:
        return
    out = labels / "qwen3.jsonl"
    done = {json.loads(line)["id"] for line in out.read_text().splitlines()} if out.exists() else set()
    todo = [row for row in rows if row["id"] not in done]
    with out.open("a", encoding="utf-8") as stream, ThreadPoolExecutor(args.workers) as pool:
        ports = [args.ports[i % len(args.ports)] for i in range(len(todo))]
        for row, text in zip(todo, pool.map(lambda r, port: ask(port, DATA / r["path"]), todo, ports)):
            stream.write(json.dumps({"id": row["id"], "text": text}, ensure_ascii=False) + "\n")
            stream.flush()
    print("answered", len(todo), "of", len(rows), flush=True)


if __name__ == "__main__":
    main()
