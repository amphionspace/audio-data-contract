#!/usr/bin/env python3
"""Spanish single-speaker TS-ASR records for online mixing, the counterpart of aishellmix / librimix ``train_1spk``.

Chinese and English TS-ASR training is led by ``train_1spk``: one clean utterance of the target and an enrollment of
the same speaker, mixed at training time (``online_mix``) with interferers from ``ts_interference_pool``, target
absence, speech-free windows, entry, lead and trail. The Spanish scene pools (ts_scene_pool es-*-20261109) name their
utterances and transcript, so training never blanks or re-mixes them. These records give Spanish the same online mix.

Targets are Common Voice es train utterances of common_voice_es@es-train-v1-20261108 (clean-pass rows only, its
written text and hotword labels); the enrollment is another utterance of the same speaker, drawn with a fixed seed.
Speakers with a single utterance are left out. Common Voice es is not in the Spanish interference pool
(ts_interference_pool@es-v1-20261110), so a target never interferes with itself; dev / test speakers are not in the
train split.

    python scripts/ts_robust/build_ts_1spk_es.py --output-dir /workspace/data/datasets/ts_scene_pool/versions/es-1spk-20261110
    python scripts/ts_robust/register_records_pool.py --catalog catalog --yaml ts_scene_pool_es.yaml \
        --dataset-id ts_scene_pool --version es-1spk-20261110 --task ts_asr --splits es --languages es ...
"""

import argparse
import gzip
import json
import random
from collections import defaultdict
from pathlib import Path

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.roots import load_roots

CATALOG = "/workspace/data/registry/catalog"
ROOTS = "/workspace/data/registry/roots.json"
ROOT_ALIAS = "aidc_data"
SOURCE = ("common_voice_es", "es-train-v1-20261108", "train")
DATASET_ID, VERSION, SPLIT = "ts_scene_pool", "es-1spk-20261110", "es"
SEED = 20261110
# The online mix crops the enrollment to 1-20 s; a shorter clip leaves almost nothing of the voice.
MIN_ENROLL_SECONDS = 1.5


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        yield from (json.loads(line) for line in stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    catalog, roots = load_catalog(CATALOG), load_roots(ROOTS)
    root = Path(roots[ROOT_ALIAS])
    recordings = {}
    for path in resolve_split(catalog, *SOURCE, "recordings", roots):
        for rec in lines(path):
            recordings[rec["id"]] = rec
    by_speaker = defaultdict(list)
    for path in resolve_split(catalog, *SOURCE, "supervisions", roots):
        for sup in lines(path):
            if (sup.get("custom") or {}).get("clean", {}).get("pass") and sup["recording_id"] in recordings:
                by_speaker[sup["speaker"]].append(sup)
    rng = random.Random(SEED)
    records, index, skipped = [], {}, {"single_utterance": 0, "no_enrollment": 0}
    for speaker in sorted(by_speaker):
        sups = sorted(by_speaker[speaker], key=lambda s: s["id"])
        if len(sups) < 2:
            skipped["single_utterance"] += 1
            continue
        for sup in sups:
            others = [o for o in sups if o["id"] != sup["id"] and o["duration"] >= MIN_ENROLL_SECONDS]
            if not others:
                skipped["no_enrollment"] += 1
                continue
            enroll = rng.choice(others)
            slots = []
            for name, item in (("enrollment", enroll), ("mixture", sup)):
                cut = f"{SOURCE[0]}:{item['recording_id']}"
                slots.append({"name": name, "purpose": name,
                              "ref": {"dataset_id": DATASET_ID, "version": VERSION, "split": SPLIT, "cut_id": cut}})
                if cut not in index:
                    rec = recordings[item["recording_id"]]
                    index[cut] = {"cut_id": cut, "root_alias": ROOT_ALIAS,
                                  "relative_path": str(Path(rec["sources"][0]["source"]).relative_to(root)),
                                  "sample_rate": rec["sampling_rate"], "channels": len(rec["channel_ids"]),
                                  "num_frames": rec["num_samples"], "duration": rec["duration"]}
            custom = sup.get("custom") or {}
            records.append({
                "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{SPLIT}:1spk:{sup['id']}", "task": "ts_asr",
                "target": sup["text"], "language": "es", "labels": {"n_spk": 1, "target_present": True},
                "hotwords": list(custom.get("hotwords") or []), "audio_slots": slots,
                "metadata": {"source_dataset": f"{SOURCE[0]}@{SOURCE[1]}", "source_record_id": sup["id"],
                             "target_speaker": f"{SOURCE[0]}:{speaker}", "accent": custom.get("accents", "")}})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for stem, items in ((f"records_{SPLIT}", records), (f"audio_index_{SPLIT}", sorted(index.values(), key=lambda r: r["cut_id"]))):
        with gzip.open(args.output_dir / f"{stem}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for item in items:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    hours = sum(index[r["audio_slots"][1]["ref"]["cut_id"]]["duration"] for r in records) / 3600
    report = {"records": len(records), "speakers": len({r["metadata"]["target_speaker"] for r in records}),
              "target_hours": round(hours, 1), "files": len(index),
              "with_hotwords": sum(bool(r["hotwords"]) for r in records), "skipped": skipped}
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
