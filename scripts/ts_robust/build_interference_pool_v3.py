#!/usr/bin/env python3
"""ts_interference_pool v3: the v2 pool with its Emilia2 short clips read from the Lance release.

Same records and record IDs as v2-20261016. A clip whose source is emilia2_short (a whole
m4a-128k standalone short) now names its sample in emilia2@tts-unified-v0.1, matched by
upstream short ID (Lance ``source_key``) and checked against the m4a file name; the
release stores the same complete decode as FLAC, so training no longer runs ffmpeg for
interferers. Other clips keep their v2 audio-index entries. Clips without a Lance sample
are dropped and counted in report.json.

    python build_interference_pool_v3.py
    python register_records_pool.py --catalog catalog --yaml ts_interference_pool.yaml \\
        --dataset-id ts_interference_pool --version v3-20261018 --task ts_asr_interference \\
        --splits zh en --languages zh en --description TEXT --sources ...

Reading a Lance clip needs open-audio-llm's pool loader to resolve records whose ref
names another dataset's Lance release.
"""

import gzip
import json
from pathlib import Path

import lance

DATA = Path("/workspace/data")
OLD = DATA / "datasets/ts_interference_pool/versions/v2-20261016"
NEW = DATA / "datasets/ts_interference_pool/versions/v3-20261018"
VERSION = "v3-20261018"
LANCE = DATA / "DATA-TTS-UNIFIED/datasets/emilia2/v0.1/samples.lance"
# The catalog pins emilia2@tts-unified-v0.1 to this Lance snapshot.
LANCE_VERSION = 3
LANCE_REF = {"dataset_id": "emilia2", "version": "tts-unified-v0.1", "split": "train"}
# m4a-128k standalone shorts; m4a-64k is a separate source config.
SOURCE_CONFIG = "Emilia2_TTS_m4a"
LOOKUP_CHUNK = 5000


def read(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def lance_samples(dataset, members):
    """Short ID -> (sample_id, duration) for standalone shorts whose file name matches."""
    keys = sorted({member.rsplit("_spk", 1)[0] for member in members})
    found = {}
    for start in range(0, len(keys), LOOKUP_CHUNK):
        chunk = keys[start:start + LOOKUP_CHUNK]
        quoted = ", ".join("'" + key.replace("'", "''") + "'" for key in chunk)
        table = dataset.to_table(
            columns=["sample_id", "source_key", "duration_seconds", "source_locator_json"],
            filter=f"source_config = '{SOURCE_CONFIG}' AND source_key IN ({quoted})",
        ).to_pydict()
        for sample, key, duration, locator in zip(*table.values()):
            found[json.loads(locator)["member"]] = (sample, duration)
    return found


def main():
    NEW.mkdir(parents=True, exist_ok=False)
    dataset = lance.dataset(str(LANCE), version=LANCE_VERSION)
    report = {"from": "ts_interference_pool@v2-20261016", "lance": "emilia2@tts-unified-v0.1", "splits": {}}
    for split in ("zh", "en"):
        records = read(OLD / f"records_{split}.jsonl.gz")
        index = {row["cut_id"]: row for row in read(OLD / f"audio_index_{split}.jsonl.gz")}
        short = {r["audio_slots"][0]["ref"]["cut_id"] for r in records if r["metadata"]["source_dataset"] == "emilia2_short"}
        members = {cut: Path(index[cut]["relative_path"]).name for cut in short}
        samples = lance_samples(dataset, members.values())
        kept, dropped, used = [], [], set()
        for record in records:
            slot = record["audio_slots"][0]
            cut = slot["ref"]["cut_id"]
            if cut in short:
                match = samples.get(members[cut])
                if match is None:
                    dropped.append(record["id"])
                    continue
                slot["ref"] = {**LANCE_REF, "cut_id": match[0]}
                record["metadata"]["duration"] = match[1]
                record["metadata"]["source_cut_id"] = cut
            else:
                slot["ref"]["version"] = VERSION
                used.add(cut)
            kept.append(record)
        write(NEW / f"records_{split}.jsonl.gz", kept)
        write(NEW / f"audio_index_{split}.jsonl.gz", [row for cut, row in index.items() if cut in used])
        report["splits"][split] = {"records": len(kept), "lance_clips": len(short) - len(dropped),
                                   "audio_index": len(used), "dropped_without_lance_sample": dropped}
        print(split, {k: v if not isinstance(v, list) else len(v) for k, v in report["splits"][split].items()}, flush=True)
    (NEW / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
