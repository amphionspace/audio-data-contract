#!/usr/bin/env python3
"""Clean zh ASR training labels where the speaker explains how a character is written.

A speaker who says "我叫刘莉，刘是文刀刘，莉是茉莉花的莉" must be transcribed the way they
explain it. Each source is processed in stages; every stage is resumable and writes
under ``<out>/<source>/`` (recipe ``clean_recipe.yaml``):

- ``units``: windows of consecutive segments of one recording, at most
  ``window_seconds`` long (same rule as ``mine.py windows``), with the segment texts.
- ``scan``: an LLM reads the windows in batches of ``scan_batch`` and flags those where a
  speaker explains a spelling (prompt ``SCAN_SYSTEM``). A source may reuse an earlier
  scan of the same windows (``reuse_scan``).
- ``regex``: rule candidates (拆字 and 偏旁 phrases, "…X…的X" at a phrase end); the ones the
  scan did not flag are scanned again in small batches (``rescan``), since the
  batch scan misses some.
- ``judge``: two LLMs of different families independently decide ``none``,
  ``consistent``, ``corrected`` or ``unsure`` and write the corrected window.
- ``decide``: mechanical checks (only explained characters change, every change keeps
  a shared reading, same length) and the two judges' agreement give one decision per
  window: ``not_hit``, ``unchanged``, ``consistent``, ``corrected`` or ``quarantine``.

    python clean.py units  --source wenetspeech_podcast
    load.sh aliyun-llm -- python clean.py rescan --source wenetspeech_podcast
    load.sh aliyun-llm -- python clean.py judge  --source wenetspeech_podcast
    python clean.py decide --source wenetspeech_podcast
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts
from common import LLM, JsonlAppender, parse_json_reply, read_jsonl, write_jsonl

HERE = Path(__file__).resolve().parent
VERDICTS = ("none", "consistent", "corrected", "unsure")


def is_han(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def gz_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


# ---------------------------------------------------------------- units

def cmd_units(recipe, name, spec, root):
    """Windows of consecutive supervisions (the rule of ``mine.py windows``), keeping segment texts."""
    by_recording = defaultdict(list)
    for row in gz_rows(Path(spec["supervisions"])):
        text = (row.get("text") or "").strip()
        if text:
            by_recording[row["recording_id"]].append((float(row["start"]), float(row["duration"]), row["id"], text))
    limit, gap = recipe["window_seconds"], recipe["max_gap_seconds"]
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
    out = root / "units.jsonl.gz"
    write_jsonl(out, (
        {"unit_id": f"{name}:{rec}:{segs[0][2].rsplit('_', 1)[-1]}", "recording_id": rec,
         "start": round(segs[0][0], 3), "end": round(segs[-1][0] + segs[-1][1], 3),
         "segments": [{"id": s[2], "text": s[3]} for s in segs], "text": "，".join(s[3] for s in segs)}
        for rec, segs in windows))
    print(f"{name}: {len(by_recording)} recordings -> {len(windows)} units -> {out}")
    if spec.get("reuse_windows"):  # the earlier scan applies only if its windows are the same
        old = {w["window_id"]: w["text"] for w in gz_rows(Path(spec["reuse_windows"]))}
        new = {u["unit_id"]: u["text"] for u in gz_rows(out)}
        print(f"reuse_windows identical: {old == new} ({len(old)} vs {len(new)})")


def units(root):
    return gz_rows(root / "units.jsonl.gz")


# ---------------------------------------------------------------- scan

def scan_batches(client_spec, base_url, key_env, rows, batch_size, sink_path, log_path, workers, tag):
    """Flag rows with the SCAN_SYSTEM prompt, ``batch_size`` rows per request (resumable by batch)."""
    log = JsonlAppender(log_path)
    llm = LLM(client_spec, log, base_url, key_env)
    done = {row["batch"] for row in read_jsonl(sink_path) if "error" not in row}
    batches = [(i // batch_size, rows[i:i + batch_size]) for i in range(0, len(rows), batch_size)]
    batches = [b for b in batches if b[0] not in done]
    sink = JsonlAppender(sink_path)

    def run(batch):
        index, chunk = batch
        listing = "\n".join(f"{k + 1}. {u['text']}" for k, u in enumerate(chunk))
        messages = [{"role": "system", "content": prompts.SCAN_SYSTEM}, {"role": "user", "content": listing}]
        try:
            reply = llm.chat(messages, tag=f"{tag}:{index}")
            flagged = parse_json_reply(reply)
            picked = sorted({int(k) for k in flagged if isinstance(k, int) and 1 <= k <= len(chunk)})
            return {"batch": index, "units": [u["unit_id"] for u in chunk],
                    "flagged": [chunk[k - 1]["unit_id"] for k in picked], "reply": reply, "model": llm.model}
        except Exception as exc:  # noqa: BLE001 - recorded; the batch is retried on resume
            return {"batch": index, "units": [u["unit_id"] for u in chunk], "flagged": [],
                    "error": f"{type(exc).__name__}: {exc}", "model": llm.model}

    with ThreadPoolExecutor(workers) as pool:
        for count, future in enumerate(as_completed([pool.submit(run, b) for b in batches]), 1):
            sink.append(future.result())
            if count % 100 == 0 or count == len(batches):
                print(f"[{tag}] {count}/{len(batches)} batches", flush=True)


def scan_flagged(spec, root) -> set[str]:
    path = Path(spec["reuse_scan"]) if spec.get("reuse_scan") else root / "scan.jsonl"
    return {u for row in read_jsonl(path) if "error" not in row for u in row["flagged"]}


def cmd_scan(recipe, name, spec, root, args):
    if spec.get("reuse_scan"):
        sys.exit(f"{name} reuses the scan {spec['reuse_scan']}")
    llm = recipe["llm"]
    rows = list(units(root))
    scan_batches(llm["scan"], args.base_url or llm["base_url"], llm["api_key_env"], rows, llm["scan_batch"],
                 root / "scan.jsonl", Path(recipe["run_dir"]) / "llm-log" / name / "scan.jsonl",
                 args.workers or llm["workers"], "scan")


# ---------------------------------------------------------------- regex candidates

CHAIZI = re.compile("耳东陈|弓长张|木子李|立早章|口天吴|文刀刘|古月胡|双木林|草头黄|言午许|走肖赵|禾口程|人可何|"
                    "双口吕|子小孙|三横王|关耳郑|干勾于|木易杨|十八子李|日月明")
PIANPANG = re.compile("三点水|两点水|草字头|单人旁|双人旁|提手旁|木字旁|言字旁|绞丝旁|宝盖头|竖心旁|金字旁|女字旁|王字旁|"
                      "日字旁|火字旁|石字旁|竹字头|雨字头|走之底|反文旁|立刀旁|口字旁|土字旁|月字旁|目字旁|示字旁|"
                      "衣字旁|足字旁|山字旁|米字旁|禾木旁|耳朵旁|斜玉旁|提土旁|心字底|四点底|宝字盖|秃宝盖|门字框|"
                      "病字旁|虫字旁|贝字旁|马字旁|鱼字旁|鸟字旁|金字边|偏旁|部首")
# "灰色的灰": the character after 的 already appears in the 1-4 characters before it, and the phrase ends there
ZUCI_STOP = set("就是的了我你他她它这那也都不有在一个说要会还很对啊嗯呢吧吗哦哈来去到和跟把被让给看想能可以没么们什怎样"
                "人子儿时候里上下中大小多少好")
PHRASE_END = set("，。？！、")
PHRASE_NEXT = {"然后", "那个", "就是", "还有", "对吧", "对对", "我们", "大家"}


def zuci_candidate(text: str) -> bool:
    for i, ch in enumerate(text[:-1]):
        c = text[i + 1]
        if ch != "的" or not is_han(c) or c in ZUCI_STOP or c not in text[max(0, i - 4):i]:
            continue
        after = text[i + 2:i + 4]
        if not after or after[0] in PHRASE_END or after[0] == "字" or after[1:2] == "是" or after in PHRASE_NEXT:
            return True
    return False


def regex_rules(text: str) -> list[str]:
    return [rule for rule, hit in (("拆字", CHAIZI.search(text)), ("偏旁", PIANPANG.search(text)),
                                   ("组词", zuci_candidate(text))) if hit]


def cmd_regex(recipe, name, spec, root, args):
    flagged = scan_flagged(spec, root)
    rows, counts = [], Counter()
    for unit in units(root):
        rules = regex_rules(unit["text"])
        if rules:
            rows.append({"unit_id": unit["unit_id"], "rules": rules, "scan_flagged": unit["unit_id"] in flagged})
            counts.update(rules)
    write_jsonl(root / "regex.jsonl", rows)
    print({"candidates": len(rows), "already_flagged": sum(r["scan_flagged"] for r in rows), **counts})


def cmd_rescan(recipe, name, spec, root, args):
    llm = recipe["llm"]
    todo = {r["unit_id"] for r in read_jsonl(root / "regex.jsonl") if not r["scan_flagged"]}
    rows = [u for u in units(root) if u["unit_id"] in todo]
    scan_batches(llm["scan"], args.base_url or llm["base_url"], llm["api_key_env"], rows, llm["rescan_batch"],
                 root / "rescan.jsonl", Path(recipe["run_dir"]) / "llm-log" / name / "rescan.jsonl",
                 args.workers or llm["workers"], "rescan")


def hits(spec, root) -> set[str]:
    rescan = {u for row in read_jsonl(root / "rescan.jsonl") if "error" not in row for u in row["flagged"]}
    return scan_flagged(spec, root) | rescan


# ---------------------------------------------------------------- judge

def cmd_judge(recipe, name, spec, root, args):
    llm_cfg = recipe["llm"]
    wanted = hits(spec, root)
    rows = [u for u in units(root) if u["unit_id"] in wanted]
    if args.limit:
        rows = rows[:args.limit]
    log = JsonlAppender(Path(recipe["run_dir"]) / "llm-log" / name / "judge.jsonl")
    judges = {key: LLM(cfg, log, llm_cfg["base_url"], llm_cfg["api_key_env"]) for key, cfg in llm_cfg["judges"].items()}
    path = root / "judge.jsonl"
    done = {(r["text"], r["judge"]) for r in read_jsonl(path) if "error" not in r["answer"]}
    sink = JsonlAppender(path)
    tasks, seen = [], set()
    for unit in rows:  # the same text (re-uploaded episodes, repeated sign-offs) is judged once
        for key in judges:
            if (unit["text"], key) not in done and (unit["text"], key) not in seen:
                tasks.append((unit, key))
                seen.add((unit["text"], key))

    def run(task):
        unit, key = task
        messages = [{"role": "system", "content": prompts.CLEAN_JUDGE_SYSTEM},
                    {"role": "user", "content": prompts.CLEAN_JUDGE_USER.format(text=unit["text"])}]
        try:
            answer = parse_json_reply(judges[key].chat(messages, tag=f"{key}:{unit['unit_id']}"))
            if not isinstance(answer, dict):
                raise TypeError(f"not an object: {answer!r}"[:200])
        except (TypeError, ValueError, RuntimeError) as exc:
            answer = {"error": str(exc)[:500]}
        return {"unit_id": unit["unit_id"], "text": unit["text"], "judge": key, "model": judges[key].model,
                "answer": answer}

    with ThreadPoolExecutor(args.workers or llm_cfg["workers"]) as pool:
        for count, future in enumerate(as_completed([pool.submit(run, t) for t in tasks]), 1):
            sink.append(future.result())
            if count % 50 == 0 or count == len(tasks):
                print(f"[judge] {count}/{len(tasks)}", flush=True)


# ---------------------------------------------------------------- decide

def readings(ch: str) -> set[str]:
    from pypinyin import Style, pinyin

    return set(pinyin(ch, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0])


def answer_issues(original: str, answer: dict) -> list[str]:
    """Mechanical checks of one judge's answer; an empty list means it may be used."""
    if "error" in answer:
        return [f"judge error: {answer['error'][:80]}"]
    verdict = answer.get("verdict")
    if verdict not in VERDICTS:
        return [f"bad verdict {verdict!r}"]
    if verdict == "none":
        return []
    issues = []
    explanations = answer.get("explanations") or []
    if not explanations or not all(isinstance(e, dict) for e in explanations):
        issues.append("explanations missing")
    corrected = answer.get("corrected") if verdict != "unsure" else None
    if verdict == "consistent" and corrected not in (None, original):
        issues.append("consistent but the transcript was changed")
    if verdict == "corrected":
        if not isinstance(corrected, str) or corrected == original:
            issues.append("corrected but nothing changed")
        elif len(corrected) != len(original):
            issues.append("length changed")
        else:
            for a, b in zip(original, corrected):
                if a == b:
                    continue
                if not (is_han(a) and is_han(b)):
                    issues.append(f"non-Han change {a}->{b}")
                elif not readings(a) & readings(b):
                    issues.append(f"reading changes {a}->{b}")
    plain = original.replace("，", "")
    fixed = (corrected or original).replace("，", "")
    for e in explanations:
        evidence = (e.get("evidence") or "").replace("，", "") if isinstance(e, dict) else ""
        if not evidence or (evidence not in plain and evidence not in fixed):
            issues.append("evidence not found in the transcript")
            break
    return issues


def contradictions(text: str, spans: list[range]) -> list[str]:
    """"乔木的桥": inside an explanation, the character after 的 is missing from the 1-4 characters
    before it while a homophone of it is there, so the explanation itself is mis-transcribed."""
    found = []
    for span in spans:
        for i in span:
            if text[i] != "的" or i + 1 >= len(text) or not is_han(text[i + 1]):
                continue
            char, before = text[i + 1], text[max(span.start, i - 4):i]
            if char not in before and any(is_han(c) and readings(c) & readings(char) for c in before):
                found.append(f"{before}的{char}")
    return found


def decide(original: str, answers: dict[str, dict]) -> tuple[str, list[str], str | None]:
    """(decision, reasons, corrected text) from the judges' answers on one window.

    Nobody asks for a change: the window stays as it is (``consistent`` only when both
    judges say so and pass the checks, otherwise ``unchanged`` / ``not_hit``). A change
    is made only when both judges write the same corrected text and pass the checks;
    every other window where someone asks for a change or is unsure is quarantined.
    """
    issues = [f"{key}: {issue}" for key, answer in sorted(answers.items()) for issue in answer_issues(original, answer)]
    verdicts = {key: answer.get("verdict") for key, answer in answers.items()}
    values = set(verdicts.values())
    detail = [f"{key}: {verdict}" for key, verdict in sorted(verdicts.items())]
    if values == {"none"}:
        return "not_hit", [], None
    contradicted = []
    for key, answer in sorted(answers.items()):
        if answer.get("verdict") in ("consistent", "corrected"):
            final = answer.get("corrected") if answer.get("verdict") == "corrected" else original
            if isinstance(final, str) and len(final) == len(original):
                spans = evidence_spans([original, final], answer.get("explanations")) or []
                contradicted += [f"{key}: {c}" for c in contradictions(final, spans)]
    if contradicted:  # a judge left an explanation that contradicts itself: the label is wrong somewhere
        return "quarantine", ["explanation_contradicts"] + contradicted, None
    if values <= {"none", "consistent"}:
        if values == {"consistent"} and not issues:
            return "consistent", [], original
        return "unchanged", detail + issues, None
    if issues:
        return "quarantine", ["check_failed"] + issues, None
    if "unsure" in values:
        return "quarantine", ["judge_unsure"] + detail, None
    if values != {"corrected"}:
        return "quarantine", ["judges_disagree"] + detail, None
    texts = {answer["corrected"] for answer in answers.values()}
    if len(texts) > 1:
        return "quarantine", ["corrections_differ"], None
    text = texts.pop()
    # every new character must be one an explanation names; judges sometimes fill "char" with the
    # transcript's character instead, so the characters named by either judge count
    named = {ch for answer in answers.values() for e in answer.get("explanations") or []
             for ch in str(e.get("char") or "") if is_han(ch)}
    unexplained = sorted({b for a, b in zip(original, text) if a != b} - named)
    if unexplained:
        return "quarantine", ["unexplained_change"] + unexplained, None
    return "corrected", [], text


def edits(original: str, corrected: str, segments: list[dict]) -> list[dict]:
    """Changed characters with the segment that holds each (window text joins segments with '，')."""
    owner, offsets = [], []
    for index, segment in enumerate(segments):
        if index:
            owner.append(None)
            offsets.append(None)
        owner.extend([index] * len(segment["text"]))
        offsets.extend(range(len(segment["text"])))
    return [{"pos": i, "from": a, "to": b, "segment": segments[owner[i]]["id"], "offset": offsets[i]}
            for i, (a, b) in enumerate(zip(original, corrected)) if a != b]


def excluded_recordings(recipe, name) -> set[str]:
    """Recording IDs of the evaluation set (lines ``<source>:<recording_id>``) that never go to training."""
    path = recipe.get("exclude_recordings", {}).get(name)
    if not path:
        return set()
    return {line.strip().split(":", 1)[1] for line in Path(path).read_text().splitlines() if line.strip()}


def cmd_decide(recipe, name, spec, root, args):
    judged = defaultdict(dict)
    for row in read_jsonl(root / "judge.jsonl"):
        judged[row["text"]][row["judge"]] = row["answer"]  # the last answer of each judge wins
    keys = set(recipe["llm"]["judges"])
    excluded = excluded_recordings(recipe, name)
    regex = {r["unit_id"]: r["rules"] for r in read_jsonl(root / "regex.jsonl")}
    audio = {r["unit_id"]: r for r in read_jsonl(root / "audio.jsonl") if "error" not in r}
    flagged = scan_flagged(spec, root)
    wanted = hits(spec, root)
    # Windows a reviewer found wrong (unit_id <TAB> note); every window with the same text goes with it.
    rejected = {}
    if name in recipe.get("review_rejected", {}):
        lines = Path(recipe["review_rejected"][name]).read_text().splitlines()
        rejected = dict(line.split("\t", 1) for line in lines if line.strip())
    rejected_texts = {u["text"]: rejected[u["unit_id"]] for u in units(root) if u["unit_id"] in rejected}
    out, counts, reasons = [], Counter(), Counter()
    for unit in units(root):
        if unit["unit_id"] not in wanted:
            continue
        answers = judged.get(unit["text"], {})
        if set(answers) != keys:
            counts["not_judged"] += 1
            continue
        failed = [f"{k}: {a['error'][:200]}" for k, a in answers.items() if "error" in a]
        # A hit window no judge could answer (e.g. refused by content moderation) cannot be checked: quarantine.
        decision, why, corrected = ("quarantine", ["judge_failed", *failed], None) if failed else decide(unit["text"], answers)
        row = {"unit_id": unit["unit_id"], "recording_id": unit["recording_id"], "start": unit["start"],
               "end": unit["end"], "segments": unit["segments"], "text": unit["text"], "decision": decision,
               "reasons": why, "corrected": corrected, "edits": [],
               "explanations": {k: a.get("explanations") for k, a in answers.items()},
               "judge_reasons": {k: a.get("reason") for k, a in answers.items()},
               "found_by": ["scan"] * (unit["unit_id"] in flagged) + ["regex:" + r for r in regex.get(unit["unit_id"], [])],
               "eval_excluded": unit["recording_id"] in excluded, "audio": None}
        if decision in ("consistent", "corrected"):
            if unit["unit_id"] not in audio:
                row["reasons"] = why + ["audio_pending"]
            else:
                row["audio"] = {"hypothesis": audio[unit["unit_id"]]["hypothesis"],
                                **audio_result(row, audio[unit["unit_id"]]["hypothesis"], recipe)}
                if not row["audio"]["pass"]:
                    row["reasons"] = ["audio_mismatch", f"text decision: {decision}"]
                    decision = row["decision"] = "quarantine"
                    row["corrected"] = None
        if decision != "quarantine" and unit["text"] in rejected_texts:
            row["reasons"] = ["review_rejected", rejected_texts[unit["text"]], f"text decision: {decision}"]
            decision = row["decision"] = "quarantine"
            row["corrected"] = None
        if row["decision"] == "corrected":
            row["edits"] = edits(unit["text"], corrected, unit["segments"])
        out.append(row)
        counts[decision] += 1
        if decision == "quarantine":
            reasons[row["reasons"][0]] += 1
    write_jsonl(root / "decisions.jsonl", out)
    print(dict(counts), dict(reasons))


# ---------------------------------------------------------------- audio check

def evidence_spans(texts: list[str], explanations: list) -> list[range] | None:
    """Character ranges of every evidence span, found in the first of ``texts`` that holds it
    (the corrected window has the same length, so ranges carry over). Commas between segments
    are ignored when matching."""
    spans = []
    for e in explanations or []:
        evidence = (e.get("evidence") or "").replace("，", "") if isinstance(e, dict) else ""
        for text in texts:
            keep = [i for i, ch in enumerate(text) if ch != "，"]
            at = "".join(text[i] for i in keep).find(evidence) if evidence else -1
            if at >= 0:
                spans.append(range(keep[at], keep[at + len(evidence) - 1] + 1))
                break
        else:
            return None
    return spans


def heard(text: str, spans: list[range], hypothesis: str, context: int, max_edits: int) -> dict:
    """Is each evidence span, with ``context`` syllables on both sides, in the ASR hypothesis with at most
    ``max_edits`` toneless-pinyin edits? Missing or extra words next to an explanation ("似舞蹈的舞" heard
    as "似乎的似，舞蹈的舞") fail; homophone choices cannot."""
    from pypinyin import Style, lazy_pinyin
    from rapidfuzz.distance import Levenshtein

    index = [i for i, ch in enumerate(text) if is_han(ch)]
    ref = lazy_pinyin("".join(text[i] for i in index), style=Style.NORMAL)
    hyp = lazy_pinyin("".join(ch for ch in hypothesis if is_han(ch)), style=Style.NORMAL)
    syllable = {char: k for k, char in enumerate(index)}
    ops = Levenshtein.opcodes(ref, hyp)
    failed = []
    for span in spans:
        own = [syllable[i] for i in span if i in syllable]
        if not own:
            continue
        lo, hi = max(0, own[0] - context), min(len(ref), own[-1] + 1 + context)
        count = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == "insert":
                count += (j2 - j1) if lo < i1 < hi else 0
            elif tag != "equal":
                count += max(0, min(i2, hi) - max(i1, lo))
        if count > max_edits:
            failed.append(f"{text[span.start:span.stop]}: {count} edits")
    return {"pinyin_error": round(Levenshtein.distance(ref, hyp) / max(1, len(ref)), 4), "failed": failed}


def audio_result(row: dict, hypothesis: str, recipe: dict) -> dict:
    """Passes when, for at least one judge, every evidence span is heard."""
    checks = {}
    for key, explanations in row["explanations"].items():
        spans = evidence_spans([row["text"], row["corrected"] or row["text"]], explanations)
        if spans is not None:
            checks[key] = heard(row["corrected"] or row["text"], spans, hypothesis,
                                recipe["audio_context_syllables"], recipe["audio_max_edits"])
    return {"checks": checks, "pass": any(not c["failed"] for c in checks.values())}


def cmd_audio(recipe, name, spec, root, args):
    """Qwen3-ASR transcribes each consistent or corrected window (``decide`` then checks the explanations)."""
    import base64
    import io

    import numpy as np
    import soundfile as sf
    import soxr
    from openai import OpenAI

    paths = {r["id"]: r["sources"][0]["source"] for r in gz_rows(Path(spec["recordings"]))}
    rows = [d for d in read_jsonl(root / "decisions.jsonl")
            if d["decision"] in ("consistent", "corrected") or "audio_mismatch" in d["reasons"]]
    out_path = root / "audio.jsonl"
    done = {r["unit_id"] for r in read_jsonl(out_path) if "error" not in r}
    rows = [d for d in rows if d["unit_id"] not in done]
    client = OpenAI(base_url=args.base_url, api_key="x", timeout=600, max_retries=0)
    sink = JsonlAppender(out_path)
    pad = 0.3

    def run(row):
        try:
            with sf.SoundFile(paths[row["recording_id"]]) as stream:
                sr = stream.samplerate
                start = max(0.0, row["start"] - pad)
                stream.seek(int(start * sr))
                wav = stream.read(int((row["end"] + pad - start) * sr), dtype="float32", always_2d=True).mean(axis=1)
            if sr != 16000:
                wav = soxr.resample(wav, sr, 16000)
            buf = io.BytesIO()
            sf.write(buf, np.clip(wav, -1, 1), 16000, format="FLAC", subtype="PCM_16")
            url = "data:audio/flac;base64," + base64.b64encode(buf.getvalue()).decode()
            reply = client.chat.completions.create(
                model=args.served_model, temperature=0, max_tokens=1024, extra_body={"repetition_penalty": 1.1},
                messages=[{"role": "user", "content": [{"type": "audio_url", "audio_url": {"url": url}}]}])
            raw = (reply.choices[0].message.content or "").strip()
            hypothesis = raw.split("<asr_text>", 1)[1].strip() if "<asr_text>" in raw else raw
        except Exception as exc:  # noqa: BLE001 - recorded; retried on resume
            return {"unit_id": row["unit_id"], "error": f"{type(exc).__name__}: {exc}"[:300]}
        return {"unit_id": row["unit_id"], "model": args.served_model, "hypothesis": hypothesis}

    with ThreadPoolExecutor(args.workers or 16) as pool:
        for count, future in enumerate(as_completed([pool.submit(run, r) for r in rows]), 1):
            sink.append(future.result())
            if count % 50 == 0 or count == len(rows):
                print(f"[audio] {count}/{len(rows)}", flush=True)


# ---------------------------------------------------------------- build

def segment_fixes(decisions: list[dict]) -> tuple[dict, dict]:
    """Segment id -> (corrected text, original text, unit id); segment id -> unit id of a quarantined window."""
    fixes, dropped = {}, {}
    for d in decisions:
        if d["decision"] == "corrected":
            chars = {s["id"]: list(s["text"]) for s in d["segments"]}
            original = {s["id"]: s["text"] for s in d["segments"]}
            for e in d["edits"]:
                if chars[e["segment"]][e["offset"]] != e["from"]:
                    raise ValueError(f"{d['unit_id']}: edit {e} does not match the segment text")
                chars[e["segment"]][e["offset"]] = e["to"]
            for sid, text in chars.items():
                if "".join(text) != original[sid]:
                    fixes[sid] = ("".join(text), original[sid], d["unit_id"])
        elif d["decision"] == "quarantine":
            for segment in d["segments"]:
                dropped[segment["id"]] = d["unit_id"]  # the whole window: its texts are in doubt
    return fixes, dropped


def cmd_build(recipe, name, spec, root, args):
    """Derived lhotse version: corrected texts; quarantined windows and evaluation recordings removed.
    Also writes the training record IDs it removes, for use as ``exclude_records`` on the original version."""
    decisions = read_jsonl(root / "decisions.jsonl")
    pending = [d["unit_id"] for d in decisions if "audio_pending" in d["reasons"]]
    if pending:
        sys.exit(f"{len(pending)} windows still wait for the audio check, e.g. {pending[:3]}")
    fixes, dropped = segment_fixes(decisions)
    excluded = excluded_recordings(recipe, name)
    dataset, base = spec["dataset"].split("@")
    version = f"{base}-{recipe['derived_suffix']}"
    out = Path(recipe["data_root"]) / "datasets" / dataset / "versions" / version
    record_prefix = f"{spec['dataset']}:{spec['split']}:"
    stats = Counter()
    hours = Counter()
    removed_ids = []

    def rows():
        for row in gz_rows(Path(spec["supervisions"])):
            stats["source_records"] += 1
            hours["source"] += row["duration"]
            reason = ("eval_recording" if row["recording_id"] in excluded
                      else "quarantine" if row["id"] in dropped else None)
            if reason:
                stats[f"removed_{reason}"] += 1
                hours[f"removed_{reason}"] += row["duration"]
                removed_ids.append(record_prefix + row["id"])
                continue
            if row["id"] in fixes:
                text, original, unit = fixes[row["id"]]
                if (row.get("text") or "").strip() != original:
                    raise ValueError(f"{row['id']}: supervision text differs from the judged window")
                row = {**row, "text": text, "custom": {**(row.get("custom") or {}), "context_correction": {
                    "original_text": row["text"], "unit_id": unit,
                    "decisions": f"{recipe['dataset_id']}@{recipe['version']}"}}}
                stats["corrected"] += 1
                hours["corrected"] += row["duration"]
            stats["records"] += 1
            hours["kept"] += row["duration"]
            yield row

    write_jsonl(out / "supervisions" / f"{spec['split']}.jsonl.gz", rows())
    kept_recordings = (r for r in gz_rows(Path(spec["recordings"])) if r["id"] not in excluded)
    write_jsonl(out / "recordings" / f"{spec['split']}.jsonl.gz", kept_recordings)
    exclude_path = root / f"exclude-records-{spec['dataset']}.txt"
    exclude_path.write_text("".join(i + "\n" for i in removed_ids))
    # Real positives: windows whose label already follows the speaker's explanation, with their derived record IDs.
    derived_prefix = f"{dataset}@{version}:{spec['split']}:"
    positives = [{**{k: d[k] for k in ("unit_id", "recording_id", "start", "end", "text", "explanations")},
                  "record_ids": [derived_prefix + s["id"] for s in d["segments"]]}
                 for d in decisions if d["decision"] == "consistent" and d["recording_id"] not in excluded]
    write_jsonl(root / "positives.jsonl", positives)
    stats["positive_windows"] = len(positives)
    summary = {"derived": f"{dataset}@{version}", **stats, **{f"{k}_hours": round(v / 3600, 3) for k, v in hours.items()},
               "exclude_records": str(exclude_path)}
    (root / "build.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["units", "scan", "regex", "rescan", "judge", "decide", "audio", "build"])
    parser.add_argument("--recipe", type=Path, default=HERE / "clean_recipe.yaml")
    parser.add_argument("--source", required=True)
    parser.add_argument("--base-url", help="OpenAI-compatible server: scan/rescan (default recipe llm.base_url), audio (Qwen3-ASR)")
    parser.add_argument("--served-model", default="Qwen/Qwen3-ASR-1.7B", help="audio: served Qwen3-ASR name")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="judge only the first N hit windows (trial)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    spec = recipe["sources"][args.source]
    root = Path(recipe["out"]) / args.source
    root.mkdir(parents=True, exist_ok=True)
    {"units": lambda: cmd_units(recipe, args.source, spec, root),
     "scan": lambda: cmd_scan(recipe, args.source, spec, root, args),
     "regex": lambda: cmd_regex(recipe, args.source, spec, root, args),
     "rescan": lambda: cmd_rescan(recipe, args.source, spec, root, args),
     "judge": lambda: cmd_judge(recipe, args.source, spec, root, args),
     "decide": lambda: cmd_decide(recipe, args.source, spec, root, args),
     "audio": lambda: cmd_audio(recipe, args.source, spec, root, args),
     "build": lambda: cmd_build(recipe, args.source, spec, root, args)}[args.stage]()


if __name__ == "__main__":
    main()
