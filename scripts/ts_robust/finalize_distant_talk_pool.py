#!/usr/bin/env python3
"""Turn the two independent models' answers on rendered distant-talk clips into training targets.

Unintelligible is what two good models cannot follow, with the source transcript as the check on both:

- ``empty``: both return nothing; or, on a one-conversation clip, both are far from the transcript and from each other
  (or one returns nothing); on a two-conversation clip, both write text and disagree, since neither can be checked
  against one transcript.
- ``text``: a one-conversation clip that both read close to the transcript; the target is the transcript. This is the
  contrast that keeps quiet far-field speech transcribed.
- dropped: everything between, such as a clip one model reads well. Teaching those as empty would remove real speech.

The cut points are judgement calls, recorded in report.json with what each class holds.

    python scripts/ts_robust/finalize_distant_talk_pool.py --version V

Writes versions/V/records_{empty,text}_{zh,en}.jsonl.gz, audio_index_*.jsonl.gz and report.json, ready for
register_records_pool.py.
"""

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path

DATA = Path("/workspace/data")
DATASET_ID = "asr_distant_talk_pool"
ROOT_ALIAS = "aidc_data"
SR = 16000
FAR = 0.7  # CER against the transcript from which a model is not following the talk
CLOSE = 0.3
DISAGREE = 0.5  # normalized edit distance between the two models
DISAGREE_NO_CHECK = 0.7  # the same with no transcript to check against, hence stricter


def norm(text):
    return re.sub(r"[^\w]", "", text or "").lower()


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def classify(streams, qwen3, firered):
    q, f = norm(qwen3), norm(firered)
    if not q and not f:
        return "empty", "both_empty"
    apart = edit_distance(q, f) / max(len(q), len(f), 1)
    if len(streams) == 2:
        return ("empty", "two_conversations_disagree") if q and f and apart >= DISAGREE_NO_CHECK else (None, "two_other")
    gold = norm(streams[0]["text"])
    to_q, to_f = edit_distance(gold, q) / max(len(gold), 1), edit_distance(gold, f) / max(len(gold), 1)
    if to_q <= CLOSE and to_f <= CLOSE:
        return "text", "both_read_it"
    if to_q >= FAR and to_f >= FAR:
        if not q or not f:
            return "empty", "one_empty_other_far"
        if apart >= DISAGREE:
            return "empty", "both_far_and_disagree"
        return None, "both_far_but_agree"
    return None, "one_or_partly_follows"


def answers(path):
    return {row["id"]: row.get("text") or "" for row in map(json.loads, path.read_text().splitlines())}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    root = DATA / "datasets" / DATASET_ID / "source" / args.version
    qwen3 = answers(root / "labels/qwen3.jsonl")
    firered = {}
    for path in sorted((root / "labels").rglob("firered.jsonl")):
        firered.update(answers(path))
    out = DATA / "datasets" / DATASET_ID / "versions" / args.version
    out.mkdir(parents=True, exist_ok=True)
    rows, reasons = {}, Counter()
    for row in map(json.loads, (root / "manifest.jsonl").read_text().splitlines()):
        if row["id"] not in qwen3 or row["id"] not in firered:
            raise ValueError(f"{row['id']} has no answer from both models")
        label, reason = classify(row["streams"], qwen3[row["id"]], firered[row["id"]])
        reasons[f"{row['language']}:{reason}"] += 1
        if label:
            rows.setdefault(f"{label}_{row['language']}", []).append((row, reason))
    report = {"thresholds": {"far": FAR, "close": CLOSE, "disagree": DISAGREE, "disagree_no_check": DISAGREE_NO_CHECK},
              "reasons": dict(sorted(reasons.items())), "splits": {}}
    for split, chosen in sorted(rows.items()):
        records, index = [], []
        for row, reason in chosen:
            frames, duration = row["frames"], round(row["frames"] / SR, 4)
            present = split.startswith("text")
            records.append({
                "schema_version": "audio-record/1.0", "id": row["id"], "task": "asr",
                "target": row["streams"][0]["text"] if present else "", "language": row["language"],
                "labels": {"target_present": present}, "hotwords": [],
                "audio_slots": [{"name": "primary", "ref": {"dataset_id": DATASET_ID, "version": args.version,
                                                            "split": split, "cut_id": row["id"], "start": 0.0,
                                                            "duration": duration}}],
                "metadata": {"source_dataset": row["streams"][0]["recording"], "source_group": row["id"], "reason": reason,
                             "qwen3": qwen3[row["id"]], "firered": firered[row["id"]], "snr_db": row["snr_db"],
                             "frame_p95_dbfs": row["frame_p95_dbfs"], "direct_cut_db": row["direct_cut_db"],
                             "dull": row["dull"], "room": row["room"], "conversations": len(row["streams"])}})
            index.append({"cut_id": row["id"], "root_alias": ROOT_ALIAS, "relative_path": row["path"], "sample_rate": SR,
                          "channels": 1, "num_frames": frames, "duration": duration})
        for stem, items in (("records", records), ("audio_index", index)):
            with gzip.open(out / f"{stem}_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
                for item in items:
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        report["splits"][split] = {"records": len(records), "hours": round(sum(i["duration"] for i in index) / 3600, 2)}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
