#!/usr/bin/env python3
"""Read the selected items aloud with Qwen3-TTS zero-shot voice cloning.

Runs in the TTS environment (``pip install qwen-tts``; conda env ``qwen-tts``):

    CUDA_VISIBLE_DEVICES=5 <qwen-tts python> scripts/context_correction/tts.py --source <source dir>

Both items of a pair get the same voice, so the pair differs only where the text
differs. Output is 16 kHz mono PCM16 under ``<source>/audio/`` plus ``tts.jsonl``
(one row per finished item; a rerun skips finished items).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
import torch
import yaml

HERE = Path(__file__).resolve().parent
SR = 16000


def read_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def stable_int(text: str) -> int:
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16)


def assign_voices(items, voices, seed):
    """Balanced, deterministic voice per pair: pairs sorted by hash, voices round-robin."""
    pairs = sorted({i["pair_id"] for i in items}, key=lambda p: hashlib.sha1(f"{seed}:{p}".encode()).hexdigest())
    return {pair: voices[index % len(voices)] for index, pair in enumerate(pairs)}


def load_audio(path):
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return wav, sr


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--items", type=Path, help="default: <source>/items.jsonl")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--shard", default="0/1",
                        help="K/N: synthesize only pairs with hash %% N == K (one process per GPU); "
                             "each shard writes tts.shardKofN.jsonl, appended to tts.jsonl when all are done")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    items = read_jsonl(args.items or args.source / "items.jsonl")
    voices = read_jsonl(args.source / "voices.jsonl")
    shard, shards = (int(x) for x in args.shard.split("/"))
    out_path = args.source / ("tts.jsonl" if shards == 1 else f"tts.shard{shard}of{shards}.jsonl")
    finished_rows = read_jsonl(args.source / "tts.jsonl") + (read_jsonl(out_path) if shards > 1 else [])
    done = {row["id"] for row in finished_rows}
    # pairs synthesized in an earlier run keep their voice; only new pairs are assigned
    voice_by_id = {v["voice_id"]: v for v in voices}
    recorded = {row["pair_id"]: voice_by_id[row["voice_id"]] for row in finished_rows}
    by_pair_voice = {**assign_voices([i for i in items if i["pair_id"] not in recorded], voices, recipe["seed"]),
                     **recorded}

    from qwen_tts import Qwen3TTSModel

    model = Qwen3TTSModel.from_pretrained(recipe["tts"]["model"], device_map="cuda:0", dtype=torch.bfloat16)
    prompts = {}
    groups = defaultdict(list)
    for item in items:
        if item["id"] not in done and stable_int(item["pair_id"]) % shards == shard:
            groups[by_pair_voice[item["pair_id"]]["voice_id"]].append(item)
    audio_dir = args.source / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    total = sum(len(g) for g in groups.values())
    finished = 0
    with out_path.open("a", encoding="utf-8") as sink:
        for voice_id, group in sorted(groups.items()):
            voice = voice_by_id[voice_id]
            if voice_id not in prompts:
                prompts[voice_id] = model.create_voice_clone_prompt(
                    ref_audio=load_audio(voice["prompt"]["path"]), ref_text=voice["prompt"]["text"])
            for start in range(0, len(group), args.batch):
                batch = group[start:start + args.batch]
                # One seed per batch keeps reruns of the same batch reproducible.
                torch.manual_seed(stable_int(batch[0]["id"]))
                wavs, sr = model.generate_voice_clone(
                    text=[i["text"] for i in batch], language=recipe["tts"]["language"],
                    voice_clone_prompt=prompts[voice_id] * len(batch))
                for item, wav in zip(batch, wavs):
                    wav = np.asarray(wav, dtype=np.float32)
                    if sr != SR:
                        wav = soxr.resample(wav, sr, SR)
                    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
                    if peak > 0.99:  # keep headroom; level is otherwise the TTS's own
                        wav = wav * (0.99 / peak)
                    path = audio_dir / f"{item['id']}.wav"
                    sf.write(path, wav, SR, subtype="PCM_16")
                    row = {"id": item["id"], "pair_id": item["pair_id"], "voice_id": voice_id,
                           "speaker": voice["speaker"], "path": str(path), "duration": round(len(wav) / SR, 4),
                           "tts_model": recipe["tts"]["model"], "tts_sample_rate": sr}
                    sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                sink.flush()
                finished += len(batch)
                print(f"[tts] {finished}/{total} {voice_id}", flush=True)


if __name__ == "__main__":
    main()
