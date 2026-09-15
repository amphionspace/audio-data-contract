import hashlib
import importlib.util
import io
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import zstandard

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cos_backup.py"
spec = importlib.util.spec_from_file_location("cos_backup", SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def item(path, data):
    path.write_bytes(data)
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "category": "audio", "sources": [
                {"path": str(path), "signature": backup.signature(path)}
            ]}


class FakeCOS:
    def __init__(self):
        self.parts = {}
        self.objects = {}
        self.calls = []
        self.fail_part = None
        self.fail_completion = False
        self.bad_crc = False

    def create_multipart_upload(self, **kwargs):
        assert kwargs["ACL"] == "private"
        self.metadata = kwargs["Metadata"]
        return {"UploadId": "test"}

    def list_parts(self, **kwargs):
        return {"Part": [{"PartNumber": n, "ETag": hashlib.md5(data).hexdigest(),
                          "Size": len(data)} for n, data in self.parts.items()]}

    def upload_part(self, **kwargs):
        n, data = kwargs["PartNumber"], kwargs["Body"]
        assert kwargs["EnableMD5"]
        self.calls.append(n)
        if self.fail_part == n:
            self.fail_part = None
            raise RuntimeError("interrupted part")
        self.parts[n] = data
        checksum = backup.crc64()
        checksum.update(data)
        return {"ETag": hashlib.md5(data).hexdigest(),
                "x-cos-hash-crc64ecma": "bad" if self.bad_crc else str(checksum.crcValue)}

    def complete_multipart_upload(self, **kwargs):
        data = b"".join(self.parts[p["PartNumber"]]
                        for p in kwargs["MultipartUpload"]["Part"])
        checksum = backup.crc64()
        checksum.update(data)
        self.objects[kwargs["Key"]] = {
            "Content-Length": str(len(data)),
            "x-cos-hash-crc64ecma": str(checksum.crcValue),
            "x-cos-meta-plan-sha256": self.metadata["x-cos-meta-plan-sha256"],
        }
        if self.fail_completion:
            self.fail_completion = False
            raise RuntimeError("completion response lost")


@pytest.fixture
def transfer(tmp_path, monkeypatch):
    client = FakeCOS()
    monkeypatch.setattr(backup, "remote_head", lambda c, b, k: c.objects.get(k))
    data = b"0123456789" * 300000
    job = {"format": "raw", "files": [item(tmp_path / "audio.bin", data)]}
    checkpoint = tmp_path / "checkpoint.json"
    args = SimpleNamespace(part_mib=1, workers=2, compression_level=3)
    return client, job, checkpoint, args


def test_interrupted_upload_reuses_verified_parts(transfer):
    client, job, checkpoint, args = transfer
    client.fail_part = 2
    with pytest.raises(RuntimeError, match="interrupted part"):
        backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    result = backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert result["status"] == "verified"
    assert client.calls.count(1) == 1
    assert result["object"]["sha256"] == job["files"][0]["sha256"]
    calls = list(client.calls)
    backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert client.calls == calls
    assert Path(job["files"][0]["sources"][0]["path"]).is_file()


def test_verified_remote_snapshot_survives_source_change(transfer):
    client, job, checkpoint, args = transfer
    backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    Path(job["files"][0]["sources"][0]["path"]).write_bytes(b"new local version")
    calls = list(client.calls)
    result = backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert result["status"] == "verified"
    assert client.calls == calls


def test_completion_response_loss_is_recovered_from_head(transfer):
    client, job, checkpoint, args = transfer
    client.fail_completion = True
    with pytest.raises(RuntimeError, match="completion response lost"):
        backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    calls = list(client.calls)
    result = backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert result["status"] == "verified"
    assert client.calls == calls


def test_bad_part_crc_never_publishes_an_object(transfer):
    client, job, checkpoint, args = transfer
    client.bad_crc = True
    with pytest.raises(ValueError, match="part CRC64 mismatch"):
        backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert not client.objects
    assert json.loads(checkpoint.read_text()).get("status") != "verified"


def test_streamed_tar_has_restore_mapping_and_original_bytes(tmp_path):
    original = item(tmp_path / "audio.wav", b"sample audio bytes")
    job = {"format": "tar.zst", "files": [original]}
    packed = io.BytesIO()
    backup.write_archive(job, packed, 3)
    with (
        zstandard.ZstdDecompressor().stream_reader(io.BytesIO(packed.getvalue())) as reader,
        tarfile.open(fileobj=reader, mode="r|") as archive,
    ):
        index = archive.next()
        assert json.loads(archive.extractfile(index).read()) == job
        audio = archive.next()
        assert audio.name == "files/" + original["sha256"]
        assert archive.extractfile(audio).read() == b"sample audio bytes"


def test_tar_upload_streams_through_multipart_sink(transfer):
    client, job, checkpoint, args = transfer
    job["format"] = "tar.zst"
    result = backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert result["status"] == "verified"
    assert result["object"]["size"] < job["files"][0]["size"]


def test_same_size_mtime_preserving_change_fails_content_check(tmp_path):
    path = tmp_path / "audio.wav"
    original = item(path, b"good")
    job = {"format": "tar.zst", "files": [original]}
    path.write_bytes(b"bad!")
    mtime = original["sources"][0]["signature"]["mtime_ns"]
    os.utime(path, ns=(mtime, mtime))
    backup.check_sources(job)
    with pytest.raises(ValueError, match="content changed"):
        backup.write_archive(job, io.BytesIO(), 3)


def test_unknown_remote_object_is_not_overwritten(transfer):
    client, job, checkpoint, args = transfer
    client.objects["key"] = {"Content-Length": "1"}
    with pytest.raises(ValueError, match="no local verification receipt"):
        backup.upload_job(client, "bucket", "key", job, "plan", checkpoint, args)
    assert not client.calls


def test_planner_deduplicates_content_and_inodes_without_losing_paths(tmp_path):
    first, second, linked = [tmp_path / n for n in ("first.wav", "second.wav", "link.wav")]
    first.write_bytes(b"same audio")
    second.write_bytes(first.read_bytes())
    os.link(first, linked)
    manifest = tmp_path / "recordings.jsonl"
    manifest.write_text(json.dumps({"id": "sample", "sampling_rate": 16000,
                                   "sources": [{"type": "file", "source": str(p)}
                                               for p in (first, second, linked)]}) + "\n")
    catalog = tmp_path / "catalog.jsonl"
    catalog.write_text(json.dumps({
        "schema_version": "dataset-catalog/1.0", "dataset_id": "test", "version": "1",
        "languages": ["zh"], "tasks": ["asr"], "aliases": [],
        "artifacts": [{"name": "recordings", "kind": "lhotse-recordings",
                       "root_alias": "data", "relative_path": manifest.name}],
        "splits": {"train": {"recordings_artifact": "recordings"}},
    }) + "\n")
    roots = tmp_path / "roots.json"
    roots.write_text(json.dumps({"data": str(tmp_path)}))
    output = tmp_path / "plan.json"
    backup.build_plan(SimpleNamespace(
        output=output, catalog=catalog, roots=roots, dataset=["test@1"],
        source_root=None, include_file=[], include_repository=False,
        workers=2, shard_bytes=1024, compression_level=3,
    ))
    plan = json.loads(output.read_text())
    assert plan["summary"]["physical_files"] == 3
    assert plan["summary"]["unique_contents"] == 2
    audio = next(j for j in plan["jobs"] if j["category"] == "audio")["files"][0]
    assert {s["path"] for s in audio["sources"]} == {str(first), str(second), str(linked)}
    assert first.exists() and second.exists() and linked.exists()
