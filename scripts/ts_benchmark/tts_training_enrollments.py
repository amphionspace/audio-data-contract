#!/usr/bin/env python3
"""Synthesize cross-lingual (and same-language) TTS enrollments for TS-ASR training targets.

The TS-ASR model never sees an enrollment in another language than the mixture, and on ts_asr_crosslingual it
answers "target absent" for 18-39% of real target speech when the enrollment language differs. This writes, for
target speakers of the online-mix sources (aishellmix ``train_1spk``: zh, librimix ``train_1spk``: en), Qwen3-TTS
clones of their voice speaking the other language and their own language, to be used as enrollments in training
(both kinds, so "synthetic" is not a cue for the language switch or for presence).

Voice: one real enrollment clip (4-12 s) of the speaker. ``--voice xvector`` (v1-20261110) clones from the speaker
embedding only; on it the zh clones of en speakers came out at mean ECAPA cosine 0.49 to the speaker (0.673 for real
speakers across languages). ``--voice icl`` also gives the clip's transcript (the target of the train_1spk record
whose mixture is that clip, available for ~all of them) so the model continues the voice in context; speakers whose
clip has no transcript are skipped.
Speaker: ``^([^_-]+)`` of the record's ``source_record_id`` (as the look-alike tables). Sentences: targets of
other records of the same sources, each used once. Output per shard: ``utterances-shard<i>.jsonl.gz`` with
``speaker`` (``<dataset>:<id>``), ``language``, ``text``, ``duration``, ``path`` (relative), ``ref_path``, ``kind``
(``cross`` / ``same``); ``--merge`` joins the shards into ``utterances.jsonl.gz``.

    python scripts/ts_benchmark/tts_training_enrollments.py --output <dir> --speakers 1000 --shard 0/8
"""

import argparse
import gzip
import json
import random
import re
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = "/workspace/data"
SOURCES = {  # language -> (dataset, records, audio index)
    "zh": ("aishellmix", "datasets/aishellmix/versions/pack3-current-audio-record-20260910-punc-20261102/records/train_1spk.jsonl.gz",
           "datasets/aishellmix/versions/pack3-current-audio-record-20260910/audio_index/audio-index.jsonl.gz"),
    "en": ("librimix", "datasets/librimix/versions/960-current-audio-record-20260910-punc-20261102/records/train_1spk.jsonl.gz",
           "datasets/librimix/versions/960-current-audio-record-20260910/audio_index/audio-index.jsonl.gz"),
}
LANGUAGE = {"zh": "Chinese", "en": "English"}
SPEAKER = re.compile(r"^([^_-]+)")
SR = 16000


def read(path):
    with gzip.open(Path(ROOT) / path, "rt") as handle:
        return [json.loads(line) for line in handle]


def plan(args):
    rng = random.Random(args.seed)
    voices, texts = [], {}
    for lang, (dataset, records_path, index_path) in SOURCES.items():
        index = {r["cut_id"]: r for r in read(index_path)}
        records = read(records_path)
        transcript = {next(s["ref"]["cut_id"] for s in r["audio_slots"] if s["name"] == "mixture"): r["target"].strip()
                      for r in records}
        by_speaker, sentences = {}, []
        for r in records:
            speaker = SPEAKER.match(r["metadata"]["source_record_id"]).group(1)
            enroll = next(s["ref"]["cut_id"] for s in r["audio_slots"] if s["name"] == "enrollment")
            entry = index.get(enroll)
            if entry and 4.0 <= entry["duration"] <= 12.0:
                by_speaker.setdefault(speaker, (entry["relative_path"], transcript.get(enroll)))
            text = r["target"].strip()
            if lang == "zh" and 8 <= len(text) <= 26 or lang == "en" and 6 <= len(text.split()) <= 18:
                sentences.append(text)
        speakers = sorted(by_speaker)
        for speaker in sorted(rng.sample(speakers, min(args.speakers, len(speakers)))):
            ref_path, ref_text = by_speaker[speaker]
            voices.append({"speaker": f"{dataset}:{speaker}", "language": lang, "ref_path": ref_path,
                           "ref_text": ref_text})
        texts[lang] = sorted(set(sentences))
        rng.shuffle(texts[lang])
    return voices, texts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="/workspace/model/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--speakers", type=int, default=1000, help="per language")
    parser.add_argument("--per-kind", type=int, default=2, help="sentences per speaker in the other / own language")
    parser.add_argument("--max-new-tokens", type=int, default=300)
    parser.add_argument("--max-seconds", type=float, default=12.0)
    parser.add_argument("--voice", choices=("xvector", "icl"), default="icl")
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--shard", default="0/1")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if args.merge:
        rows = []
        for part in sorted(args.output.glob("utterances-shard*.jsonl.gz")):
            with gzip.open(part, "rt") as handle:
                rows += [json.loads(line) for line in handle]
        rows.sort(key=lambda r: r["id"])
        with gzip.open(args.output / "utterances.jsonl.gz", "wt") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps({"utterances": len(rows), "speakers": len({r["speaker"] for r in rows})}))
        return
    shard, shards = map(int, args.shard.split("/"))
    voices, texts = plan(args)
    cursor = {"zh": 0, "en": 0}
    jobs = []
    for index, voice in enumerate(voices):  # sentences are assigned over all voices so shards never share one
        other = "en" if voice["language"] == "zh" else "zh"
        for kind, lang in (("cross", other), ("same", voice["language"])):
            for _ in range(args.per_kind):
                jobs.append((index, voice, kind, lang, texts[lang][cursor[lang]]))
                cursor[lang] += 1
    import torch
    from qwen_tts import Qwen3TTSModel
    from scipy.signal import resample_poly

    model = Qwen3TTSModel.from_pretrained(args.model, device_map="cuda:0", dtype=torch.bfloat16)
    args.output.mkdir(parents=True, exist_ok=True)
    rows, dropped = [], 0
    mine = [j for j in jobs if j[0] % shards == shard]
    if args.voice == "icl":
        skipped = len({j[0] for j in mine if not j[1]["ref_text"]})
        mine = [j for j in mine if j[1]["ref_text"]]
        print(f"shard {shard}: {skipped} speakers skipped without a transcript of their clip", flush=True)
    for v_index in sorted({j[0] for j in mine}):
        group = [j for j in mine if j[0] == v_index]
        voice = group[0][1]
        if args.voice == "icl":
            prompt = model.create_voice_clone_prompt(ref_audio=str(Path(ROOT) / voice["ref_path"]),
                                                     ref_text=voice["ref_text"])
        else:
            prompt = model.create_voice_clone_prompt(ref_audio=str(Path(ROOT) / voice["ref_path"]),
                                                     x_vector_only_mode=True)
        wavs, sr = model.generate_voice_clone(text=[j[4] for j in group], language=[LANGUAGE[j[3]] for j in group],
                                              voice_clone_prompt=prompt * len(group), max_new_tokens=args.max_new_tokens)
        for n, ((_, _, kind, lang, text), wav) in enumerate(zip(group, wavs)):
            wav = np.asarray(wav, dtype=np.float32)
            if sr != SR:
                g = gcd(SR, sr)
                wav = resample_poly(wav, SR // g, sr // g).astype(np.float32)
            if not 0.8 <= len(wav) / SR <= args.max_seconds:
                dropped += 1
                continue
            uid = f"{voice['speaker'].replace(':', '-')}-{kind}-{lang}-{n:02d}"
            rel = Path("audio") / voice["speaker"].replace(":", "-") / f"{uid}.flac"
            (args.output / rel).parent.mkdir(parents=True, exist_ok=True)
            sf.write(args.output / rel, wav, SR, subtype="PCM_16")
            rows.append({"id": uid, "speaker": voice["speaker"], "language": lang, "kind": kind, "text": text,
                         "duration": round(len(wav) / SR, 3), "path": str(rel), "ref_path": voice["ref_path"],
                         "voice": args.voice})
        if len(rows) % 200 < len(group):
            print(f"shard {shard}: {len(rows)} utterances, {dropped} dropped", flush=True)
    with gzip.open(args.output / f"utterances-shard{shard:02d}.jsonl.gz", "wt") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"shard": shard, "utterances": len(rows), "dropped": dropped}), flush=True)


if __name__ == "__main__":
    main()
