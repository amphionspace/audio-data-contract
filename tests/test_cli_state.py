import gzip
import hashlib
import json

from audio_data_contract import DatasetState, DownloadState
from audio_data_contract.cli import main
from audio_data_contract.state import load_state, write_state_atomic


def test_state_cli_validates_inspects_and_transitions(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    write_state_atomic(
        DatasetState("demo", "1.0", DownloadState.DOWNLOADING), state_path
    )
    assert main(["validate-state", str(state_path)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "downloading"

    artifact = tmp_path / "archive"
    artifact.write_bytes(b"done")
    assert main(["inspect-download", str(artifact), "--expected-bytes", "4"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "downloaded"

    assert main(["transition-state", str(state_path), "downloaded"]) == 0
    assert load_state(state_path).state == DownloadState.DOWNLOADED


def test_verify_artifact_cli(tmp_path, capsys):
    artifact_path = tmp_path / "records.jsonl.gz"
    with gzip.open(artifact_path, "wt", encoding="utf-8") as stream:
        stream.write('{"id":"one"}\n')
    content = artifact_path.read_bytes()
    catalog_path = tmp_path / "catalog.jsonl"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": "dataset-catalog/2.0",
                "dataset_id": "demo",
                "version": "1",
                "languages": ["en"],
                "tasks": ["asr"],
                "artifacts": [
                    {
                        "name": "records",
                        "kind": "lhotse-supervisions",
                        "root_alias": "managed",
                        "relative_path": artifact_path.name,
                        "expected_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "metadata": {"record_count": 1},
                    }
                ],
                "splits": {"train": {"artifacts": {"supervisions": ["records"]}}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    roots_path = tmp_path / "roots.json"
    roots_path.write_text(json.dumps({"managed": str(tmp_path)}), encoding="utf-8")

    assert (
        main(
            [
                "verify-artifact",
                str(catalog_path),
                "demo",
                "1",
                "records",
                "--roots",
                str(roots_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["records"] == 1


def test_check_registration_cli(tmp_path, capsys):
    (tmp_path / "a.wav").write_bytes(b"RIFF....WAVE")
    (tmp_path / "empty.wav").write_bytes(b"")
    index_path = tmp_path / "audio-index.jsonl.gz"
    rows = [
        {"cut_id": "a", "root_alias": "managed", "relative_path": "a.wav"},
        {"cut_id": "b", "root_alias": "managed", "relative_path": "missing.wav"},
        {"cut_id": "c", "root_alias": "managed", "relative_path": "empty.wav"},
        {"cut_id": "d", "root_alias": "elsewhere", "relative_path": "d.wav"},
        {"cut_id": "e", "root_alias": ["managed"], "relative_path": "a.wav"},
    ]
    with gzip.open(index_path, "wt", encoding="utf-8") as stream:
        stream.writelines(json.dumps(row) + "\n" for row in rows)
    content = index_path.read_bytes()
    spec = {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": "demo",
        "version": "1",
        "languages": ["en"],
        "tasks": ["asr"],
        "artifacts": [
            {
                "name": "audio_index",
                "kind": "audio-index",
                "root_alias": "managed",
                "relative_path": index_path.name,
                "sha256": hashlib.sha256(content).hexdigest(),
            },
            {
                "name": "notes",
                "kind": "metadata",
                "root_alias": "managed",
                "relative_path": "a.wav",
                "sha256": "0" * 64,
            },
        ],
        "splits": {"train": {"artifacts": {"audio_index": ["audio_index"]}}},
    }
    catalog_path = tmp_path / "catalog.jsonl"
    catalog_path.write_text(json.dumps(spec) + "\n", encoding="utf-8")
    roots_path = tmp_path / "roots.json"
    roots_path.write_text(json.dumps({"managed": str(tmp_path)}), encoding="utf-8")

    argv = ["check-registration", str(catalog_path), "--roots", str(roots_path)]
    assert main(argv) == 1
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert len(problems) == 5
    assert any("bad index row" in item for item in problems)
    assert any("sha256 mismatch" in item for item in problems)
    assert any("'elsewhere' is not configured" in item for item in problems)
    assert any("missing.wav" in item for item in problems)
    assert any("empty file" in item for item in problems)

    spec["artifacts"].pop()
    with gzip.open(index_path, "wt", encoding="utf-8") as stream:
        stream.writelines(json.dumps(row) + "\n" for row in rows[:-1])
    spec["artifacts"][0]["sha256"] = hashlib.sha256(
        index_path.read_bytes()
    ).hexdigest()
    catalog_path.write_text(json.dumps(spec) + "\n", encoding="utf-8")
    (tmp_path / "empty.wav").write_bytes(b"x")
    (tmp_path / "missing.wav").write_bytes(b"x")
    roots_path.write_text(
        json.dumps({"managed": str(tmp_path), "elsewhere": str(tmp_path)}),
        encoding="utf-8",
    )
    (tmp_path / "d.wav").write_bytes(b"x")
    assert main(argv[:2] + ["demo", "1"] + argv[2:]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
