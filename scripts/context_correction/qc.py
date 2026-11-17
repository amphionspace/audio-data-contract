#!/usr/bin/env python3
"""Check that each synthesized item says its text, at the pinyin level.

QC ASRs that are not under evaluation (``qc.models``; v1: SenseVoiceSmall alone as ``qc.model``) transcribe every
clip. Hypothesis and reference are compared as pinyin, so homophone choices (the very thing the benchmark tests)
never fail an item. A transcript passes when

- the whole clip's toneless pinyin error rate is at most ``qc.max_pinyin_error``;
- every evidence span matches the hypothesis in toneless pinyin, so the deciding context is audible;
- every target span matches in toneless pinyin and, syllable by syllable, the reference tone is a reading of the
  character the ASR wrote, so the tested word is read with the reading its homophones share. The reference reading
  is taken in the context of the whole text; the ASR's character may be any homophone, so all its readings count
  (pypinyin gives 子 a neutral tone in 刘子尧, though the ASR heard 梓 zǐ);
- the clip is no longer than ``max_seconds`` (longer clips fail untranscribed).

With several QC ASRs, ``qc.pass_when`` says whether ``any`` or ``all`` of their transcripts must pass; each ASR's
transcript and issues are kept under ``teachers``. Failures are kept with their reasons (``qc.jsonl``) and go to
quarantine.

    CUDA_VISIBLE_DEVICES=5 <dolphin python> scripts/context_correction/qc.py --source <source dir>
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


def readings(char: str) -> set[str]:
    from pypinyin import Style, pinyin

    return set(pinyin(char, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0])


def span_checks(segments: list[dict], hypothesis: str) -> tuple[float, list[str]]:
    """Pinyin error rate of the clip and the spans whose pinyin is not matched."""
    from rapidfuzz.distance import Levenshtein

    text = "".join(segment["text"] for segment in segments)
    ref_toneless, ref_tone = syllables(text, False), syllables(text, True)
    owner = [index for index, segment in enumerate(segments) for _ in HAN.findall(segment["text"])]
    hyp_chars = HAN.findall(hypothesis)
    hyp_toneless, hyp_tone = syllables(hypothesis, False), syllables(hypothesis, True)
    error = Levenshtein.distance(ref_toneless, hyp_toneless) / max(1, len(ref_toneless))
    heard = {}  # reference syllable -> hypothesis syllable it is aligned to, where the toneless syllables are equal
    for tag, i1, i2, j1, _ in Levenshtein.opcodes(ref_toneless, hyp_toneless):
        if tag == "equal":
            heard.update(zip(range(i1, i2), range(j1, j1 + i2 - i1)))
    failed = []
    for index, segment in enumerate(segments):
        positions = [k for k, o in enumerate(owner) if o == index]
        if segment["role"] == "evidence" and not all(k in heard for k in positions):
            failed.append(f"evidence not heard: {segment['text']}")
        if segment["role"] == "target" and not all(
                k in heard and ref_tone[k] in {hyp_tone[heard[k]]} | readings(hyp_chars[heard[k]]) for k in positions):
            failed.append(f"target not read as written: {segment['text']}")
    return error, failed


def load_teacher(spec: dict):
    """A function from clip paths to transcripts, for one ``qc.models`` entry."""
    if spec["backend"] == "sensevoice":
        from funasr import AutoModel
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        model = AutoModel(model=spec["path"], device="cuda:0", disable_update=True)

        def transcribe(paths):
            outputs = model.generate(input=paths, language="zh", use_itn=False, batch_size=len(paths))
            return [rich_transcription_postprocess(output["text"]) for output in outputs]
        return transcribe
    if spec["backend"] == "firered_aed":
        sys.path.insert(0, spec["code"])
        from fireredasr2s.fireredasr2 import FireRedAsr2, FireRedAsr2Config

        model = FireRedAsr2.from_pretrained("aed", spec["path"], FireRedAsr2Config(use_gpu=True, **spec["decode"]))

        def transcribe(paths):
            keys = [str(k) for k in range(len(paths))]
            by_key = {row["uttid"]: row["text"] for row in model.transcribe(keys, paths)}
            if set(by_key) != set(keys):  # the runtime drops clips it fails on instead of raising
                raise RuntimeError(f"FireRed returned {len(by_key)} of {len(keys)} transcripts")
            return [by_key[k] for k in keys]
        return transcribe
    raise ValueError(f"unknown QC backend {spec['backend']!r}")


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
    specs = qc_cfg.get("models") or [{"path": qc_cfg["model"], "backend": "sensevoice"}]
    rule = {"any": any, "all": all}[qc_cfg.get("pass_when", "all")]
    items = {i["id"]: i for i in read_jsonl(args.items or args.source / "items.jsonl")}
    clips = [c for c in read_jsonl(args.clips or args.source / "tts.jsonl") if c["id"] in items]

    # over-long clips fail without transcription (a runaway TTS generation can last minutes)
    results = {c["id"]: {"id": c["id"], "qc_model": specs[0]["path"], "hypothesis": None, "pinyin_error": None,
                         "duration": c["duration"], "pass": False,
                         "issues": [f"duration {c['duration']} s > {recipe['max_seconds']} s"]}
               for c in clips if c["duration"] > recipe["max_seconds"]}
    clips = [c for c in clips if c["duration"] <= recipe["max_seconds"]]
    heard = {c["id"]: [] for c in clips}
    for spec in specs:
        transcribe = load_teacher(spec)
        for start in range(0, len(clips), args.batch):
            batch = clips[start:start + args.batch]
            for clip, hypothesis in zip(batch, transcribe([c["path"] for c in batch])):
                error, failed = span_checks(items[clip["id"]]["segments"], hypothesis)
                if error > qc_cfg["max_pinyin_error"]:
                    failed.append(f"pinyin error {error:.3f} > {qc_cfg['max_pinyin_error']}")
                heard[clip["id"]].append({"model": spec["path"], "hypothesis": hypothesis,
                                          "pinyin_error": round(error, 4), "issues": failed})
            print(f"[qc] {Path(spec['path']).name} {min(start + args.batch, len(clips))}/{len(clips)}", flush=True)
        del transcribe
    for clip in clips:
        teachers = heard[clip["id"]]
        passed = rule(not t["issues"] for t in teachers)
        shown = next((t for t in teachers if not t["issues"]), teachers[0]) if passed else teachers[0]
        issues = [] if passed else [f"{Path(t['model']).name}: {i}" if len(teachers) > 1 else i
                                    for t in teachers for i in t["issues"]]
        results[clip["id"]] = {"id": clip["id"], "qc_model": shown["model"], "hypothesis": shown["hypothesis"],
                               "pinyin_error": shown["pinyin_error"], "duration": clip["duration"], "pass": passed,
                               "issues": issues, **({"teachers": teachers} if len(teachers) > 1 else {})}
    write_jsonl(args.out or args.source / "qc.jsonl", list(results.values()))
    passed = sum(r["pass"] for r in results.values())
    print({"clips": len(results), "pass": passed, "fail": len(results) - passed})


if __name__ == "__main__":
    main()
