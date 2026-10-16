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

    python build_ts_scene_pool.py --output-dir DIR [--zh 150000 --en 100000]
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
DATASET_ID, VERSION = "ts_scene_pool", "v2-20261016"
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
SCENE_SECONDS = {"alternate": 30.0, "burst": 22.0, "short": 14.0}
MEAN_GAP_SECONDS = {"alternate": 0.6, "burst": 0.25, "short": 0.15}
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
    def __init__(self, language, rng):
        self.language, self.rng = language, rng
        self.corpora = [Corpus(*c, language) for c in CORPORA[language]]
        self.targets = [c for c in self.corpora if c.target]
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

    def scene(self, mode):
        """A scene no longer than SCENE_SECONDS[mode]; draws again when one comes out too long."""
        while True:
            self.pending = {}
            scene, joiner, seconds = self.draw(mode)
            if seconds <= SCENE_SECONDS[mode]:
                self.audio.update(self.pending)
                return scene, joiner

    def draw(self, mode):
        rng = self.rng
        corpus = rng.choice(self.targets)
        short_low, short_high = SHORT_TARGET_SECONDS[self.language]
        while True:
            speaker = rng.randrange(len(corpus.speakers))
            wanted = 1 if mode != "alternate" else (2 if rng.random() < 0.4 else 1)
            targets = corpus.pick(rng, speaker, wanted, *((short_low, short_high) if mode == "short" else (None, None)))
            enrollment = targets and corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=set(targets))
            if targets and enrollment:
                break
        used = {corpus.speakers[speaker]}
        if mode == "alternate":
            k, per_speaker = rng.choices((2, 3, 4, 5, 6), (0.25, 0.25, 0.2, 0.15, 0.15))[0], lambda: 2 if rng.random() < 0.3 else 1
        elif mode == "burst":
            k, per_speaker = rng.choices((1, 2, 3, 4, 5, 6), (0.1, 0.15, 0.2, 0.2, 0.2, 0.15))[0], lambda: rng.randint(2, 4)
        else:
            k, per_speaker = rng.choices((1, 2, 3, 4, 5), (0.25, 0.2, 0.2, 0.2, 0.15))[0], lambda: rng.randint(1, 2)
        others, lengths = [], []
        for _ in range(k):
            count = per_speaker()
            while True:
                try:
                    other, who, picks = self.other_speaker(used, count)
                    break
                except RuntimeError:
                    count = max(1, count - 1)
            others.append({"speaker": other.speakers[who], "utts": [self.ref(other, i) for i in picks]})
            lengths.append(sum(other.duration[i] for i in picks) + MEAN_GAP_SECONDS[mode] * (len(picks) - 1))
        target_seconds = sum(corpus.duration[i] for i in targets) + MEAN_GAP_SECONDS[mode] * (len(targets) - 1)
        # alternate puts everything in a row; burst and short last as long as the longest speaker
        seconds = sum(lengths) + target_seconds + MEAN_GAP_SECONDS[mode] * (len(lengths) + 1) if mode == "alternate" \
            else max([target_seconds, *lengths])
        joiner = "" if self.language == "zh" else " "
        return {
            "mode": mode, "target_speaker": corpus.speakers[speaker],
            "targets": [{**self.ref(corpus, i), "text": corpus.rows["text"][i].strip()} for i in targets],
            "enrollment": self.ref(corpus, enrollment[0]), "interferers": others}, joiner, seconds


def record(language, number, scene, joiner):
    base = {"dataset_id": DATASET_ID, "version": VERSION, "split": language}
    target = joiner.join(t["text"] for t in scene["targets"])
    return {
        "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{language}:{scene['mode']}:{number:07d}",
        "task": "ts_asr", "target": target, "language": language,
        "labels": {"target_present": True, "schedule": scene["mode"], "n_interferers": len(scene["interferers"])},
        "hotwords": [],
        "audio_slots": [
            {"name": "enrollment", "purpose": "enrollment", "ref": {**base, **scene["enrollment"]}},
            {"name": "mixture", "purpose": "mixture", "ref": {**base, **{k: scene["targets"][0][k] for k in ("cut_id", "start", "duration")}}}],
        "metadata": {"scene": {**scene, "enrollment": scene["enrollment"]}, "source_group": scene["target_speaker"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zh", type=int, default=150000)
    parser.add_argument("--en", type=int, default=100000)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for language, count in (("zh", args.zh), ("en", args.en)):
        builder = Builder(language, random.Random(f"{SEED}:{language}"))
        modes, weights = zip(*MODES[language])
        records, tally = [], Counter()
        for number in range(count):
            mode = builder.rng.choices(modes, weights)[0]
            scene, joiner = builder.scene(mode)
            row = record(language, number, scene, joiner)
            records.append(row)
            tally[mode] += 1
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
