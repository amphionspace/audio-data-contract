#!/usr/bin/env python3
"""Export Common Voice utterance lists for the cross-lingual TS benchmark (ts_asr_crosslingual).

Bilingual targets are the Common Voice accounts (``client_id``, the ``speaker`` of the Lhotse supervisions) that
recorded both zh-CN and en; speakers already used as TS training targets (``--exclude-speakers``) are dropped.
Their zh and en utterances go to two lists under one dataset name, so a speaker has the same id in both pools and a
recipe can draw the enrollment from the other language (``enroll_pool``). Interferer lists are the other speakers
of the given splits, bilingual ones removed so a target never appears as an interferer.

Each list is ``utterances.jsonl.gz`` (``id``, ``speaker``, ``text``, ``duration``, ``path``), read by a recipe pool
source ``{manifest: {alias, path}, dataset, version, split}``; ``path`` is the Common Voice clip (absolute).

    python scripts/ts_benchmark/export_bilingual_pool.py --exclude-speakers used.json \
        --output /workspace/data/datasets/ts_asr_crosslingual/source/pools
"""

import argparse
import glob
import gzip
import json
from collections import defaultdict
from pathlib import Path

LEGACY = "/workspace/data/datasets/common_voice_{lang}/versions/legacy-20260804"
SUPERVISIONS = {"zh": "cv-zh-CN_supervisions_{split}*.jsonl.gz", "en": "cv-en_supervisions_{split}*.jsonl.gz"}
RECORDINGS = {"zh": "cv-zh-CN_recordings_{split}*.jsonl.gz", "en": "cv-en_recordings_{split}*.jsonl.gz"}


def rows(lang, split, kind):
    pattern = (SUPERVISIONS if kind == "sup" else RECORDINGS)[lang].format(split=split)
    for path in sorted(glob.glob(f"{LEGACY.format(lang=lang)}/{split}_{kind[:3]}_*/{pattern}")):
        with gzip.open(path, "rt") as handle:
            for line in handle:
                yield json.loads(line)


def utterances(lang, splits, seconds):
    audio = {r["id"]: r["sources"][0]["source"] for split in splits for r in rows(lang, split, "rec")}
    out = defaultdict(list)
    for split in splits:
        for s in rows(lang, split, "sup"):
            if s["recording_id"] in audio and seconds[0] <= s["duration"] <= seconds[1] and s.get("text"):
                out[s["speaker"]].append({"id": s["id"], "speaker": s["speaker"], "text": s["text"],
                                          "duration": round(s["duration"], 3), "path": audio[s["recording_id"]],
                                          "split": split})
    return out


def write(path, by_speaker, keep):
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt") as handle:
        for speaker in sorted(keep):
            for row in by_speaker[speaker]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-speakers", type=Path, help="JSON list of client_ids used as TS training targets")
    parser.add_argument("--min-utterances", type=int, default=5, help="per language, for scenes and enrollments")
    parser.add_argument("--seconds", type=float, nargs=2, default=(1.5, 12.0))
    args = parser.parse_args()
    excluded = set(json.loads(args.exclude_speakers.read_text())) if args.exclude_speakers else set()
    splits = ("train", "dev", "test")
    zh, en = utterances("zh", splits, args.seconds), utterances("en", splits, args.seconds)
    bilingual = {s for s in set(zh) & set(en) if len(zh[s]) >= args.min_utterances and len(en[s]) >= args.min_utterances}
    targets = bilingual - excluded
    stats = {"bilingual": len(bilingual), "excluded_ts_targets": len(bilingual & excluded), "targets": len(targets)}
    stats["target_zh_utterances"] = write(args.output / "cv-bilingual-zh/utterances.jsonl.gz", zh, targets)
    stats["target_en_utterances"] = write(args.output / "cv-bilingual-en/utterances.jsonl.gz", en, targets)
    every = set(zh) | set(en)
    for lang, by_speaker, interferer_splits in (("zh", zh, ("dev", "test")), ("en", en, ("test",))):
        held = {s: [u for u in us if u["split"] in interferer_splits] for s, us in by_speaker.items()}
        keep = {s for s, us in held.items() if len(us) >= 2 and s not in (set(zh) & set(en))}
        stats[f"interferer_{lang}_speakers"] = len(keep)
        stats[f"interferer_{lang}_utterances"] = write(args.output / f"cv-interferer-{lang}/utterances.jsonl.gz", held, keep)
    stats["all_speakers_seen"] = len(every)
    (args.output / "cv-pools.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
