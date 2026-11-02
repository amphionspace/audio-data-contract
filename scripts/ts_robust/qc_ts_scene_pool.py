#!/usr/bin/env python3
"""Check a built ts_scene_pool split before it is registered (build_ts_scene_pool.py output).

Hard checks (exit code 1 when any fails):
  held_out   no speaker and no utterance of a corpus's dev / test splits (HELD_OUT_SPEAKERS of the builder), no VCTK
  audio      every slot and scene utterance names a cut of the audio index, inside the indexed file; with
             ``--files`` the indexed files exist
  text       the target is the scene's target texts joined in order, empty exactly when no target is in the scene,
             and every target text is the source corpus's text (Common Voice: the clean manifest; CS-Dialogue: the
             supervision without tags; others: the Lance record index)
Summary: present / twin shares, enrolled accent groups, distinct speakers, target utterance reuse.

    python qc_ts_scene_pool.py --dir DIR --split en [--files] > qc.json
"""

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import lance
import numpy as np
from build_ts_scene_pool import (
    CV_CLEAN,
    DATA,
    HELD_OUT_SPEAKERS,
    TAGGED_TEXT,
    catalog_entry,
    lhotse_rows,
    tagless,
)

TOLERANCE = 0.002  # seconds: spans are rounded to the millisecond


def read(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def held_out(dataset):
    """(speakers, utterance IDs) of the held-out splits of ``dataset``."""
    version, splits = HELD_OUT_SPEAKERS[dataset]
    rows = [row for split in splits for row in lhotse_rows(catalog_entry(dataset, version), split, "supervisions")]
    return {row["speaker"] for row in rows}, {row["id"] for row in rows}


def source_texts(dataset, ids):
    """Source text of the utterances ``ids`` of a corpus, as the builder reads it."""
    if dataset == "common_voice_en":
        entry = catalog_entry(dataset, CV_CLEAN[0])
        return {row["id"]: row["text"] for row in lhotse_rows(entry, *CV_CLEAN[1:]) if row["id"] in ids}
    entry = catalog_entry(dataset, "legacy-20260804")
    if "records_lance" not in entry["splits"]["train"]["artifacts"]:
        clean = tagless if dataset in TAGGED_TEXT else str
        return {row["id"]: clean(row["text"]) for row in lhotse_rows(entry, "train", "supervisions") if row["id"] in ids}
    artifact = next(a for a in entry["artifacts"] if a["name"] == entry["splits"]["train"]["artifacts"]["records_lance"][0])
    directory = DATA / artifact["relative_path"].rsplit("/", 1)[0]
    table = json.loads((directory / "index.json").read_text())["table_path"]
    rows = lance.dataset(str(directory / table)).to_table(columns=["id", "text"], filter="array_has(splits, 'train')")
    return {i: t for i, t in zip(rows["id"].to_pylist(), rows["text"].to_pylist()) if i in ids}


def utterances(scene):
    """(role, speaker, item) of every utterance the scene names."""
    yield "enrollment", scene["target_speaker"], scene["enrollment"]
    for item in scene["targets"]:
        yield "target", scene["target_speaker"], item
    for other in scene["interferers"]:
        for item in other["utts"]:
            yield "other", other["speaker"], item


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--split", default="en")
    parser.add_argument("--files", action="store_true", help="also check that every indexed file exists")
    args = parser.parse_args()
    records = read(args.dir / f"records_{args.split}.jsonl.gz")
    index = {row["cut_id"]: row for row in read(args.dir / f"audio_index_{args.split}.jsonl.gz")}
    failures = Counter()
    speakers, cuts, targets_by_corpus, reuse = Counter(), set(), {}, Counter()
    for record in records:
        scene = record["metadata"]["scene"]
        for slot in record["audio_slots"]:
            if slot["ref"]["cut_id"] not in index:
                failures["audio: slot cut not in the audio index"] += 1
        for role, speaker, item in utterances(scene):
            speakers[speaker] += 1
            cuts.add(item["cut_id"])
            row = index.get(item["cut_id"])
            if row is None:
                failures["audio: scene cut not in the audio index"] += 1
            elif item["start"] < 0 or item["start"] + item["duration"] > row["duration"] + TOLERANCE:
                failures["audio: span outside the indexed file"] += 1
            if role == "target":
                corpus, cut = item["cut_id"].split(":", 1)
                targets_by_corpus.setdefault(corpus, {})[cut] = item["text"]
                reuse[item["cut_id"]] += 1
        joined = " ".join(t["text"] for t in scene["targets"]) if args.split != "zh" else "".join(t["text"] for t in scene["targets"])
        if record["target"] != joined:
            failures["text: target is not the scene's target texts"] += 1
        if bool(record["target"].strip()) != bool(scene["targets"]) or record["labels"]["target_present"] != bool(scene["targets"]):
            failures["text: target presence disagrees with the scene"] += 1
    corpora = sorted({s.split(":", 1)[0] for s in speakers} | {c.split(":", 1)[0] for c in cuts})
    checks = {}
    for corpus in corpora:
        if corpus.lower().startswith("vctk"):
            failures["held_out: VCTK in the pool"] += 1
        if corpus not in HELD_OUT_SPEAKERS:
            checks[corpus] = "no held-out split declared"
            continue
        held_speakers, held_cuts = held_out(corpus)
        mine = {s.split(":", 1)[1] for s in speakers if s.startswith(f"{corpus}:")}
        used = {c.split(":", 1)[1] for c in cuts if c.startswith(f"{corpus}:")}
        checks[corpus] = {"speakers": len(mine), "held_out_speakers": len(held_speakers), "shared_speakers": len(mine & held_speakers),
                          "utterances": len(used), "held_out_utterances": len(held_cuts), "shared_utterances": len(used & held_cuts)}
        failures["held_out: shared speaker"] += len(mine & held_speakers)
        failures["held_out: shared utterance"] += len(used & held_cuts)
    for corpus, texts in targets_by_corpus.items():
        source = source_texts(corpus, set(texts))
        failures["text: target text differs from the source"] += sum((source.get(cut) or "").strip() != text for cut, text in texts.items())
    if args.files:
        failures["audio: indexed file missing"] += sum(not (DATA / row["relative_path"]).exists() for row in index.values())
    present = [r for r in records if r["labels"]["target_present"]]
    uses = np.array(list(reuse.values()))
    summary = {
        "records": len(records), "present_share": round(len(present) / len(records), 3),
        "twins": dict(Counter(r["labels"].get("twin_enrollment") for r in records if "twin_enrollment" in r["labels"])),
        "hard": dict(Counter(r["id"].split(":")[2].split("-")[0] for r in records if "hard_cosine" in r["labels"]
                             and "twin_enrollment" not in r["labels"])),
        "schedules": dict(Counter(r["labels"]["schedule"] for r in records)),
        "enrolled_accents_present": dict(Counter(r["labels"].get("accent") for r in present).most_common()),
        "enrolled_accents_absent": dict(Counter(r["labels"].get("accent") for r in records
                                                if not r["labels"]["target_present"]).most_common()),
        "target_speakers": dict(Counter(r["metadata"]["scene"]["target_speaker"].split(":", 1)[0] for r in present)),
        "distinct_target_speakers": len({r["metadata"]["scene"]["target_speaker"] for r in present}),
        "other_speaker_corpora": dict(Counter(o["speaker"].split(":", 1)[0] for r in records
                                              for o in r["metadata"]["scene"]["interferers"])),
        "target_utterance_uses_median_max": [float(np.median(uses)), int(uses.max())] if len(uses) else [],
        "audio_files": len(index),
    }
    failed = {k: v for k, v in failures.items() if v}
    json.dump({"dir": str(args.dir), "split": args.split, "passed": not failed, "failures": failed,
               "held_out": checks, "summary": summary}, sys.stdout, ensure_ascii=False, indent=1)
    print()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
