"""Shared helpers for the hotword benchmark builder.

Text checks use the normalization of AmphionEval's hotword scorer
(``amphion_eval.legacy.open_audio_llm.qwen3_asr.normalize``: NFKC, lowercase,
punctuation and symbols to spaces), so "the hotword is in the reference" means
the same thing here and at scoring time. Chinese compares space-free text,
English compares whole words.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

DATA_ROOT = Path("/workspace/data")
DATASETS = DATA_ROOT / "datasets"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(
        "".join(" " if unicodedata.category(c)[0] in {"P", "S"} else c for c in text).split()
    )


def compact(text: str, language: str) -> str:
    text = normalize(text)
    return text.replace(" ", "") if language == "zh" else text


def contains(text: str, word: str, language: str) -> bool:
    text, word = compact(text, language), compact(word, language)
    if not word:
        return False
    if language == "zh":
        return word in text
    return f" {word} " in f" {text} "


def occurrences(text: str, words, language: str) -> list[str]:
    """Words found in ``text``, longest first, without overlaps (left to right per length).

    "搜狐娱乐" in the text counts once even when "搜狐" is also listed.
    """
    target = compact(text, language)
    if language != "zh":
        target = f" {target} "
    taken = [False] * len(target)
    found = []
    forms = sorted({(compact(w, language), w) for w in words if compact(w, language)},
                   key=lambda item: (-len(item[0]), item[0]))
    for form, word in forms:
        needle = form if language == "zh" else f" {form} "
        start = target.find(needle)
        while start >= 0:
            lo, hi = (start, start + len(needle)) if language == "zh" else (start + 1, start + len(needle) - 1)
            if not any(taken[lo:hi]):
                for i in range(lo, hi):
                    taken[i] = True
                found.append((lo, word))
            start = target.find(needle, start + 1)
    return [word for _, word in sorted(found)]


def order_key(seed, *parts) -> str:
    """Deterministic ordering independent of any model output."""
    return hashlib.sha256(":".join(map(str, (seed, *parts))).encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _open(path: Path, mode: str):
    return gzip.open(path, mode, encoding="utf-8") if path.suffix == ".gz" else path.open(mode, encoding="utf-8")


def read_jsonl(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with _open(path, "rt") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def iter_jsonl(path):
    with _open(Path(path), "rt") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path, rows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open(path, "wt") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def manifest_files(pattern: str) -> list[Path]:
    """``*.jsonl.gz`` files of a path relative to the datasets root (file, directory or glob)."""
    files = []
    for match in sorted(glob.glob(str(DATASETS / pattern))):
        match = Path(match)
        files.extend(sorted(match.glob("*.jsonl.gz")) if match.is_dir() else [match])
    if not files:
        raise FileNotFoundError(f"no manifest under {DATASETS / pattern}")
    return files


def iter_manifest(pattern: str):
    for path in manifest_files(pattern):
        yield from iter_jsonl(path)


class JsonlAppender:
    """Thread-safe append-only JSONL log (LLM calls, resumable stage outputs)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, row: dict) -> None:
        line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(line)


class LLM:
    """OpenAI-compatible chat client that archives every call (prompt, model, raw reply)."""

    def __init__(self, spec: dict, log: JsonlAppender, base_url: str, api_key_env: str):
        from openai import OpenAI

        self.model = spec["model"]
        self.extra_body = spec.get("extra_body") or {}
        self.temperature = spec.get("temperature")
        self.max_tokens = spec.get("max_tokens", 16000)
        self.log = log
        self.client = OpenAI(api_key=os.environ[api_key_env], base_url=base_url, timeout=600)

    def chat(self, messages: list[dict], *, tag: str, attempts: int = 4, temperature: float | None = None) -> str:
        last = None
        for attempt in range(1, attempts + 1):
            started = time.time()
            try:
                kwargs = {"model": self.model, "messages": messages,
                          "extra_body": self.extra_body, "max_tokens": self.max_tokens}
                temp = self.temperature if temperature is None else temperature
                if temp is not None:
                    kwargs["temperature"] = temp
                response = self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                text = message.content or ""
                self.log.append({
                    "tag": tag, "model": self.model, "attempt": attempt, "temperature": temp,
                    "started": started, "seconds": round(time.time() - started, 2),
                    "messages": messages, "extra_body": self.extra_body, "response": text,
                    "reasoning": getattr(message, "reasoning_content", None),
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": response.usage.model_dump() if response.usage else None,
                    "response_id": response.id,
                })
                return text
            except Exception as exc:  # noqa: BLE001 - network/API errors are retried, then raised
                last = exc
                self.log.append({"tag": tag, "model": self.model, "attempt": attempt,
                                 "started": started, "error": f"{type(exc).__name__}: {exc}"})
                time.sleep(min(60, 5 * attempt))
        raise RuntimeError(f"{self.model} failed after {attempts} attempts: {last}")


def parse_json_reply(text: str):
    """Parse the JSON value in an LLM reply (optionally inside a ```json fence)."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    body = (fence.group(1) if fence else text).strip()
    starts = [i for i in (body.find("["), body.find("{")) if i >= 0]
    if not starts:
        raise ValueError(f"no JSON in reply: {text[:120]}")
    start = min(starts)
    end = max(body.rfind("]"), body.rfind("}"))
    text = body[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # a trailing comma before ] or } is the common slip of local models
        return json.loads(re.sub(r",\s*([\]}])", r"\1", text))
