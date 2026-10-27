"""Shared helpers for the context-correction benchmark builder.

Item text carries inline markup written by the generator LLM:

- ``[[T:gold|alt]]`` the tested word; ``alt`` is the homophone written the other way.
- ``[[D:...]]`` the context that decides the spelling (description, cue).
- ``[[P:...]]`` a word holding the common homophone that must stay unchanged.

Removing the markup gives the read-aloud text. Scoring works on these segments.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

MARKUP = re.compile(r"\[\[([TDP]):([^\[\]]*?)\]\]")
ROLES = {"T": "target", "D": "evidence", "P": "protected"}


class MarkupError(ValueError):
    pass


def parse_markup(marked: str) -> list[dict]:
    """Split marked text into ``{text, role[, alt]}`` segments (role ``None`` = plain)."""
    segments, cursor = [], 0
    for match in MARKUP.finditer(marked):
        if match.start() > cursor:
            segments.append({"text": marked[cursor:match.start()], "role": None})
        kind, body = match.group(1), match.group(2)
        if kind == "T":
            gold, sep, alt = body.partition("|")
            if not sep or not gold or not alt or "|" in alt:
                raise MarkupError(f"target needs gold|alt: {match.group(0)}")
            segments.append({"text": gold, "role": "target", "alt": alt})
        else:
            if not body:
                raise MarkupError(f"empty span: {match.group(0)}")
            segments.append({"text": body, "role": ROLES[kind]})
        cursor = match.end()
    if cursor < len(marked):
        segments.append({"text": marked[cursor:], "role": None})
    plain = "".join(s["text"] for s in segments)
    if "[[" in plain or "]]" in plain:
        raise MarkupError(f"unbalanced markup: {marked}")
    return segments


def plain_text(segments: list[dict]) -> str:
    return "".join(s["text"] for s in segments)


def alt_text(segments: list[dict]) -> str:
    """The text with every target written the other way."""
    return "".join(s.get("alt", s["text"]) if s["role"] == "target" else s["text"] for s in segments)


def han_count(text: str) -> int:
    return sum(1 for ch in text if "一" <= ch <= "鿿")


_PINYIN_LOCK = threading.Lock()


def tone_pinyin(word: str) -> list[str]:
    """Tone-numbered pinyin of a word (pypinyin's default reading in context)."""
    from pypinyin import Style, lazy_pinyin

    with _PINYIN_LOCK:  # pypinyin's phrase segmenter is not documented as thread-safe
        return lazy_pinyin(word, style=Style.TONE3, neutral_tone_with_five=True)


def same_sound(gold: str, alt: str) -> bool:
    return gold != alt and tone_pinyin(gold) == tone_pinyin(alt)


def sha1(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


class JsonlAppender:
    """Thread-safe append-only JSONL log (LLM calls, resumable stage outputs)."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def chat(self, messages: list[dict], *, tag: str, attempts: int = 4) -> str:
        last = None
        for attempt in range(1, attempts + 1):
            started = time.time()
            try:
                kwargs = {"model": self.model, "messages": messages,
                          "extra_body": self.extra_body, "max_tokens": self.max_tokens}
                if self.temperature is not None:
                    kwargs["temperature"] = self.temperature
                response = self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                text = message.content or ""
                self.log.append({
                    "tag": tag, "model": self.model, "attempt": attempt,
                    "started": started, "seconds": round(time.time() - started, 2),
                    "messages": messages, "extra_body": self.extra_body,
                    "response": text,
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
    return json.loads(body[start:end + 1])
