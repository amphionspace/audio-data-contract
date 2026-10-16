"""Lance record index: build from JSONL sources, pinned open, filtered reads, checks."""

import gzip
import hashlib
import json
import os

import pytest

from audio_data_contract import DatasetCatalog, DatasetSpec
from audio_data_contract.catalog import check_registration, load_catalog
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
        "metadata": {
            "speaker": f"demo:spk{i % 2}",
            # Quality facts only on even records; odd ones stay null.
            **(
                {"loudness_dbfs": -20.5 - i, "clip_ratio": 0, "voiced_ratio": 0.75,
                 "source_group": f"group{i % 3}"}
                if i % 2 == 0 else {}
            ),
        },
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
    assert (row["language"], row["speaker"], row["text"]) == ("zh", "demo:spk0", "text 2")
    assert (row["loudness_dbfs"], row["clip_ratio"], row["voiced_ratio"]) == (-22.5, 0.0, 0.75)
    assert row["source_group"] == "group2"
    quiet = to_table(index, split="train_zh", filter="loudness_dbfs < -22 AND voiced_ratio > 0.5")
    assert sorted(quiet.column("id").to_pylist()) == ["train_zh:r2", "train_zh:r4"]
    assert to_table(index, split="train_zh", filter="loudness_dbfs IS NULL").num_rows == 2
    assert to_table(index, filter="speaker = 'demo:spk1'").num_rows == 4
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


def test_ts_slots_and_ids_repeated_across_source_files(tmp_path):
    base = "demo/ts"
    audio = tmp_path / base / "mix.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"\0" * 128)

    def ts(split, i):
        ref = {"dataset_id": "demo", "version": "ts", "split": split, "cut_id": "mix"}
        return {
            "schema_version": "audio-record/1.0",
            "id": f"r{i}",
            "task": "ts_asr",
            "audio_slots": [
                {"name": "enrollment", "purpose": "enrollment",
                 "ref": {**ref, "start": 1.0, "duration": 2.0}},
                {"name": "mixture", "purpose": "mixture",
                 "ref": {**ref, "start": 10.0 * i, "duration": 5.0}},
            ],
            "target": f"t{i}",
            "language": "en",
        }

    # "subset" repeats the IDs of "all" from another file, like hw_sft train_hotwords.
    refs = [
        artifact(name, "audio-records", f"{base}/{name}.jsonl.gz",
                 write_jsonl(tmp_path / base / f"{name}.jsonl.gz", [ts(name, i) for i in rows]))
        for name, rows in (("all", range(3)), ("subset", range(2)))
    ]
    index = [{"cut_id": "mix", "root_alias": "data", "relative_path": f"{base}/mix.wav",
              "sample_rate": 16000, "num_frames": 16000 * 60, "duration": 60.0}]
    refs.append(artifact("audio_index", "audio-index", f"{base}/index.jsonl.gz",
                         write_jsonl(tmp_path / base / "index.jsonl.gz", index)))
    spec = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": "demo", "version": "ts",
        "languages": ["en"], "tasks": ["ts_asr"], "artifacts": refs,
        "splits": {
            name: {"artifacts": {"records": [name], "audio_index": ["audio_index"]}}
            for name in ("all", "subset")
        },
    }
    roots = {"data": tmp_path}
    catalog, _ = register(spec, tmp_path, roots)
    index = open_index(catalog, "demo", "ts", "record_index", roots)
    assert index.manifest["record_count"] == 5
    row = to_table(index, split="subset", filter="id = 'r1'").to_pylist()[0]
    assert (row["start_frame"], row["num_frames"], row["duration"]) == (160000, 80000, 5.0)
    enrollment, mixture = row["slots"]
    assert (enrollment["name"], enrollment["start_frame"], enrollment["num_frames"]) == (
        "enrollment", 16000, 32000
    )
    assert mixture["start_frame"] == row["start_frame"]
    assert check_registration(catalog.get("demo", "ts"), roots) == []


def test_lhotse_recording_without_channel_ids(tmp_path):
    spec = lhotse_spec(tmp_path)
    path = tmp_path / "demo/l1/rec.jsonl.gz"
    with gzip.open(path, "rt") as stream:
        recordings = [json.loads(line) for line in stream]
    del recordings[0]["channel_ids"]
    spec["artifacts"][0].update(write_jsonl(path, recordings))
    roots = {"data": tmp_path}
    catalog, _ = register(spec, tmp_path, roots)
    index = open_index(catalog, "demo", "l1", "record_index", roots)
    assert to_table(index, columns=["channels"]).column(0).to_pylist() == [1] * 4


def cli_setup(tmp_path):
    from audio_data_contract.declarations import write_declarations

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    path = catalog / "demo.yaml"
    write_declarations(path, [records_spec(tmp_path)])
    roots = tmp_path / "roots.json"
    roots.write_text(json.dumps({"data": str(tmp_path)}))
    return catalog, path, roots


def run_cli(capsys, *args):
    from audio_data_contract.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


def test_cli_register_writes_catalog_and_check_warns_until_then(tmp_path, capsys):
    catalog, path, roots = cli_setup(tmp_path)
    check = ("check-registration", str(catalog), "demo", "v1", "--roots", str(roots))
    code, result = run_cli(capsys, *check)
    assert code == 0 and result["warnings"] and not result["problems"]
    code, result = run_cli(capsys, *check, "--require-record-index")
    assert code == 1 and "no lance-record-index" in result["problems"][0]

    before = path.read_text()
    code, ref = run_cli(
        capsys, "build-record-index", str(catalog), "demo", "v1",
        str(tmp_path / "demo/v1/record_index"), "--roots", str(roots), "--register",
    )
    assert code == 0 and ref["registered_in"] == str(path)
    after = path.read_text()
    # Only additions: every original line survives in order.
    original = iter(after.split("\n"))
    assert all(line in original for line in before.split("\n"))

    code, result = run_cli(capsys, *check, "--require-record-index")
    assert code == 0 and result == {**result, "problems": [], "warnings": []}
    loaded = load_catalog(catalog)
    index = open_index(loaded, "demo", "v1", "record_index", {"data": tmp_path})
    assert index.manifest["record_count"] == 10


def test_register_refuses_a_file_it_would_reformat(tmp_path, capsys):
    catalog, path, roots = cli_setup(tmp_path)
    # A hand-wrapped long value cannot be reproduced by a YAML rewrite.
    text = path.read_text().replace(
        "    dataset_id: demo\n",
        "    dataset_id: demo\n    provenance:\n      note: a long note\n        wrapped by hand\n",
    )
    path.write_text(text)
    with pytest.raises(ContractError, match="reformat"):
        run_cli(
            capsys, "build-record-index", str(catalog), "demo", "v1",
            str(tmp_path / "demo/v1/record_index"), "--roots", str(roots), "--register",
        )
    assert path.read_text() == text


def test_quality_must_be_numeric(tmp_path):
    spec = records_spec(tmp_path)
    path = tmp_path / "demo/v1/train_zh.jsonl.gz"
    rows = [record("train_zh", i, 1.0 + i) for i in range(5)]
    rows[1]["metadata"]["clip_ratio"] = "high"
    spec["artifacts"][0].update(write_jsonl(path, rows))
    catalog = DatasetCatalog([DatasetSpec.from_dict(spec)])
    with pytest.raises(ContractError, match="clip_ratio must be a number"):
        build_index(catalog, "demo", "v1", tmp_path / "out", {"data": tmp_path})


def test_register_replaces_a_rebuilt_index_in_place(tmp_path, capsys):
    catalog, path, roots = cli_setup(tmp_path)
    build = (
        "build-record-index", str(catalog), "demo", "v1",
        str(tmp_path / "demo/v1/record_index"), "--roots", str(roots), "--register",
    )
    run_cli(capsys, *build)
    first = path.read_text()
    # Rebuild at the same location, as after a mapping upgrade.
    (tmp_path / "demo/v1/record_index").rename(tmp_path / "old_index")
    code, ref = run_cli(capsys, *build)
    assert code == 0
    second = path.read_text()
    assert second.count("lance-record-index") == 1
    assert second.count("records_lance") == first.count("records_lance")
    assert ref["sha256"] in second
    index = open_index(load_catalog(catalog), "demo", "v1", "record_index", {"data": tmp_path})
    assert index.manifest["record_count"] == 10
