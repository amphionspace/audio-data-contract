#!/usr/bin/env python3
"""Label hotwords with amphiondata's extraction prompt on local vLLM servers, then a second review pass.

usage: label_hotwords.py IN_JSONL OUT_JSONL PORT[,PORT...] --prompts AMPHIONDATA/src/amphiondata/llm/prompts.py
                         [--model NAME] [--no-review] [--batch N] [--workers N]
Used for the hotword versions registered by register_hotwords.py (model qwen3.8-27b on vLLM 0.18, --no-review
--batch 12) and for the ts_asr_hotwords eval labels (review on, one text per request).
IN rows: {id, text, language}. OUT rows: {id, text, language, extracted, hotwords, review}; resumable (skips ids
already in OUT). Extraction = amphiondata PROMPTS["extract_hotword"] (the prompt `amphion-data hotwords` uses);
a word must occur verbatim in the text. Review = a second request that keeps only words matching the same
definition. Thinking is off (Qwen3.x chat template), temperature 0.
"""
import argparse
import importlib.util
import itertools
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

REVIEW = """You review hotwords extracted from one ASR transcript. A hotword is a proper noun or domain term that an
ASR system could mis-transcribe from pronunciation alone: personal names, specific (not world-famous) places,
organizations/brands/teams, technical, legal or scientific terms. Common nouns, verbs, adjectives, numbers, time
expressions, pronouns, fillers, single characters, and the most common countries/capitals are NOT hotwords.
Given the transcript and candidates, return JSON {"hotwords": [...]} with the candidates that are genuine hotwords,
unchanged and in the given order. Return {"hotwords": []} if none qualify."""


def extract_prompt(path):
    """amphiondata's extraction prompt; the module alone, since importing the package pulls its client dependencies."""
    spec = importlib.util.spec_from_file_location("amphiondata_prompts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PROMPTS["extract_hotword"]


def parse(content):
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    try:
        words = json.loads(content).get("hotwords", [])
    except (json.JSONDecodeError, AttributeError):
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            words = json.loads(content[start:end + 1]).get("hotwords", [])
        except (json.JSONDecodeError, AttributeError):
            return None
    return [w.strip() for w in words if isinstance(w, str) and w.strip()]


def ask(client, model, system, user):
    for _ in range(3):
        response = client.chat.completions.create(
            model=model, temperature=0, max_tokens=512,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        words = parse(response.choices[0].message.content)
        if words is not None:
            return words
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inp")
    parser.add_argument("out")
    parser.add_argument("ports")
    parser.add_argument("--prompts", required=True, help="amphiondata src/amphiondata/llm/prompts.py")
    parser.add_argument("--model", default="qwen3.8-27b")
    parser.add_argument("--no-review", action="store_true")
    parser.add_argument("--workers", type=int, default=96)
    parser.add_argument("--batch", type=int, default=1,
                        help="texts per extraction request (no review); a batch that does not parse falls back to one text per request")
    args = parser.parse_args()
    extract = extract_prompt(args.prompts)
    done = set()
    if Path(args.out).exists():
        with open(args.out) as stream:
            done = {json.loads(line)["id"] for line in stream if line.strip()}
    with open(args.inp) as stream:
        rows = [json.loads(line) for line in stream]
    rows = [r for r in rows if r["id"] not in done]
    clients = itertools.cycle([OpenAI(base_url=f"http://127.0.0.1:{p}/v1", api_key="EMPTY", timeout=600)
                               for p in args.ports.split(",")])
    lock = threading.Lock()
    print(f"{len(done)} done, {len(rows)} to label", flush=True)

    def one(row):
        with lock:
            client = next(clients)
        text = row["text"]
        extracted = ask(client, args.model, extract, text)
        valid = [w for w in dict.fromkeys(extracted or []) if w in text and len(w.replace(" ", "")) >= 2]
        review = None
        if valid and not args.no_review:
            kept = ask(client, args.model, REVIEW,
                       json.dumps({"transcript": text, "candidates": valid}, ensure_ascii=False))
            review = [w for w in (kept or []) if w in valid] if kept is not None else None
        hotwords = valid if args.no_review or review is None else review
        return {**row, "extracted": extracted, "hotwords": hotwords, "review": review}

    def batch(group):
        with lock:
            client = next(clients)
        user = ("Extract hotwords from each numbered text separately. Return one JSON object whose keys are the "
                "numbers and whose values are the hotword lists, e.g. {\"1\": [...], \"2\": []}.\n"
                + "\n".join(f"{k}. {r['text']}" for k, r in enumerate(group, 1)))
        got = None
        for _ in range(2):
            response = client.chat.completions.create(
                model=args.model, temperature=0, max_tokens=64 * len(group) + 64,
                messages=[{"role": "system", "content": extract}, {"role": "user", "content": user}],
                extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            content = (response.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.strip("`").removeprefix("json").strip()
            try:
                value = json.loads(content[content.find("{"):content.rfind("}") + 1])
                if isinstance(value, dict) and all(str(k) in value for k in range(1, len(group) + 1)):
                    got = value
                    break
            except json.JSONDecodeError:
                pass
        if got is None:
            return [one({**r}) for r in group]
        out = []
        for k, r in enumerate(group, 1):
            words = got[str(k)] if isinstance(got[str(k)], list) else []
            words = [w.strip() for w in words if isinstance(w, str) and w.strip()]
            valid = [w for w in dict.fromkeys(words) if w in r["text"] and len(w.replace(" ", "")) >= 2]
            out.append({**r, "extracted": words, "hotwords": valid, "review": None})
        return out

    count = 0
    step = max(args.batch, 1)
    groups = [rows[i:i + step] for i in range(0, len(rows), step)]
    work = batch if step > 1 else (lambda g: [one(g[0])])
    with ThreadPoolExecutor(args.workers) as pool, open(args.out, "a") as f:
        for b0 in range(0, len(groups), 20000):  # bounded number of futures
            for results in pool.map(work, groups[b0:b0 + 20000]):
                for result in results:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 5000 == 0:
                        f.flush()
                        print(f"{count}/{len(rows)}", flush=True)
    print("done", count, flush=True)


if __name__ == "__main__":
    main()
