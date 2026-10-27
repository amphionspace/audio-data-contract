#!/usr/bin/env python3
"""Run Xiaomi-CocktailASR-1 (a third-party target-speaker ASR) on the benchmark records.

CocktailASR has no vLLM support, so this follows the official inference: ``model(target, ref)`` through
transformers with ``trust_remote_code``, bf16, greedy. The model's own feature extractor lays out
``peak_normalize(ref cut to 1-4 s) + 1 s silence + peak_normalize(target)``; it cuts a reference longer
than 4 s at a random point, so the random generator is seeded per record to make a run reproducible.
The output has the layout ``analyze.py`` reads (``predictions.jsonl`` with ``id`` and ``prediction``).

Under AmphionEval it runs as a ``--worker-command`` (``worker`` subcommand): the request audio is the
enrollment (the eval set's ``enroll_seconds``, 3 s unless set; pass the same ``--enroll-seconds``) followed by
the mixture, split back there, and ``--gpus`` shards the requests over GPUs. With ``--cot`` the model writes
``<think>...</think><answer>...</answer>`` and only the answer is kept.

    python scripts/ts_benchmark/cocktail.py jobs --dataset ts_asr_benchmark --version v3-20261013 \
        --per-split 40 --roots roots.json --output jobs.jsonl
    CUDA_VISIBLE_DEVICES=0 python scripts/ts_benchmark/cocktail.py run --jobs jobs.jsonl \
        --shard 0 --shards 3 --output run-cocktail
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MODEL = "/workspace/model/Xiaomi-CocktailASR-1"
ENROLL_SECONDS = 3  # AmphionEval's default TS-ASR enrollment length (eval sets may set enroll_seconds)
SAMPLE_RATE = 16000


def make_jobs(args):
    roots = json.loads(args.roots.read_text())
    root = Path(roots[args.dataset])
    index = {}
    with gzip.open(root / "versions" / args.version / "audio-index.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            index[row["cut_id"]] = root / row["relative_path"]
    count = 0
    with args.output.open("w", encoding="utf-8") as out:
        for path in sorted((root / "versions" / args.version / "records").glob("*.jsonl.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for position, line in enumerate(stream):
                    if position >= args.per_split:
                        break
                    record = json.loads(line)
                    enroll, mix = (index[s["ref"]["cut_id"]] for s in record["audio_slots"])
                    out.write(json.dumps({"id": record["id"], "enroll": str(enroll), "mix": str(mix),
                                          "reference": record["target"]}, ensure_ascii=False) + "\n")
                    count += 1
    print(f"{count} jobs -> {args.output}")


def load_model():
    import torch
    from transformers import AutoModel

    model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, dtype=torch.bfloat16).cuda().eval()
    # The feature extractor module draws the reference crop from its own `random`.
    return model, sys.modules[type(model._feature_extractor).__module__].random


def transcribe(model, extractor_random, sample_id, mix, enroll, args):
    import random

    extractor_random.seed(int(hashlib.sha256(sample_id.encode()).hexdigest()[:8], 16))
    random.seed(0)
    return model(mix, enroll, cot=args.cot, max_new_tokens=args.max_new_tokens)


def final_text(output, cot):
    """The transcript in the model output; with CoT only the <answer> part."""
    if not cot:
        return output
    # No <answer> means the reasoning ran out of tokens: the model gave no transcript.
    answer = re.search(r"<answer>(.*?)(?:</answer>|$)", output, re.DOTALL)
    return answer.group(1).strip() if answer else ""


def run(args):
    import soundfile as sf

    jobs = [json.loads(line) for line in args.jobs.read_text(encoding="utf-8").splitlines() if line.strip()]
    jobs = [job for i, job in enumerate(jobs) if i % args.shards == args.shard]
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / f"predictions-{args.shard}.jsonl"
    done = {json.loads(line)["id"] for line in target.read_text().splitlines()} if target.exists() else set()
    started = time.time()
    model, extractor_random = load_model()
    print(f"loaded in {time.time() - started:.0f}s; {len(jobs) - len(done)} jobs", flush=True)
    with target.open("a", encoding="utf-8") as out:
        for n, job in enumerate(jobs):
            if job["id"] in done:
                continue
            try:
                # Arrays, not paths: torchaudio.load needs torchcodec in recent torch versions.
                mix, enroll = (sf.read(job[k], dtype="float32")[0] for k in ("mix", "enroll"))
                text, error = final_text(transcribe(model, extractor_random, job["id"], mix, enroll, args),
                                         args.cot), None
            except Exception as exc:  # noqa: BLE001 - recorded, the run continues
                text, error = "", f"{type(exc).__name__}: {exc}"
            out.write(json.dumps({"id": job["id"], "prediction": text, "reference": job["reference"],
                                  "error": error}, ensure_ascii=False) + "\n")
            out.flush()
            if n % 50 == 0:
                print(f"{n}/{len(jobs)} {time.time() - started:.0f}s", flush=True)


def worker(args):
    """AmphionEval worker: one process per GPU, each takes every ``len(gpus)``-th request."""
    gpus = args.gpus.split(",")
    if args.shard is None:
        children = [
            subprocess.Popen([sys.executable, *sys.argv, "--shard", str(i)],
                             env={**os.environ, "CUDA_VISIBLE_DEVICES": gpu})
            for i, gpu in enumerate(gpus)
        ]
        codes = [child.wait() for child in children]
        with args.output.open("w", encoding="utf-8") as out:
            for i in range(len(gpus)):
                part = Path(f"{args.output}.{i}")
                if part.exists():
                    out.write(part.read_text(encoding="utf-8"))
                    part.unlink()
        sys.exit(max(codes))
    import soundfile as sf

    requests = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    model, extractor_random = load_model()
    cut = round(args.enroll_seconds * SAMPLE_RATE)
    with Path(f"{args.output}.{args.shard}").open("w", encoding="utf-8") as out:
        for request in requests[args.shard::len(gpus)]:
            started = time.time()
            try:
                audio, rate = sf.read(request["audio"], dtype="float32")
                assert rate == SAMPLE_RATE, rate
                output = transcribe(model, extractor_random, request["id"], audio[cut:], audio[:cut], args)
                # The full CoT output stays in the worker file for auditing; ae scores "text" only.
                result = {"status": "success", "text": final_text(output, args.cot),
                          **({"cot_output": output} if args.cot else {})}
            except Exception as exc:  # noqa: BLE001 - reported per sample
                result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            out.write(json.dumps({"id": request["id"], **result,
                                  "elapsed_seconds": round(time.time() - started, 3)}, ensure_ascii=False) + "\n")
            out.flush()


def merge(args):
    rows = []
    for path in sorted(args.output.glob("predictions-*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    (args.output / "predictions.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    errors = sum(bool(r["error"]) for r in rows)
    print(f"{len(rows)} predictions, {errors} errors -> {args.output / 'predictions.jsonl'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("jobs")
    p.add_argument("--dataset", default="ts_asr_benchmark")
    p.add_argument("--version", required=True)
    p.add_argument("--per-split", type=int, default=40)
    p.add_argument("--roots", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=make_jobs)
    p = sub.add_parser("run")
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cot", action="store_true")
    p.add_argument("--max-new-tokens", type=int, default=None)
    p.set_defaults(func=run)
    p = sub.add_parser("worker")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--gpus", default="0")
    p.add_argument("--shard", type=int)
    p.add_argument("--enroll-seconds", type=float, default=ENROLL_SECONDS)
    p.add_argument("--cot", action="store_true")
    p.add_argument("--max-new-tokens", type=int, default=None)
    p.set_defaults(func=worker)
    p = sub.add_parser("merge")
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=merge)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
