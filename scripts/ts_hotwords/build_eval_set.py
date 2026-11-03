#!/usr/bin/env python3
"""Build TS-ASR + hotword eval records from ts-asr-benchmark v12 (zh) and ts-asr-benchmark-en v1 (en).

usage: build_eval_set.py OUT_DIR LABELS_JSONL [LABELS_JSONL ...]
Built ts_asr_hotwords@v1-20261102 from the labels now registered as <dataset>@<v>-hotword-labels-20261102
(metadata.hotword_labels; see register_eval_hotword_labels.py).
Every source record whose mixture has words we can label keeps its audio refs, target, labels and metadata; it gains
- ``hotwords``: hotwords of the enrolled speaker's transcript (empty when the target is absent);
- ``metadata.bias_lists``: ``random`` = gold + random words to 10; ``interferer`` = gold + words the other speakers
  say + random to 20 (only when someone else says a hotword);
- ``metadata.distractor_kinds``: interferer words -> "interferer", the rest "random";
- ``labels.hotword_case``: gold+interferer / gold / interferer / none.
Interferer text: synthetic records keep ``metadata.interferers[*].utts[*].text``; real records keep
``metadata.window_utts`` (speakers other than the target). Random words come from the labelled words of the same
language that occur in neither transcript. Records go to four splits, <lang>-synthetic and <lang>-real (ts_asr_real sources); labels.source_split keeps the
source split (sampling: see KEEP_*). Writes OUT_DIR/records/<split>.jsonl.gz and OUT_DIR/manifest.json.
"""
import ast
import gzip
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

DATA = Path("/workspace/data/datasets")
DATASET, VERSION = "ts_asr_hotwords", "v1-20261102"
SETS = {
    "zh": "/workspace/data/ae-state/eval-sets/open-audio-llm/ts-asr-benchmark@v12-20261022/eval-set.yaml",
    "en": "/workspace/data/ae-state/eval-sets/open-audio-llm/ts-asr-benchmark-en@v1-20261031/eval-set.yaml",
}
RANDOM_LIST = 10
INTERFERER_LIST = 20
# Sampling keeps the request count near v12's: every record with a gold word stays; records whose only listed
# speech is someone else's keep 1 in 4; records with neither keep 1 in 8 (list-induced output on plain audio).
KEEP_INTERFERER_ONLY = 4
KEEP_PLAIN = 8


def other_texts(record):
    meta = record.get("metadata") or {}
    texts = [u.get("text") or "" for i in meta.get("interferers") or [] for u in i.get("utts", [])]
    window = meta.get("window_utts") or []
    if isinstance(window, str):
        window = ast.literal_eval(window)
    target = meta.get("target_speaker")
    texts += [u.get("text") or "" for u in window if u.get("speaker") != target]
    return [t.strip() for t in texts if t and t.strip()]


def main():
    out = Path(sys.argv[1])
    labels = {}
    for path in sys.argv[2:]:
        with open(path) as stream:
            for line in stream:
                row = json.loads(line)
                labels[row["text"]] = row["hotwords"]
    pools = {lang: sorted({w for t, ws in labels.items() for w in ws if (lang == "zh") == any("一" <= c <= "鿿" for c in t)})
             for lang in SETS}
    (out / "records").mkdir(parents=True, exist_ok=True)
    manifest = {"sources": {}, "counts": {}}
    merged, audio_index = {}, {}
    for lang, eval_set in SETS.items():
        with open(eval_set) as stream:
            spec = yaml.safe_load(stream)
        for source in spec["evaluation"]:
            if source["dataset_id"].startswith("business"):
                continue
            path = DATA / source["dataset_id"] / "versions" / source["version"] / "records" / f"{source['split']}.jsonl.gz"
            rng = random.Random(f"ts-hotwords:{lang}:{source['split']}")
            rows, unlabeled, cases = [], 0, Counter()
            with gzip.open(path, "rt") as stream:
                records = [json.loads(line) for line in stream]
            for record in records:
                target = (record.get("target") or "").strip()
                others = other_texts(record)
                if any(t not in labels for t in ([target] if target else []) + others):
                    unlabeled += 1
                    continue
                gold = list(dict.fromkeys(labels[target])) if target else []
                said = set(gold)
                interferer = [w for t in others for w in labels[t] if w not in said]
                interferer = list(dict.fromkeys(interferer))
                case = ("gold+interferer" if gold and interferer else "gold" if gold
                        else "interferer" if interferer else "none")
                if case == "none" and rng.randrange(KEEP_PLAIN):
                    continue
                if case == "interferer" and rng.randrange(KEEP_INTERFERER_ONLY):
                    continue
                spoken = set(gold) | set(interferer) | {w for t in others for w in labels[t]}
                text_all = target + "".join(others)
                candidates = [w for w in rng.sample(pools[lang], min(len(pools[lang]), 400))
                              if w not in spoken and w not in text_all]
                lists = {"random": gold + candidates[: max(0, RANDOM_LIST - len(gold))]}
                rng.shuffle(lists["random"])
                if interferer:
                    words = gold + interferer
                    lists["interferer"] = words + [w for w in candidates if w not in words][: max(0, INTERFERER_LIST - len(words))]
                    rng.shuffle(lists["interferer"])
                kinds = {w: "interferer" for w in interferer}
                kinds.update({w: "random" for w in candidates})
                # ids repeat across the zh and en benchmarks (same scenario names): prefix the language
                record["id"] = f"{lang}:{record['id']}"
                record["hotwords"] = gold
                record["labels"] = {**(record.get("labels") or {}), "hotword_case": case}
                record["metadata"] = {**(record.get("metadata") or {}), "bias_lists": lists,
                                      "distractor_kinds": {w: k for w, k in kinds.items()
                                                           if any(w in ws for ws in lists.values())},
                                      "source_record": f"{source['dataset_id']}@{source['version']}:{source['split']}:{record['id']}"}
                rows.append(record)
                cases[case] += 1
            if not any(cases[c] for c in ("gold+interferer", "gold", "interferer")):
                continue
            split = f"{lang}-{'real' if source['dataset_id'] == 'ts_asr_real' else 'synthetic'}"
            index_path = DATA / source["dataset_id"] / "versions" / source["version"] / "audio-index.jsonl.gz"
            wanted = {slot["ref"]["cut_id"] for record in rows for slot in record["audio_slots"]}
            found = {}
            with gzip.open(index_path, "rt") as stream:
                for line in stream:
                    entry = json.loads(line)
                    if entry["cut_id"] in wanted:
                        found[entry["cut_id"]] = entry
            for record in rows:
                record["labels"]["source_split"] = source["label"]
                for slot in record["audio_slots"]:
                    ref = slot["ref"]
                    assert (ref["dataset_id"], ref["version"]) == (source["dataset_id"], source["version"]), ref
                    # self-referencing refs resolved by this dataset's audio index (the hotword_bench layout);
                    # the index rows point at the source files, so no audio is copied
                    cut_id = f"{lang}:{ref['dataset_id']}:{ref['cut_id']}"
                    audio_index[cut_id] = {**found[ref["cut_id"]], "cut_id": cut_id}
                    slot["ref"] = {**ref, "dataset_id": DATASET, "version": VERSION, "split": split, "cut_id": cut_id}
            merged.setdefault(split, []).extend(rows)
            manifest["sources"][f"{lang}:{source['label']}"] = {**{k: source[k] for k in ("dataset_id", "version", "split")},
                                                    "language": lang, "split": split, "records": len(rows),
                                                    "unlabeled_skipped": unlabeled, **cases}
    for split, rows in merged.items():
        target_path = out / "records" / f"{split}.jsonl.gz"
        with gzip.open(target_path, "wt") as f:
            for record in rows:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        manifest["counts"][split] = {"records": len(rows), **Counter(r["labels"]["hotword_case"] for r in rows),
                                     "sha256": hashlib.sha256(target_path.read_bytes()).hexdigest()}
    with gzip.open(out / "audio-index.jsonl.gz", "wt") as f:
        for cut_id in sorted(audio_index):
            f.write(json.dumps(audio_index[cut_id], ensure_ascii=False, sort_keys=True) + "\n")
    manifest["audio_index"] = {"rows": len(audio_index),
                               "sha256": hashlib.sha256((out / "audio-index.jsonl.gz").read_bytes()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    total = Counter()
    for c in manifest["counts"].values():
        for k, v in c.items():
            if isinstance(v, int):
                total[k] += v
    print(len(manifest["sources"]), "splits", dict(total))


if __name__ == "__main__":
    main()
