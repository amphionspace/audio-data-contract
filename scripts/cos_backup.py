#!/usr/bin/env python3
"""Plan explicit dataset batches and stream verified shards to private COS.

Runtime extras: cos-python-sdk-v5, crcmod, zstandard. No archive is staged on
disk, and this tool never deletes source files. Local plans/checkpoints belong
under state/, outside the versioned catalog.
"""

import argparse
import fcntl
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from audio_data_contract import load_catalog
from audio_data_contract.audio_prepare import _parse, _sources
from audio_data_contract.roots import load_roots


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded(value) + b"\n")
    temporary.replace(path)


def signature(path):
    info = Path(path).stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not a regular file: {path}")
    if Path(str(path) + ".aria2").exists():
        raise ValueError(f"unfinished download: {path}")
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "device": info.st_dev, "inode": info.st_ino}


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_plan(args):
    if args.output.exists():
        raise ValueError("plan already exists; reuse it or choose a new output")
    roots = load_roots(args.roots)
    catalog = load_catalog(args.catalog)
    selected = [catalog.get(*key.rsplit("@", 1)) for key in args.dataset]
    paths = {}
    expected = {}
    recordings = set()
    # These artifacts are self-contained, or have the explicit expansion below.
    supported = {"lhotse-recordings", "lhotse-supervisions", "metadata",
                 "json-metadata", "jsonl-metadata", "quality-report", "license",
                 "archive", "source-archive", "source-archive-part",
                 "repaired-source-archive"}

    def add(path, category):
        path = Path(os.path.abspath(path))
        current = signature(path)
        if path in paths and paths[path]["signature"] != current:
            raise ValueError(f"source changed during inventory: {path}")
        paths[path] = {"path": str(path), "signature": current,
                       "category": category}
        return path

    for spec in selected:
        if spec.provenance.get("inventory_status") == "download_planned":
            raise ValueError(f"download is not cataloged as complete: {spec.key}")
        for artifact in spec.artifacts:
            if artifact.kind not in supported:
                raise ValueError(f"dependency expansion not supported: {artifact.kind}")
            category = "archive" if "archive" in artifact.kind else "metadata"
            path = add(roots[artifact.root_alias] / artifact.relative_path, category)
            if (artifact.expected_bytes is not None
                    and paths[path]["signature"]["size"] != artifact.expected_bytes):
                raise ValueError(f"catalog size mismatch: {path}")
            if artifact.sha256:
                if path in expected and expected[path] != artifact.sha256:
                    raise ValueError(f"conflicting catalog hashes: {path}")
                expected[path] = artifact.sha256
            if artifact.kind == "lhotse-recordings":
                recordings.add(path)
    for path in sorted(recordings):
        opener = gzip.open if path.name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                for source in _sources(json.loads(line)):
                    if not args.source_root and not Path(source["source"]).is_absolute():
                        raise ValueError("relative/command audio requires --source-root")
                    _, source_path, _ = _parse(
                        source, args.source_root or Path("/"), extract=True
                    )
                    add(source_path, "audio")
                    # Preserve the original absolute spelling used by manifests.
                    if source["type"] == "file" and Path(source["source"]).is_absolute():
                        add(source["source"], "audio")
    for path in args.include_file:
        add(path, "metadata")
    if args.include_repository:
        repo = Path(__file__).resolve().parents[1]
        filenames = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=repo
        ).decode().split("\0")
        for filename in filter(None, filenames):
            add(repo / filename, "metadata")
        add(Path(__file__).resolve(), "metadata")

    physical = defaultdict(list)
    for row in paths.values():
        sig = row["signature"]
        physical[sig["device"], sig["inode"]].append(row)
    representatives = [rows[0]["path"] for rows in physical.values()]
    with ThreadPoolExecutor(args.workers) as pool:
        hashes = dict(zip(representatives, pool.map(digest_file, representatives)))
    objects = {}
    for rows in physical.values():
        sha = hashes[rows[0]["path"]]
        for row in rows:
            path = Path(row["path"])
            if signature(path) != row["signature"]:
                raise ValueError(f"source changed during hashing: {path}")
            if path in expected and sha != expected[path]:
                raise ValueError(f"catalog hash mismatch: {path}")
        key = (rows[0]["signature"]["size"], sha)
        item = objects.setdefault(key, {
            "sha256": sha, "size": key[0], "sources": [],
            "category": rows[0]["category"],
        })
        item["sources"].extend(rows)

    jobs = []
    for category in ("metadata", "audio"):
        members, size = [], 0
        for row in sorted(objects.values(), key=lambda r: r["sha256"]):
            if row["category"] != category:
                continue
            if members and size + row["size"] > args.shard_bytes:
                jobs.append({"category": category, "format": "tar.zst", "files": members})
                members, size = [], 0
            members.append(row)
            size += row["size"]
        if members:
            jobs.append({"category": category, "format": "tar.zst", "files": members})
    for row in sorted(objects.values(), key=lambda r: r["sha256"]):
        if row["category"] == "archive":
            jobs.append({"category": "archive", "format": "raw", "files": [row]})
    plan = {
        "schema_version": "cos-backup-plan/1", "datasets": [s.to_dict() for s in selected],
        "roots": {name: str(path) for name, path in roots.items()},
        "jobs": jobs, "compression_level": args.compression_level,
        "summary": {
            "logical_paths": len(paths), "physical_files": len(physical),
            "unique_contents": len(objects),
            "physical_bytes": sum(rows[0]["signature"]["size"] for rows in physical.values()),
            "unique_bytes": sum(row["size"] for row in objects.values()),
        },
    }
    save(args.output, plan)
    print(json.dumps({"plan": str(args.output), **plan["summary"], "shards": len(jobs)}))


def crc64():
    import crcmod
    return crcmod.Crc(0x142F0E1EBA9EA3693, initCrc=0,
                      xorOut=0xFFFFFFFFFFFFFFFF, rev=True)


class MultipartSink:
    """Bounded RAM, parallel parts, and content-checked replay after interruption."""

    def __init__(self, client, bucket, key, state, checkpoint, part_size, workers):
        self.client, self.bucket, self.key = client, bucket, key
        self.state, self.checkpoint = state, checkpoint
        self.part_size, self.workers = part_size, workers
        self.buffer = bytearray()
        self.pending = deque()
        self.pool = ThreadPoolExecutor(workers)
        self.sha = hashlib.sha256()
        self.crc = crc64()
        self.size = self.number = 0
        self.remote = {}
        marker = 0
        while True:
            response = client.list_parts(Bucket=bucket, Key=key,
                                         UploadId=state["upload_id"],
                                         PartNumberMarker=marker)
            for part in response.get("Part", []):
                self.remote[int(part["PartNumber"])] = part
            if str(response.get("IsTruncated", "false")).lower() != "true":
                break
            next_marker = int(response["NextPartNumberMarker"])
            if next_marker <= marker:
                raise ValueError("COS part pagination did not advance")
            marker = next_marker

    def _send(self, number, data):
        sha = hashlib.sha256(data).hexdigest()
        previous = self.state["parts"].get(str(number))
        remote = self.remote.get(number)
        if (previous and remote and previous["sha256"] == sha
                and int(remote["Size"]) == len(data)
                and remote["ETag"] == previous["ETag"]):
            return number, previous
        result = self.client.upload_part(
            Bucket=self.bucket, Key=self.key, UploadId=self.state["upload_id"],
            PartNumber=number, Body=data, EnableMD5=True,
        )
        local = crc64()
        local.update(data)
        if str(local.crcValue) != str(result.get("x-cos-hash-crc64ecma")):
            raise ValueError(f"part CRC64 mismatch: {number}")
        return number, {"ETag": result["ETag"], "sha256": sha, "size": len(data)}

    def _collect(self):
        number, result = self.pending.popleft().result()
        self.state["parts"][str(number)] = result
        save(self.checkpoint, self.state)
        print(json.dumps({"key": self.key, "part": number,
                          "bytes": result["size"]}), flush=True)

    def _submit(self, data):
        if len(self.pending) >= self.workers:
            self._collect()
        self.number += 1
        if self.number > 10000:
            raise ValueError("COS part limit reached; increase --part-mib")
        self.pending.append(self.pool.submit(self._send, self.number, data))

    def write(self, data):
        self.sha.update(data)
        self.crc.update(data)
        self.size += len(data)
        view = memoryview(data)
        while view:
            count = min(self.part_size - len(self.buffer), len(view))
            self.buffer.extend(view[:count])
            view = view[count:]
            if len(self.buffer) == self.part_size:
                self._submit(bytes(self.buffer))
                self.buffer.clear()
        return len(data)

    def finish(self):
        if self.buffer:
            self._submit(bytes(self.buffer))
            self.buffer.clear()
        while self.pending:
            self._collect()
        return {"size": self.size, "sha256": self.sha.hexdigest(),
                "crc64": str(self.crc.crcValue), "part_count": self.number}

    def close(self):
        self.pool.shutdown(wait=True)


def check_sources(job):
    for item in job["files"]:
        for source in item["sources"]:
            if signature(source["path"]) != source["signature"]:
                raise ValueError(f"source changed since planning: {source['path']}")


def write_archive(job, sink, level):
    import zstandard
    with (
        zstandard.ZstdCompressor(level=level, threads=4).stream_writer(
            sink, closefd=False
        ) as compressed,
        tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive,
    ):
        content = encoded(job)
        info = tarfile.TarInfo(".backup/index.json")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
        for item in job["files"]:
            source = item["sources"][0]
            info = tarfile.TarInfo("files/" + item["sha256"])
            info.size = item["size"]
            with Path(source["path"]).open("rb") as stream:
                reader = HashingReader(stream)
                archive.addfile(info, reader)
                if reader.sha.hexdigest() != item["sha256"]:
                    raise ValueError(f"content changed since planning: {source['path']}")


class HashingReader:
    def __init__(self, stream):
        self.stream, self.sha = stream, hashlib.sha256()

    def read(self, size=-1):
        data = self.stream.read(size)
        self.sha.update(data)
        return data


def remote_head(client, bucket, key):
    from qcloud_cos.cos_exception import CosServiceError
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except CosServiceError as exc:
        if exc.get_status_code() == 404:
            return None
        raise


def verify_head(head, record, plan_sha):
    head = {k.lower(): v for k, v in head.items()}
    if (int(head["content-length"]) != record["size"]
            or str(head.get("x-cos-hash-crc64ecma")) != record["crc64"]
            or head.get("x-cos-meta-plan-sha256") != plan_sha):
        raise ValueError("COS object size, CRC64, or plan identity mismatch")


def upload_job(client, bucket, key, job, plan_sha, checkpoint, args):
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    identity = {"bucket": bucket, "key": key, "plan_sha256": plan_sha}
    if state and any(state.get(k) != v for k, v in identity.items()):
        raise ValueError("checkpoint belongs to a different upload")
    head = remote_head(client, bucket, key)
    if head is not None:
        if not state.get("object"):
            raise ValueError(f"existing object has no local verification receipt: {key}")
        verify_head(head, state["object"], plan_sha)
    else:
        check_sources(job)
        if not state.get("upload_id"):
            result = client.create_multipart_upload(
                Bucket=bucket, Key=key, ACL="private",
                Metadata={"x-cos-meta-plan-sha256": plan_sha},
                ContentType="application/octet-stream", StorageClass="STANDARD",
            )
            state = {**identity, "upload_id": result["UploadId"], "parts": {}}
            save(checkpoint, state)
        sink = MultipartSink(client, bucket, key, state, checkpoint,
                             args.part_mib * 1024 * 1024, args.workers)
        try:
            if job["format"] == "raw":
                item = job["files"][0]
                with Path(item["sources"][0]["path"]).open("rb") as stream:
                    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                        sink.write(block)
                if sink.sha.hexdigest() != item["sha256"]:
                    raise ValueError("archive changed since planning")
            else:
                write_archive(job, sink, args.compression_level)
            state["object"] = sink.finish()
            check_sources(job)
            save(checkpoint, state)  # Recover if completion succeeds but receipt write stops.
            client.complete_multipart_upload(
                Bucket=bucket, Key=key, UploadId=state["upload_id"],
                MultipartUpload={"Part": [
                    {"PartNumber": n, "ETag": state["parts"][str(n)]["ETag"]}
                    for n in range(1, sink.number + 1)
                ]},
            )
        finally:
            sink.close()
        head = remote_head(client, bucket, key)
        if head is None:
            raise ValueError("completed COS object is missing")
        verify_head(head, state["object"], plan_sha)
    state["status"] = "verified"
    save(checkpoint, state)
    return state


def upload(args):
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosClientError, CosServiceError
    plan = json.loads(args.plan.read_text())
    plan_sha = hashlib.sha256(encoded(plan)).hexdigest()
    args.compression_level = plan["compression_level"]
    client = CosS3Client(CosConfig(
        Region=args.region, SecretId=os.environ["COS_SecretID"],
        SecretKey=os.environ["COS_SecretKey"], Token=os.environ.get("COS_Token"),
        Scheme="https", VerifySSL=True, AutoSwitchDomainOnRetry=False, Timeout=60,
    ))
    work = args.plan.parent / "upload"
    work.mkdir(exist_ok=True)
    try:
        with (work / "upload.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            records = []
            for number, original in enumerate(plan["jobs"]):
                job = {**original, "roots": plan["roots"], "datasets": plan["datasets"],
                       "shard_number": number, "shard_count": len(plan["jobs"])}
                suffix = "bin" if original["format"] == "raw" else "tar.zst"
                key = f"{args.prefix.rstrip('/')}/{plan_sha}/shard-{number:05d}.{suffix}"
                record = upload_job(client, args.bucket, key, job, plan_sha,
                                    work / f"shard-{number:05d}.json", args)
                records.append(record)
                print(json.dumps({"key": key, "status": record["status"],
                                  **record["object"]}), flush=True)
            complete = {"plan_sha256": plan_sha, "status": "verified",
                        "summary": plan["summary"], "roots": plan["roots"],
                        "datasets": plan["datasets"], "shards": [
                            {"key": record["key"], **record["object"], **job}
                            for record, job in zip(records, plan["jobs"])
                        ]}
            content = encoded(complete)
            checksum = crc64()
            checksum.update(content)
            facts = {"size": len(content), "crc64": str(checksum.crcValue)}
            key = f"{args.prefix.rstrip('/')}/{plan_sha}/complete.json"
            head = remote_head(client, args.bucket, key)
            if head is None:
                client.put_object(Bucket=args.bucket, Key=key, Body=content,
                                  ACL="private", EnableMD5=True,
                                  Metadata={"x-cos-meta-plan-sha256": plan_sha},
                                  ContentType="application/json")
                head = remote_head(client, args.bucket, key)
            verify_head(head, facts, plan_sha)
            save(work / "complete.json", complete)
    except (CosClientError, CosServiceError) as exc:
        # SDK errors can include signed URLs; log only diagnostic codes.
        print(json.dumps({"error": type(exc).__name__,
                          "status": exc.get_status_code() if isinstance(exc, CosServiceError) else None,
                          "code": exc.get_error_code() if isinstance(exc, CosServiceError) else None}), flush=True)
        raise SystemExit(1) from None
    finally:
        client._session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--catalog", type=Path, default=Path("catalog"))
    plan.add_argument("--roots", type=Path, default=Path("roots.json"))
    plan.add_argument("--dataset", action="append", default=[])
    plan.add_argument("--include-file", type=Path, action="append", default=[])
    plan.add_argument("--include-repository", action="store_true")
    plan.add_argument("--source-root", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--shard-bytes", type=int, default=4 * 1024**3)
    plan.add_argument("--compression-level", type=int, default=3)
    transfer = commands.add_parser("upload")
    transfer.add_argument("plan", type=Path)
    transfer.add_argument("--bucket", required=True)
    transfer.add_argument("--region", default="ap-guangzhou")
    transfer.add_argument("--prefix", required=True)
    transfer.add_argument("--part-mib", type=int, default=32)
    for command in (plan, transfer):
        command.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.command == "plan":
        if args.shard_bytes < 1:
            parser.error("--shard-bytes must be positive")
        build_plan(args)
    else:
        if not 1 <= args.part_mib <= 5120:
            parser.error("--part-mib must be between 1 and 5120")
        upload(args)


if __name__ == "__main__":
    main()
