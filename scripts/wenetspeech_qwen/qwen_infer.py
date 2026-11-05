"""Transcribe WenetSpeech dialect train audio with Qwen3-ASR-1.7B on an OpenAI-compatible vLLM service.

The label sets wenetspeech_chuan@qwen3-asr-full-v1-20261023, wenetspeech_yue@clean-qwen3-asr-full-v1-20261024,
wenetspeech_yue@nonclean-qwen3-asr-full-v1-20261025 and wenetspeech_wu@qwen3-asr-pilot-v1-20261025 were produced with
this request: chat completion with one audio_url part, temperature 0, max_tokens 2048, repetition_penalty 1.1, and
to_language zh for Sichuanese / Wu (Cantonese: language auto, no to_language; same settings that measured Qwen at
12.1 / 21.1 CER on WSC-Eval and 6.2 on WSYue-ASR-eval short). Audio is read straight out of the source tars at the
byte range in each row's `dd` command (each member is a 16 kHz PCM WAV).

Rows are appended to OUT as {id, duration, hypothesis, raw} or {id, duration, error}; rerunning skips ids that
already have a hypothesis, so errors are retried. Audio over about 157 s is refused by the service.

    python scripts/wenetspeech_qwen/qwen_infer.py --format cuts CUTS.jsonl.gz OUT.jsonl --to-language zh
    python scripts/wenetspeech_qwen/qwen_infer.py --format recordings RECORDINGS.jsonl.gz OUT.jsonl
"""

import argparse
import base64
import gzip
import json
import os
import random
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from openai import OpenAI

DD = re.compile(r"dd if=(\S+) iflag=skip_bytes,count_bytes skip=(\d+) count=(\d+)")
ASR_TEXT = "<asr_text>"
PILOT_SEED = 42
IN_FLIGHT_PER_WORKER = 4


def read_tasks(path, kind):
    tasks = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            recording = row["recording"] if kind == "cuts" else row
            path_, skip, count = DD.match(recording["sources"][0]["source"]).groups()
            tasks.append((row["id"], path_, int(skip), int(count), row["duration"]))
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--format", choices=["cuts", "recordings"], required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8003/v1")
    parser.add_argument("--model", default="Qwen/Qwen3-ASR-1.7B")
    parser.add_argument("--to-language", help="sent as to_language; omitted = language auto")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--sample", type=int, help=f"seed-{PILOT_SEED} random subset (pilot)")
    args = parser.parse_args()

    client = OpenAI(base_url=args.base_url, api_key="x", timeout=600, max_retries=0)
    extra = {"repetition_penalty": 1.1}
    if args.to_language:
        extra["to_language"] = args.to_language
    tasks = read_tasks(args.source, args.format)
    if args.sample:
        tasks = random.Random(PILOT_SEED).sample(tasks, args.sample)
    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as stream:
            done = {r["id"] for r in map(json.loads, stream) if "hypothesis" in r}
    tasks = sorted((t for t in tasks if t[0] not in done), key=lambda t: (t[1], t[2]))
    print(f"{len(done)} done, {len(tasks)} to transcribe ({sum(t[4] for t in tasks) / 3600:.1f} h)", flush=True)

    fds, lock = {}, threading.Lock()

    def run(task):
        row_id, path, skip, count, duration = task
        try:
            with lock:
                fd = fds.get(path) or fds.setdefault(path, os.open(path, os.O_RDONLY))
            wav = os.pread(fd, count, skip)
            if len(wav) != count or wav[:4] != b"RIFF":
                raise ValueError(f"bad audio bytes at {path}:{skip}+{count}")
            audio = "data:audio/wav;base64," + base64.b64encode(wav).decode()
            reply = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": [{"type": "audio_url", "audio_url": {"url": audio}}]}],
                temperature=0, max_tokens=2048, extra_body=extra)
            raw = (reply.choices[0].message.content or "").strip()
            hypothesis = raw.split(ASR_TEXT, 1)[1].strip() if ASR_TEXT in raw else raw
            return {"id": row_id, "duration": duration, "hypothesis": hypothesis, "raw": raw}
        except Exception as error:  # noqa: BLE001 - any failure is recorded and retried on the next run
            return {"id": row_id, "duration": duration, "error": repr(error)[:300]}

    count = errors = 0
    hours = 0.0
    started = time.time()
    with open(args.out, "a", encoding="utf-8") as sink, ThreadPoolExecutor(args.workers) as pool:
        pending, remaining = set(), iter(tasks)
        while True:
            while len(pending) < args.workers * IN_FLIGHT_PER_WORKER:
                task = next(remaining, None)
                if task is None:
                    break
                pending.add(pool.submit(run, task))
            if not pending:
                break
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                result = future.result()
                sink.write(json.dumps(result, ensure_ascii=False) + "\n")
                count += 1
                errors += "error" in result
                hours += result["duration"] / 3600
                if count % 5000 == 0 or count == len(tasks):
                    sink.flush()
                    elapsed = time.time() - started
                    print(f"{time.strftime('%m-%d %H:%M:%S')} {count}/{len(tasks)} errors {errors} {hours:.1f} h "
                          f"{count / elapsed:.1f} utt/s {hours * 3600 / elapsed:.0f}x realtime", flush=True)
    print("finished", count, "errors", errors, flush=True)


if __name__ == "__main__":
    main()
