#!/usr/bin/env python3
"""Read the selected items aloud with CosyVoice3 zero-shot voice cloning (v2 independent split).

The v2 benchmark's synthetic split must not share a TTS with the training data (Qwen3-TTS, tts.py), so it is read
by CosyVoice3 (recipe ``tts.model``, code ``tts.code`` = FunAudioLLM/CosyVoice). Runs in its own environment:

    CUDA_VISIBLE_DEVICES=0 <cosyvoice python> scripts/context_correction/tts_cosyvoice.py \
        --recipe scripts/context_correction/recipe_v2_indep.yaml --source <source dir> [--shard K/N]

Same inputs, outputs and resume rules as tts.py: both items of a pair get the same voice, 16 kHz mono PCM16 under
``<source>/audio/``, one row per finished item in ``tts.jsonl`` (or ``tts.shardKofN.jsonl``). A dialogue item
(``turns``) alternates between the pair's voice and a second voice of another speaker, with a short pause between
turns; its row lists both voices.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
import torch
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tts import SR, assign_voices, read_jsonl, stable_int  # noqa: E402

PROMPT_PREFIX = "You are a helpful assistant.<|endofprompt|>"  # CosyVoice3's zero-shot prompt format
TURN_PAUSE_SECONDS = 0.4
PARTNER_OFFSET = 37  # second voice of a dialogue: a fixed step through the voice list, never the same speaker


def partner_voice(voice, voices):
    index = next(i for i, v in enumerate(voices) if v["voice_id"] == voice["voice_id"])
    for step in range(PARTNER_OFFSET, PARTNER_OFFSET + len(voices)):
        other = voices[(index + step) % len(voices)]
        if other["speaker"] != voice["speaker"]:
            return other
    raise ValueError("a dialogue needs two speakers")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--items", type=Path, help="default: <source>/items.jsonl")
    parser.add_argument("--shard", default="0/1", help="K/N: only pairs with hash %% N == K (one process per GPU)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    items = read_jsonl(args.items or args.source / "items.jsonl")
    voices = read_jsonl(args.source / "voices.jsonl")
    shard, shards = (int(x) for x in args.shard.split("/"))
    out_path = args.source / ("tts.jsonl" if shards == 1 else f"tts.shard{shard}of{shards}.jsonl")
    finished_rows = read_jsonl(args.source / "tts.jsonl") + (read_jsonl(out_path) if shards > 1 else [])
    done = {row["id"] for row in finished_rows}
    voice_by_id = {v["voice_id"]: v for v in voices}
    recorded = {row["pair_id"]: voice_by_id[row["voice_id"]] for row in finished_rows}
    by_pair_voice = {**assign_voices([i for i in items if i["pair_id"] not in recorded], voices, recipe["seed"]),
                     **recorded}

    sys.path.insert(0, recipe["tts"]["code"])
    sys.path.insert(0, str(Path(recipe["tts"]["code"]) / "third_party" / "Matcha-TTS"))
    from cosyvoice.cli.cosyvoice import AutoModel

    model = AutoModel(model_dir=recipe["tts"]["model"])

    def speak(text, voice):
        torch.manual_seed(stable_int(text + voice["voice_id"]))
        chunks = [out["tts_speech"].squeeze(0).float().cpu().numpy() for out in model.inference_zero_shot(
            text, PROMPT_PREFIX + voice["prompt"]["text"], voice["prompt"]["path"], stream=False)]
        wav = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return soxr.resample(wav, model.sample_rate, SR) if model.sample_rate != SR else wav

    groups = defaultdict(list)
    for item in items:
        if item["id"] not in done and stable_int(item["pair_id"]) % shards == shard:
            groups[by_pair_voice[item["pair_id"]]["voice_id"]].append(item)
    audio_dir = args.source / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    total, finished = sum(len(g) for g in groups.values()), 0
    with out_path.open("a", encoding="utf-8") as sink:
        for voice_id, group in sorted(groups.items()):
            voice = voice_by_id[voice_id]
            for item in group:
                turns = item.get("turns") or [item["text"]]
                speakers = [voice, partner_voice(voice, voices)] if len(turns) > 1 else [voice]
                pause = np.zeros(int(TURN_PAUSE_SECONDS * SR), dtype=np.float32)
                parts = []
                for index, turn in enumerate(turns):
                    parts += ([pause] if index else []) + [speak(turn, speakers[index % len(speakers)])]
                wav = np.concatenate(parts).astype(np.float32)
                peak = float(np.max(np.abs(wav))) if wav.size else 0.0
                if peak > 0.99:  # keep headroom; level is otherwise the TTS's own
                    wav = wav * (0.99 / peak)
                path = audio_dir / f"{item['id']}.wav"
                sf.write(path, wav, SR, subtype="PCM_16")
                row = {"id": item["id"], "pair_id": item["pair_id"], "voice_id": voice_id,
                       "speaker": voice["speaker"], "path": str(path), "duration": round(len(wav) / SR, 4),
                       "tts_model": recipe["tts"]["model"], "tts_sample_rate": model.sample_rate}
                if len(speakers) > 1:
                    row["turn_voice_ids"] = [speakers[i % 2]["voice_id"] for i in range(len(turns))]
                sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                sink.flush()
                finished += 1
                if finished % 20 == 0 or finished == total:
                    print(f"[tts] {finished}/{total}", flush=True)


if __name__ == "__main__":
    main()
