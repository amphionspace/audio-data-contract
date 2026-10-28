#!/usr/bin/env python3
"""Build and register the police scene simulation benchmark (police_scene_bench).

One split per concrete usage scenario of the acceptance sheet (技术指标_场景分级拆分), ``default_n``
samples each, following ``recipe.yaml``. The officer wearing the device speaks near the microphone
(no room response); everyone else stands 1-2 m away and gets a measured room response of the
scenario's place (MIT IR survey). The noise is a real recording bed (DEMAND, or synthetic Chinese
babble from test talkers) plus FSD50K evaluation events of the place, scaled to the level's SNR
against the officer's speech level.

Forms (see the recipe): ``short`` and ``long`` are ``asr`` records, ``meeting`` is
``speaker_attributed_asr`` with every segment's speaker and times, ``owner`` is ``ts_asr`` with an
enrollment slot, ``context`` puts a context-correction item into the scene. Term splits also get a
``-hw300`` copy whose records reference the same audio and carry a 300-word police hotword list.
A split can also pass the scene through a PDT radio link (``channel: pdt``), the body-worn recorder
(``device``: clipping, high-pass, AGC) or move the officer away from the device (``far_field``);
``variant_of`` renders another split's exact plans with only those changed, for paired comparison.

Speech comes from the police synthetic test split (dev only when a short pool runs out); neither is
used in training. Planning runs in order in the main process, rendering in workers.

    python scripts/police_scene_bench/build.py --roots /workspace/data/registry/roots.json --workers 32
"""

from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import json
import multiprocessing
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts" / "ts_benchmark"))
import mixer

# The target-speaker benchmark's helpers (audio I/O, registration I/O), loaded under another name.
_spec = importlib.util.spec_from_file_location("ts_build", REPO / "scripts" / "ts_benchmark" / "build.py")
ts_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts_build)

from audio_data_contract import AudioRecord, load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

SR = mixer.SAMPLE_RATE
GENERATOR_VERSION = "1"
DIGITS = "零〇幺一二两三四五六七八九0-9"
DIGIT_RUN = re.compile(f"[{DIGITS}]{{6,}}[{DIGITS}叉Xx]*")
PLATE = re.compile("[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Za-z]")
TRAILING_PUNCT = "，。！？、,.!?;；： "
# FSD50K labels of clips with intelligible voices; left out of events unless the place is a crowd
VOICE_LABELS = {"Speech", "Male_speech_and_man_speaking", "Female_speech_and_woman_speaking",
                "Child_speech_and_kid_speaking", "Conversation", "Speech_synthesizer", "Singing", "Male_singing",
                "Female_singing", "Whispering"}
G = {}  # worker-global state, set before the pool forks
FORK = multiprocessing.get_context("fork")  # Python 3.14 defaults to forkserver, which would not see G


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Utt:
    id: str
    speaker: str
    text: str
    duration: float
    path: str
    split: str
    category: str | None
    profile: str | None
    terms: tuple[str, ...]


def number_kinds(text):
    """Spoken numbers in a text: 11 digits = phone, 17-18 = ID card, province + letter = plate."""
    kinds = set()
    for match in DIGIT_RUN.finditer(text):
        if len(match.group()) == 11:
            kinds.add("phone")
        elif len(match.group()) in (17, 18):
            kinds.add("id")
    if PLATE.search(text):
        kinds.add("plate")
    return kinds


def join_texts(texts):
    return "，".join(t.rstrip(TRAILING_PUNCT) for t in texts)


# --- sources -------------------------------------------------------------------------


def load_police(recipe, catalog, roots):
    utts = []
    for source in recipe["speech"]["police"]:
        paths = {role: resolve_split(catalog, source["dataset"], source["version"], source["split"], role, roots)
                 for role in ("recordings", "supervisions")}
        audio = {r["id"]: r["sources"][0]["source"] for path in paths["recordings"] for r in ts_build._rows(path)}
        for row in (row for path in paths["supervisions"] for row in ts_build._rows(path)):
            custom = row.get("custom") or {}
            if row.get("start", 0) != 0 or row["recording_id"] not in audio or not (row.get("text") or "").strip():
                continue
            utts.append(Utt(
                id=f"{source['split']}:{row['id']}", speaker=row["speaker"], text=row["text"].strip(),
                duration=float(row["duration"]), path=audio[row["recording_id"]], split=source["split"],
                category=(custom.get("source_metadata") or {}).get("category"), profile=custom.get("speech_profile"),
                terms=tuple(custom.get("target_terms") or ())))
    for source in recipe["speech"].get("extra", []):  # manifests this benchmark synthesized itself
        base = Path(roots[source["alias"]])
        audio = {r["id"]: r["sources"][0]["source"] for r in ts_build._rows(base / source["recordings"])}
        for row in ts_build._rows(base / source["supervisions"]):
            custom = row.get("custom") or {}
            utts.append(Utt(
                id=f"{source['name']}:{row['id']}", speaker=row["speaker"], text=row["text"].strip(),
                duration=float(row["duration"]), path=audio[row["recording_id"]], split=source["name"],
                category=(custom.get("source_metadata") or {}).get("category"), profile=custom.get("speech_profile"),
                terms=tuple(custom.get("target_terms") or ())))
    return utts


def speech_splits(recipe):
    """Order in which pools draw: the police test split, its dev split, then the synthesized extras."""
    return [s["split"] for s in recipe["speech"]["police"]] + [s["name"] for s in recipe["speech"].get("extra", [])]


def build_pools(recipe, utts):
    pools = {}
    police = [s["split"] for s in recipe["speech"]["police"]]
    for name, spec in recipe["pools"].items():
        lo, hi = spec.get("seconds", [0.0, 1e9])
        terms = sorted(spec.get("terms", []), key=len, reverse=True)
        term_re = re.compile("|".join(map(re.escape, terms))) if terms else None
        pattern = re.compile(spec["pattern"]) if "pattern" in spec else None
        allowed = set(spec.get("splits", police))
        keep = []
        for u in utts:
            if u.split not in allowed:
                continue
            if not lo <= u.duration <= hi or u.category in spec.get("exclude_categories", ()):
                continue
            if "categories" in spec and u.category not in spec["categories"]:
                continue
            if "profiles" in spec and u.profile not in spec["profiles"]:
                continue
            if "numbers" in spec and not number_kinds(u.text) & set(spec["numbers"]):
                continue
            if (pattern and not pattern.search(u.text)) or (term_re and not term_re.search(u.text)):
                continue
            keep.append(u)
        pools[name] = {"utts": keep, "terms": terms}
    return pools


def load_context(recipe, catalog, roots):
    spec = recipe["speech"]["context"]
    items = []
    for split in spec["splits"]:
        index = {}
        for path in resolve_split(catalog, spec["dataset"], spec["version"], split, "audio_index", roots):
            for row in ts_build._rows(path):
                index[row["cut_id"]] = str(Path(roots[row["root_alias"]]) / row["relative_path"])
        for path in resolve_split(catalog, spec["dataset"], spec["version"], split, "records", roots):
            for record in ts_build._rows(path):
                ref = record["audio_slots"][0]["ref"]
                items.append({"id": record["id"], "path": index[ref["cut_id"]], "duration": ref["duration"],
                              "target": record["target"], "context": record["labels"]["context_correction"]})
    return items


def noise_assets(recipe, roots):
    """Bed files per name, FSD50K evaluation clips per label, MIT room responses per place."""
    beds = {"babble_zh": sorted(str(p) for p in (Path(roots["asr_babble_bench"]) / "source" / "v2-20261023" / "babble"
                                                 / "zh").glob("*.flac"))}
    demand = Path(roots["demand"]) / "source" / "zenodo-1227121-16k-20261023" / "extracted"
    for env in recipe["environments"].values():
        for bed in env["beds"]:
            if bed.startswith("demand/"):
                beds[bed] = sorted(str(p) for p in (demand / bed.split("/", 1)[1]).glob("ch*.wav"))
    base = Path(roots["open_noise"]) / "fsd50k" / "extracted"
    wanted = {label for env in recipe["environments"].values() for label in env["events"]}
    events = defaultdict(lambda: defaultdict(list))  # voices allowed? -> label -> [(path, seconds)]
    with (base / "FSD50K.ground_truth" / "eval.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            labels = set(row["labels"].split(","))
            if not labels & wanted:
                continue
            path = base / "FSD50K.eval_audio" / f"{row['fname']}.wav"
            seconds = sf.info(path).duration
            if seconds < 1.0:
                continue
            for label in labels & wanted:
                events[True][label].append((str(path), seconds))
                if not labels & VOICE_LABELS:
                    events[False][label].append((str(path), seconds))
    mit = Path(roots["mit_ir_survey"]) / "versions" / "flac16k-20261026"
    places = json.loads((mit / "manifests" / "mit_ir_survey_places.json").read_text())
    by_place = defaultdict(list)
    recordings = {r["id"]: r["sources"][0]["source"]
                  for r in ts_build._rows(mit / "manifests" / "mit_ir_survey_recordings_all.jsonl.gz")}
    for place in places:
        name = re.sub(r"^h\d+_", "", place["source_file"]).split("_")[0]
        source = recordings[place["id"]]
        by_place[name].append(source if source.startswith("/") else str(mit / source))
    return beds, {k: {label: sorted(v) for label, v in d.items()} for k, d in events.items()}, dict(by_place)


# --- planning --------------------------------------------------------------------------


def ordered(utts, rng, split_order):
    """Utterances of the first speech split first, each split in a seeded random order."""
    out = []
    for split in split_order:
        items = sorted((u for u in utts if u.split == split), key=lambda u: u.id)
        rng.shuffle(items)
        out += items
    return out


class Drawer:
    """Unique utterances for one split: record ``i`` draws from pool ``i % len(pools)``, at most ``cap`` per text."""

    def __init__(self, pools, names, rng, cap, split_order):
        self.names, self.cap = list(names), cap
        self.queues = [ordered(pools[n]["utts"], rng, split_order) for n in self.names]
        self.pos = [0] * len(self.names)
        self.used, self.texts = set(), Counter()

    def take(self, index):
        k = index % len(self.names)
        queue = self.queues[k]
        while self.pos[k] < len(queue):
            u = queue[self.pos[k]]
            self.pos[k] += 1
            if u.id not in self.used and self.texts[u.text] < self.cap:
                self.mark(u)
                return self.names[k], u
        raise PlanError(f"pool {self.names[k]} ran out")

    def mark(self, u):
        self.used.add(u.id)
        self.texts[u.text] += 1


def as_list(value):
    return list(value) if isinstance(value, list) else [value]


def plan_noise(rng, recipe, env_name, seconds, level):
    env = recipe["environments"][env_name]
    beds, events = G["beds"], G["events"][bool(env.get("speech_events"))]
    bed = rng.choice(env["beds"])
    plan = {"env": env_name, "snr_db": round(rng.uniform(*recipe["levels"][level]["snr_db"]), 2),
            "bed": {"kind": bed, "files": [], "offset_s": 0.0}, "babble": None, "events": []}

    def stream(kind):  # one file long enough, or babble clips back to back
        files = beds[kind]
        if kind == "babble_zh":
            count = int(seconds // 30.0) + 2
            return {"kind": kind, "files": rng.sample(files, count), "offset_s": round(rng.uniform(0.0, 30.0), 3)}
        path = rng.choice(files)
        length = sf.info(path).duration
        return {"kind": kind, "files": [path], "offset_s": round(rng.uniform(0.0, max(length - seconds, 0.0)), 3)}

    plan["bed"] = stream(bed)
    if bed != "babble_zh" and rng.random() < env.get("babble", 0.0):
        plan["babble"] = {**stream("babble_zh"), "gain_db": round(rng.uniform(-8.0, -2.0), 2)}
    if env["events"]:
        count = round(seconds / 10.0 * rng.uniform(*recipe["event_rate"]))
        for _ in range(max(count, 1)):
            label = rng.choice([e for e in env["events"] if events.get(e)])
            path, length = rng.choice(events[label])
            take = min(length, recipe["event_max_seconds"], seconds)
            plan["events"].append({"label": label, "file": path, "clip_offset_s": round(rng.uniform(0.0, length - take), 3),
                                   "seconds": round(take, 3), "start_s": round(rng.uniform(0.0, max(seconds - take, 0.0)), 3),
                                   "gain_db": round(rng.uniform(*recipe["event_gain_db"]), 2)})
    return plan


def room_response(rng, recipe, env_name):
    places = [p for p in recipe["environments"][env_name]["rir_places"] if p in G["rirs"]]
    return rng.choice(G["rirs"][rng.choice(places)]) if places else None


def turns_plan(rng, recipe, split, speakers, utts_by_speaker, seconds, key_utt=None):
    """Turns of ``speakers`` (S1 first) until ``seconds``: each speaker at least once, never twice in a row.

    ``key_utt`` (a line with the scenario's terms) is its speaker's first turn.
    """
    remaining = {s: [u for u in utts_by_speaker[s] if key_utt is None or u.id != key_utt.id] for s in speakers}
    for s in speakers:
        rng.shuffle(remaining[s])
    if key_utt is not None:
        remaining[key_utt.speaker].append(key_utt)  # popped first
    order = [speakers[0]] + rng.sample(speakers[1:], len(speakers) - 1)
    turns, now, last = [], rng.uniform(*recipe["padding_seconds"]), None
    while order or now < seconds:
        if order:
            s = order.pop(0)
        else:
            choices = [x for x in speakers if x != last and remaining[x]] or [x for x in speakers if remaining[x]]
            if not choices:
                break
            s = rng.choice(choices)
        if not remaining[s]:
            continue
        u = remaining[s].pop()
        start = now
        if turns and split.get("overlap") and turns[-1]["speaker"] != s and rng.random() < split["overlap"]:
            prev = turns[-1]
            start = max(prev["start"] + 0.5, prev["start"] + prev["utt"].duration
                        - rng.uniform(0.3, min(1.5, 0.5 * prev["utt"].duration)))
        turns.append({"speaker": s, "utt": u, "start": round(start, 3)})
        now = max(now, start + u.duration) + rng.uniform(0.3, 1.2 if split["form"] == "long" else 1.0)
        last = s
    return turns


def plan_split(recipe, split, pools, by_speaker, context, owner_index):
    seed, name, n = recipe["seed"], split["name"], split["n"]
    rng = random.Random(f"{seed}:{name}")
    order = speech_splits(recipe)
    first_split = order[0]
    form, plans = split["form"], []
    drawer = (Drawer(pools, as_list(split["pool"]), rng, recipe["max_text_repeats"], order)
              if form in ("short", "owner") else None)
    if form == "context":
        wanted = set(split["scenarios"])
        contexts = sorted((c for c in context if c["context"].get("scenario") in wanted), key=lambda c: c["id"])
        rng.shuffle(contexts)
        if len(contexts) < n:
            raise PlanError(f"{name}: {len(contexts)} context items")
    used = set()
    for index in range(n):
        r = random.Random(f"{seed}:{name}:{index}")
        env = r.choice(as_list(split["env"]))
        plan = {"env": env, "floor": {"kind": r.choice(recipe["noise_floor"]["kinds"]),
                                      "dbfs": round(r.uniform(*recipe["noise_floor"]["dbfs"]), 2),
                                      "seed": r.getrandbits(32)}}
        lead, trail = (round(r.uniform(*recipe["padding_seconds"]), 3) for _ in range(2))
        if form == "short":
            pool, first = drawer.take(index)
            utts = [first]
            if "count" in split:  # the same officer reads several of them; skip speakers with only one
                want = r.randint(*split["count"])
                while True:
                    same = sorted((u for u in pools[pool]["utts"] if u.speaker == first.speaker
                                   and u.id not in drawer.used and u.text != first.text), key=lambda u: u.id)
                    if same:
                        break
                    pool, first = drawer.take(index)
                r.shuffle(same)
                utts = [first] + same[:want - 1]
                for u in utts[1:]:
                    drawer.mark(u)
            turns, now = [], lead
            for u in utts:
                turns.append({"speaker": u.speaker, "utt": u, "start": round(now, 3)})
                now += u.duration + r.uniform(0.5, 1.5)
            plan.update(pool=pool, turns=turns)
        elif form in ("long", "meeting"):
            k = r.randint(*split["speakers"])
            key = None
            if "key_pool" in split:
                keys = [u for u in pools[split["key_pool"]]["utts"] if u.split == first_split and u.id not in used]
                key = r.choice(sorted(keys, key=lambda u: u.id))
            pool = split["pool"]
            pool_speakers = sorted(s for s, us in by_speaker[pool].items() if len(us) >= 4)
            speakers = [key.speaker] if key else []
            speakers += r.sample([s for s in pool_speakers if s not in speakers], k - len(speakers))
            if key:  # the officer (S1) is someone else than the key line's speaker half of the time
                r.shuffle(speakers)
            avail = {s: [u for u in by_speaker[pool].get(s, []) if u.id not in used] or by_speaker[pool].get(s, [])
                     for s in speakers}
            turns = turns_plan(r, recipe, split, speakers, avail, r.uniform(*split["seconds"]), key)
            used.update(t["utt"].id for t in turns)
            plan.update(pool=pool, turns=turns, speakers=speakers)
        elif form == "owner":
            pool, owner_utt = drawer.take(index)
            owner = owner_utt.speaker
            enroll_choices = sorted((u for u in owner_index[owner] if u.text != owner_utt.text and 2.0 <= u.duration <= 8.0),
                                    key=lambda u: u.id)
            r.shuffle(enroll_choices)
            enroll, total = [], 0.0
            for u in enroll_choices:
                if total >= 4.0:
                    break
                enroll.append(u)
                total += u.duration
            if total < 4.0:
                raise PlanError(f"{name}: owner {owner} has too little enrollment speech")
            absent = r.random() < split.get("absent", 0.0)
            others = r.sample(sorted(s for s in by_speaker["dialogue"] if s != owner), r.randint(*split["interferers"]))
            lines, same_text = [], False
            for j, s in enumerate(others):
                if j == 0 and r.random() < split.get("same_text", 0.0):
                    twins = sorted((u for u in G["by_text"][owner_utt.text] if u.speaker != owner), key=lambda u: u.id)
                    if twins:
                        lines.append(r.choice(twins))
                        same_text = True
                        continue
                lines.append(r.choice(by_speaker["dialogue"][s]))
            items = ([] if absent else [("owner", owner_utt)]) + [("other", u) for u in lines]
            turns = []
            if split["mode"] == "separate":
                r.shuffle(items)
                now = lead
                for role, u in items:
                    turns.append({"speaker": u.speaker, "utt": u, "start": round(now, 3), "role": role})
                    now += u.duration + r.uniform(0.3, 1.0)
            else:  # overlap: everyone starts around the owner's sentence
                anchor = owner_utt.duration
                for role, u in items:
                    start = 0.0 if role == "owner" else r.uniform(-0.6 * u.duration, 0.8 * anchor)
                    turns.append({"speaker": u.speaker, "utt": u, "start": start, "role": role})
                shift = lead - min(t["start"] for t in turns)
                for t in turns:
                    t["start"] = round(t["start"] + shift, 3)
            plan.update(pool=pool, turns=turns, enroll=enroll, owner=owner, owner_utt=owner_utt, absent=absent,
                        same_text=same_text)
        else:  # context
            item = contexts[index]
            plan.update(context=item, turns=[{"speaker": "context", "utt": None, "start": lead,
                                              "duration": item["duration"]}])
        seconds = max(t["start"] + (t["utt"].duration if t["utt"] else t["duration"]) for t in plan["turns"]) + trail + 0.5
        plan["noise"] = plan_noise(r, recipe, env, seconds, split["level"])
        plan["rir"] = room_response(r, recipe, env)
        plan["gains"] = {}
        for t in plan["turns"]:
            officer = (t.get("role") == "owner" or form in ("short", "context")
                       or (form in ("long", "meeting") and t["speaker"] == plan["speakers"][0]))
            t["officer"] = officer
            if not officer and t["speaker"] not in plan["gains"]:
                plan["gains"][t["speaker"]] = round(r.uniform(*recipe["other_gain_db"]), 2)
        plan["trail"] = trail
        plan_channels(r, recipe, split, plan)
        plans.append(plan)
    return plans


def plan_channels(rng, recipe, split, plan):
    """Radio link, recorder chain and far-field officer of a split, drawn per sample (last, so they do not
    change the other draws)."""
    if split.get("channel") == "pdt":
        spec = recipe["pdt"]
        plan["pdt"] = {"codec": rng.choice(spec["codecs"]), "drive": round(rng.uniform(*spec["drive"]), 2),
                       "loss": round(rng.uniform(*spec["frame_loss"]), 4), "seed": rng.getrandbits(32),
                       "pre_s": round(rng.uniform(*spec["key_up_s"]), 3), "post_s": round(rng.uniform(*spec["hang_s"]), 3),
                       "squelch_s": round(rng.uniform(*spec["squelch_s"]), 3),
                       "squelch_dbfs": round(rng.uniform(*spec["squelch_dbfs"]), 2), "beep": rng.random() < spec["beep"]}
    if split.get("device"):
        spec = recipe["device"]
        plan["device"] = {"overload_db": round(rng.uniform(*spec["overload_db"][split["level"]]), 2),
                          "highpass_hz": round(rng.uniform(*spec["highpass_hz"])), "agc_dbfs": spec["agc_dbfs"],
                          "agc_max_gain_db": spec["agc_max_gain_db"]}
    if split.get("far_field"):
        plan["officer_rir"] = True


# --- rendering -------------------------------------------------------------------------


def read_span(path, offset_s, n):
    """``n`` samples from ``offset_s`` of a 16 kHz file; wraps around if the file is shorter."""
    info = sf.info(path)
    if info.samplerate != SR:  # FSD50K is 44.1 kHz: resample the whole (short) clip
        w = ts_build.read_audio(path)
        start = min(int(offset_s * SR), max(len(w) - n, 0))
        w = w[start:start + n]
    else:
        start = min(int(offset_s * SR), max(info.frames - n, 0))
        w, _ = sf.read(path, start=start, stop=start + n, dtype="float32", always_2d=False)
        if w.ndim > 1:
            w = w.mean(axis=1)
    if len(w) < n:
        w = np.tile(w, n // max(len(w), 1) + 1)
    return w[:n]


def stream_audio(spec, n):
    if len(spec["files"]) == 1:
        return read_span(spec["files"][0], spec["offset_s"], n)
    w = np.concatenate([ts_build.read_audio(f) for f in spec["files"]])
    start = int(spec["offset_s"] * SR)
    return np.tile(w, 2)[start:start + n] if len(w) - start < n else w[start:start + n]


def active_rms(w, frame=320, below_db=30.0):
    """RMS over frames within ``below_db`` of the loudest frame (events are mostly silence around a burst)."""
    frames = w[:len(w) // frame * frame].reshape(-1, frame) if len(w) >= frame else w.reshape(1, -1)
    levels = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1)) + 1e-12
    keep = levels >= levels.max() * 10.0 ** (-below_db / 20.0)
    return float(np.sqrt(np.mean(np.square(levels[keep]))))


def render_noise(spec, n):
    noise = mixer.normalize_rms(stream_audio(spec["bed"], n).astype(np.float32), -30.0).astype(np.float64)
    if spec["babble"]:
        layer = stream_audio(spec["babble"], n)
        noise += layer / mixer.rms(layer) * mixer.rms(noise) * 10.0 ** (spec["babble"]["gain_db"] / 20.0)
    bed_rms = mixer.rms(noise)
    fade = int(mixer.FADE_SECONDS * SR)
    for event in spec["events"]:
        w = read_span(event["file"], event["clip_offset_s"], int(event["seconds"] * SR)).astype(np.float64)
        if len(w) > 2 * fade:
            ramp = np.linspace(0.0, 1.0, fade)
            w[:fade] *= ramp
            w[-fade:] *= ramp[::-1]
        w *= bed_rms * 10.0 ** (event["gain_db"] / 20.0) / active_rms(w)
        start = int(event["start_s"] * SR)
        w = w[:max(n - start, 0)]
        noise[start:start + len(w)] += w
    return noise


def codec_round_trip(x, codec):
    """Encode and decode 8 kHz audio with ffmpeg (AMR-NB or Speex narrowband)."""
    import subprocess

    args = (["-c:a", "libopencore_amrnb", "-b:a", str(codec["bitrate"]), "-f", "amr"] if codec["name"] == "amr_nb"
            else ["-c:a", "libspeex", "-cbr_quality", str(codec["quality"]), "-f", "ogg"])
    quiet = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    raw = np.clip(x, -1.0, 1.0).astype("<f4").tobytes()
    coded = subprocess.run([*quiet, "-f", "f32le", "-ar", "8000", "-ac", "1", "-i", "pipe:0", *args, "pipe:1"],
                           input=raw, capture_output=True, check=True).stdout
    decoded = subprocess.run([*quiet, "-i", "pipe:0", "-f", "f32le", "-ar", "8000", "-ac", "1", "pipe:1"],
                             input=coded, capture_output=True, check=True).stdout
    return np.frombuffer(decoded, dtype="<f4").astype(np.float64)


def radio_link(w, spec, segments):
    """Handheld radio: press-to-talk window, mic limiter, 8 kHz band 300-3400 Hz, low-rate codec, lost 20 ms
    frames (muted, a lost frame makes the next one likelier lost), squelch tail and optional end beep."""
    from scipy.signal import butter, correlate, resample_poly, sosfilt

    n = len(w)
    first = min(s["start"] for s in segments)
    last = max(s["start"] + s["duration"] for s in segments)
    on, off = max(int((first - spec["pre_s"]) * SR), 0), min(int((last + spec["post_s"]) * SR), n)
    seg = w[on:off] / mixer.rms(w[on:off]) * 10.0 ** (-20.0 / 20.0)
    seg = np.tanh(spec["drive"] * seg) / spec["drive"]
    narrow = sosfilt(butter(4, [300, 3400], "bandpass", fs=8000, output="sos"), resample_poly(seg, 1, 2))
    coded = codec_round_trip(narrow, spec["codec"])
    lags = correlate(coded[:len(narrow)], narrow, mode="full")[len(narrow) - 1:len(narrow) - 1 + 800]
    coded = coded[int(np.argmax(lags)):][:len(narrow)]  # drop the codec delay
    coded = np.pad(coded, (0, len(narrow) - len(coded)))
    g = np.random.default_rng(spec["seed"])
    lost = False
    for f in range(len(coded) // 160):
        lost = g.random() < (0.5 if lost else spec["loss"])
        if lost:
            coded[f * 160:(f + 1) * 160] = 0.0
    out = np.zeros(n)
    wide = resample_poly(coded, 2, 1)[:off - on]
    out[on:on + len(wide)] = wide
    band = butter(4, [300, 3400], "bandpass", fs=SR, output="sos")
    level = 10.0 ** (spec["squelch_dbfs"] / 20.0)

    def burst(start, seconds):
        m = max(min(int(seconds * SR), n - start), 0)
        if m:
            noise = sosfilt(band, g.standard_normal(m))
            out[start:start + m] += noise / mixer.rms(noise) * level

    burst(on, 0.02)  # key-up click
    tail = off
    if spec["beep"] and off < n:
        m = min(int(0.12 * SR), n - off)
        out[off:off + m] += np.sin(2 * np.pi * 1000.0 * np.arange(m) / SR) * 10.0 ** (-24.0 / 20.0) * np.sqrt(2)
        tail = off + m
    burst(tail, spec["squelch_s"])
    return out


def recorder_chain(w, spec):
    """Body-worn recorder: mic/ADC clipping when the scene is loud, high-pass, then automatic gain control
    (20 ms RMS, 10 ms attack, 400 ms release, gain within +-agc_max_gain_db)."""
    from scipy.signal import butter, sosfilt

    x = np.asarray(w, dtype=np.float64)
    if spec["overload_db"] > 0:
        x = np.clip(x / np.abs(x).max() * 10.0 ** (spec["overload_db"] / 20.0), -1.0, 1.0)
    x = sosfilt(butter(2, spec["highpass_hz"], "highpass", fs=SR, output="sos"), x)
    frame = 320
    frames = len(x) // frame
    env = np.sqrt(np.mean(np.square(x[:frames * frame]).reshape(frames, frame), axis=1)) + 1e-9
    want = np.clip(spec["agc_dbfs"] - 20.0 * np.log10(env), -spec["agc_max_gain_db"], spec["agc_max_gain_db"])
    attack, release = np.exp(-frame / (0.01 * SR)), np.exp(-frame / (0.4 * SR))
    gains, g = np.empty(frames), want[0]
    for i, target in enumerate(want):
        a = attack if target < g else release
        g = a * g + (1.0 - a) * target
        gains[i] = g
    curve = np.repeat(10.0 ** (gains / 20.0), frame)
    curve = np.concatenate([curve, np.full(len(x) - len(curve), curve[-1] if len(curve) else 1.0)])
    return x * curve


def render_job(job):
    split, index, plan, out = job
    recipe = G["recipe"]
    level = recipe["speech_dbfs"]
    rir = ts_build.read_audio(plan["rir"]) if plan["rir"] else None
    pieces, segments = [], []
    for t in plan["turns"]:
        w = ts_build.read_audio(t["utt"].path if t["utt"] else plan["context"]["path"])
        gain = 0.0 if t["officer"] else plan["gains"][t["speaker"]]
        w = mixer.normalize_rms(w, level + gain)
        dry = len(w)  # the segment ends where the speech ends, not the room's tail
        if (not t["officer"] or plan.get("officer_rir")) and rir is not None:
            w = mixer.apply_rir(w, rir)
        pieces.append((round(t["start"] * SR), w))
        segments.append({"start": t["start"], "duration": round(dry / SR, 3), "speaker": t["speaker"],
                         "officer": t["officer"], "role": t.get("role"),
                         "utterance": t["utt"].id if t["utt"] else plan["context"]["id"],
                         "text": t["utt"].text if t["utt"] else plan["context"]["target"]})
    length = max(s + len(w) for s, w in pieces) + int(plan["trail"] * SR)
    speech = np.zeros(length, dtype=np.float64)
    for s, w in pieces:
        speech[s:s + len(w)] += w
    noise = render_noise(plan["noise"], length)
    noise *= 10.0 ** ((level - plan["noise"]["snr_db"]) / 20.0) / mixer.rms(noise)
    mix = speech + noise
    if "pdt" in plan:  # what the remote handset picked up, as heard through the radio
        mix = radio_link(mix, plan["pdt"], segments)
    mix = mix + mixer.floor_noise(length, plan["floor"])
    if "device" in plan:
        mix = recorder_chain(mix, plan["device"])
    peak = float(np.abs(mix).max())
    scale_db = 0.0
    if peak > 0.99:  # keep the relative levels, avoid clipping
        scale_db = 20.0 * np.log10(0.99 / peak)
        mix *= 0.99 / peak
    name = split["name"]
    entries = []
    relative = f"audio/{name}/{name}-{index:04d}.wav"
    ts_build.write_wav(out / relative, mix.astype(np.float32))
    entries.append({"cut_id": f"{name}-{index:04d}", "relative_path": relative, "num_frames": length,
                    "duration": round(length / SR, 4), "sha256": ts_build.sha256_file(out / relative)})
    if "enroll" in plan:
        gap = np.zeros(int(0.3 * SR), dtype=np.float32)
        parts = []
        for u in plan["enroll"]:
            parts += [mixer.normalize_rms(ts_build.read_audio(u.path), level), gap]
        w = np.concatenate(parts[:-1])
        floor = {**plan["floor"], "seed": plan["floor"]["seed"] + 1}
        w = (w + mixer.floor_noise(len(w), floor)).astype(np.float32)
        relative = f"audio/{name}/{name}-{index:04d}-enroll.wav"
        ts_build.write_wav(out / relative, w)
        entries.append({"cut_id": f"{name}-{index:04d}-enroll", "relative_path": relative, "num_frames": len(w),
                        "duration": round(len(w) / SR, 4), "sha256": ts_build.sha256_file(out / relative)})
    return {"split": name, "index": index, "entries": entries, "segments": segments,
            "peak_scale_db": round(scale_db, 2)}


# --- records -----------------------------------------------------------------------------


def describe(recipe, split, plan, result, pools):
    """Target, task, labels and metadata of one sample."""
    form, segments = split["form"], result["segments"]
    env = recipe["environments"][plan["env"]]
    labels = {"scenario": split["name"], "display": split["display"], "sheet_rows": split["rows"],
              "form": form, "level": split["level"], "env": plan["env"], "env_display": env["display"],
              "snr_db": plan["noise"]["snr_db"], "duration_s": result["entries"][0]["duration"],
              "noise_floor_dbfs": plan["floor"]["dbfs"], "noise_floor_kind": plan["floor"]["kind"]}
    if result["peak_scale_db"]:
        labels["peak_scale_db"] = result["peak_scale_db"]
    if "pdt" in plan:
        labels["channel"] = {k: v for k, v in plan["pdt"].items() if k != "seed"}
    if "device" in plan:
        labels["device"] = plan["device"]
    if plan.get("officer_rir"):
        labels["officer_far_field"] = True
    if "variant_of" in split:
        labels["variant_of"] = split["variant_of"]
    texts =[s["text"] for s in sorted(segments, key=lambda s: s["start"])]
    task, slots = "asr", ["primary"]
    if form in ("short", "long", "context"):
        target = join_texts(texts)
    elif form == "meeting":
        task, slots = "speaker_attributed_asr", ["mixture"]
        names = {}  # S1, S2, ... by first turn; the officer speaks first
        for s in sorted(segments, key=lambda s: s["start"]):
            names.setdefault(s["speaker"], f"S{len(names) + 1}")
        by = defaultdict(list)
        for s in sorted(segments, key=lambda s: s["start"]):
            by[names[s["speaker"]]].append(s["text"])
        target = "\n".join(f"[{label}] {join_texts(by[label])}" for label in sorted(by, key=lambda x: int(x[1:])))
        labels["speaker_count"] = len(by)
        labels["segments"] = [{"start": s["start"], "duration": s["duration"], "speaker_id": names[s["speaker"]]}
                              for s in sorted(segments, key=lambda s: s["start"])]
        # reference turns as AmphionEval's meeting scorer reads them (cpER and DER)
        turns = [{"speaker": names[s["speaker"]], "start": s["start"], "end": round(s["start"] + s["duration"], 3),
                  "text": s["text"]} for s in sorted(segments, key=lambda s: s["start"])]
        labels["overlap_ratio"] = round(overlap_seconds(labels["segments"]) / labels["duration_s"], 4)
    else:  # owner
        task, slots = "ts_asr", ["enrollment", "mixture"]
        target = "" if plan["absent"] else plan["owner_utt"].text
        owner = next((s for s in segments if s["role"] == "owner"), None)
        others = [s for s in segments if s["role"] == "other"]
        labels.update(mode=split["mode"], owner_present=not plan["absent"], same_text=plan["same_text"],
                      num_interferers=len(others), enrollment_s=result["entries"][1]["duration"])
        if owner:
            covered = overlap_with(owner, others)
            labels["owner_overlap_ratio"] = round(covered / owner["duration"], 4)
    if form in ("short", "owner") and plan.get("pool"):
        terms = pools[plan["pool"]]["terms"]
        spoken = [t for t in plan["turns"] if t.get("role") in (None, "owner") and t["utt"]]
        keywords = sorted({k for t in spoken for k in terms if k in t["utt"].text}
                          | {k for t in spoken for k in t["utt"].terms if k in t["utt"].text})
        if keywords:
            labels["keywords"] = keywords
        kinds = sorted({k for t in spoken for k in number_kinds(t["utt"].text)})
        if split["name"].startswith("num-") and kinds:
            labels["number_types"] = kinds
    if form == "context":
        labels["context_correction"] = plan["context"]["context"]
    metadata = {"generator": GENERATOR_VERSION, "seed": recipe["seed"], "split": split["name"],
                "index": result["index"], "segments": segments, "room_response": plan["rir"] and Path(plan["rir"]).stem,
                "noise": noise_meta(plan["noise"], G["roots"])}
    if form == "meeting":
        metadata["turns"] = turns
    if form == "owner":
        metadata["enrollment"] = [{"id": u.id, "speaker": u.speaker, "text": u.text} for u in plan["enroll"]]
    return task, slots, target, labels, metadata


def overlap_seconds(segments):
    """Seconds where two or more segments are active."""
    edges = sorted([(s["start"], 1) for s in segments] + [(s["start"] + s["duration"], -1) for s in segments])
    active, last, total = 0, 0.0, 0.0
    for t, step in edges:
        if active >= 2:
            total += t - last
        active += step
        last = t
    return total


def overlap_with(segment, others):
    lo, hi = segment["start"], segment["start"] + segment["duration"]
    spans = sorted((max(lo, o["start"]), min(hi, o["start"] + o["duration"])) for o in others)
    total, end = 0.0, lo
    for a, b in spans:
        a = max(a, end)
        if b > a:
            total += b - a
            end = b
    return total


def noise_meta(spec, roots):
    def rel(path):
        for alias in ("demand", "asr_babble_bench", "open_noise"):
            if path.startswith(roots[alias]):
                return f"{alias}:{Path(path).relative_to(roots[alias])}"
        return path

    out = {"snr_db": spec["snr_db"], "bed": {**spec["bed"], "files": [rel(f) for f in spec["bed"]["files"]]},
           "events": [{**e, "file": rel(e["file"])} for e in spec["events"]]}
    if spec["babble"]:
        out["babble"] = {**spec["babble"], "files": [rel(f) for f in spec["babble"]["files"]]}
    return out


def hotword_list(rng, gold, vocabulary, size):
    """``size`` words: every gold keyword of the split plus police terms drawn at random, shuffled."""
    words = sorted(set(gold))
    rest = sorted(set(vocabulary) - set(words))
    words += rng.sample(rest, max(size - len(words), 0))
    rng.shuffle(words)
    return words[:max(size, len(gold))]


# --- registration --------------------------------------------------------------------------


def register(recipe, splits, plans, results, pools, data_root, alias):
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    by_split = defaultdict(dict)
    for r in results:
        by_split[r["split"]][r["index"]] = r
    vocabulary = sorted({t for u in G["utts"] for t in u.terms if 2 <= len(t) <= 12}
                        | {t for p in pools.values() for t in p["terms"]})
    index_rows, records_by_split, split_specs = [], {}, []
    for split in splits:
        records = []
        for index, plan in enumerate(plans[split["name"]]):
            result = by_split[split["name"]][index]
            for entry in result["entries"]:
                index_rows.append({**entry, "root_alias": alias, "sample_rate": SR, "channels": 1,
                                   "relative_path": f"source/{version}/{entry['relative_path']}"})
            task, slot_names, target, labels, metadata = describe(recipe, split, plan, result, pools)
            refs = {slot_names[-1]: result["entries"][0]}
            if task == "ts_asr":
                refs["enrollment"] = result["entries"][1]
            records.append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{split['name']}:{index:04d}", "task": task,
                "audio_slots": [{"name": slot, "purpose": slot, "ref": {
                    "dataset_id": dataset_id, "version": version, "split": split["name"],
                    "cut_id": refs[slot]["cut_id"], "duration": refs[slot]["duration"]}} for slot in slot_names],
                "target": target, "language": "zh", "labels": labels, "metadata": metadata,
            }).to_dict())
        records_by_split[split["name"]] = records
        split_specs.append(split)
        if split.get("hotwords"):
            rng = random.Random(f"{recipe['seed']}:{split['name']}:hotwords")
            gold = [k for record in records for k in record["labels"].get("keywords", [])]
            words = hotword_list(rng, gold, vocabulary, recipe["hotword_list_size"])
            name = f"{split['name']}-hw{recipe['hotword_list_size']}"
            # hotword_bench layout: hotwords = the gold words spoken, metadata.bias_lists = the list to send
            records_by_split[name] = [AudioRecord.from_dict({
                **record, "id": record["id"].replace(split["name"], name, 1), "task": "asr_hotwords",
                "hotwords": record["labels"].get("keywords", []),
                "labels": {**record["labels"], "scenario": name, "hotword_list_size": len(words)},
                "metadata": {**record["metadata"], "bias_lists": {"list300": words},
                             "distractor_kinds": {w: "police_term" for w in words
                                                  if w not in record["labels"].get("keywords", [])}},
            }).to_dict() for record in records]
            split_specs.append({**split, "name": name, "hotword_copy_of": split["name"],
                                "display": f"{split['display']}（{len(words)} 词热词表）"})
    for name, records in records_by_split.items():
        ts_build.write_jsonl_gz(data_root / "versions" / version / "records" / f"{name}.jsonl.gz", records)
    if len({e["cut_id"] for e in index_rows}) != len(index_rows):
        raise ValueError("duplicate cut ids: two samples would share one audio index entry")
    ts_build.write_jsonl_gz(data_root / "versions" / version / "audio-index.jsonl.gz",
                            sorted(index_rows, key=lambda e: e["cut_id"]))

    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": alias, "relative_path": path,
                "sha256": ts_build.sha256_file(data_root / path), "metadata": {"record_count": count}}

    artifacts = [artifact("audio-index", "audio-index", f"versions/{version}/audio-index.jsonl.gz", len(index_rows))]
    split_decl = {}
    for split in split_specs:
        name, records = split["name"], records_by_split[split["name"]]
        artifacts.append(artifact(f"{name}-records", "audio-records", f"versions/{version}/records/{name}.jsonl.gz",
                                  len(records)))
        level = recipe["levels"][split["level"]]
        envs = "、".join(recipe["environments"][e]["display"] for e in as_list(split["env"]))
        rows = "、".join(str(r) for r in split["rows"])
        note = f"音频与 {split['hotword_copy_of']} 相同，每条带同一份热词表。" if "hotword_copy_of" in split else ""
        if "variant_of" in split:
            note += f"与 {split['variant_of']} 逐条同一批语音和噪声，只改通道，可配对比较。"
        split_decl[name] = {
            "artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
            "task": records[0]["task"],
            "statistics": {"records": len(records),
                           "duration_hours": round(sum(next(s["ref"]["duration"] for s in r["audio_slots"]
                                                           if s["name"] != "enrollment") for r in records) / 3600, 4),
                           "duration_basis": "mixture duration"},
            "provenance": {"description": f"{split['display']}：{split['description']}。表格第 {rows} 行，"
                                          f"{level['display']}（信噪比 {level['snr_db'][0]}～{level['snr_db'][1]} dB），{envs}。{note}"},
        }
        if "hotword_copy_of" in split:  # same audio as its base split: not a top-level split, not counted twice
            split_decl[name]["group"] = split["hotword_copy_of"]
    for source in recipe["speech"].get("extra", []):  # the synthesized speech the splits read
        for role in ("recordings", "supervisions"):
            path = source[role]
            artifacts.append(artifact(f"{source['name']}-{role}", f"lhotse-{role}", path,
                                      sum(1 for _ in ts_build._rows(data_root / path))))
    texts = recipe["tts_texts"]
    artifacts.append(artifact("tts-eval-texts", "jsonl-metadata", texts,
                              sum(1 for line in (data_root / texts).open(encoding="utf-8") if line.strip())))
    sources = [f"{s['dataset']}@{s['version']}:{s['split']}" for s in recipe["speech"]["police"]]
    context = recipe["speech"]["context"]
    sources += [f"{context['dataset']}@{context['version']}:{s}" for s in context["splits"]]
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": ["zh"], "tasks": sorted({d["task"] for d in split_decl.values()}),
        "artifacts": artifacts, "splits": split_decl,
        "provenance": {
            "status": "complete", "synthetic": "full",
            "summary": "鼎桥验收表各使用场景的模拟评测，仅评测",
            "description": "警务场景模拟评测集，用于与鼎桥（td-tech）的验收：按《技术指标_场景分级拆分_鼎桥沟通更新版_20261026》的具体使用场景逐个模拟，"
                           "每个场景 100 条，覆盖通用识别、行业术语（含 300 词热词表）、号码（含新合成的全国车牌、新能源车牌和"
                           "电动车号牌）、机主识别（分开/重叠讲话）、角色分离（≤4 人、5–8 人）、上下文矫正和各能力的极限档。"
                           "佩戴设备的民警近讲不加混响，其他人加所在场所的 MIT 实测混响；噪声为 DEMAND、FSD50K 评测划分的真实录音"
                           "和不进训练的中文合成背景人声，按表格噪声分档的信噪比混合。PDT 对讲机用低码率窄带编解码模拟链路，"
                           "执法记录仪用过载削波、高通和自动增益近似（极限档全部经过，另有与原场景配对的设备通道和 2 米远场版本）。"
                           "另附 TTS 听测文本（tts-eval-texts，在线 LLM 生成，MOS 仍需人工听测）。"
                           "语音是合成数据（Qwen3-TTS 等，未人工听审），多人对话由独立的句子拼接，内容不连贯。只用于评测，不进训练。"
                           "配方 scripts/police_scene_bench/recipe.yaml。",
            "sources": [*sources, "demand@zenodo-1227121-16k-20261023:all", "fsd50k@zenodo-4060432-20261013:eval",
                        "asr_babble_bench@v2-20261023:babble-zh", "mit_ir_survey@flac16k-20261026:all"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, help="samples per split (smoke runs)")
    parser.add_argument("--only", nargs="*", help="build only these splits (smoke runs)")
    parser.add_argument("--no-register", action="store_true", help="write audio and records but not the catalog")
    args = parser.parse_args()

    recipe = yaml.safe_load(args.recipe.read_text())
    roots = json.loads(args.roots.read_text())
    alias, version = recipe["dataset_id"], recipe["version"]
    data_root = Path(roots[alias])
    final = data_root / "source" / version
    if (data_root / "versions" / version).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {version}")
    splits = [{"n": recipe["default_n"], **s} for s in recipe["splits"]]
    by_name = {s["name"]: s for s in splits}
    if len(by_name) != len(splits):
        raise ValueError("duplicate split names in the recipe")
    for i, s in enumerate(splits):  # a variant takes its base's scene and changes only the channel
        if "variant_of" in s:
            base = {k: v for k, v in by_name[s["variant_of"]].items() if k not in ("name", "rows", "display", "description",
                                                                                   "hotwords", "device", "far_field", "channel")}
            splits[i] = by_name[s["name"]] = {**base, **s}
    if args.only:
        splits = [s for s in splits if s["name"] in args.only]
    if args.limit:
        for s in splits:
            s["n"] = min(s["n"], args.limit)

    catalog = load_catalog(args.catalog)
    utts = load_police(recipe, catalog, roots)
    pools = build_pools(recipe, utts)
    first = recipe["speech"]["police"][0]["split"]
    by_speaker = {name: defaultdict(list) for name in pools}
    for name, pool in pools.items():
        for u in pool["utts"]:
            if u.split == first:  # multi-speaker scenes only use speakers of the first split
                by_speaker[name][u.speaker].append(u)
    owner_index, by_text = defaultdict(list), defaultdict(list)
    for u in utts:
        owner_index[u.speaker].append(u)
        by_text[u.text].append(u)
    context = load_context(recipe, catalog, roots)
    beds, events, rirs = noise_assets(recipe, roots)
    G.update(recipe=recipe, beds=beds, events=events, rirs=rirs, roots=roots, by_text=by_text, utts=utts)
    print({name: len(p["utts"]) for name, p in pools.items()}, f"{len(context)} context items",
          {k: len(v) for k, v in beds.items()}, {k: len(v) for k, v in events[False].items()},
          {k: len(v) for k, v in rirs.items() if k in {p for e in recipe["environments"].values() for p in e["rir_places"]}},
          flush=True)
    plans = {}
    for s in splits:
        if "variant_of" in s:  # same speech, noise and room as the base split; only the channel draws differ
            base = plans.get(s["variant_of"]) or plan_split(recipe, {**by_name[s["variant_of"]], "n": s["n"]}, pools,
                                                            by_speaker, context, owner_index)
            plans[s["name"]] = copy.deepcopy(base[:s["n"]])
            for i, plan in enumerate(plans[s["name"]]):
                for key in ("pdt", "device", "officer_rir"):
                    plan.pop(key, None)
                plan_channels(random.Random(f"{recipe['seed']}:{s['name']}:{i}:channel"), recipe, s, plan)
        else:
            plans[s["name"]] = plan_split(recipe, s, pools, by_speaker, context, owner_index)
    partial = data_root / "source" / (version + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    jobs = [(split, i, plan, partial) for split in splits for i, plan in enumerate(plans[split["name"]])]
    print(f"{len(splits)} splits, {len(jobs)} samples", flush=True)
    with ProcessPoolExecutor(args.workers, mp_context=FORK) as pool:
        results = list(pool.map(render_job, jobs, chunksize=4))
    partial.rename(final)
    declaration = register(recipe, splits, plans, results, pools, data_root, alias)
    if args.no_register:
        return
    path = REPO / "catalog" / f"{recipe['dataset_id']}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == version for r in rows):
        raise FileExistsError(f"version already registered: {version}")
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512),
                    encoding="utf-8")
    print(json.dumps(Counter(s["form"] for s in splits)), "registered", version)


if __name__ == "__main__":
    main()
