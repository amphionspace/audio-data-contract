#!/usr/bin/env python3
"""Check that each synthesized item says its text, at the pinyin level.

A QC ASR that is not under evaluation (SenseVoiceSmall) transcribes every clip.
Hypothesis and reference are compared as pinyin, so homophone choices (the very
thing the benchmark tests) never fail an item. An item passes when

- the whole clip's toneless pinyin error rate is at most ``qc.max_pinyin_error``;
- every evidence span matches the hypothesis in toneless pinyin, so the deciding
  context is audible;
- every target span matches in tone-exact pinyin, so the tested word is read
  with the reading its homophones share;
- the clip is no longer than ``max_seconds`` (longer clips fail untranscribed).

Failures are kept with their reasons (``qc.jsonl``) and go to quarantine.

    CUDA_VISIBLE_DEVICES=5 <asr-baselines python> scripts/context_correction/qc.py --source <source dir>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl, write_jsonl

HERE = Path(__file__).resolve().parent
HAN = re.compile(r"[一-鿿]")


def syllables(text: str, tone: bool) -> list[str]:
    from pypinyin import Style, lazy_pinyin

    han = "".join(HAN.findall(text))
    style = Style.TONE3 if tone else Style.NORMAL
    return lazy_pinyin(han, style=style, neutral_tone_with_five=True)


def span_checks(segments: list[dict], hypothesis: str) -> tuple[float, list[str]]:
    """Pinyin error rate of the clip and the spans whose pinyin is not matched."""
    from rapidfuzz.distance import Levenshtein

    hyp_toneless, hyp_tone = syllables(hypothesis, False), syllables(hypothesis, True)
    ref_toneless, ref_tone, owner = [], [], []
    for index, segment in enumerate(segments):
        for plain, toned in zip(syllables(segment["text"], False), syllables(segment["text"], True)):
            ref_toneless.append(plain)
            ref_tone.append(toned)
            owner.append(index)
    error = Levenshtein.distance(ref_toneless, hyp_toneless) / max(1, len(ref_toneless))
    matched_toneless = set()
    for tag, i1, i2, j1, _ in Levenshtein.opcodes(ref_toneless, hyp_toneless):
        if tag == "equal":
            matched_toneless.update(range(i1, i2))
    matched_tone = set()
    for tag, i1, i2, _, _ in Levenshtein.opcodes(ref_tone, hyp_tone):
        if tag == "equal":
            matched_tone.update(range(i1, i2))
    failed = []
    for index, segment in enumerate(segments):
        positions = [k for k, o in enumerate(owner) if o == index]
        if segment["role"] == "evidence" and not set(positions) <= matched_toneless:
            failed.append(f"evidence not heard: {segment['text']}")
        if segment["role"] == "target" and not set(positions) <= matched_tone:
            failed.append(f"target not read as written: {segment['text']}")
    return error, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--items", type=Path, help="default: <source>/items.jsonl")
    parser.add_argument("--clips", type=Path, help="default: <source>/tts.jsonl")
    parser.add_argument("--out", type=Path, help="default: <source>/qc.jsonl")
    parser.add_argument("--batch", type=int, default=8, help="clips per QC batch (attention memory grows with length)")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    qc_cfg = recipe["qc"]
    items = {i["id"]: i for i in read_jsonl(args.items or args.source / "items.jsonl")}
    clips = [c for c in read_jsonl(args.clips or args.source / "tts.jsonl") if c["id"] in items]

    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess

    model = AutoModel(model=qc_cfg["model"], device="cuda:0", disable_update=True)
    # over-long clips fail without transcription (a runaway TTS generation can last minutes)
    results = [{"id": c["id"], "qc_model": qc_cfg["model"], "hypothesis": None, "pinyin_error": None,
                "duration": c["duration"], "pass": False,
                "issues": [f"duration {c['duration']} s > {recipe['max_seconds']} s"]}
               for c in clips if c["duration"] > recipe["max_seconds"]]
    clips = [c for c in clips if c["duration"] <= recipe["max_seconds"]]
    for start in range(0, len(clips), args.batch):
        batch = clips[start:start + args.batch]
        outputs = model.generate(input=[c["path"] for c in batch], language="zh", use_itn=False,
                                 batch_size=len(batch))
        for clip, output in zip(batch, outputs):
            hypothesis = rich_transcription_postprocess(output["text"])
            item = items[clip["id"]]
            error, failed = span_checks(item["segments"], hypothesis)
            if error > qc_cfg["max_pinyin_error"]:
                failed.append(f"pinyin error {error:.3f} > {qc_cfg['max_pinyin_error']}")
            results.append({"id": clip["id"], "qc_model": qc_cfg["model"], "hypothesis": hypothesis,
                            "pinyin_error": round(error, 4), "duration": clip["duration"],
                            "pass": not failed, "issues": failed})
        print(f"[qc] {min(start + args.batch, len(clips))}/{len(clips)}", flush=True)
    write_jsonl(args.out or args.source / "qc.jsonl", results)
    passed = sum(r["pass"] for r in results)
    print({"clips": len(results), "pass": passed, "fail": len(results) - passed})


if __name__ == "__main__":
    main()
