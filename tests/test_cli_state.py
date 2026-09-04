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
                "schema_version": "dataset-catalog/1.0",
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
                "splits": {"train": {"supervisions_artifact": "records"}},
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
