#!/usr/bin/env python3
"""emilia2_short short-lance-20261023: short-20261014 with every clip read as FLAC from the Lance release.

Same records and record IDs as short-20261014. Each record's audio slot names its sample in
emilia2@tts-unified-v0.1 instead of the m4a-128k file, matched by upstream short ID (Lance
``source_key``) and checked against the m4a file name; the release stores the same complete
decode as FLAC, so training no longer runs ffmpeg for these clips. The ref carries the Lance
duration, which the trainer's sampler reads. Records without a Lance sample are dropped and
counted in report.json. There is no audio index (no clip is a file any more), so the version
has no Lance record index either and trainers read it through the JSONL record cache.

    python build_emilia2_short_lance.py
    python scripts/ts_robust/register_records_pool.py ...   # see the catalog entry

Reading the clips needs open-audio-llm's catalog loader to resolve refs that name another
dataset's Lance release (code-v14 and later).
"""

import gzip
import json
from pathlib import Path

import lance
import pyarrow as pa
import pyarrow.compute as pc

DATA = Path("/workspace/data")
OLD = DATA / "datasets/emilia2_short/versions/short-20261014"
VERSION = "short-lance-20261023"
NEW = DATA / f"datasets/emilia2_short/versions/{VERSION}"
SPLITS = ("train_zh", "train_en")
LANCE = DATA / "DATA-TTS-UNIFIED/datasets/emilia2/v0.1/samples.lance"
# The catalog pins emilia2@tts-unified-v0.1 to this Lance snapshot.
LANCE_VERSION = 3
LANCE_REF = {"dataset_id": "emilia2", "version": "tts-unified-v0.1", "split": "train"}
# m4a-128k standalone shorts; m4a-64k is a separate source config.
SOURCE_CONFIG = "Emilia2_TTS_m4a"


def records(split):
    with gzip.open(OLD / f"records/{split}.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def lance_samples(members):
    """m4a file name -> (sample_id, duration) for the standalone shorts named in ``members``.

    One filtered scan of the release; a key list of millions does not fit a SQL IN filter.
    """
    keys = pa.array(sorted({member.rsplit("_spk", 1)[0] for member in members}))
    dataset = lance.dataset(str(LANCE), version=LANCE_VERSION)
    found, scanned = {}, 0
    for batch in dataset.to_batches(columns=["sample_id", "source_key", "duration_seconds", "source_locator_json"],
                                    filter=f"source_config = '{SOURCE_CONFIG}'", batch_size=1 << 18):
        scanned += batch.num_rows
        hit = batch.filter(pc.is_in(batch.column("source_key"), value_set=keys)).to_pydict()
        for sample, locator, duration in zip(hit["sample_id"], hit["source_locator_json"], hit["duration_seconds"]):
            member = Path(json.loads(locator)["member"]).name
            if member in members:
                found[member] = (sample, duration)
        if scanned % (1 << 24) < (1 << 18):
            print("scanned", scanned, "found", len(found), flush=True)
    return found


def main():
    NEW.mkdir(parents=True, exist_ok=False)
    (NEW / "records").mkdir()
    members = {Path(r["metadata"]["audio_path"]).name for split in SPLITS for r in records(split)}
    print("records' m4a files", len(members), flush=True)
    samples = lance_samples(members)
    report = {"from": "emilia2_short@short-20261014", "lance": "emilia2@tts-unified-v0.1", "splits": {}}
    for split in SPLITS:
        kept = dropped = 0
        seconds = 0.0
        missing = []
        with gzip.open(NEW / f"records/{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for record in records(split):
                slot = record["audio_slots"][0]
                match = samples.get(Path(record["metadata"]["audio_path"]).name)
                if match is None:
                    dropped += 1
                    if len(missing) < 100:
                        missing.append(record["id"])
                    continue
                record["metadata"]["source_cut_id"] = slot["ref"]["cut_id"]
                slot["ref"] = {**LANCE_REF, "cut_id": match[0], "duration": match[1]}
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1
                seconds += match[1]
        report["splits"][split] = {"records": kept, "duration_hours": round(seconds / 3600, 3),
                                   "dropped_without_lance_sample": dropped, "dropped_examples": missing}
        print(split, {k: v for k, v in report["splits"][split].items() if k != "dropped_examples"}, flush=True)
    (NEW / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
