#!/usr/bin/env python3
"""Real-conversation target-speaker windows (ts_asr_real).

Cuts windows out of long, human-annotated real conversations (the test splits of AliMeeting far-field,
AISHELL-4 and MagicData-RAMC phone calls). Nothing is mixed: the interfering speech, the overlaps, the
room and the device are the real ones. A window is a run of whole utterances (no utterance crosses a
window edge), so the reference of a target speaker is the concatenated text of that speaker's
utterances in the window.

Every window yields a paired sample on the same audio: a positive (a speaker present in the window,
enrolled with another utterance of theirs from outside the window, same recording) and a negative (a
speaker of the same recording who does not speak in the window, or a speaker of another recording when
there is none). Recording-level facts, speaker counts and overlap are kept in the labels.

Recipe ``overlap`` cuts target-anchored windows instead (``target_windows``): the window is a run of
whole utterances of the target only, everyone else's speech is clipped to the window edges, and windows
are sampled per bucket of the target's overlap ratio, so heavily overlapped stretches of real meetings are
kept (the run-of-whole-utterances closure drops most of them). Recipe ``dev`` cuts both kinds from the dev
splits for model selection.

Recipe ``en`` applies the same rules to English test/eval sets (AMI, NOTSOFAR-1, CHiME-6, DiPCo, ICSI; loaders and
transcript cleaning in ``english.py``): references join a speaker's utterances with spaces, records carry
``language: en``, enrollments follow v4 (an utterance others overlap for up to 20%, stored to 10 s; >= 0.3 s of
others in the first 5 s moves the record to ``<split>-enrollmix``), and every enrollment passes a voice check
(``voice_check.py``; ``--embed-python`` is a Python with onnxruntime and torchaudio for ``embed_worker.py``).

    python scripts/ts_real/build.py --roots /workspace/data/registry/roots.json [--recipe overlap]
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ts_benchmark"))
import build as synth

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

REPO = Path(__file__).resolve().parents[2]
SR = 16000
DATASET_ID = "ts_asr_real"
MAX_WINDOW = 26.0  # the TS service accepts at most 27 s of mixture; keep the edges inside
ENROLL_MIN = 3.0
ENROLL_MAX = 6.0
ENROLL_MAX_OVERLAP = 0.2  # share of the enrollment utterance that another speaker may overlap
ENROLL_CROP = 5.0  # seconds of the enrollment the TS client sends (5 s in production since 2026-10-22, 3 s before)
ENROLL_STORE = 10.0  # seconds of the enrolled speaker kept per enrollment, so one dataset serves clients up to 10 s
ENROLL_PIECE_MIN = 1.0  # shortest further utterance appended to an enrollment
# Annotated speech of anyone else inside that crop. From this much on the enrollment is "others_speech", a
# degradation reported apart from clean enrollments (ts_asr_real v2: false alarms rise from 0.3-0.5 s on).
ENROLL_CROP_OTHERS_MAX = 0.3
MIN_TARGET_SECONDS = 1.0
ATTEMPTS = 60
ENROLLMIX = "-enrollmix"
JOINERS = {"zh": "", "en": " "}  # between a speaker's utterances in the reference
# Fillers Whisper's EnglishTextNormalizer (the English scorer) deletes; a target needs a word beyond them.
EN_FILLERS = re.compile(r"\b(hmm|mm|mhm|mmm|uh|um)\b")
SPEAKER_MODEL = "/workspace/model/wespeaker-ecapa-tdnn512-LM/voxceleb_ECAPA512_LM.onnx"
VOICE_ATTEMPTS = 20  # further enrollment utterances tried when one fails the voice check

RECIPE = yaml.safe_load("""
version: v2-20261013
seed: 20261013
corpora:
  alimeeting: {dataset: alimeeting_sdm, version: icefall-20260908, split: test, label: AliMeeting 远场会议, windows: 150}
  aishell4: {dataset: aishell4, version: icefall-20260908, split: test, label: AISHELL-4 远场会议, windows: 150}
  ramc: {dataset: magicdata_ramc, version: icefall-20260908, split: test, label: MagicData-RAMC 手机通话, windows: 150}
  emilia2: {kind: emilia2, dataset: emilia2_zh_dialogue_diarize, version: moss-transcribe-diarize-0.9B, split: train_120s, label: Emilia2 网络爬取的对话（MOSS 伪标签）, windows: 150, recordings: 260, annotation: moss}
buckets:
  1spk: [1, 1]
  2spk: [2, 2]
  3plus: [3, 99]
""")
# Share of the target's speech that someone else talks over, as (lo, hi]; o0 is [0, 0.05].
OVERLAP_BUCKETS = {"o0": [0.0, 0.05], "o20": [0.05, 0.2], "o50": [0.2, 0.5], "o100": [0.5, 1.0]}
RECIPES = {
    "v2": RECIPE,
    "overlap": yaml.safe_load("""
version: overlap-v1-20261017
seed: 20261017
prefix: real
windowing: target
exclude_train_speakers: true
description: >-
  真实会议的目标重叠窗口：从 AliMeeting 远场、AISHELL-4 远场的人工标注测试集里以目标说话人为锚切 8–26 秒窗口
  （目标的语句完整，别人的语句截到窗口边界），按目标语音被别人重叠的比例分 5–20%、20–50%、50% 以上三档，
  不做任何混合；同一窗口配一条目标在场和一条目标缺席的样本。只用于评测，不进训练。
corpora:
  alimeeting: {dataset: alimeeting_sdm, version: icefall-20260908, split: test, label: AliMeeting 远场会议, windows: {o20: 100, o50: 250, o100: 350}}
  aishell4: {dataset: aishell4, version: icefall-20260908, split: test, label: AISHELL-4 远场会议, windows: {o20: 100, o50: 200, o100: 250}}
"""),
    "dev": yaml.safe_load("""
version: dev-v1-20261017
seed: 20261017
prefix: dev
windowing: target
exclude_train_speakers: true
description: >-
  真实对话的目标说话人开发集（选模型和阈值用）：从 AliMeeting 远场、MagicData-RAMC 手机通话的人工标注 dev 划分里
  以目标说话人为锚切窗口，按目标被重叠的比例分档（RAMC 标注没有重叠，只有 o0），去掉在 train 划分出现过的说话人所在的录音；
  同一窗口配一条目标在场和一条目标缺席的样本。不进训练，也不作最终评测。
corpora:
  alimeeting: {dataset: alimeeting_sdm, version: icefall-20260908, split: dev, label: AliMeeting 远场会议 dev, windows: {o0: 100, o20: 100, o50: 150, o100: 150}}
  ramc: {dataset: magicdata_ramc, version: icefall-20260908, split: dev, label: MagicData-RAMC 手机通话 dev, windows: {o0: 150}}
"""),
    "en": yaml.safe_load("""
version: en-v2-20261031
seed: 20261031
language: en
enrollmix: true
voice_check: true
description: >-
  英文真实对话的目标说话人窗口（ts_asr_real 中文版的英文对照，规则相同）：从 AMI 单远场麦、NOTSOFAR-1 单通道设备、
  CHiME-6 家庭聚会（所在房间参考阵列通道 1，窗口内所有人在同一房间）、DiPCo 晚宴（远场设备通道 1，时间轴按近讲麦对齐）的
  人工标注 test/eval 划分，以及 ICSI 会议测试会议（官方近讲耳麦混音，不是远场）里按完整语句切出 8–22 秒窗口，不做任何混合；
  同一窗口配一条目标在场（注册取窗外同一人的语句）和一条目标缺席的样本。参考文本为目标在窗口内各句按时间顺序用空格拼接，
  去掉了笑声、噪声、截断词等标注；含听不清、外语、被消音或数字朗读的语句算作有人说话，但不作目标、不作注册。注册存 10 秒、
  客户端取前 5 秒，前 5 秒里他人说话不少于 0.3 秒的在 -enrollmix 划分；每条注册都过声纹核对（与本人在本录音其他语句比
  与其他人更像，有近讲麦的语料用近讲麦之和），不过的换一句或剔除，见 source/<版本>/report.json。只用于评测，不进训练。
corpora:
  ami: {dataset: ami_sdm, version: icefall-20260908, split: test, label: AMI 远场会议, windows: 150}
  notsofar: {kind: notsofar, dataset: notsofar_sdm, version: icefall-20260908, split: test, label: NOTSOFAR-1 远场会议, windows: 150}
  chime6: {kind: chime6, dataset: chime6, version: speaker-records-v1-20260912, split: test, label: CHiME-6 家庭聚会, windows: 150}
  dipco: {kind: dipco, dataset: dipco, version: zenodo-8122551-20261023, split: eval, label: DiPCo 晚宴, windows: 150}
  icsi: {kind: icsi, dataset: icsi, version: modelscope-argmaxinc-20261025, split: test, label: ICSI 会议（近讲耳麦混音）, windows: 150, meetings: [Bmr013, Bmr018, Bro021]}
"""),
}


# --- corpus --------------------------------------------------------------------


def load_corpus(spec, catalog, roots, split=None):
    """{recording_id: {path, channel, sups: [(start, end, speaker, text)]}} from lhotse files."""
    def rows(role):
        out = []
        for path in resolve_split(catalog, spec["dataset"], spec["version"], split or spec["split"], role, roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                out += [json.loads(line) for line in stream if line.strip()]
        return out

    recordings = {r["id"]: r for r in rows("recordings")}
    english = spec.get("language") == "en"
    out = {}
    for row in rows("supervisions"):
        rid = row["recording_id"]
        if rid not in recordings or not (row.get("text") or "").strip():
            continue
        text = _english().clean(row["text"], "ami")[0] if english else "".join(row["text"].split())
        entry = out.setdefault(rid, {"path": recordings[rid]["sources"][0]["source"], "sups": [],
                                     "duration": float(recordings[rid]["duration"]),
                                     "channels": len(recordings[rid].get("channel_ids") or [0])})
        entry["sups"].append((float(row["start"]), float(row["start"]) + float(row["duration"]),
                              str(row["speaker"]), text))
    for rid, entry in out.items():
        if english:
            entry.update(language="en", enrollmix=spec.get("enrollmix"), excluded={},
                         source=Path(recordings[rid]["sources"][0]["source"]).stem.split(".")[-1])
        finish_entry(entry)
    return out


_SIBLINGS = {}


def _sibling(name):
    """A module next to this file, loaded once (this file is itself loaded under other names)."""
    if name not in _SIBLINGS:
        spec = importlib.util.spec_from_file_location(f"ts_real_{name}", Path(__file__).with_name(f"{name}.py"))
        _SIBLINGS[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_SIBLINGS[name])
    return _SIBLINGS[name]


def _english():
    return _sibling("english")


def load_recordings(name, corpus, catalog, roots, seed, report):
    """{recording: entry} of one recipe corpus, by its ``kind``."""
    kind = corpus.get("kind")
    if kind == "emilia2":
        return load_emilia2(corpus, catalog, roots, random.Random(f"{seed}:{name}:recordings"))
    if kind is None:
        return load_corpus(corpus, catalog, roots)
    english = _english()
    if kind == "notsofar":
        out = english.load_notsofar(corpus, catalog, roots, random.Random(f"{seed}:{name}:devices"))
    elif kind == "chime6":
        out = english.load_chime6(corpus, catalog, roots)
    elif kind == "icsi":
        out = english.load_icsi(corpus, catalog, roots)
    elif kind == "dipco":
        out = english.load_dipco(corpus, catalog, roots, random.Random(f"{seed}:{name}:devices"))
        for session, entry in out.items():
            # 120 s stretches every 300 s; a session-wide offset must agree across them within 50 ms.
            starts = [60.0 + 300.0 * i for i in range(int(max(entry["duration"] - 240.0, 0) // 300) + 1)]
            lag, lags, peaks = english.measure_offset(entry["close_talk"], entry["path"], starts)
            if lag is None or max(lags) - min(lags) > 0.05:
                raise ValueError(f"DiPCo {session} {entry['source']}: no stable far-field offset {lags} {peaks}")
            english.shift(entry, round(lag, 3))
            report.setdefault("timeline_offsets_s", {})[f"{name}:{session}"] = {
                "channel": entry["source"], "offset": round(lag, 3), "per_stretch": lags, "correlation": peaks}
            print(f"DiPCo {session} {entry['source']}: far-field lags the transcript by {lag:+.3f} s {lags}", flush=True)
    else:
        raise ValueError(f"unknown corpus kind {kind}")
    for entry in out.values():
        entry.update(language=corpus.get("language"), enrollmix=corpus.get("enrollmix"))
        finish_entry(entry)
    return out


def finish_entry(entry):
    """Sort the utterances and index the enrollment candidates of one recording."""
    entry["sups"].sort()
    entry["starts"] = [u[0] for u in entry["sups"]]
    entry["longest"] = max(u[1] - u[0] for u in entry["sups"])
    entry["eligible"] = defaultdict(list)
    excluded = entry.get("excluded", {})
    for s, e, spk, text in entry["sups"]:
        if e - s >= ENROLL_MIN and (s, e, spk) not in excluded:
            others = sum(max(0.0, min(e, oe) - max(s, os_)) for os_, oe, ospk, _ in overlapping(entry, s, e) if ospk != spk)
            # ``enrollmix`` recipes keep v2's rule (20% overlap) and split off crowded crops; others drop them here.
            if (others <= ENROLL_MAX_OVERLAP * (e - s)
                    and (entry.get("enrollmix")
                         or crop_others(entry, spk, s, min(e, s + ENROLL_CROP))[0] < ENROLL_CROP_OTHERS_MAX)):
                entry["eligible"][spk].append((s, e, text))


def crop_others(entry, speaker, start, end=None):
    """(seconds, speakers) of annotated speech by anyone but ``speaker`` in [start, end) (default: the client crop)."""
    end = start + ENROLL_CROP if end is None else end
    spans = sorted((max(start, s), min(end, e), spk) for s, e, spk, _ in overlapping(entry, start, end) if spk != speaker)
    seconds, reach = 0.0, start
    for s, e, _ in spans:
        s = max(s, reach)
        if e > s:
            seconds, reach = seconds + e - s, e
    return round(seconds, 3), sorted({spk for *_, spk in spans})


def enrollment_pieces(entry, speaker, first, lo, hi, rng):
    """[(start, end)] of an enrollment: ``first``, then other utterances of ``speaker`` in random order up to
    ENROLL_STORE seconds. Appended utterances lie outside the window [lo, hi] (1 s margin) and nobody else is
    annotated in them, so only the first utterance can carry someone else's voice (``labels.enroll_others_s``)."""
    pieces, have = [first], first[1] - first[0]
    excluded = entry.get("excluded", {})
    candidates = [(s, e) for s, e, spk, _ in entry["sups"]
                  if spk == speaker and e - s >= ENROLL_PIECE_MIN and not (e > lo - 1.0 and s < hi + 1.0)
                  and (s, e, spk) not in excluded
                  and not (e > first[0] and s < first[1])
                  and not any(o[2] != speaker for o in overlapping(entry, s, e))]
    rng.shuffle(candidates)
    for piece in candidates:
        if have >= ENROLL_STORE:
            break
        pieces.append(piece)
        have += piece[1] - piece[0]
    return pieces


def pieces_others(entry, speaker, pieces):
    """crop_others over the first ENROLL_CROP seconds of the concatenated pieces."""
    seconds, speakers, left = 0.0, set(), ENROLL_CROP
    for s, e in pieces:
        if left <= 0:
            break
        part = crop_others(entry, speaker, s, min(e, s + left))
        seconds, left = seconds + part[0], left - (e - s)
        speakers.update(part[1])
    return round(seconds, 3), sorted(speakers)


def cut_pieces(recordings, recording, pieces):
    return np.concatenate([cut(recordings, recording, s, e) for s, e in pieces])[: int(ENROLL_STORE * SR)]


def load_emilia2(spec, catalog, roots, rng):
    """Windows of crawled web conversations with MOSS diarization labels, one entry per window.

    The labels are pseudo labels (MOSS-Transcribe-Diarize, window text checked against Qwen3-ASR). Only
    windows with 2-3 speakers and no more than 3 active at once are used, one window per recording.
    """
    from audio_data_contract import resolve_artifact

    (records,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "records", roots)
    index_path = resolve_artifact(catalog, spec["dataset"], spec["version"], "train-audio-index", roots)
    paths = {}
    with gzip.open(index_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            paths[row["cut_id"]] = Path(roots[row["root_alias"]]) / row["relative_path"]
    by_recording = {}
    with gzip.open(records, "rt", encoding="utf-8") as stream:
        for line in stream:
            r = json.loads(line)
            ref = r["audio_slots"][0]["ref"]
            labels = r["labels"]
            if labels["speaker_count"] in (2, 3) and not labels["ge4_active"] and 40 <= ref["duration"] <= 120:
                by_recording.setdefault(ref["cut_id"], (r["id"], ref, r["metadata"]["turns"]))
    chosen = sorted(by_recording)
    rng.shuffle(chosen)
    out = {}
    for cut_id in chosen[: spec["recordings"]]:
        window_id, ref, turns = by_recording[cut_id]
        entry = {"path": str(paths[cut_id]), "offset": ref["start"], "duration": ref["duration"], "emilia2": True,
                 "recording_id": cut_id,
                 "sups": [(t["start"], t["end"], f"{cut_id}:{t['speaker']}", "".join(t["text"].split()))
                          for t in turns if t["text"].strip()]}
        if entry["sups"]:
            finish_entry(entry)
            out[window_id] = entry
    return out


def decode_m4a(path, start, duration):
    """16 kHz mono float samples of ``duration`` seconds from ``start`` with ffmpeg."""
    exe = os.environ.get("FFMPEG", "ffmpeg")
    raw = subprocess.run([exe, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(path),
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def overlapping(entry, lo, hi):
    """Utterances of a recording that overlap [lo, hi], by bisection on the start times."""
    first = bisect.bisect_left(entry["starts"], lo - entry["longest"])
    last = bisect.bisect_left(entry["starts"], hi)
    return [u for u in entry["sups"][first:last] if u[0] < hi and u[1] > lo]


def read_channel0(path, start, end):
    first = round(max(start, 0) * SR)
    w, sr = sf.read(path, start=first, stop=round(end * SR), dtype="float32", always_2d=True)
    if sr != SR:
        raise ValueError(f"{path}: expected {SR} Hz, got {sr}")
    return w[:, 0].astype(np.float32)


# --- windows -------------------------------------------------------------------


def closure(entry, lo, hi):
    """Smallest [lo, hi] containing whole utterances for every utterance that overlaps it."""
    while True:
        inside = overlapping(entry, lo, hi)
        new_lo, new_hi = min([lo] + [u[0] for u in inside]), max([hi] + [u[1] for u in inside])
        if (new_lo, new_hi) == (lo, hi):
            return lo, hi, inside
        lo, hi = new_lo, new_hi


def candidate_windows(entry, rng, duration_range=(8.0, 22.0)):
    """Non-overlapping windows over a recording, each a run of whole utterances."""
    out, cursor = [], 0.0
    for u in entry["sups"]:
        if u[0] < cursor:
            continue
        lo, hi, inside = closure(entry, u[0], u[0] + rng.uniform(*duration_range))
        if hi - lo > MAX_WINDOW or lo < cursor or hi > entry.get("duration", float("inf")):
            continue
        out.append({"lo": lo, "hi": hi, "utts": inside})
        cursor = hi + 0.5
    return out


def target_windows(entry, rng, duration_range=(8.0, 22.0)):
    """Target-anchored windows: whole utterances of one speaker, everyone else clipped to the edges.

    Per speaker, windows open 0-4 s before an utterance of theirs (never before the end of their previous
    utterance, so the target does not always speak first) and run 8-22 s from it, extended to the end of the
    last of their utterances that started inside; their windows do not overlap each other. ``utts`` holds
    the target's utterances whole and the others' clipped, ``clipped`` the clipped ones.
    """
    by_speaker = defaultdict(list)
    for u in entry["sups"]:
        by_speaker[u[2]].append(u)
    out = []
    for speaker, own in sorted(by_speaker.items()):
        cursor = -1.0
        for u in own:
            if u[0] < cursor:
                continue
            previous = max([t[1] for t in own if t[1] <= u[0]], default=0.0)
            lo = max(u[0] - rng.uniform(0.0, 4.0), previous, cursor, 0.0)
            hi = u[0] + rng.uniform(*duration_range)
            hi = max([hi] + [t[1] for t in own if u[0] <= t[0] < hi])
            if hi - lo > MAX_WINDOW or hi > entry.get("duration", float("inf")):
                continue
            utts, clipped = [], set()
            for v in overlapping(entry, lo, hi):
                if v[2] == speaker and lo <= v[0] and v[1] <= hi:
                    utts.append(v)
                elif v[2] != speaker:
                    w = (max(v[0], lo), min(v[1], hi), v[2], v[3])
                    utts.append(w)
                    if w[:2] != v[:2]:
                        clipped.add(w)
            out.append({"lo": lo, "hi": hi, "utts": sorted(utts), "clipped": clipped, "target": speaker})
            cursor = hi + 0.5
    return out


def train_speakers(spec, catalog, roots):
    """Speaker ids of the corpus's train split, to keep evaluation windows free of trained-on voices."""
    return {u[2] for entry in load_corpus(spec, catalog, roots, split="train").values() for u in entry["sups"]}


def speaker_seconds(utts):
    seconds = defaultdict(float)
    for s, e, spk, _ in utts:
        seconds[spk] += e - s
    return seconds


def eligible_enrollments(entry, speaker, window_lo, window_hi):
    """Utterances of ``speaker`` outside the window, long enough and little overlapped by others."""
    return [(s, e, text) for s, e, text in entry["eligible"].get(speaker, [])
            if not (e > window_lo - 1.0 and s < window_hi + 1.0)]


def single_room(entry, window):
    """CHiME-6: everyone in the window talks in one room (the one whose array the audio comes from)."""
    rooms = entry.get("locations")
    return rooms is None or len({rooms[u[:3]] for u in window["utts"]}) == 1


def scorable(entry, utts, speaker):
    """``speaker`` can be a window's target: none of their utterances in it is excluded (words missing from the
    transcript), and an English reference keeps a word after the scorer drops fillers."""
    own = [u for u in utts if u[2] == speaker]
    if any(u[:3] in entry.get("excluded", {}) for u in own):
        return False
    if entry.get("language") == "en":
        return any(ch.isalnum() for ch in EN_FILLERS.sub(" ", " ".join(u[3] for u in own).lower()))
    return True


def overlap_ratio(target_utts, all_utts):
    covered = total = 0.0
    for s, e, spk, _ in target_utts:
        total += e - s
        others = sorted((max(s, os_), min(e, oe)) for os_, oe, ospk, _ in all_utts if ospk != spk and oe > s and os_ < e)
        merged = []
        for a, b in others:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        covered += sum(b - a for a, b in merged)
    return covered / total if total else 0.0


def plan_samples(name, corpus, recordings, rng):
    """Paired positive and negative plans per bucket, sampled to the recipe's window quota."""
    by_bucket = defaultdict(list)
    for rid, rec in recordings.items():
        for window in candidate_windows(rec, rng):
            if not single_room(rec, window):
                continue
            present = speaker_seconds(window["utts"])
            window.update(recording=rid, present=present, speakers=len(present))
            for bucket, (lo, hi) in RECIPE["buckets"].items():
                if lo <= window["speakers"] <= hi:
                    by_bucket[bucket].append(window)
    plans = {}
    for bucket, windows in by_bucket.items():
        rng.shuffle(windows)
        chosen = []
        for window in windows:
            if len(chosen) >= corpus["windows"] // len(RECIPE["buckets"]) + (6 if bucket == "3plus" else 0):
                break
            rec = recordings[window["recording"]]
            usable = [s for s, sec in window["present"].items()
                      if sec >= MIN_TARGET_SECONDS and scorable(rec, window["utts"], s)]
            rng.shuffle(usable)
            target = next((s for s in usable if eligible_enrollments(rec, s, window["lo"], window["hi"])), None)
            if target is None:
                continue
            absent = pick_absent(window, recordings, rng, strict=corpus.get("language") == "en")
            if absent is None:
                continue
            chosen.append({"window": window, "target": target, "absent": absent})
        plans[f"real-{name}-{bucket}"] = chosen
    return plans


def pick_absent(window, recordings, rng, strict=False):
    """(recording, speaker, source) of a speaker not talking in the window, enrollable outside it.

    ``strict``: a speaker taken from another recording must not talk in the window either (the English corpora
    reuse speaker IDs across meetings).
    """
    rec = recordings[window["recording"]]
    speakers_in_recording = {u[2] for u in rec["sups"]}
    absent = [s for s in sorted(speakers_in_recording - set(window["present"]))
              if eligible_enrollments(rec, s, window["lo"], window["hi"])]
    if absent:
        return window["recording"], rng.choice(absent), "same_recording"
    pool = [(r, s) for r, other in sorted(recordings.items()) if r != window["recording"]
            for s in sorted({u[2] for u in other["sups"]})
            if eligible_enrollments(other, s, -1e9, -1e9) and not (strict and s in window["present"])]
    if not pool:
        return None
    absent_recording, absent_speaker = rng.choice(pool)
    return absent_recording, absent_speaker, "other_recording"


def overlap_bucket(ratio):
    for bucket, (lo, hi) in OVERLAP_BUCKETS.items():
        if (lo <= ratio <= hi) if bucket == "o0" else (lo < ratio <= hi):
            return bucket
    raise ValueError(ratio)


def plan_overlap_samples(name, corpus, recordings, rng, prefix):
    """Paired plans of target-anchored windows per overlap bucket, sampled to the corpus quota.

    Windows of different targets may cover the same stretch of a recording; a window that shares more
    than half of itself with one already chosen is skipped, so no stretch is scored twice.
    """
    by_bucket = defaultdict(list)
    for rid, rec in sorted(recordings.items()):
        for window in target_windows(rec, rng):
            target_utts = [u for u in window["utts"] if u[2] == window["target"]]
            if (sum(e - s for s, e, _, _ in target_utts) < MIN_TARGET_SECONDS
                    or not eligible_enrollments(rec, window["target"], window["lo"], window["hi"])):
                continue
            present = speaker_seconds(window["utts"])
            ratio = overlap_ratio(target_utts, window["utts"])
            window.update(recording=rid, present=present, speakers=len(present), overlap=ratio)
            by_bucket[overlap_bucket(ratio)].append(window)
    plans, taken = {}, defaultdict(list)
    for bucket, quota in corpus["windows"].items():
        windows = by_bucket[bucket]
        rng.shuffle(windows)
        chosen = []
        for window in windows:
            if len(chosen) >= quota:
                break
            lo, hi = window["lo"], window["hi"]
            if any(min(hi, b) - max(lo, a) > 0.5 * min(hi - lo, b - a) for a, b in taken[window["recording"]]):
                continue
            absent = pick_absent(window, recordings, rng)
            if absent is None:
                continue
            chosen.append({"window": window, "target": window["target"], "absent": absent})
            taken[window["recording"]].append((lo, hi))
        plans[f"{prefix}-{name}-{bucket}"] = chosen
    return plans


# --- rendering ------------------------------------------------------------------


_DECODED = {}


def cut(recordings, recording, start, end):
    entry = recordings[recording]
    if entry.get("emilia2"):  # the whole window is decoded once and sliced
        if recording not in _DECODED:
            _DECODED.clear()
            _DECODED[recording] = decode_m4a(entry["path"], entry["offset"], entry["duration"])
        return _DECODED[recording][round(max(start, 0) * SR):round(end * SR)]
    if "samples" in entry:  # decoded at load time (ICSI)
        return entry["samples"][round(max(start, 0) * SR):round(end * SR)]
    if "paths" in entry:  # one array per room (CHiME-6)
        return read_channel0(entry["paths"][_english().location_at(entry, start, end)], start, end)
    return read_channel0(entry["path"], start, end)


def check_cut(recordings, recording, start, end):
    """Audio for the voice check: the sum of the close-talk microphones where the corpus has them (on the
    transcript's time base, before ``offset_s``), else the channel the set is cut from."""
    entry = recordings[recording]
    if "close_talk" not in entry:
        return cut(recordings, recording, start, end)
    first = round((start - entry.get("offset_s", 0.0)) * SR)
    count = round((end - start) * SR)
    total = np.zeros(count, dtype=np.float32)
    for path in entry["close_talk"]:
        w = read_channel0(path, max(first, 0) / SR, (first + count) / SR)
        total[max(-first, 0):max(-first, 0) + len(w)] += w[: count - max(-first, 0)]
    return total


def check_view(entry):
    return "close_talk_sum" if "close_talk" in entry else "mixture_channel"


def verified_enrollment(checker, recordings, recording, speaker, first, lo, hi, key, pieces, audio):
    """(first, pieces, audio, verdict, failed verdict or None) of an enrollment that passes the voice check:
    the given one, else another eligible utterance of the speaker (``key``'s own order); None if none passes."""
    verdict = checker.check(recordings, recording, speaker, pieces)
    if verdict["passed"]:
        return first, pieces, audio, verdict, None
    entry = recordings[recording]
    alternatives = [(s, min(e, s + ENROLL_MAX)) for s, e, _ in eligible_enrollments(entry, speaker, lo, hi) if s != first[0]]
    random.Random(f"{key}:voice-check").shuffle(alternatives)
    for alternative in alternatives[:VOICE_ATTEMPTS]:
        new_pieces = enrollment_pieces(entry, speaker, alternative, lo, hi, random.Random(f"{key}:enroll-pieces"))
        new_verdict = checker.check(recordings, recording, speaker, new_pieces)
        if new_verdict["passed"]:
            return alternative, new_pieces, cut_pieces(recordings, recording, new_pieces), new_verdict, verdict
    checker.events.append({"key": key, "recording": recording, "speaker": speaker, "verdict": verdict,
                           "alternatives_tried": min(len(alternatives), VOICE_ATTEMPTS)})
    return None


def render(plan, name, corpus, recordings, rng, out_dir, split, index, checker=None):
    window = plan["window"]
    rec = recordings[window["recording"]]
    mix = cut(recordings, window["recording"], window["lo"], window["hi"])
    if abs(len(mix) / SR - (window["hi"] - window["lo"])) > 0.05:
        raise ValueError(f"{window['recording']}: the audio is shorter than its annotation")
    target = plan["target"]
    target_utts = sorted(u for u in window["utts"] if u[2] == target)
    enroll_s, enroll_e, _ = rng.choice(eligible_enrollments(rec, target, window["lo"], window["hi"]))
    absent_recording, absent_speaker, absent_source = plan["absent"]
    absent_rec = recordings[absent_recording]
    absent_s, absent_e, _ = rng.choice(eligible_enrollments(absent_rec, absent_speaker, -1e9, -1e9)
                                       if absent_source == "other_recording" else
                                       eligible_enrollments(absent_rec, absent_speaker, window["lo"], window["hi"]))
    files, pieces, firsts, checks, replaced = {}, {}, {}, {}, {}
    for kind, (recording, start, end, speaker) in {
        "pos": (window["recording"], enroll_s, min(enroll_e, enroll_s + ENROLL_MAX), target),
        "neg": (absent_recording, absent_s, min(absent_e, absent_s + ENROLL_MAX), absent_speaker),
    }.items():
        lo, hi = (window["lo"], window["hi"]) if recording == window["recording"] else (-1e9, -1e9)
        # Own stream per record: the windows and first utterances do not depend on the appended ones.
        own = random.Random(f"{split}-{kind}:{index:04d}:enroll-pieces")
        pieces[kind] = enrollment_pieces(recordings[recording], speaker, (start, end), lo, hi, own)
        files[kind] = cut_pieces(recordings, recording, pieces[kind])
        firsts[kind] = (start, end)
        if checker is not None:
            picked = verified_enrollment(checker, recordings, recording, speaker, (start, end), lo, hi,
                                         f"{split}-{kind}:{index:04d}", pieces[kind], files[kind])
            if picked is None:
                checker.stats[(name, kind, "dropped")] += 1
                del files[kind]
                continue
            firsts[kind], pieces[kind], files[kind], checks[kind], failed = picked
            checker.stats[(name, kind, "replaced" if failed else "passed")] += 1
            if failed:
                replaced[kind] = {"start": round(start, 3), "end": round(end, 3), "voice_check": failed}
    base = f"{split}-{index:04d}"
    results = []
    for kind in [k for k in ("pos", "neg") if k in files]:
        sample = f"{split}-{kind}"
        entries = []
        for suffix, w in (("mix", mix), ("enroll", files[kind])):
            relative = f"audio/{sample}/{base}-{kind}-{suffix}.wav"
            synth.write_wav(out_dir / relative, w)
            entries.append({"cut_id": f"{base}-{kind}-{suffix}", "relative_path": relative,
                            "num_frames": len(w), "duration": round(len(w) / SR, 4),
                            "sha256": synth.sha256_file(out_dir / relative)})
        present = kind == "pos"
        labels = {
            "scenario": sample, "group": "real", "kind": kind, "target_present": present, "corpus": name,
            "recording": window["recording"], "duration_s": round(window["hi"] - window["lo"], 3),
            "speakers_in_window": window["speakers"], "window_start_s": round(window["lo"], 3),
            "n_interferers": window["speakers"] - (1 if present else 0),
            "mixture_rms_dbfs": round(float(20 * np.log10(np.sqrt(np.mean(mix ** 2)) + 1e-9)), 2),
            "annotation": corpus.get("annotation", "human"),
        }
        if "overlap" in window:
            labels["overlap_bucket"] = overlap_bucket(window["overlap"])
        if present:
            labels["target_overlap_ratio"] = round(overlap_ratio(target_utts, window["utts"]), 3)
            labels["target_seconds"] = round(sum(e - s for s, e, _, _ in target_utts), 2)
        else:
            labels["absent_source"] = absent_source
        speaker = target if present else absent_speaker
        enroll_rec = window["recording"] if present else absent_recording
        labels["enroll_seconds"] = round(len(files[kind]) / SR, 3)
        labels["enroll_others_s"] = pieces_others(recordings[enroll_rec], speaker, pieces[kind])[0]
        labels["enroll_condition"] = "clean" if labels["enroll_others_s"] < ENROLL_CROP_OTHERS_MAX else "others_speech"
        excluded = rec.get("excluded", {})
        metadata = {
            "split": sample, "index": index, "target_speaker": f"{name}:{speaker}",
            "enrollment": {"recording": enroll_rec, "start": round(firsts[kind][0], 3), "end": round(firsts[kind][1], 3)},
            "enrollment_pieces": [[round(s, 3), round(e, 3)] for s, e in pieces[kind]],
            "window_utts": [{"speaker": f"{name}:{spk}", "start": round(s - window["lo"], 3),
                             "duration": round(e - s, 3), "text": text,
                             **({"clipped": True} if (s, e, spk, text) in window.get("clipped", ()) else {}),
                             **({"excluded": excluded[(s, e, spk)]} if (s, e, spk) in excluded else {})}
                            for s, e, spk, text in sorted(window["utts"])],
        }
        if "source" in rec:
            metadata["mixture_source"] = (rec["arrays"][_english().location_at(rec, window["lo"], window["hi"])]
                                          if "arrays" in rec else rec["source"])
        if "offset_s" in rec:
            metadata["timeline_offset_s"] = rec["offset_s"]
        if kind in checks:
            metadata["enroll_voice_check"] = checks[kind]
        if kind in replaced:  # as ts_asr_real v3: the first utterance drawn sounded like someone else
            metadata["enrollment_replaced"] = replaced[kind]
        joiner = JOINERS[corpus.get("language", "zh")]
        results.append({"split": sample, "index": index, "target": joiner.join(t for *_, t in target_utts) if present else "",
                        "labels": labels, "metadata": metadata, "entries": entries})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--limit", type=int, help="windows per bucket (smoke runs)")
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--recipe", choices=sorted(RECIPES), default="v2")
    parser.add_argument("--embed-python", type=Path, help="Python with onnxruntime and torchaudio (voice_check recipes)")
    parser.add_argument("--speaker-model", type=Path, default=Path(SPEAKER_MODEL))
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    recipe_spec = RECIPES[args.recipe]
    if recipe_spec.get("voice_check") and not args.embed_python:
        parser.error(f"recipe {args.recipe} checks enrollment voices: pass --embed-python")
    version = recipe_spec["version"]
    data_root = Path(roots[DATASET_ID])
    final = data_root / "source" / version
    if (data_root / "versions" / version).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {version}")
    catalog = load_catalog(args.catalog)
    partial = data_root / "source" / (version + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    splits, results, excluded = [], [], []
    seed = recipe_spec["seed"]
    rng = random.Random(seed)
    language, enrollmix = recipe_spec.get("language", "zh"), recipe_spec.get("enrollmix", False)
    report, checker = {"language": language}, None
    if recipe_spec.get("voice_check"):
        voice = _sibling("voice_check")
        checker = voice.VoiceCheck(voice.Embedder(args.embed_python, args.speaker_model), check_cut, ENROLL_CROP,
                                   ENROLL_STORE, check_view)
    for name, corpus in recipe_spec["corpora"].items():
        corpus = {**corpus, **({"language": language, "enrollmix": enrollmix} if language != "zh" else {})}
        recordings = load_recordings(name, corpus, catalog, roots, seed, report)
        if corpus.get("kind") == "emilia2":
            excluded = sorted({e["recording_id"] for e in recordings.values()})
        if recipe_spec.get("exclude_train_speakers"):
            trained = train_speakers(corpus, catalog, roots)
            dropped = sorted(r for r, e in recordings.items() if trained & {u[2] for u in e["sups"]})
            recordings = {r: e for r, e in recordings.items() if r not in dropped}
            print(name, "dropped recordings with train speakers:", dropped, flush=True)
        if recipe_spec.get("windowing") == "target":
            plans = plan_overlap_samples(name, corpus, recordings, random.Random(f"{seed}:{name}"),
                                         recipe_spec["prefix"])
        else:
            plans = plan_samples(name, corpus, recordings, random.Random(f"{seed}:{name}"))
        counts = Counter()
        for split, chosen in sorted(plans.items()):
            if args.limit:
                chosen = chosen[: args.limit]
            for index, plan in enumerate(chosen):
                for result in render(plan, name, corpus, recordings, rng, partial, split, index, checker):
                    if enrollmix and result["labels"]["enroll_condition"] != "clean":
                        result["split"] += ENROLLMIX
                        result["labels"]["scenario"] = result["metadata"]["split"] = result["split"]
                    counts[result["split"]] += 1
                    results.append(result)
            for kind in ("pos", "neg"):
                if not enrollmix:
                    splits.append({"name": f"{split}-{kind}", "group": "real", "params": {"corpus": name, "kind": kind}, "n": len(chosen)})
                    continue
                for suffix, extra in (("", {}), (ENROLLMIX, {"enroll_condition": "others_speech"})):
                    if counts[f"{split}-{kind}{suffix}"]:
                        splits.append({"name": f"{split}-{kind}{suffix}", "group": "real",
                                       "params": {"corpus": name, "kind": kind, **extra}, "n": counts[f"{split}-{kind}{suffix}"]})
        print(name, {s: len(c) for s, c in plans.items()}, flush=True)
        if language != "zh":
            report.setdefault("corpora", {})[name] = {
                "recordings": len(recordings), "windows_planned": {s: len(c) for s, c in sorted(plans.items())},
                "records": dict(sorted(counts.items())),
                "sources": {r: e.get("source") for r, e in sorted(recordings.items())
                            if any(p["window"]["recording"] == r for c in plans.values() for p in c)}}
    if checker is not None:
        checker.embed.close()
        report["voice_check"] = {"counts": {"/".join(k): v for k, v in sorted(checker.stats.items())},
                                 "dropped": checker.events}
    (partial).mkdir(parents=True, exist_ok=True)
    if language != "zh":
        (partial / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if excluded or args.recipe == "v2":
        (partial / "excluded-recordings.txt").write_text("\n".join(excluded) + "\n")
    partial.rename(final)
    recipe = {"version": version, "dataset_id": DATASET_ID, "pools": {}, "language": language}
    declaration = synth.register(recipe, splits, results, data_root, DATASET_ID)
    if declaration["languages"] != [language]:  # register() takes the language from the recipe since 2026-10-31
        raise RuntimeError(f"ts_benchmark/build.py register() wrote {declaration['languages']}, expected {language}")
    declaration["provenance"] = {
        "status": "complete", "synthetic": "none",
        "description": recipe_spec.get("description") or "真实对话的目标说话人窗口：从 AliMeeting 远场、AISHELL-4 远场、MagicData-RAMC 手机通话的人工标注测试集，"
                       "以及 Emilia2 网络爬取的对话（MOSS 说话人日志伪标签）里按完整语句切出 8–22 秒窗口，不做任何混合；"
                       "同一窗口配一条目标在场（注册取窗外的另一条语句）和一条目标缺席的样本。只用于评测，不进训练；"
                       "所用 Emilia2 录音列在 source/<版本>/excluded-recordings.txt，训练必须排除。",
        "sources": [f"{c['dataset']}@{c['version']}:{c['split']}" for c in recipe_spec["corpora"].values()],
    }
    if args.no_register:
        return
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", version, len(results), "samples")


if __name__ == "__main__":
    main()
