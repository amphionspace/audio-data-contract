"""Exercise restart and transient failure without network or large downloads."""

import pytest

pytest.importorskip("requests")

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def test_download_resumes_after_timeout_and_skips_completed_file(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "realman_download",
        (Path(__file__).resolve().parents[2] / "scripts/icefall").joinpath(
            "download_realman_asr.py"
        ),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    corpus = tmp_path / "RealMAN"
    corpus.mkdir()
    files = [{"path": "transcriptions.trn", "size": 2}] + [
        {
            "path": f"{part}/audio.rar",
            "size": 4,
            "lfs": {"oid": hashlib.sha256(b"xxxx").hexdigest()},
        }
        for part in ("train", "val", "test")
    ]
    (corpus / "transcriptions.trn").write_text("ok")
    (corpus / "asr_download.json").write_text(
        json.dumps(
            {"repo": "AISHELL/RealMAN", "revision": module.REVISION, "files": files}
        )
    )
    attempts = []
    sleeps = []

    def run(command, **kwargs):
        if command[0] == "aria2c":
            text = (corpus / "asr_urls.txt").read_text()
            assert "transcriptions.trn" not in text
            assert "checksum=sha-256=" in text
            assert "--continue=true" in command
            attempts.append(command)
            if len(attempts) == 1:
                p = corpus / files[1]["path"]
                p.write_bytes(b"xx")
                Path(str(p) + ".aria2").write_text("progress")
                return subprocess.CompletedProcess(command, 2)
            assert (corpus / files[1]["path"]).read_bytes() == b"xx"
            for row in files[1:]:
                p = corpus / row["path"]
                p.write_bytes(b"xxxx")
                Path(str(p) + ".aria2").unlink(missing_ok=True)
        elif command[0] == "7zz":
            destination = Path(next(x[2:] for x in command if x.startswith("-o")))
            (destination / "sample_CH0.flac").touch()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must reuse pinned plan")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download",
            "-r",
            str(tmp_path),
            "-l",
            str(tmp_path / "lhotse"),
            "--retry-delay",
            "1",
        ],
    )
    module.main()
    assert len(attempts) == 2 and sleeps == [1]
    assert (
        json.loads((corpus / "preparation_status.json").read_text())["phase"] == "ready"
    )
    module.main()
    assert len(attempts) == 2  # Restart skips complete downloads and extraction.


def test_same_size_corruption_and_partial_control_file_are_not_complete(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "realman_download",
        (Path(__file__).resolve().parents[2] / "scripts/icefall").joinpath(
            "download_realman_asr.py"
        ),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = {
        "path": "a.rar",
        "size": 4,
        "lfs": {"oid": hashlib.sha256(b"good").hexdigest()},
    }
    path = tmp_path / "a.rar"
    path.write_bytes(b"bad!")
    verified = set()
    assert not module.download_complete(tmp_path, row, verified)
    path.write_bytes(b"good")
    assert module.download_complete(tmp_path, row, verified)
    (tmp_path / "a.rar.aria2").touch()
    assert not module.download_complete(tmp_path, row, verified)
