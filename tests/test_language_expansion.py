"""Verify download recovery and reporting without network or corpus writes."""

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def download(tmp_path, monkeypatch):
    script = load_script("download_language_expansion")
    row = {
        "path": "sample.bin", "size": 4, "algorithm": "sha256",
        "digest": hashlib.sha256(b"good").hexdigest(),
        "url": "https://example.invalid/sample.bin",
    }
    plan = {
        "version": "test", "destination": str(tmp_path / "data"),
        "license": "test", "scope": "test", "files": [row],
    }
    plan_file = tmp_path / "http-plan.json"
    plan_file.write_text(json.dumps({"sample": plan}))
    monkeypatch.setattr(sys, "argv", ["download", str(plan_file), "sample"])
    monkeypatch.setattr(script.time, "sleep", lambda _: None)
    attempts = []

    def fetch(command, *, check):
        assert check
        attempts.append(command)
        directory = next(x.removeprefix("--dir=") for x in command
                         if x.startswith("--dir="))
        filename = next(x.removeprefix("--out=") for x in command
                        if x.startswith("--out="))
        path = Path(directory) / filename
        path.write_bytes(b"good")
        Path(str(path) + ".aria2").unlink(missing_ok=True)

    monkeypatch.setattr(script.subprocess, "run", fetch)
    return script, plan_file, plan, attempts


@pytest.mark.parametrize("pause", [{"active": True}, {}])
def test_quota_pause_precedes_plan_loading_and_download_imports(
    tmp_path, monkeypatch, pause
):
    script = load_script("download_language_expansion")
    (tmp_path / "storage-quota-pause.json").write_text(json.dumps(pause))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    monkeypatch.setattr(sys, "argv", ["download", str(tmp_path / "missing"), "x"])
    with pytest.raises(SystemExit) as exc:
        script.main()
    assert exc.value.code == 2
    assert [p.name for p in tmp_path.iterdir()] == ["storage-quota-pause.json"]


def test_invalid_workers_leave_no_download_state(download, monkeypatch):
    script, plan_file, _, _ = download
    monkeypatch.setattr(
        sys, "argv", ["download", str(plan_file), "sample", "--workers", "0"]
    )
    with pytest.raises(SystemExit) as exc:
        script.main()
    assert exc.value.code == 2
    assert not (plan_file.parent / "sample").exists()
    assert not (plan_file.parent / "data").exists()


@pytest.mark.parametrize("tail", ["", '\n{"path":'])
def test_resume_separates_unterminated_journal_before_new_records(download, tail):
    script, plan_file, plan, attempts = download
    assert script.main() == 0
    journal = plan_file.parent / "sample/verified.jsonl"
    journal.write_text(journal.read_text().rstrip("\n") + tail)
    plan["files"].append({**plan["files"][0], "path": "second.bin"})
    plan_file.write_text(json.dumps({"sample": plan}))
    assert script.main() == 0
    assert script.main() == 0
    assert len(attempts) == 2
    assert json.loads(journal.read_text().splitlines()[-1])["path"] == "second.bin"
    source = json.loads((journal.parent / "state.json").read_text())["artifacts"]
    assert source["source"]["verified_files"] == 2
    assert source["source"]["verified_bytes"] == 8


@pytest.mark.parametrize("change", ["control-file", "algorithm", "mtime"])
def test_resume_rechecks_unfinished_or_changed_files(download, change):
    script, plan_file, plan, attempts = download
    assert script.main() == 0
    journal = plan_file.parent / "sample/verified.jsonl"
    previous = json.loads(journal.read_text())
    if change == "control-file":
        (Path(plan["destination"]) / "sample.bin.aria2").touch()
    elif change == "algorithm":
        previous["algorithm"] = "sha1"
    else:
        previous["mtime_ns"] -= 1
    journal.write_text(json.dumps(previous) + "\n")
    assert script.main() == 0
    assert len(attempts) == 2


def test_hashless_corrupt_archive_is_replaced_then_reused(download, monkeypatch):
    script, plan_file, plan, attempts = download
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("audio.txt", b"good")
    payload = buffer.getvalue()
    row = plan["files"][0]
    row.update(path="audio.zip", size=len(payload), digest="")
    plan_file.write_text(json.dumps({"sample": plan}))

    def fetch(command, *, check):
        attempts.append(command)
        data = payload.replace(b"good", b"bad!") if len(attempts) == 1 else payload
        (Path(plan["destination"]) / "audio.zip").write_bytes(data)

    monkeypatch.setattr(script.subprocess, "run", fetch)
    assert script.main() == 0
    assert len(attempts) == 2
    assert "--continue=true" in attempts[0]
    assert "--continue=false" in attempts[1]
    assert "--allow-overwrite=true" in attempts[1]
    assert script.main() == 0
    assert len(attempts) == 2
    record = json.loads((plan_file.parent / "sample/verified.jsonl").read_text())
    assert record["expected_digest"] == ""
    assert record["digest"] == hashlib.sha256(payload).hexdigest()


def test_http_failures_leave_partial_state(download, monkeypatch):
    script, plan_file, _, attempts = download

    def fail(command, *, check):
        attempts.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(script.subprocess, "run", fail)
    assert script.main() == 1
    assert len(attempts) == 3
    state = json.loads((plan_file.parent / "sample/state.json").read_text())
    assert state["state"] == "partial"
    assert state["artifacts"]["source"]["verified_files"] == 0
    assert state["metadata"]["failures"]["sample.bin"]["type"] == "CalledProcessError"


@pytest.mark.parametrize("algorithm", ["sha1", "sha256"])
def test_hf_revision_hash_verification_and_auth_failure(download, monkeypatch, algorithm):
    script, plan_file, plan, attempts = download
    row = plan["files"][0]
    payload = b"blob 4\0good" if algorithm == "sha1" else b"good"
    row.update(algorithm=algorithm, digest=hashlib.new(algorithm, payload).hexdigest())
    plan.update(repo="test/sample", revision="pinned-revision")
    plan_file.write_text(json.dumps({"sample": plan}))

    class HubError(Exception):
        response = SimpleNamespace(status_code=403)

    def fetch(repo, filename, **kwargs):
        assert repo == "test/sample"
        assert kwargs["repo_type"] == "dataset"
        assert kwargs["revision"] == "pinned-revision"
        attempts.append(kwargs)
        if len(attempts) > 2:
            raise HubError("gated")
        path = Path(kwargs["local_dir"]) / filename
        path.write_bytes(b"bad!" if len(attempts) == 1 else b"good")
        return str(path)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        hf_hub_download=fetch,
    ))
    monkeypatch.setitem(sys.modules, "huggingface_hub.utils", SimpleNamespace(
        HfHubHTTPError=HubError, disable_progress_bars=lambda: None,
    ))
    assert script.main() == 0
    assert len(attempts) == 2
    assert not attempts[0]["force_download"]
    assert attempts[1]["force_download"]
    assert script.main() == 0
    assert len(attempts) == 2
    (Path(plan["destination"]) / row["path"]).unlink()
    assert script.main() == 1
    assert len(attempts) == 3  # Authorization failures do not retry.
    state = json.loads((plan_file.parent / "sample/state.json").read_text())
    assert state["state"] == "partial"
    assert state["metadata"]["failures"][row["path"]]["http_status"] == 403


def test_report_preserves_verified_counts_and_honors_default_pause(download):
    script, plan_file, _, _ = download
    assert script.main() == 0
    work = plan_file.parent
    (work / "hf-plan.json").write_text("{}")
    (work / "storage-quota-pause.json").write_text("{}")
    before = (work / "sample/state.json").read_bytes()
    summaries = load_script("report_language_expansion").report(work)
    assert summaries[0]["state"] == "verified"
    assert summaries[0]["verified_bytes"] == 4
    assert json.loads((work / "summary.json").read_text())["datasets"] == summaries
    progress = (work / "progress.md").read_text()
    assert "下载已暂停" in progress
    assert "运行中的传输需单独停止" in progress
    assert "下载和校验完成" in progress
    assert (work / "sample/state.json").read_bytes() == before
