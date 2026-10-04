#!/usr/bin/env python3
"""Build an isolated CHiME-6 dev pilot from repaired transcripts and original WAVs."""

import argparse
import gzip
import json
import wave
from pathlib import Path

from audio_data_contract import AudioRecord, AudioRef, AudioSlot, write_records


def seconds(value):
    hour, minute, second = map(float, value.split(":"))
    return hour * 3600 + minute * 60 + second


def prepare(extracted, output):
    extracted, output = Path(extracted).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    audio = extracted / "dev_archive/CHiME6_dev/CHiME6/audio/dev"
    transcripts = (
        extracted / "transcriptions_repaired_archive/transcriptions/transcriptions/dev"
    )
    index, records, skipped = {}, [], 0
    for source in sorted(transcripts.glob("*.json")):
        for number, row in enumerate(json.loads(source.read_text())):
            start, end = seconds(row["start_time"]), seconds(row["end_time"])
            names = [
                f"{row['session_id']}_{row['speaker']}",
                f"{row['session_id']}_{row['ref']}.CH1",
            ]
            for name in names:
                if name not in index:
                    path = audio / (name + ".wav")
                    with wave.open(str(path)) as stream:
                        index[name] = {
                            "cut_id": name,
                            "root_alias": "chime6_pilot_audio",
                            "relative_path": path.name,
                            "sample_rate": stream.getframerate(),
                            "channels": stream.getnchannels(),
                            "duration": stream.getnframes() / stream.getframerate(),
                        }
            if (
                start < 0
                or end <= start
                or any(end > index[n]["duration"] for n in names)
            ):
                skipped += 1
                continue
            slots = tuple(
                AudioSlot(
                    slot,
                    AudioRef(
                        "chime6",
                        "lance-pilot-dev-v1",
                        "dev",
                        name,
                        channel=tuple(range(index[name]["channels"]))
                        if index[name]["channels"] > 1
                        else 0,
                        start=start,
                        duration=end - start,
                    ),
                )
                for slot, name in zip(("worn", "far"), names)
            )
            records.append(
                AudioRecord(
                    id=f"{source.stem}-{number:06d}",
                    task="asr",
                    language="en",
                    audio_slots=slots,
                    target=row["words"],
                    metadata={
                        "speaker": row["speaker"],
                        "session": row["session_id"],
                        "source_transcript": str(source),
                        "source_row": number,
                    },
                )
            )
    write_records(records, output / "records.jsonl")
    with gzip.open(output / "audio-index.jsonl.gz", "wt") as stream:
        for row in index.values():
            stream.write(json.dumps(row) + "\n")
    # This private catalog is solely for exercising the existing audio-index resolver.
    catalog = {
        "schema_version": "dataset-catalog/1.0",
        "dataset_id": "chime6",
        "version": "lance-pilot-dev-v1",
        "languages": ["en"],
        "tasks": ["asr"],
        "artifacts": [
            {
                "name": "audio_index",
                "kind": "audio-index",
                "root_alias": "pilot",
                "relative_path": "audio-index.jsonl.gz",
            }
        ],
        "splits": {"dev": {"audio_index_artifact": "audio_index"}},
    }
    (output / "catalog.jsonl").write_text(json.dumps(catalog) + "\n")
    (output / "roots.json").write_text(
        json.dumps({"pilot": str(output), "chime6_pilot_audio": str(audio)}) + "\n"
    )
    (output / "preparation.json").write_text(
        json.dumps(
            {
                "source": str(extracted),
                "records": len(records),
                "skipped_invalid_bounds": skipped,
                "empty_targets": sum(r.target == "" for r in records),
                "audio_files": len(index),
                "note": "Isolated dev pilot, not the registered speaker View or a production cleaning Layer.",
            },
            indent=2,
        )
        + "\n"
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted")
    parser.add_argument("output")
    args = parser.parse_args()
    print(prepare(args.extracted, args.output))
