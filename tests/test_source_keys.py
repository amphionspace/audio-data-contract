import hashlib
import json

import pytest

from audio_data_contract import (
    ArtifactRef,
    AudioRecord,
    DatasetSpec,
    Split,
    load_catalog,
    load_holdouts,
    record_source_keys,
    source_key_specs,
)
from audio_data_contract.cli import main
from audio_data_contract.declarations import write_declarations
from audio_data_contract.errors import ContractError, IntegrityError
from audio_data_contract.records import write_records

HEX = "(?<![0-9a-f])[0-9a-f]{16}(?![0-9a-f])"
HELD = "00602576e3621f70"
OTHER = "0a3f901e60fd3df5"


def record(record_id, recording, enrollment=None):
    slots = [
        {
            "name": "mixture",
            "ref": {"dataset_id": "mix", "version": "1", "split": "train", "cut_id": f"{recording}_L0000"},
        }
    ]
    if enrollment:
        slots.append(
            {
                "name": "enrollment",
                "ref": {"dataset_id": "src", "version": "1", "split": "train", "cut_id": f"{enrollment}_000"},
            }
        )
    return AudioRecord.from_dict(
        {
            "schema_version": "audio-record/1.0",
            "id": record_id,
            "task": "ts_asr",
            "audio_slots": slots,
            "target": "x",
            "metadata": {"recording_id": recording},
        }
    )


def training_spec(source_keys=None, split_keys=None):
    return DatasetSpec(
        dataset_id="mix",
        version="1",
        languages=("zh",),
        tasks=("ts_asr",),
        artifacts=(ArtifactRef("records", "audio-records", "data", "mix.jsonl"),),
        splits={
            "train": Split(
                {"records": ("records",)},
                provenance={"source_keys": split_keys} if split_keys else {},
            ),
            "eval": Split({"records": ("records",)}),
        },
        provenance={"source_keys": source_keys} if source_keys else {},
    )


def holdout_spec(path, *, sha256=None, pattern="^[0-9a-f]{16}"):
    entry = {"namespace": "emilia2", "artifact": "held"}
    if pattern:
        entry["pattern"] = pattern
    return DatasetSpec(
        dataset_id="evalset",
        version="v2",
        languages=("zh",),
        tasks=("ts_asr",),
        artifacts=(
            ArtifactRef("held", "source-keys", "data", path, sha256=sha256),
        ),
        splits={"test": Split({"keys": ("held",)})},
        provenance={"holdout": [entry]},
    )


def test_split_declaration_replaces_the_dataset_declaration():
    dataset = [{"namespace": "emilia2", "fields": ["metadata.recording_id"]}]
    split = [{"namespace": "other", "fields": ["id"]}]
    spec = training_spec(dataset, split)
    assert [s.namespace for s in source_key_specs(spec, "train")] == ["other"]
    assert [s.namespace for s in source_key_specs(spec, "eval")] == ["emilia2"]
    assert source_key_specs(training_spec(), "train") == ()


def test_pattern_reads_every_slot_and_plain_fields_are_keys():
    spec = training_spec(
        [{"namespace": "emilia2", "fields": ["metadata.recording_id", "audio_slots"], "pattern": HEX}]
    )
    keys = record_source_keys(record("r1", HELD, enrollment=OTHER), source_key_specs(spec, "train"))
    assert keys == {f"emilia2:{HELD}", f"emilia2:{OTHER}"}
    plain = training_spec([{"namespace": "rec", "fields": ["metadata.recording_id"]}])
    # Plain mappings work as well as AudioRecord objects.
    as_dict = record("r1", HELD).to_dict()
    assert record_source_keys(as_dict, source_key_specs(plain, "train")) == {f"rec:{HELD}"}


def test_a_record_without_a_declared_key_is_an_error():
    spec = training_spec([{"namespace": "emilia2", "fields": ["metadata.missing"], "pattern": HEX}])
    with pytest.raises(ContractError, match="no emilia2 source key"):
        record_source_keys(record("r1", HELD), source_key_specs(spec, "train"))


@pytest.mark.parametrize(
    "declaration, message",
    [
        ({"namespace": "Emilia2", "fields": ["id"]}, "namespace"),
        ({"namespace": "e", "fields": []}, "fields"),
        ({"namespace": "e", "fields": ["id"], "pattern": "("}, "pattern"),
        ({"namespace": "e", "fields": ["id"], "extra": 1}, "unknown"),
    ],
)
def test_malformed_declarations_fail_catalog_validation(tmp_path, declaration, message):
    write_declarations(tmp_path / "c.yaml", [training_spec([declaration]).to_dict()])
    with pytest.raises(ContractError, match=message):
        load_catalog(tmp_path / "c.yaml")


def test_holdout_artifact_must_be_a_source_key_list(tmp_path):
    spec = holdout_spec("held.txt").to_dict()
    spec["artifacts"][0]["kind"] = "audio-records"
    write_declarations(tmp_path / "c.yaml", [spec])
    with pytest.raises(ContractError, match="kind source-keys"):
        load_catalog(tmp_path / "c.yaml")


def test_holdouts_are_read_through_the_pattern_and_verified(tmp_path):
    held = tmp_path / "held.txt"
    held.write_text(f"{HELD}_dlg_00003\n{HELD}_dlg_00006_p0\n")
    digest = hashlib.sha256(held.read_bytes()).hexdigest()
    write_declarations(tmp_path / "c.yaml", [holdout_spec("held.txt", sha256=digest).to_dict()])
    catalog = load_catalog(tmp_path / "c.yaml")
    holdouts = load_holdouts(catalog, {"data": tmp_path})
    # Both windows of the recording, suffixed or not, reduce to its source.
    assert holdouts.keys == {f"emilia2:{HELD}"}
    assert holdouts.sources == ("evalset@v2:held",)
    held.write_text("changed\n")
    with pytest.raises(IntegrityError):
        load_holdouts(catalog, {"data": tmp_path})


def test_check_holdout_counts_overlapping_records(tmp_path, capsys):
    (tmp_path / "held.txt").write_text(f"{HELD}_dlg_00003\n")
    write_records([record("r1", HELD), record("r2", OTHER), record("r3", OTHER, HELD)], tmp_path / "mix.jsonl")
    keys = [{"namespace": "emilia2", "fields": ["metadata.recording_id", "audio_slots"], "pattern": HEX}]
    write_declarations(
        tmp_path / "c.yaml", [training_spec(keys).to_dict(), holdout_spec("held.txt").to_dict()]
    )
    (tmp_path / "roots.json").write_text(json.dumps({"data": str(tmp_path)}))
    argv = ["check-holdout", str(tmp_path / "c.yaml"), "mix", "1", "train", "--roots", str(tmp_path / "roots.json")]
    assert main(argv) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["records"] == 3
    assert result["overlapping_records"] == 2
    assert result["examples"] == ["r1", "r3"]
    assert result["holdouts"] == ["evalset@v2:held"]
