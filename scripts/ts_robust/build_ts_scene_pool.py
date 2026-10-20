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
records are twins: the same utterance, but the enrollment is another speaker, so the transcript is empty.

    python build_ts_scene_pool.py --output-dir DIR --version solo-20261019 --solo --zh 60000 --en 20000
"""

import argparse
import gzip
import json
import random
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
FULL_INTERFERERS = ((1, 2, 3, 4), (0.3, 0.3, 0.25, 0.15))
MAX_UTTERANCES_PER_TRACK = 6
COLUMNS = ["id", "speaker", "text", "duration", "cut_id", "root_alias", "relative_path",
           "start_frame", "num_frames", "sample_rate", "channels"]


class Corpus:
    def __init__(self, dataset, version, split, weight, target, language):
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
        self.rows = table.filter(keep).to_pydict()
        self.duration = duration[keep]
        names, inverse = np.unique(np.array(self.rows["speaker"]), return_inverse=True)
        order = np.argsort(inverse, kind="stable")
        bounds = np.searchsorted(inverse[order], np.arange(len(names) + 1))
        self.speakers = [f"{dataset}:{n}" for n in names]
        self.by_speaker = [order[bounds[i]:bounds[i + 1]] for i in range(len(names))]
        print(dataset, "utterances", int(keep.sum()), "speakers", len(names), flush=True)

    def pick(self, rng, speaker, count, low=None, high=None, exclude=()):
        """``count`` distinct utterances of one speaker, optionally within a duration range."""
        rows = [i for i in self.by_speaker[speaker] if i not in exclude
                and (low is None or low <= self.duration[i] <= high)]
        return rng.sample(rows, count) if len(rows) >= count else None

    def usable(self, speaker, count):
        return len(self.by_speaker[speaker]) >= count


class Builder:
    def __init__(self, language, rng, neighbors=None, hard_rank=10):
        self.language, self.rng = language, rng
        self.corpora = [Corpus(*c, language) for c in CORPORA[language]]
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
            targets = corpus.pick(rng, speaker, turns, low, high)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=set(targets)) if targets else None
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
        former = {"speaker": scene["target_speaker"], "gap": scene["target_gap"],
                  "utts": [{k: t[k] for k in ("cut_id", "start", "duration")} for t in scene["targets"]]}
        interferers = [*scene["interferers"], former]
        rng.shuffle(interferers)
        return {"mode": "full", "target_speaker": corpus.speakers[who], "target_gap": scene["target_gap"],
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
    args = parser.parse_args()
    if (args.multi or args.solo) and not 0 <= args.twin_share < 1:
        parser.error("--twin-share must be in [0, 1)")
    VERSION = args.version
    args.output_dir.mkdir(parents=True, exist_ok=True)
    neighbors = json.loads(args.neighbors.read_text()) if args.neighbors else None
    report = {}
    for language, count in (("zh", args.zh), ("en", args.en)):
        builder = Builder(language, random.Random(f"{SEED}:{language}:{args.version}"),
                          neighbors and neighbors[language], args.hard_rank)
        modes, weights = zip(*MODES[language])
        records, tally = [], Counter()
        if args.multi or args.solo:
            twin_chance = args.twin_share / (1 - args.twin_share)  # twins per base scene
            number = 0
            while number < count:
                scene, paired = (builder.solo_pair if args.solo else builder.full_pair)(builder.rng.random() < twin_chance)
                joiner = "" if language == "zh" else " "
                records.append(record(language, number, scene, joiner, pair=number if paired else None))
                tally["solo" if args.solo else f"full-{len(scene['targets'])}turns"] += 1
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
