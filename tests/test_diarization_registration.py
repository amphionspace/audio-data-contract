"""Protect existing machine configuration when preparing benchmark snapshots."""
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("soundfile")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diarization/register_benchmark.py"
spec = importlib.util.spec_from_file_location("register_benchmark", SCRIPT)
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)


def test_preserves_existing_roots(tmp_path):
    path = tmp_path / "roots.json"
    path.write_text(json.dumps({"existing": "/data/existing"}))
    output = tmp_path / "snapshot"
    roots = registration.merged_roots(path, output)
    registration.write_roots(path, roots)
    assert json.loads(path.read_text()) == {
        "existing": "/data/existing", registration.ALIAS: str(output)
    }
    assert registration.merged_roots(path, output) == roots


def test_conflict_keeps_original_bytes(tmp_path):
    path = tmp_path / "roots.json"
    original = json.dumps({registration.ALIAS: "/published/snapshot"})
    path.write_text(original)
    with pytest.raises(ValueError, match="already points"):
        registration.merged_roots(path, tmp_path / "new-snapshot")
    assert path.read_text() == original


@pytest.mark.parametrize("value", [[], {"root": None}, {"root": 123}])
def test_invalid_mapping_rejected(tmp_path, value):
    path = tmp_path / "roots.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid roots"):
        registration.merged_roots(path, tmp_path / "snapshot")


def test_new_configuration_and_digest(tmp_path):
    path = tmp_path / "roots.json"
    roots = registration.merged_roots(path, tmp_path / "snapshot")
    registration.write_roots(path, roots)
    assert json.loads(path.read_text()) == roots
    data = tmp_path / "data"
    data.write_bytes(b"abc")
    assert registration.digest(data) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
