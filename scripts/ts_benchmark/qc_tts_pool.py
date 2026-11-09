#!/usr/bin/env python3
"""Quality check of the Qwen3-TTS cross-lingual pools (tts_crosslingual_pool.py) before they enter a recipe.

1. Content: every utterance is transcribed by a plain-ASR server (OpenAI chat API of the AmphionASR package,
   ``client.py`` request form); units are CJK characters / Latin words after lower-casing and dropping punctuation;
   an utterance whose error rate exceeds ``--max-error`` is dropped.
2. Voice: ECAPA (WeSpeaker ECAPA-TDNN512-LM) cosine between a voice's zh and en utterances (mean embedding per
   language) against the cosine between different voices; a voice whose cross-language cosine falls below
   ``--min-voice-cos`` is dropped from both lists.

Kept utterances are written back as ``utterances.jsonl.gz`` (the unfiltered list is kept as
``utterances-unfiltered.jsonl.gz``) and the statistics as ``tts-qc.json``. Needs ``onnxruntime`` and ``requests``.

    python scripts/ts_benchmark/qc_tts_pool.py --pools <pools dir> --asr-url http://127.0.0.1:8100 \
        --package /workspace/data/packages/amphionasr-1.7b-v3-sumfull-mtp-candidate
"""

import argparse
import base64
import gzip
import io
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

ECAPA = "/workspace/model/wespeaker-ecapa-tdnn512-LM/voxceleb_ECAPA512_LM.onnx"
UNITS = re.compile(r"[㐀-鿿]|[a-z0-9']+")


def units(text):
    return UNITS.findall(text.lower())


def edit(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def transcribe(url, model, prepare, path):
    import requests

    wav, context = prepare(path)
    buffer = io.BytesIO()
    sf.write(buffer, wav, 16000, format="WAV", subtype="PCM_16")
    body = {"model": model, "temperature": 0, "max_tokens": 256,
            "messages": [{"role": "system", "content": context},
                         {"role": "user", "content": [{"type": "input_audio", "input_audio": {
                             "data": base64.b64encode(buffer.getvalue()).decode("ascii"), "format": "wav"}}]}]}
    raw = requests.post(url.rstrip("/") + "/v1/chat/completions", json=body, timeout=180).json()
    raw = raw["choices"][0]["message"]["content"] or ""
    return raw.partition("<asr_text>")[2].strip()


def embedder():
    import onnxruntime as ort
    import torch
    from torchaudio.compliance import kaldi

    session = ort.InferenceSession(ECAPA, providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name

    def embed(path):
        wav, _ = sf.read(path, dtype="float32")
        f = kaldi.fbank(torch.from_numpy(wav).unsqueeze(0) * 32768, num_mel_bins=80, frame_length=25,
                        frame_shift=10, dither=0.0, sample_frequency=16000, window_type="hamming", use_energy=False)
        f = f - f.mean(0, keepdim=True)
        e = session.run(None, {name: f.unsqueeze(0).numpy()})[0].reshape(-1)
        return e / np.linalg.norm(e)
    return embed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pools", type=Path, required=True)
    parser.add_argument("--asr-url", required=True)
    parser.add_argument("--asr-model", default="amphionasr-v3-asr")
    parser.add_argument("--package", type=Path, required=True, help="AmphionASR package (for common.prepare_input)")
    parser.add_argument("--max-error", type=float, default=0.3)
    parser.add_argument("--min-voice-cos", type=float, default=0.5)
    parser.add_argument("--threads", type=int, default=16)
    args = parser.parse_args()
    sys.path.insert(0, str(args.package))
    from common import prepare_input

    lists = {}
    for lang in ("zh", "en"):
        folder = args.pools / f"tts-bilingual-{lang}"
        source = folder / "utterances-unfiltered.jsonl.gz"
        if not source.exists():
            shutil.copy(folder / "utterances.jsonl.gz", source)
        with gzip.open(source, "rt") as handle:
            lists[lang] = [json.loads(line) for line in handle]
    rows = [(lang, row) for lang, items in lists.items() for row in items]
    paths = [str(args.pools / f"tts-bilingual-{lang}" / row["path"]) for lang, row in rows]
    with ThreadPoolExecutor(args.threads) as pool:
        hyps = list(pool.map(lambda p: transcribe(args.asr_url, args.asr_model, lambda x: prepare_input(x), p), paths))
    embed = embedder()
    vectors = [embed(p) for p in paths]
    stats = {"utterances": len(rows), "content_dropped": 0, "error_rate_by_lang": {}}
    per_voice = {}
    errors = {"zh": [0, 0], "en": [0, 0]}
    keep = []
    for (lang, row), hyp, vector in zip(rows, hyps, vectors):
        ref, out = units(row["text"]), units(hyp)
        e = edit(ref, out)
        errors[lang][0] += e
        errors[lang][1] += len(ref)
        rate = e / max(len(ref), 1)
        row["qc"] = {"asr": hyp, "error_rate": round(rate, 3)}
        per_voice.setdefault(row["speaker"], {"zh": [], "en": []})[lang].append(vector)
        if rate > args.max_error:
            stats["content_dropped"] += 1
        else:
            keep.append((lang, row))
    stats["error_rate_by_lang"] = {k: round(v[0] / max(v[1], 1), 4) for k, v in errors.items()}
    means = {v: {l: np.mean(x, 0) / np.linalg.norm(np.mean(x, 0)) for l, x in d.items() if x} for v, d in per_voice.items()}
    cross = {v: float(m["zh"] @ m["en"]) for v, m in means.items() if "zh" in m and "en" in m}
    voices = sorted(cross)
    other = [float(means[a]["zh"] @ means[b]["en"]) for a in voices for b in voices if a != b]
    stats["voice_cross_language_cos"] = {"mean": round(float(np.mean(list(cross.values()))), 3),
                                         "min": round(min(cross.values()), 3),
                                         "different_voices_mean": round(float(np.mean(other)), 3),
                                         "different_voices_p99": round(float(np.percentile(other, 99)), 3)}
    bad = {v for v, c in cross.items() if c < args.min_voice_cos}
    stats["voices"] = len(cross)
    stats["voices_dropped"] = sorted(bad)
    for lang in ("zh", "en"):
        kept = [row for l, row in keep if l == lang and row["speaker"] not in bad]
        stats[f"kept_{lang}"] = len(kept)
        with gzip.open(args.pools / f"tts-bilingual-{lang}/utterances.jsonl.gz", "wt") as handle:
            for row in kept:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats["per_voice_cross_cos"] = {v: round(c, 3) for v, c in sorted(cross.items())}
    (args.pools / "tts-qc.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in stats.items() if k != "per_voice_cross_cos"}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
