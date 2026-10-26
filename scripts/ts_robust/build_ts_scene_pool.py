#!/usr/bin/env python3
"""Build ts_scene_pool: target-speaker scenes with several utterances per speaker.

Each record names every utterance of one scene, so the loader only places them in time:
  alternate  target and others take turns without overlap (target may speak twice)
  burst      each other speaker talks several utterances in a row while the target speaks
  short      a 1-3 s target utterance inside the others' speech
Speakers come from corpora with real speaker labels, read through the Lance record index
(speaker, text and span of every utterance). Other speakers always differ from the target
and from each other. The record's slots are the enrollment (another utterance of the target)
and the first target utterance; the whole scene is in metadata.scene.

With ``--multi`` it builds the multi-turn version: the benchmark's base scenes, where every speaker has a
track of its own and the target speaks 2-5 times with other speakers talking in between and over it
  full       parallel tracks; the target and each other speaker have their own silence between utterances
A share of the scenes (``--twin-share`` of the records) is followed by a twin: the same utterances and
timeline, but the enrollment is another speaker (half of the time one that sounds like the target, from
``--neighbors``), the target's utterances become one more interferer's and the transcript is empty.
The twin pairs share ``labels.pair`` so the model can only tell them apart by the voice.

With ``--neighbors neighbors.json`` (from speaker_neighbors.py) it builds the hard version
instead: one of the other speakers is a close neighbour of the target (a random one of the
``--hard-rank`` nearest by ERes2NetV2), in two kinds
  absent   the target is not in the scene: enrollment A, the scene holds a similar voice B
           and others, the transcript is empty (the benchmark's abs-hard)
  present  the target speaks and a similar voice B is among the others

    python build_ts_scene_pool.py --output-dir DIR [--zh 150000 --en 100000]
    python build_ts_scene_pool.py --output-dir DIR --version hard-20261016 --neighbors FILE --zh 40000 --en 25000
    python build_ts_scene_pool.py --output-dir DIR --version multi-20261017 --multi --neighbors FILE --zh 120000 --en 40000

With ``--solo`` it builds the short solo version: the target says one short utterance and nobody else speaks. The
multi-turn and one-target mixes hold almost no target utterance under 3 s (aishellmix / librimix ``train_1spk`` have
none under 3 s for aishellmix), so a model trained on them learns to stay silent on a bare short phrase. A share of the
records are twins: the same utterance, but the enrollment is another speaker, so the transcript is empty. With
``--neighbors`` half of the twins enroll a close neighbour of the target, as in the multi-turn version.

    python build_ts_scene_pool.py --output-dir DIR --version solo-20261019 --solo --twin-share 0.3 --zh 60000 --en 20000
    python build_ts_scene_pool.py --output-dir DIR --version solo-20261020 --solo --neighbors FILE --twin-share 0.3 \\
        --zh 60000 --en 20000

With ``--handover`` it builds the handover version: the target says one utterance and one other speaker says one
utterance, one after the other without overlap, in either order (alternate mode). The other pools never hold this:
alternate scenes have at least two other speakers and the solo scenes have none, and the benchmark's handover scenes
(ts_asr_handover) showed the model staying silent on them. With ``--neighbors`` half of the other speakers are a close
neighbour of the target. A share of the records are twins: the same two utterances, but the enrollment is another
speaker (half of the time a neighbour of the target), so both utterances are interferers and the transcript is empty.

    python build_ts_scene_pool.py --output-dir DIR --version handover-20261021 --handover --neighbors FILE \\
        --twin-share 0.3 --zh 40000 --en 12000

With ``--multi --xsession`` the targets are KeSpeech speakers who recorded both a Mandarin (phase1) and a dialect
(phase2) session. A scene's target utterances come from one session; with XSESSION_CROSS_PROB the enrollment comes
from the other session (``labels.cross_session``), otherwise from the same one. The other pools take their targets from
AISHELL-2 / AISHELL-1, one session per speaker, so the model never has to accept a voice across sessions and can lean on
the channel; on ts-asr-benchmark@v12 a Mandarin/dialect mismatch between enrollment and target leaves 34% of KeSpeech
targets untranscribed (5.7% within one variety). AISHELL-2 stays among the other speakers, and twins enroll another
KeSpeech speaker, so neither the channel nor the corpus tells present from absent.

    python build_ts_scene_pool.py --output-dir DIR --version xsession-20261023 --multi --xsession --twin-share 0.3 \\
        --zh 80000 --en 0

With ``--multi --magicdata`` the targets are MagicData speakers (read speech recorded on phones). On
ts-asr-benchmark@v12 a MagicData target speaking alone is transcribed at 14.5% CER through TS against 1.7% for plain
ASR (mostly untranscribed targets), while AISHELL-1/2/3 targets alone match plain ASR; no pool has had a MagicData
target. Twins enroll another MagicData speaker. 73% of MagicData test utterances repeat a train sentence, so train
utterances whose text is in the test split are dropped (HELD_OUT_TEXT).

    python build_ts_scene_pool.py --output-dir DIR --version magicdata-20261023 --multi --magicdata --twin-share 0.3 \\
        --zh 80000 --en 0
"""

import argparse
import gzip
import json
import random
import unicodedata
from collections import Counter
from pathlib import Path

import lance
import numpy as np
import yaml

DATA = Path("/workspace/data")
REGISTRY = DATA / "registry/catalog/datasets.yaml"
DATASET_ID = "ts_scene_pool"
VERSION = "v2-20261016"
SEED = 20261016
# Corpora per language: (dataset, version, split, weight as other speaker, can be the target)
CORPORA = {
    "zh": [("aishell2", "legacy-20260804", "train", 0.5, True), ("kespeech", "legacy-20260804", "train", 0.5, False)],
    "en": [("librispeech", "legacy-20260804", "train", 0.5, True), ("common_voice_en", "legacy-20260804", "train", 0.5, False)],
}
MODES = {"zh": (("alternate", 0.35), ("burst", 0.35), ("short", 0.30)),
         "en": (("alternate", 0.40), ("burst", 0.40), ("short", 0.20))}
UTTERANCE_SECONDS = {"zh": (1.0, 12.0), "en": (1.0, 8.0)}
SHORT_TARGET_SECONDS = {"zh": (0.8, 2.5), "en": (1.0, 3.5)}
ENROLLMENT_SECONDS = (2.5, 8.0)
# --xsession: targets are KeSpeech speakers with both sessions (phase1 Mandarin, phase2 dialect, the directory names).
XSESSION_CORPORA = [("aishell2", "legacy-20260804", "train", 0.5, False), ("kespeech", "legacy-20260804", "train", 0.5, True)]
SESSIONS = ("phase1", "phase2")
XSESSION_CROSS_PROB = 0.5
# --magicdata: targets are MagicData speakers; the other speakers are half AISHELL-2, half MagicData.
MAGICDATA_CORPORA = [("aishell2", "legacy-20260804", "train", 0.5, False), ("magicdata", "legacy-20260804", "train", 0.5, True)]
# Splits whose sentences a corpus must not train on (73% of MagicData test utterances repeat a train sentence).
HELD_OUT_TEXT = {"magicdata": "test"}
# Longest scene per mode, gaps included. The benchmark's scenes run 5-18 s; the training
# batch holds about a dozen windows, so a 70 s scene would not fit.
SCENE_SECONDS = {"alternate": 30.0, "burst": 22.0, "short": 14.0, "full": 32.0}
MEAN_GAP_SECONDS = {"alternate": 0.6, "burst": 0.25, "short": 0.15}
# The benchmark's pauses between one speaker's utterances: dense, medium and sparse talk.
GAP_PROFILES = ((0.2, 1.0), (0.2, 1.0), (1.0, 3.0), (2.5, 6.0))
FULL_UTTERANCE_SECONDS = (1.5, 9.0)
FULL_TARGET_TURNS = ((2, 3, 4, 5), (0.4, 0.3, 0.2, 0.1))
# --solo: one short target utterance, nobody else. The benchmark's solo-mid clips are 2-6 s with a median of 6 characters.
SOLO_UTTERANCE_SECONDS = (1.0, 3.5)
# --handover: one target utterance and one other utterance in a row. The benchmark's handover utterances are 1.5-5 s.
HANDOVER_UTTERANCE_SECONDS = (1.0, 6.0)
FULL_INTERFERERS = ((1, 2, 3, 4), (0.3, 0.3, 0.25, 0.15))
MAX_UTTERANCES_PER_TRACK = 6
COLUMNS = ["id", "speaker", "text", "duration", "cut_id", "root_alias", "relative_path",
           "start_frame", "num_frames", "sample_rate", "channels"]


def _plain(text):
    """Text compared for held-out sentences: NFKC, lower case, no punctuation, symbols or spaces."""
    return "".join(c for c in unicodedata.normalize("NFKC", text or "").lower() if unicodedata.category(c)[0] not in "PSZ")


class Corpus:
    def __init__(self, dataset, version, split, weight, target, language, sessions=False):
        self.name, self.weight, self.target = dataset, weight, target
        entry = next(e for e in yaml.safe_load(REGISTRY.read_text())
                     if e["dataset_id"] == dataset and e["version"] == version)
        artifact = next(a for a in entry["artifacts"]
                        if a["name"] == entry["splits"][split]["artifacts"]["records_lance"][0])
        directory = DATA / artifact["relative_path"].rsplit("/", 1)[0]
        manifest = json.loads((directory / "index.json").read_text())
        table = lance.dataset(str(directory / manifest["table_path"])).to_table(
            columns=COLUMNS, filter=f"array_has(splits, '{split}')")
        duration = table["duration"].to_numpy(zero_copy_only=False)
        text = table["text"].to_pylist()
        speaker = table["speaker"].to_pylist()
        keep = np.array([bool(t and len(t.strip()) >= 2) and bool(s) for t, s in zip(text, speaker)]
                        ) & (duration >= UTTERANCE_SECONDS[language][0]) & (duration <= UTTERANCE_SECONDS[language][1])
        if dataset in HELD_OUT_TEXT:
            held = {_plain(t) for t in lance.dataset(str(directory / manifest["table_path"])).to_table(
                columns=["text"], filter=f"array_has(splits, '{HELD_OUT_TEXT[dataset]}')")["text"].to_pylist()}
            same = np.array([_plain(t) in held for t in text])
            print(dataset, "dropped", int((keep & same).sum()), "utterances with a", HELD_OUT_TEXT[dataset], "sentence", flush=True)
            keep &= ~same
        session = None
        if sessions:
            # Keep only speakers with an utterance in every session, so any scene can enroll across sessions.
            session = np.array([path.rsplit("/", 2)[-2] for path in table["relative_path"].to_pylist()])
            names = np.array(speaker)
            both = set.intersection(*(set(names[keep & (session == s)]) for s in SESSIONS))
            keep &= np.isin(names, sorted(both))
        self.rows = table.filter(keep).to_pydict()
        self.session = session[keep] if sessions else None
        self.duration = duration[keep]
        names, inverse = np.unique(np.array(self.rows["speaker"]), return_inverse=True)
        order = np.argsort(inverse, kind="stable")
        bounds = np.searchsorted(inverse[order], np.arange(len(names) + 1))
        self.speakers = [f"{dataset}:{n}" for n in names]
        self.by_speaker = [order[bounds[i]:bounds[i + 1]] for i in range(len(names))]
        print(dataset, "utterances", int(keep.sum()), "speakers", len(names), flush=True)

    def pick(self, rng, speaker, count, low=None, high=None, exclude=(), session=None):
        """``count`` distinct utterances of one speaker, optionally within a duration range and one session."""
        rows = [i for i in self.by_speaker[speaker] if i not in exclude
                and (low is None or low <= self.duration[i] <= high)
                and (session is None or self.session[i] == session)]
        return rng.sample(rows, count) if len(rows) >= count else None

    def usable(self, speaker, count):
        return len(self.by_speaker[speaker]) >= count


class Builder:
    def __init__(self, language, rng, neighbors=None, hard_rank=10, xsession=False, magicdata=False):
        self.language, self.rng, self.xsession = language, rng, xsession
        corpora = XSESSION_CORPORA if xsession else MAGICDATA_CORPORA if magicdata else CORPORA[language]
        self.corpora = [Corpus(*c, language, sessions=xsession and c[4]) for c in corpora]
        self.targets = [c for c in self.corpora if c.target]
        self.neighbors, self.hard_rank = neighbors, hard_rank
        self.where = {name: (c, i) for c in self.corpora for i, name in enumerate(c.speakers)}
        self.audio, self.pending = {}, {}

    def ref(self, corpus, i):
        rows = corpus.rows
        cut = f"{corpus.name}:{rows['cut_id'][i]}"
        rate, start, frames = rows["sample_rate"][i], rows["start_frame"][i], rows["num_frames"][i]
        self.pending.setdefault(cut, {
            "cut_id": cut, "root_alias": rows["root_alias"][i], "relative_path": rows["relative_path"][i],
            "sample_rate": rate, "channels": rows["channels"][i] or 1,
            "num_frames": start + frames, "duration": round((start + frames) / rate, 3)})
        return {"cut_id": cut, "start": round(start / rate, 3), "duration": round(frames / rate, 3)}

    def other_speaker(self, used, count):
        """A (corpus, speaker, utterances) for one other speaker, never one already in the scene."""
        rng = self.rng
        for _ in range(200):
            corpus = rng.choices(self.corpora, [c.weight for c in self.corpora])[0]
            speaker = rng.randrange(len(corpus.speakers))
            if corpus.speakers[speaker] in used or not corpus.usable(speaker, count):
                continue
            picks = corpus.pick(rng, speaker, count)
            if picks:
                used.add(corpus.speakers[speaker])
                return corpus, speaker, picks
        raise RuntimeError("no other speaker found")

    def scene(self, mode, hard=None):
        """A scene no longer than SCENE_SECONDS[mode]; draws again when one comes out too long."""
        while True:
            self.pending = {}
            scene, joiner, seconds = self.draw(mode, hard)
            if seconds <= SCENE_SECONDS[mode]:
                self.audio.update(self.pending)
                return scene, joiner

    def draw(self, mode, hard=None):
        rng = self.rng
        corpus = rng.choice(self.targets)
        short_low, short_high = SHORT_TARGET_SECONDS[self.language]
        while True:
            speaker = rng.randrange(len(corpus.speakers))
            if hard:
                near = [n for n, _ in self.neighbors.get(corpus.speakers[speaker], [])[: self.hard_rank] if n in self.where]
                if not near:
                    continue
            wanted = 0 if hard == "absent" else 1 if mode != "alternate" else (2 if rng.random() < 0.4 else 1)
            targets = corpus.pick(rng, speaker, wanted, *((short_low, short_high) if mode == "short" else (None, None))) if wanted else []
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=set(targets)) if targets is not None else None
            if targets is not None and enrollment:
                break
        used = {corpus.speakers[speaker]}
        if mode == "alternate":
            k, per_speaker = rng.choices((2, 3, 4, 5, 6), (0.25, 0.25, 0.2, 0.15, 0.15))[0], lambda: 2 if rng.random() < 0.3 else 1
        elif mode == "burst":
            k, per_speaker = rng.choices((1, 2, 3, 4, 5, 6), (0.1, 0.15, 0.2, 0.2, 0.2, 0.15))[0], lambda: rng.randint(2, 4)
        else:
            k, per_speaker = rng.choices((1, 2, 3, 4, 5), (0.25, 0.2, 0.2, 0.2, 0.15))[0], lambda: rng.randint(1, 2)
        others, lengths = [], []
        if hard:
            # The similar voice is the first of the others; its cosine is kept for analysis.
            name = rng.choice(near)
            close, who = self.where[name]
            count = per_speaker()
            picks = close.pick(rng, who, count) if close.usable(who, count) else close.pick(rng, who, 1)
            if not picks:
                raise RuntimeError("similar speaker has no usable utterance")
            used.add(name)
            others.append({"speaker": name, "utts": [self.ref(close, i) for i in picks]})
            lengths.append(sum(close.duration[i] for i in picks) + MEAN_GAP_SECONDS[mode] * (len(picks) - 1))
        for _ in range(k - len(others)):
            count = per_speaker()
            while True:
                try:
                    other, who, picks = self.other_speaker(used, count)
                    break
                except RuntimeError:
                    count = max(1, count - 1)
            others.append({"speaker": other.speakers[who], "utts": [self.ref(other, i) for i in picks]})
            lengths.append(sum(other.duration[i] for i in picks) + MEAN_GAP_SECONDS[mode] * (len(picks) - 1))
        target_seconds = sum(corpus.duration[i] for i in targets) + MEAN_GAP_SECONDS[mode] * max(len(targets) - 1, 0)
        # alternate puts everything in a row; burst and short last as long as the longest speaker
        seconds = sum(lengths) + target_seconds + MEAN_GAP_SECONDS[mode] * (len(lengths) + 1) if mode == "alternate" \
            else max([target_seconds, *lengths])
        joiner = "" if self.language == "zh" else " "
        scene = {"hard": {"kind": hard, "neighbor": name,
                          "cosine": dict(self.neighbors[corpus.speakers[speaker]])[name]}} if hard else {}
        return {
            **scene, "mode": mode, "target_speaker": corpus.speakers[speaker],
            "targets": [{**self.ref(corpus, i), "text": corpus.rows["text"][i].strip()} for i in targets],
            "enrollment": self.ref(corpus, enrollment[0]), "interferers": others}, joiner, seconds

    def full_pair(self, twin):
        """A multi-turn scene and, when ``twin``, its twin. Draws again when the scene is too long.

        The twin keeps every utterance and gap of the scene but enrolls another speaker, so the
        target's utterances turn into one more interferer's and the transcript is empty.
        """
        while True:
            self.pending = {}
            scene, seconds = self.draw_full()
            if seconds > SCENE_SECONDS["full"]:
                continue
            paired = self.draw_twin(scene) if twin else None
            self.audio.update(self.pending)
            return scene, paired

    def draw_full(self):
        rng = self.rng
        corpus = rng.choice(self.targets)
        turns = rng.choices(*FULL_TARGET_TURNS)[0]
        low, high = FULL_UTTERANCE_SECONDS
        while True:
            speaker = rng.randrange(len(corpus.speakers))
            own = enrolled = None
            if self.xsession:
                own = rng.choice(SESSIONS)
                enrolled = next(s for s in SESSIONS if s != own) if rng.random() < XSESSION_CROSS_PROB else own
            targets = corpus.pick(rng, speaker, turns, low, high, session=own)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=set(targets), session=enrolled) if targets else None
            if enrollment:
                break
        used = {corpus.speakers[speaker]}
        target_gap = rng.choice(GAP_PROFILES)
        mean = lambda gap: (gap[0] + gap[1]) / 2
        target_length = sum(corpus.duration[i] for i in targets) + mean(target_gap) * (turns - 1)
        seconds = target_length + (target_gap[1] - mean(target_gap)) * (turns - 1)
        others = []
        for _ in range(rng.choices(*FULL_INTERFERERS)[0]):
            gap = rng.choice(GAP_PROFILES)
            other, who, picks = self.other_speaker(used, 1)
            wanted, length = target_length * rng.uniform(0.7, 1.3), other.duration[picks[0]]
            while length < wanted and len(picks) < MAX_UTTERANCES_PER_TRACK:
                more = other.pick(rng, who, 1, low, high, exclude=set(picks))
                if not more:
                    break
                picks += more
                length += mean(gap) + other.duration[more[0]]
            others.append({"speaker": other.speakers[who], "gap": list(gap), "utts": [self.ref(other, i) for i in picks]})
            seconds = max(seconds, sum(other.duration[i] for i in picks) + gap[1] * (len(picks) - 1))
        return {
            **({"session": {"targets": own, "enrollment": enrolled}} if self.xsession else {}),
            "mode": "full", "target_speaker": corpus.speakers[speaker], "target_gap": list(target_gap),
            "targets": [{**self.ref(corpus, i), "text": corpus.rows["text"][i].strip()} for i in targets],
            "enrollment": self.ref(corpus, enrollment[0]), "interferers": others}, seconds

    def solo_pair(self, twin):
        """One short target utterance and, when ``twin``, the scene with another speaker enrolled (transcript empty)."""
        rng = self.rng
        self.pending = {}
        corpus = rng.choice(self.targets)
        while True:
            speaker = rng.randrange(len(corpus.speakers))
            targets = corpus.pick(rng, speaker, 1, *SOLO_UTTERANCE_SECONDS)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=set(targets)) if targets else None
            if enrollment:
                break
        gap = rng.choice(GAP_PROFILES)
        scene = {"mode": "full", "target_speaker": corpus.speakers[speaker], "target_gap": list(gap),
                 "targets": [{**self.ref(corpus, targets[0]), "text": corpus.rows["text"][targets[0]].strip()}],
                 "enrollment": self.ref(corpus, enrollment[0]), "interferers": []}
        paired = self.draw_twin(scene) if twin else None
        self.audio.update(self.pending)
        return scene, paired

    def handover_pair(self, twin):
        """One target utterance and one other speaker's utterance in a row; when ``twin``, the same with another speaker enrolled."""
        rng = self.rng
        self.pending = {}
        corpus = rng.choice(self.targets)
        low, high = HANDOVER_UTTERANCE_SECONDS
        while True:
            speaker = rng.randrange(len(corpus.speakers))
            targets = corpus.pick(rng, speaker, 1, low, high)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=set(targets)) if targets else None
            if enrollment:
                break
        name = corpus.speakers[speaker]
        hard, other = None, None
        near = [(n, c) for n, c in (self.neighbors or {}).get(name, [])[: self.hard_rank] if n in self.where]
        if near and rng.random() < 0.5:
            neighbor, cosine = rng.choice(near)
            close, who = self.where[neighbor]
            picks = close.pick(rng, who, 1, low, high)
            if picks:
                hard, other = {"kind": "handover", "neighbor": neighbor, "cosine": cosine}, (close, who, picks)
        while other is None:
            close, who, _ = self.other_speaker({name}, 1)
            picks = close.pick(rng, who, 1, low, high)
            other = (close, who, picks) if picks else None
        close, who, picks = other
        scene = {**({"hard": hard} if hard else {}), "mode": "alternate", "target_speaker": name,
                 "targets": [{**self.ref(corpus, targets[0]), "text": corpus.rows["text"][targets[0]].strip()}],
                 "enrollment": self.ref(corpus, enrollment[0]),
                 "interferers": [{"speaker": close.speakers[who], "utts": [self.ref(close, picks[0])]}]}
        paired = self.draw_twin(scene) if twin else None
        self.audio.update(self.pending)
        return scene, paired

    def draw_twin(self, scene):
        """The scene with another speaker enrolled; half of the time one close to the real target."""
        rng = self.rng
        present = {scene["target_speaker"], *(o["speaker"] for o in scene["interferers"])}
        kind, cosine = "random", None
        near = [(n, c) for n, c in (self.neighbors or {}).get(scene["target_speaker"], [])[: self.hard_rank]
                if n in self.where and n not in present]
        enrollment = None
        if near and rng.random() < 0.5:
            name, cosine = rng.choice(near)
            corpus, who = self.where[name]
            picks = corpus.pick(rng, who, 1, *ENROLLMENT_SECONDS)
            if picks:
                kind, enrollment = "near", (corpus, who, picks[0])
        while enrollment is None:
            corpus = rng.choice(self.targets)
            who = rng.randrange(len(corpus.speakers))
            picks = corpus.pick(rng, who, 1, *ENROLLMENT_SECONDS) if corpus.speakers[who] not in present else None
            enrollment = (corpus, who, picks[0]) if picks else None
        corpus, who, utterance = enrollment
        timed = scene["mode"] == "full"  # alternate scenes take their gaps from the loader
        former = {"speaker": scene["target_speaker"], **({"gap": scene["target_gap"]} if timed else {}),
                  "utts": [{k: t[k] for k in ("cut_id", "start", "duration")} for t in scene["targets"]]}
        interferers = [*scene["interferers"], former]
        rng.shuffle(interferers)
        return {"mode": scene["mode"], "target_speaker": corpus.speakers[who],
                **({"target_gap": scene["target_gap"]} if timed else {}),
                "targets": [], "enrollment": self.ref(corpus, utterance), "interferers": interferers,
                "twin": {"kind": kind, **({"cosine": cosine} if cosine is not None else {})}}


def record(language, number, scene, joiner, pair=None):
    base = {"dataset_id": DATASET_ID, "version": VERSION, "split": language}
    target = joiner.join(t["text"] for t in scene["targets"])
    present = bool(scene["targets"])
    # With no target, the mixture slot points at the first other speaker's first utterance.
    mixture = scene["targets"][0] if present else scene["interferers"][0]["utts"][0]
    kind = f"{scene['hard']['kind']}-" if "hard" in scene else "twin-" if "twin" in scene else ""
    labels = {"target_present": present, "schedule": scene["mode"], "n_interferers": len(scene["interferers"])}
    if scene["mode"] == "full" and present:
        labels["n_target_turns"] = len(scene["targets"])
    if "hard" in scene:
        labels["hard_cosine"] = scene["hard"]["cosine"]
    if pair is not None:
        labels["pair"] = pair
    if "session" in scene:
        labels["cross_session"] = scene["session"]["targets"] != scene["session"]["enrollment"]
    if "twin" in scene:
        labels["twin_enrollment"] = scene["twin"]["kind"]
        if "cosine" in scene["twin"]:
            labels["hard_cosine"] = scene["twin"]["cosine"]
    return {
        "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{language}:{kind}{scene['mode']}:{number:07d}",
        "task": "ts_asr", "target": target, "language": language, "labels": labels,
        "hotwords": [],
        "audio_slots": [
            {"name": "enrollment", "purpose": "enrollment", "ref": {**base, **scene["enrollment"]}},
            {"name": "mixture", "purpose": "mixture", "ref": {**base, **{k: mixture[k] for k in ("cut_id", "start", "duration")}}}],
        "metadata": {"scene": {**scene, "enrollment": scene["enrollment"]}, "source_group": scene["target_speaker"]}}


def main():
    global VERSION
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zh", type=int, default=150000)
    parser.add_argument("--en", type=int, default=100000)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--neighbors", type=Path, help="neighbors.json: build the hard (similar voice) version")
    parser.add_argument("--hard-rank", type=int, default=10)
    parser.add_argument("--absent-share", type=float, default=0.55)
    parser.add_argument("--multi", action="store_true", help="build the multi-turn (full) version with twins")
    parser.add_argument("--twin-share", type=float, default=0.26, help="share of the records that are twins")
    parser.add_argument("--solo", action="store_true", help="build the short solo version (one short target utterance, nobody else) with twins")
    parser.add_argument("--handover", action="store_true", help="build the handover version (target and one other speaker, one utterance each, in a row) with twins")
    parser.add_argument("--xsession", action="store_true", help="with --multi: KeSpeech targets enrolled from the same or the other session (zh only)")
    parser.add_argument("--magicdata", action="store_true", help="with --multi: MagicData targets (zh only)")
    args = parser.parse_args()
    if sum((args.multi, args.solo, args.handover)) > 1:
        parser.error("--multi, --solo and --handover build different pools; pick one")
    if args.xsession and (not args.multi or args.en):
        parser.error("--xsession builds the zh multi-turn pool: pass --multi and --en 0")
    if args.magicdata and (not args.multi or args.en or args.xsession):
        parser.error("--magicdata builds the zh multi-turn pool: pass --multi and --en 0, without --xsession")
    if (args.multi or args.solo or args.handover) and not 0 <= args.twin_share < 1:
        parser.error("--twin-share must be in [0, 1)")
    VERSION = args.version
    args.output_dir.mkdir(parents=True, exist_ok=True)
    neighbors = json.loads(args.neighbors.read_text()) if args.neighbors else None
    report = {}
    for language, count in (("zh", args.zh), ("en", args.en)):
        if (args.xsession or args.magicdata) and not count:
            continue
        builder = Builder(language, random.Random(f"{SEED}:{language}:{args.version}"),
                          neighbors and neighbors[language], args.hard_rank, args.xsession, args.magicdata)
        modes, weights = zip(*MODES[language])
        records, tally = [], Counter()
        if args.multi or args.solo or args.handover:
            twin_chance = args.twin_share / (1 - args.twin_share)  # twins per base scene
            number = 0
            while number < count:
                draw = builder.solo_pair if args.solo else builder.handover_pair if args.handover else builder.full_pair
                scene, paired = draw(builder.rng.random() < twin_chance)
                joiner = "" if language == "zh" else " "
                records.append(record(language, number, scene, joiner, pair=number if paired else None))
                tally["solo" if args.solo else f"handover-{'near' if 'hard' in scene else 'random'}" if args.handover
                      else f"full-{len(scene['targets'])}turns"] += 1
                number += 1
                if paired and number < count:
                    records.append(record(language, number, paired, joiner, pair=number - 1))
                    tally[f"twin-{paired['twin']['kind']}"] += 1
                    number += 1
                if number % 25000 < 2:
                    print(language, number, flush=True)
        else:
            for number in range(count):
                hard = None
                if neighbors:
                    hard = "absent" if builder.rng.random() < args.absent_share else "present"
                if hard == "absent":
                    mode = builder.rng.choices(("alternate", "burst"), (0.35, 0.65))[0]  # no target, so no short
                else:
                    mode = builder.rng.choices(modes, weights)[0]
                scene, joiner = builder.scene(mode, hard)
                records.append(record(language, number, scene, joiner))
                tally[f"{hard}-{mode}" if hard else mode] += 1
                if (number + 1) % 25000 == 0:
                    print(language, number + 1, flush=True)
        with gzip.open(args.output_dir / f"records_{language}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        with gzip.open(args.output_dir / f"audio_index_{language}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in sorted(builder.audio.values(), key=lambda r: r["cut_id"]):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        report[language] = {"records": count, "modes": dict(tally), "audio_files": len(builder.audio)}
        print(language, report[language], flush=True)
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
