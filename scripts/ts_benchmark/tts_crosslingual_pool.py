#!/usr/bin/env python3
"""Synthesize same-voice zh and en utterances with Qwen3-TTS voice cloning for ts_asr_crosslingual.

Each voice is cloned (ICL mode: reference clip + its transcript) from one utterance of a speaker of a test split no
training used (AISHELL-1 test for zh, LibriSpeech test-clean for en), then speaks ``--per-voice`` Chinese and
``--per-voice`` English sentences. The reference clip itself is not used, so enrollment and mixture of every scene
are synthetic and the two enrollment conditions differ only in language. Sentences are test transcripts of other
speakers, each used once. Writes ``tts-bilingual-{zh,en}/utterances.jsonl.gz`` (dataset ``tts_bilingual``, one
speaker id per voice in both lists) and 16 kHz FLAC files; ``voices.json`` records the references.

Run in an environment with ``qwen_tts`` (Qwen3-TTS-12Hz-1.7B-Base):

    python scripts/ts_benchmark/tts_crosslingual_pool.py --output <pools dir> --zh-voices 20 --en-voices 30 --shard 0/6
    (one per GPU and shard), then the same command with --merge
"""

import argparse
import gzip
import json
import random
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = "/workspace/data/datasets"
SOURCES = {
    "zh": (f"{ROOT}/aishell/versions/legacy-20260804/test_sup_0/aishell_supervisions_test.jsonl.gz",
           f"{ROOT}/aishell/versions/legacy-20260804/test_rec_0/aishell_recordings_test.jsonl.gz"),
    "en": (f"{ROOT}/librispeech/versions/legacy-20260804/test_clean_sup_0/librispeech_supervisions_test-clean.jsonl.gz",
           f"{ROOT}/librispeech/versions/legacy-20260804/test_clean_rec_0/librispeech_recordings_test-clean.jsonl.gz"),
}
TEXT_SOURCES = {  # sentences to speak: other test transcripts
    "zh": f"{ROOT}/aishell/versions/legacy-20260804/test_sup_0/aishell_supervisions_test.jsonl.gz",
    "en": f"{ROOT}/librispeech/versions/legacy-20260804/test_other_sup_0/librispeech_supervisions_test-other.jsonl.gz",
}
LANGUAGE = {"zh": "Chinese", "en": "English"}
SR = 16000


def read(path):
    with gzip.open(path, "rt") as handle:
        return [json.loads(line) for line in handle]


def sentences(lang):
    out = []
    for s in read(TEXT_SOURCES[lang]):
        text = s["text"].strip()
        if lang == "zh":
            text = text.replace(" ", "")
            if 8 <= len(text) <= 24:
                out.append(text)
        else:
            words = text.split()
            if 6 <= len(words) <= 18:
                out.append(text.capitalize() if text.isupper() else text)
    return sorted(set(out))


def references(lang, count, rng):
    sups, recs = SOURCES[lang]
    audio = {r["id"]: r["sources"][0]["source"] for r in read(recs)}
    by_speaker = {}
    for s in read(sups):
        if 4.0 <= s["duration"] <= 10.0 and s["recording_id"] in audio and s.get("start", 0) == 0:
            by_speaker.setdefault(s["speaker"], []).append(s)
    speakers = sorted(by_speaker)
    chosen = rng.sample(speakers, min(count, len(speakers)))
    out = []
    for speaker in sorted(chosen):
        s = rng.choice(by_speaker[speaker])
        text = s["text"].replace(" ", "") if lang == "zh" else s["text"].lower()
        out.append({"voice": f"{lang}ref-{speaker}", "ref_lang": lang, "ref_id": s["id"], "ref_text": text,
                    "ref_audio": audio[s["recording_id"]], "gender": s.get("gender")})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="/workspace/model/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--zh-voices", type=int, default=20)
    parser.add_argument("--en-voices", type=int, default=30)
    parser.add_argument("--per-voice", type=int, default=10)
    parser.add_argument("--batch", type=int, default=10)
    parser.add_argument("--max-new-tokens", type=int, default=300, help="codec frames (12 Hz): ~25 s, far above a sentence")
    parser.add_argument("--max-seconds", type=float, default=12.0, help="longer outputs are runaway generations; dropped")
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--shard", default="0/1", help="i/n: synthesize voices i, i+n, ... (one GPU per shard)")
    parser.add_argument("--merge", action="store_true", help="join the shard lists into utterances.jsonl.gz")
    args = parser.parse_args()
    if args.merge:
        for lang in ("zh", "en"):
            rows = []
            for part in sorted((args.output / f"tts-bilingual-{lang}").glob("utterances-shard*.jsonl.gz")):
                rows += read(part)
            rows.sort(key=lambda r: r["id"])
            with gzip.open(args.output / f"tts-bilingual-{lang}/utterances.jsonl.gz", "wt") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(lang, len(rows))
        return
    shard, shards = map(int, args.shard.split("/"))
    import torch
    from qwen_tts import Qwen3TTSModel

    rng = random.Random(args.seed)
    voices = references("zh", args.zh_voices, rng) + references("en", args.en_voices, rng)
    texts = {lang: sentences(lang) for lang in ("zh", "en")}
    for items in texts.values():
        rng.shuffle(items)
    need = len(voices) * args.per_voice
    if any(len(t) < need for t in texts.values()):
        raise SystemExit(f"not enough sentences: {[(k, len(v)) for k, v in texts.items()]} < {need}")
    model = Qwen3TTSModel.from_pretrained(args.model, device_map="cuda:0", dtype=torch.bfloat16)
    lists = {"zh": [], "en": []}
    for v_index, voice in enumerate(voices):
        if v_index % shards != shard:
            continue
        prompt = model.create_voice_clone_prompt(ref_audio=voice["ref_audio"], ref_text=voice["ref_text"])
        for lang in ("zh", "en"):
            chunk = texts[lang][v_index * args.per_voice:(v_index + 1) * args.per_voice]
            for start in range(0, len(chunk), args.batch):
                batch = chunk[start:start + args.batch]
                wavs, sr = model.generate_voice_clone(text=batch, language=[LANGUAGE[lang]] * len(batch),
                                                      voice_clone_prompt=prompt * len(batch),
                                                      max_new_tokens=args.max_new_tokens)
                for i, (text, wav) in enumerate(zip(batch, wavs)):
                    wav = np.asarray(wav, dtype=np.float32)
                    if sr != SR:
                        from math import gcd

                        from scipy.signal import resample_poly
                        g = gcd(SR, sr)
                        wav = resample_poly(wav, SR // g, sr // g).astype(np.float32)
                    if not 0.8 <= len(wav) / SR <= args.max_seconds:
                        print(f"dropped {voice['voice']} {lang} {len(wav) / SR:.1f}s: {text}", flush=True)
                        continue
                    uid = f"{voice['voice']}-{lang}-{start + i:02d}"
                    rel = Path("audio") / voice["voice"] / f"{uid}.flac"
                    path = args.output / f"tts-bilingual-{lang}" / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    sf.write(path, wav, SR, subtype="PCM_16")
                    lists[lang].append({"id": uid, "speaker": voice["voice"], "text": text,
                                        "duration": round(len(wav) / SR, 3), "path": str(rel), "gender": voice["gender"]})
        print(f"voice {v_index + 1}/{len(voices)} {voice['voice']}", flush=True)
    for lang, rows in lists.items():
        (args.output / f"tts-bilingual-{lang}").mkdir(parents=True, exist_ok=True)
        with gzip.open(args.output / f"tts-bilingual-{lang}/utterances-shard{shard:02d}.jsonl.gz", "wt") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    if shard == 0:
        (args.output / "tts-voices.json").write_text(json.dumps(voices, indent=1, ensure_ascii=False))
    print(json.dumps({lang: len(rows) for lang, rows in lists.items()}))


if __name__ == "__main__":
    main()
