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
