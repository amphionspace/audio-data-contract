"""Lance record index: build from JSONL sources, pinned open, filtered reads, checks."""

import gzip
import hashlib
import json
import os

import pytest

from audio_data_contract import DatasetCatalog, DatasetSpec
from audio_data_contract.catalog import check_registration
from audio_data_contract.errors import ContractError
from audio_data_contract.record_index import (
    build_index,
    catalog_ref,
    iter_batches,
    open_index,
    to_table,
)

pytest.importorskip("lance")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "expected_bytes": len(data)}


def artifact(name, kind, relative, digest):
    return {"name": name, "kind": kind, "root_alias": "data", "relative_path": relative, **digest}


def record(split, i, duration):
    return {
        "schema_version": "audio-record/1.0",
        "id": f"{split}:r{i}",
        "task": "asr",
        "audio_slots": [
            {
                "name": "primary",
                "purpose": "primary",
                "ref": {
                    "dataset_id": "demo",
                    "version": "v1",
                    "split": split,
                    "cut_id": f"c-{split}-{i}",
                    "duration": duration,
                },
            }
        ],
        "target": f"text {i}",
        "language": "zh" if split == "train_zh" else "en",
        "metadata": {"speaker": f"spk{i % 2}"},
    }


def records_spec(root):
    base = "demo/v1"
    refs, index = [], []
    for split in ("train_zh", "train_en"):
        rows = [record(split, i, 1.0 + i) for i in range(5)]
        digest = write_jsonl(root / base / f"{split}.jsonl.gz", rows)
        refs.append(artifact(split, "audio-records", f"{base}/{split}.jsonl.gz", digest))
        for i in range(5):
            audio = root / base / "audio" / f"{split}-{i}.m4a"
            audio.parent.mkdir(parents=True, exist_ok=True)
            audio.write_bytes(b"\0" * 128)
            index.append(
                {
                    "cut_id": f"c-{split}-{i}",
                    "root_alias": "data",
                    "relative_path": f"{base}/audio/{split}-{i}.m4a",
                    "sample_rate": 16000,
                    "channels": 1,
                    "num_frames": 16000 * (1 + i),
                    "duration": 1.0 + i,
                }
            )
    digest = write_jsonl(root / base / "audio-index.jsonl.gz", index)
    refs.append(artifact("audio_index", "audio-index", f"{base}/audio-index.jsonl.gz", digest))
    splits = {
        split: {"artifacts": {"records": [split], "audio_index": ["audio_index"]}}
        for split in ("train_zh", "train_en")
    }
    # A union split over the same sources must not duplicate records.
    splits["train"] = {
        "artifacts": {"records": ["train_zh", "train_en"], "audio_index": ["audio_index"]}
    }
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": "demo",
        "version": "v1",
        "languages": ["zh", "en"],
        "tasks": ["asr"],
        "artifacts": refs,
        "splits": splits,
    }


def lhotse_spec(root):
    base = "demo/l1"
    audio = root / base / "long.opus"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"\0" * 128)
    recordings = [
        {
            "id": "rec",
            "sources": [{"type": "file", "channels": [0], "source": str(audio)}],
            "sampling_rate": 16000,
            "num_samples": 16000 * 100,
            "duration": 100.0,
            "channel_ids": [0],
        }
    ]
    supervisions = [
        {"id": f"rec_S{i}", "recording_id": "rec", "start": 10.5 * i, "duration": 2.25,
         "channel": 0, "text": f"t{i}", "language": "Chinese"}
        for i in range(4)
    ]
    refs = [
        artifact("recordings", "lhotse-recordings", f"{base}/rec.jsonl.gz",
                 write_jsonl(root / base / "rec.jsonl.gz", recordings)),
        artifact("supervisions", "lhotse-supervisions", f"{base}/sup.jsonl.gz",
                 write_jsonl(root / base / "sup.jsonl.gz", supervisions)),
    ]
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": "demo",
        "version": "l1",
        "languages": ["zh"],
        "tasks": ["asr"],
        "artifacts": refs,
        "splits": {
            "train": {
                "artifacts": {"recordings": ["recordings"], "supervisions": ["supervisions"]}
            }
        },
    }


def register(spec_dict, root, roots):
    """Build the index, then add it to the spec under the records_lance role."""
    catalog = DatasetCatalog([DatasetSpec.from_dict(spec_dict)])
    destination = root / spec_dict["dataset_id"] / spec_dict["version"] / "record_index"
    build_index(catalog, spec_dict["dataset_id"], spec_dict["version"], destination, roots)
    ref = catalog_ref(destination / "index.json", name="record_index", roots=roots)
    spec_dict = {**spec_dict, "artifacts": [*spec_dict["artifacts"], ref]}
    for split in spec_dict["splits"].values():
        split["artifacts"]["records_lance"] = ["record_index"]
    return DatasetCatalog([DatasetSpec.from_dict(spec_dict)]), destination


def test_records_index_reads_metadata_and_locations(tmp_path):
    roots = {"data": tmp_path}
    umask = os.umask(0o022)
    try:
        catalog, _ = register(records_spec(tmp_path), tmp_path, roots)
    finally:
        os.umask(umask)
    index = open_index(catalog, "demo", "v1", "record_index", roots)
    assert (index.manifest_path.parent.stat().st_mode & 0o055) == 0o055
    assert index.manifest["split_counts"] == {"train_zh": 5, "train_en": 5, "train": 10}
    assert index.manifest["record_count"] == 10
    assert to_table(index, split="train", filter="language = 'en'").num_rows == 5

    rows = to_table(index, split="train_zh", filter="duration >= 3").to_pylist()
    assert [r["id"] for r in sorted(rows, key=lambda r: r["id"])] == [
        "train_zh:r2", "train_zh:r3", "train_zh:r4"
    ]
    row = next(r for r in rows if r["id"] == "train_zh:r2")
    assert row["relative_path"] == "demo/v1/audio/train_zh-2.m4a"
    assert (row["start_frame"], row["num_frames"], row["sample_rate"]) == (0, 48000, 16000)
    assert (row["language"], row["speaker"], row["text"]) == ("zh", "spk0", "text 2")
    assert row["splits"] == ["train_zh", "train"]
    assert "record_json" not in rows[0]

    shards = [
        r for s in range(3)
        for b in iter_batches(index, shard=s, num_shards=3, epoch=1)
        for r in b.column("id").to_pylist()
    ]
    assert sorted(shards) == sorted(to_table(index, columns=["id"]).column(0).to_pylist())

    assert check_registration(catalog.get("demo", "v1"), roots) == []


def test_lhotse_index_keeps_segment_offsets(tmp_path):
    # "zzz" ties with "data"; the recordings artifact's own alias must win.
    roots = {"data": tmp_path, "zzz": tmp_path}
    catalog, _ = register(lhotse_spec(tmp_path), tmp_path, roots)
    index = open_index(catalog, "demo", "l1", "record_index", roots)
    row = to_table(index, filter="id = 'rec_S2'").to_pylist()[0]
    assert (row["root_alias"], row["relative_path"]) == ("data", "demo/l1/long.opus")
    assert (row["start_frame"], row["num_frames"], row["duration"]) == (336000, 36000, 2.25)
    assert (row["task"], row["cut_id"], row["channel"]) == ("asr", "rec_S2", 0)
    assert check_registration(catalog.get("demo", "l1"), roots) == []


def test_open_rejects_changed_manifest_and_check_reports_it(tmp_path):
    roots = {"data": tmp_path}
    catalog, destination = register(records_spec(tmp_path), tmp_path, roots)
    manifest = destination / "index.json"
    manifest.write_text(manifest.read_text() + " ")
    with pytest.raises(ContractError, match="sha256"):
        open_index(catalog, "demo", "v1", "record_index", roots)
    problems = check_registration(catalog.get("demo", "v1"), roots)
    assert any("record_index" in p for p in problems)


def test_build_rejects_record_without_audio_and_publishes_nothing(tmp_path):
    spec = records_spec(tmp_path)
    index = tmp_path / "demo/v1/audio-index.jsonl.gz"
    with gzip.open(index, "rt") as stream:
        rows = [json.loads(line) for line in stream][1:]
    spec["artifacts"][-1].update(write_jsonl(index, rows))
    catalog = DatasetCatalog([DatasetSpec.from_dict(spec)])
    destination = tmp_path / "out"
    with pytest.raises(ContractError, match="not in audio_index"):
        build_index(catalog, "demo", "v1", destination, {"data": tmp_path})
    assert not destination.exists()
    assert not list(tmp_path.glob(".record-index-*"))
