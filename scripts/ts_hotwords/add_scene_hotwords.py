#!/usr/bin/env python3
"""Add hotword labels to the records of a TS scene pool (the *-punchw versions), from per-utterance labels.

Each record keeps its scene, text and audio; it gains
- ``hotwords``: the words labelled in the target's utterances, in order, each once;
- ``metadata.interferer_hotwords``: the words labelled in the other speakers' utterances that the target does not say
  (case-insensitive), so a hotword prompt can hold words the model must not transcribe.
Labels are rows {id: "<dataset>:<utterance id>", hotwords: [...]} of label_hotwords.py, whose ids are the scene's cut
ids. The text is not changed: the Spanish pools take Common Voice es text, written with punctuation and case already.
Audio slots still point at the source version's audio index.

    python add_scene_hotwords.py SRC_RECORDS.jsonl.gz LABELS.jsonl OUT_RECORDS.jsonl.gz STATS.json
"""

import gzip
import json
import sys
from collections import Counter


def utterances(scene):
    targets = [t["cut_id"] for t in scene["targets"]]
    others = [u["cut_id"] for o in scene["interferers"] for u in o["utts"]]
    return targets, others


def words(cuts, labels):
    out = {}
    for cut in cuts:
        for word in labels.get(cut, ()):
            out.setdefault(word.lower(), word)
    return out


def main():
    src, label_path, dst, stats_path = sys.argv[1:5]
    labels = {}
    with open(label_path, encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            labels[row["id"]] = row.get("hotwords") or []
    counts = Counter()
    with gzip.open(src, "rt", encoding="utf-8") as inp, gzip.open(dst, "wt", encoding="utf-8") as out:
        for line in inp:
            record = json.loads(line)
            targets, others = utterances(record["metadata"]["scene"])
            missing = [c for c in targets + others if c not in labels]
            if missing:
                raise SystemExit(f"{record['id']}: no hotword label for {missing[:3]}")
            said = words(targets, labels)
            heard = {k: v for k, v in words(others, labels).items() if k not in said}
            record["hotwords"] = list(said.values())
            record["metadata"]["interferer_hotwords"] = list(heard.values())
            counts["records"] += 1
            counts["with target hotwords"] += bool(said)
            counts["with interferer hotwords"] += bool(heard)
            counts["target absent"] += not targets
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    with open(stats_path, "w") as stream:
        json.dump(dict(counts), stream, indent=1)
    print(dict(counts), flush=True)


if __name__ == "__main__":
    main()
