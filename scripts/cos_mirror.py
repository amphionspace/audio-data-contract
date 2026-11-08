#!/usr/bin/env python3
"""Keep a COS copy of every registered data directory, and record what is verified.

  plan   (audio-data-contract env): registered directories -> plan.json
  push   (AmphionBucket venv):      compare each directory with COS by path and
         size, upload what is missing with ab's own push_one (never overwrites),
         then write the ledger of verified directories and dataset versions.
  unpack (AmphionBucket venv):      stream a directory's tar shards back from COS
         and extract them (the counterpart of the packing below).

COS keys mirror paths under the data root, e.g. /workspace/data/datasets/x/a.wav
-> <prefix>datasets/x/a.wav. Registered versions are immutable, so a file that
already exists with the same size is not read again; ab compares content only
when it uploads. Nothing on COS is deleted or overwritten.

Files smaller than --pack-below are not uploaded one by one (millions of tiny
requests): the missing ones are streamed into tar shards of about --shard-size
and uploaded as a COS multipart upload, cut into --part-size parts held in
memory. Nothing is staged on disk. A shard <dest minus "/">.packed/<id>.tar is
listed by <id>.json.gz (member keys and sizes), which is written after the
tar is complete; a member counts as present when an index lists it. To restore,
read the index, then extract the tar (tar x) into the directory.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ----------------------------------------------------------------------- plan


def plan(args):
    from ruamel.yaml import YAML

    from audio_data_contract import load_catalog
    from audio_data_contract.errors import ContractError
    from audio_data_contract.roots import load_roots, resolve_root_path
    from audio_data_contract.storage_audit import load_zones

    data_root = os.path.normpath(args.data_root)
    config = YAML(typ="safe").load(Path(args.zones).read_text(encoding="utf-8"))["catalog"]
    units = sorted(set(load_zones(args.zones).units) | {os.path.normpath(p) for p in args.include})
    top = outermost(u for u in units if u.startswith(data_root + "/"))

    def owner(path):
        return next((u for u in top if path == u or path.startswith(u + "/")), None)

    shared = [Path(p).parts for p in config.get("shared_patterns", [])]
    roots = load_roots(config.get("roots"))
    datasets = {}
    for spec in load_catalog(config["path"]):
        claimed = set()
        for artifact in spec.artifacts:
            try:
                path = str(resolve_root_path(artifact.root_alias, artifact.relative_path, roots, spec.key))
            except ContractError:
                continue
            unit = owner(path)
            if unit is None:
                continue
            claimed.add(unit)
            for pattern in shared:  # e.g. datasets/<id>/source, read by the version's records
                parts = Path(unit).parts
                if len(parts) >= len(pattern) - 1:
                    sibling = owner(str(Path(*parts[: len(pattern) - 1], pattern[-1])))
                    if sibling:
                        claimed.add(sibling)
        if claimed:
            datasets[spec.key] = sorted(os.path.relpath(u, data_root) for u in claimed)
    known = {}
    for ledger in args.known:
        record = json.loads(Path(ledger).read_text(encoding="utf-8"))
        for name, entry in record.get("directories", {}).items():
            if "only" not in entry:  # a whole directory already mirrored under another name
                known[os.path.relpath(os.path.normpath(entry["local"]), data_root)] = (
                    record["prefix"] + name + "/")
    result = {
        "data_root": data_root,
        "units": [os.path.relpath(u, data_root) for u in top],
        "known": known,
        "datasets": datasets,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(top)} directories, {len(datasets)} versions", flush=True)


def outermost(paths):
    """Drop paths inside another path of the set."""
    top = []
    # Sort by component so a parent comes right before its children ("a" < "a/b" < "a-b").
    for path in sorted(paths, key=lambda item: item.split("/")):
        if not (top and path.startswith(top[-1] + "/")):
            top.append(path)
    return top


# ----------------------------------------------------------------------- push


# ab's own resume directories next to downloaded files (amphion_bucket.config.is_state_name).
STATE_NAME = re.compile(r"\.amphion-bucket-[0-9a-f]{32}")


def local_files(root, skipped):
    """(relative key, size, path) under root, in COS key order (code point order)."""

    def walk(directory, prefix):
        entries = []
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_symlink():
                    skipped.append(entry.path)
                elif entry.is_dir():
                    if not STATE_NAME.fullmatch(entry.name):
                        entries.append((entry.name + "/", entry))
                elif entry.is_file():
                    entries.append((entry.name, entry))
        entries.sort(key=lambda item: item[0])
        for name, entry in entries:
            if name.endswith("/"):
                yield from walk(entry.path, prefix + name)
            else:
                yield prefix + name, entry.stat(follow_symlinks=False).st_size, entry.path

    yield from walk(root, "")


def remote_files(backend, prefix):
    """(relative key, size) under prefix, in key order."""
    marker = ""
    while True:
        response = backend.client.list_objects(
            Bucket=backend.remote.bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        for item in response.get("Contents", []):
            if not item["Key"].endswith("/"):
                yield item["Key"][len(prefix):], int(item["Size"])
        if str(response.get("IsTruncated", "false")).lower() != "true":
            return
        marker = response["NextMarker"]


def merge(local, remote):
    """Yield (key, size, path, remote size or None) for local files, and extra remote keys."""
    remote = iter(remote)
    other = next(remote, None)
    for key, size, path in local:
        while other is not None and other[0] < key:
            yield other[0], None, None, other[1]
            other = next(remote, None)
        if other is not None and other[0] == key:
            yield key, size, path, other[1]
            other = next(remote, None)
        else:
            yield key, size, path, None
    while other is not None:
        yield other[0], None, None, other[1]
        other = next(remote, None)


# -------------------------------------------------------------------- packing


def packed_prefix(dest):
    """COS directory of the tar shards of a mirrored directory (a sibling of it)."""
    return dest.rstrip("/") + ".packed/"


def load_packed(backend, dest):
    """{key relative to dest: size} of every file already inside a shard."""
    prefix, members, marker = packed_prefix(dest), {}, ""
    while True:
        response = backend.client.list_objects(
            Bucket=backend.remote.bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        for item in response.get("Contents", []):
            if item["Key"].endswith(".json.gz"):
                body = backend.client.get_object(Bucket=backend.remote.bucket, Key=item["Key"])
                index = json.loads(gzip.decompress(body["Body"].get_raw_stream().read()))
                members.update((key, size) for key, size in index["members"])
        if str(response.get("IsTruncated", "false")).lower() != "true":
            return members
        marker = response["NextMarker"]


class PartWriter(io.RawIOBase):
    """Write-only file that uploads what is written as a COS multipart upload.

    Data is kept in memory in parts of part_size; at most `inflight` parts are
    held or uploading at once. finish() completes the object and checks its size.
    """

    def __init__(self, mirror, key):
        self.mirror, self.key = mirror, key
        self.backend = mirror.backend()
        self.bucket = self.backend.remote.bucket
        self.upload_id = self.backend.client.create_multipart_upload(
            Bucket=self.bucket, Key=key)["UploadId"]
        self.buffer, self.size, self.parts = bytearray(), 0, []
        self.inflight = threading.BoundedSemaphore(mirror.args.part_inflight)

    def writable(self):
        return True

    def write(self, data):
        self.buffer += data
        self.size += len(data)
        while len(self.buffer) >= self.mirror.args.part_size:
            self.send(self.mirror.args.part_size)
        return len(data)

    def send(self, length):
        body = bytes(self.buffer[:length])
        del self.buffer[:length]
        number = len(self.parts) + 1
        self.inflight.acquire()
        future = self.mirror.parts.submit(self.upload_part, number, body)
        future.add_done_callback(lambda _: self.inflight.release())
        self.parts.append(future)

    def upload_part(self, number, body):
        for attempt in range(3):
            try:
                response = self.mirror.backend().client.upload_part(
                    Bucket=self.bucket, Key=self.key, Body=body, PartNumber=number,
                    UploadId=self.upload_id, EnableMD5=True)
                return {"PartNumber": number, "ETag": response["ETag"]}
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))

    def finish(self):
        if self.buffer or not self.parts:
            self.send(len(self.buffer))
        done = [future.result() for future in self.parts]
        self.backend.client.complete_multipart_upload(
            Bucket=self.bucket, Key=self.key, UploadId=self.upload_id,
            MultipartUpload={"Part": done})
        info = self.backend.head(self.key)
        if info is None or info.size != self.size:
            raise RuntimeError(f"{self.key}: COS size {info and info.size} != written {self.size}")

    def abort(self):
        for future in self.parts:
            future.cancel()
        try:
            self.backend.client.abort_multipart_upload(
                Bucket=self.bucket, Key=self.key, UploadId=self.upload_id)
        except Exception as exc:  # noqa: BLE001 - the shard already failed; do not mask that
            print(f"could not abort multipart upload {self.key} ({self.upload_id}): {exc}",
                  file=sys.stderr, flush=True)


def shard_name(dest, first):
    return f"{packed_prefix(dest)}{hashlib.sha1(first.encode()).hexdigest()[:12]}"


def connect(args):
    from amphion_bucket.cli import make_backend
    from amphion_bucket.config import load_remotes

    return make_backend(load_remotes()[args.bucket])


def unpack_shards(backend, dest, target, workers=8, only=()):
    """Stream every tar shard of a mirrored directory into target; return (files, errors).

    Nothing is staged on disk: each shard is read from COS as a stream and
    extracted member by member. Files already in target with the right size are
    skipped; every member is checked against the shard's index.
    """
    bucket = backend.remote.bucket
    prefix, indexes, marker = packed_prefix(dest), [], ""
    while True:
        response = backend.client.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        indexes += [i["Key"] for i in response.get("Contents", []) if i["Key"].endswith(".json.gz")]
        if str(response.get("IsTruncated", "false")).lower() != "true":
            break
        marker = response["NextMarker"]
    target = os.path.abspath(target)

    def one(index_key):
        body = backend.client.get_object(Bucket=bucket, Key=index_key)["Body"].get_raw_stream()
        index = json.loads(gzip.decompress(body.read()))
        wanted = {key: size for key, size in index["members"]
                  if not only or any(key.startswith(sub) for sub in only)}
        if not wanted:
            return 0, None
        stream = backend.client.get_object(
            Bucket=bucket, Key=index_key.rsplit("/", 1)[0] + "/" + index["tar"])["Body"].get_raw_stream()
        got = 0
        try:
            with tarfile.open(fileobj=stream, mode="r|") as tar:
                for member in tar:
                    if member.name not in wanted:
                        continue
                    if member.size != wanted[member.name]:
                        raise RuntimeError(f"{member.name}: size {member.size} != index {wanted[member.name]}")
                    path = os.path.join(target, member.name)
                    if not (os.path.isfile(path) and os.path.getsize(path) == member.size):
                        # tarfile creates parents without exist_ok: shards racing in one directory fail
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        tar.extract(member, target, filter="data")
                    got += 1
        except Exception as exc:  # noqa: BLE001 - report the shard, keep the others going
            return got, f"{index['tar']}: {type(exc).__name__}: {exc}"
        if got != len(wanted):
            return got, f"{index['tar']}: {got} of {len(wanted)} indexed files found"
        return got, None

    files, errors = 0, []
    with ThreadPoolExecutor(workers) as pool:
        for got, error in pool.map(one, sorted(indexes)):
            files += got
            if error:
                errors.append(error)
    return files, errors


class Mirror:
    def __init__(self, args):
        from amphion_bucket import transfer
        from amphion_bucket.cli import make_backend
        from amphion_bucket.config import load_remotes

        class Quiet:  # ab prints two progress lines per file; keep the log readable
            def __init__(self, label, size):
                pass

            def __call__(self, *unused):
                pass

            def done(self):
                pass

        transfer.Progress = Quiet
        self.args = args
        self.remote = load_remotes()[args.bucket]
        self.make_backend = make_backend
        self.local = threading.local()
        self.slots = threading.BoundedSemaphore(args.workers * 8)  # queued uploads
        self.lock = threading.Lock()
        self.uploaded = self.bytes = 0
        self.parts = ThreadPoolExecutor(args.part_workers)  # multipart parts of all shards
        self.shards = ThreadPoolExecutor(args.packers)
        self.shard_slots = threading.BoundedSemaphore(args.packers * 2)  # queued shards

    def backend(self):
        if not hasattr(self.local, "backend"):
            self.local.backend = self.make_backend(self.remote)
        return self.local.backend

    def push(self, path, key):
        """Upload one file with ab's conflict policy; drop its spent resume lock."""
        from amphion_bucket.config import Conflict
        from amphion_bucket.transfer import digest_id, push_one, state_root

        backend = self.backend()
        for attempt in range(2):
            try:
                action = push_one(backend, path, key)
            except Conflict as exc:
                return "conflict", str(exc)
            except Exception as exc:  # noqa: BLE001 - network errors: retry once, then report
                if attempt:
                    return "failed", f"{type(exc).__name__}: {exc}"
                time.sleep(5)
                continue
            location = state_root() / digest_id([backend.remote.identity, key, str(path)])
            try:  # push_one keeps an empty lock directory per file; nothing to resume
                (location / "lock").unlink()
                location.rmdir()
            except OSError:
                pass
            return ("same" if action == "相同，跳过" else "uploaded"), None

    def pack_shard(self, dest, members):
        """Stream files into one tar shard on COS; return (bytes sent, error or None)."""
        name = shard_name(dest, members[0][0])
        writer = PartWriter(self, name + ".tar")
        try:
            with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for key, size, path in members:
                    info = tar.gettarinfo(path, arcname=key)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    if info.size != size:
                        raise RuntimeError(f"{path} changed size while scanning")
                    with open(path, "rb") as handle:
                        tar.addfile(info, handle)
            writer.finish()
        except Exception as exc:  # noqa: BLE001 - one bad shard is reported, not fatal
            writer.abort()
            return 0, f"{name}.tar: {type(exc).__name__}: {exc}"
        # The index goes last: a tar without one is not trusted and is packed again.
        index = gzip.compress(json.dumps(
            {"tar": name.rsplit("/", 1)[1] + ".tar", "size": writer.size,
             "members": [[key, size] for key, size, _ in members]},
            ensure_ascii=False).encode())
        try:
            self.backend().client.put_object(
                Bucket=self.remote.bucket, Body=index, Key=name + ".json.gz", EnableMD5=True)
        except Exception as exc:  # noqa: BLE001
            return 0, f"{name}.json.gz: {type(exc).__name__}: {exc}"
        return writer.size, None

    def unit(self, rel, dest, only):
        """Compare one directory with COS; upload missing files; return its summary."""
        root = os.path.join(self.args.data_root, rel)
        counts = {"files": 0, "bytes": 0, "present": 0, "uploaded": 0, "same": 0,
                  "extra": 0, "conflict": 0, "failed": 0}
        errors, skipped = [], []
        pending = [0]
        done = threading.Condition()

        def finish(future, size):
            status, error = future.result()
            self.slots.release()
            with done:
                counts[status] += 1
                if error and len(errors) < 20:
                    errors.append(error)
                if status == "uploaded":
                    with self.lock:
                        self.uploaded += 1
                        self.bytes += size
                pending[0] -= 1
                done.notify_all()

        def finish_shard(future, members):
            sent, error = future.result()
            self.shard_slots.release()
            with done:
                if error:
                    counts["failed"] += len(members)
                    if len(errors) < 20:
                        errors.append(error)
                else:
                    counts["packed"] += len(members)
                    counts["shards"] += 1
                    with self.lock:
                        self.uploaded += len(members)
                        self.bytes += sent
                pending[0] -= 1
                done.notify_all()

        def submit_shard(members):
            self.shard_slots.acquire()
            with done:
                pending[0] += 1
            future = self.shards.submit(self.pack_shard, dest, members)
            future.add_done_callback(lambda f, m=members: finish_shard(f, m))

        small = self.args.pack_below
        packed = load_packed(self.backend(), dest) if small else {}
        counts.update(packed=0, shards=0)
        members, member_bytes = [], 0
        prefixes = [f"{dest}{sub}" for sub in only] if only else [dest]
        roots = [os.path.join(root, sub.rstrip("/")) for sub in only] if only else [root]
        for prefix, base in zip(prefixes, roots):
            offset = prefix[len(dest):]  # shard members are named relative to dest
            pairs = merge(local_files(base, skipped), remote_files(self.backend(), prefix))
            for key, size, path, remote_size in pairs:
                if path is None:
                    counts["extra"] += 1
                    continue
                counts["files"] += 1
                counts["bytes"] += size
                if remote_size == size:
                    counts["present"] += 1
                    continue
                if remote_size is None and size < small:
                    if packed.get(offset + key) == size:
                        counts["present"] += 1
                        continue
                    members.append((offset + key, size, path))
                    member_bytes += size
                    if member_bytes >= self.args.shard_size:
                        submit_shard(members)
                        members, member_bytes = [], 0
                    continue
                self.slots.acquire()
                with done:
                    pending[0] += 1
                future = self.pool.submit(self.push, Path(path), prefix + key)
                future.add_done_callback(lambda f, s=size: finish(f, s))
        if members:
            submit_shard(members)
        with done:
            done.wait_for(lambda: not pending[0])
        counts["symlinks"] = len(skipped)
        counts["ok"] = counts["conflict"] == counts["failed"] == 0
        if errors:
            counts["errors"] = errors
        return counts

    def run(self, plan, state):
        args = self.args
        today = time.strftime("%F")  # deploy sets TZ=Asia/Shanghai
        units = plan["units"]
        only = [o.strip("/") for o in args.only]

        def within(path, base):
            return path == base or path.startswith(base + "/")

        if only:  # a whole directory, or part of one
            units = [u for u in units if any(within(u, o) or within(o, u) for o in only)]
        # Unverified directories first, smallest known size first, so new
        # registrations are not stuck behind a large first upload.
        units.sort(key=lambda u: (state.get(u, {}).get("verified") is not None,
                                  state.get(u, {}).get("bytes", 0)))
        self.pool = ThreadPoolExecutor(args.workers)
        stop = threading.Event()

        def report():
            last = (0, 0)
            while not stop.wait(600):
                with self.lock:
                    now = (self.uploaded, self.bytes)
                rate = (now[1] - last[1]) / 600 / 2**20
                print(f"{time.strftime('%F %T')} uploaded {now[0]} files, "
                      f"{now[1] / 2**30:.1f} GiB ({rate:.0f} MiB/s)", flush=True)
                last = now

        threading.Thread(target=report, daemon=True).start()

        def one(rel):
            parts = [] if any(within(rel, o) for o in only) else sorted(
                o[len(rel) + 1:] + "/" for o in only if within(o, rel))
            dest = destination(plan, rel, args.prefix)
            try:
                counts = self.unit(rel, dest, parts)
            except Exception as exc:  # noqa: BLE001 - one bad directory must not stop the rest
                counts = {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}
            with self.lock:
                entry = state.setdefault(rel, {})
                entry["dest"] = dest
                if parts:  # a partial run never marks the whole directory verified
                    entry.setdefault("parts", {})[",".join(parts)] = dict(counts, checked=today)
                else:
                    entry.update(counts, checked=today)
                    if counts["ok"]:
                        entry["verified"] = today
                        entry.setdefault("first_verified", today)
                    else:
                        entry.pop("verified", None)
                save(args.state, state)
                if args.ledger:
                    save(args.ledger, ledger(plan, state, args.bucket, args.prefix))
            print(f"{time.strftime('%F %T')} {'OK ' if counts['ok'] else 'BAD'} {rel} "
                  + json.dumps({k: v for k, v in counts.items() if k != "ok"}, ensure_ascii=False),
                  flush=True)

        with ThreadPoolExecutor(args.scanners) as scanners:
            list(scanners.map(one, units))
        stop.set()
        self.pool.shutdown()
        self.shards.shutdown()
        self.parts.shutdown()


def destination(plan, rel, prefix):
    """COS directory for a local directory; known mirrors keep their own names."""
    for local, dest in plan["known"].items():
        if rel == local or rel.startswith(local + "/"):
            return dest + (rel[len(local) + 1:] + "/" if rel != local else "")
    return f"{prefix}{rel}/"


def save(path, value):
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    tmp.replace(path)


def ledger(plan, state, bucket, prefix):
    """Verified directories, and the versions whose directories are all verified."""
    directories = {rel: {k: state[rel][k] for k in ("dest", "files", "bytes", "verified")}
                   for rel in plan["units"] if state.get(rel, {}).get("verified")}
    datasets = {}
    for key, units in sorted(plan["datasets"].items()):
        if units and all(u in directories for u in units):
            dests = [directories[u]["dest"].removeprefix(prefix) for u in units]
            # One location per dataset directory keeps the overview short:
            # the version's own <...>/<dataset_id>/ when it has one.
            dataset_id = key.split("@", 1)[0]
            parts = next((d.rstrip("/").split("/") for d in dests
                          if dataset_id in d.split("/")), None)
            if parts:
                alias = "/".join(parts[: parts.index(dataset_id) + 1])
            else:
                first = dests[0].split("/")
                alias = "/".join(first[:2]) if first[0] == "datasets" else dests[0].rstrip("/")
            synced = max(state[u]["first_verified"] for u in units)
            datasets[key] = {"alias": alias, "synced": synced}
            if any(not d.startswith(alias + "/") for d in dests):
                datasets[key]["requires"] = sorted(d.rstrip("/") for d in dests)
    return {"bucket": bucket, "prefix": prefix, "data_root": plan["data_root"],
            "directories": directories, "datasets": datasets}


def push(args):
    if args.pack_below <= 0 and not args.allow_small_files:
        print("refusing --pack-below 0: small files must be packed into tar shards, "
              "not uploaded one by one (--allow-small-files overrides)", file=sys.stderr)
        return 2
    plan_data = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    args.data_root = plan_data["data_root"]
    state = json.loads(Path(args.state).read_text()) if Path(args.state).exists() else {}
    Mirror(args).run(plan_data, state)
    bad = [rel for rel, entry in state.items()
           if not entry.get("ok", True)
           or any(not part["ok"] for part in entry.get("parts", {}).values())]
    print(f"{time.strftime('%F %T')} done; {len(bad)} directories with problems", flush=True)
    return 1 if bad else 0


def unpack(args):
    dest = args.dest or f"{args.prefix}{args.rel.strip('/')}/"
    target = args.target or os.path.join(args.data_root, args.rel.strip("/"))
    only = [o if o.endswith("/") else o + "/" for o in args.only]
    files, errors = unpack_shards(connect(args), dest, target, args.workers, only)
    print(f"{time.strftime('%F %T')} unpacked {files} files into {target}; {len(errors)} shard errors",
          flush=True)
    for error in errors[:20]:
        print(f"  {error}", file=sys.stderr)
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="list registered directories")
    p.add_argument("--zones", default="/workspace/data/registry/storage-zones.yaml")
    p.add_argument("--data-root", default="/workspace/data")
    p.add_argument("--include", action="append", default=[],
                   help="extra directory read through registered manifests")
    p.add_argument("--known", action="append", default=[],
                   help="ab ledger whose directories are already mirrored elsewhere")
    p.add_argument("--output", required=True)
    p = sub.add_parser("push", help="upload missing files and write the ledger")
    p.add_argument("plan")
    p.add_argument("--bucket", default="amphion-audio-backup-1373259071")
    p.add_argument("--prefix", default="audio-data-contract/")
    p.add_argument("--state", required=True, help="per-directory results (JSON)")
    p.add_argument("--ledger", help="write the verified-copy ledger here")
    p.add_argument("--only", action="append", default=[],
                   help="limit to these paths under the data root")
    p.add_argument("--workers", type=int, default=128, help="parallel file uploads")
    p.add_argument("--scanners", type=int, default=8, help="directories compared at once")
    p.add_argument("--pack-below", type=int, default=8 * 2**20,
                   help="missing files smaller than this many bytes go into tar shards (0: never)")
    p.add_argument("--shard-size", type=int, default=4 * 2**30, help="bytes of files per tar shard")
    p.add_argument("--part-size", type=int, default=32 * 2**20, help="multipart part size")
    p.add_argument("--part-inflight", type=int, default=4, help="parts held in memory per shard")
    p.add_argument("--packers", type=int, default=16, help="tar shards streamed at once")
    p.add_argument("--part-workers", type=int, default=64, help="parallel part uploads")
    p.add_argument("--allow-small-files", action="store_true",
                   help="with --pack-below 0: upload small files one by one (almost never right)")
    p = sub.add_parser("unpack", help="stream a directory's tar shards from COS and extract them")
    p.add_argument("rel", help="directory under the data root, e.g. datasets/yodas_es/source")
    p.add_argument("--target", help="extract here (default: <data root>/<rel>)")
    p.add_argument("--dest", help="COS directory when it is not <prefix><rel>/ (known mirrors)")
    p.add_argument("--only", action="append", default=[], help="only files under these subdirectories")
    p.add_argument("--data-root", default="/workspace/data")
    p.add_argument("--bucket", default="amphion-audio-backup-1373259071")
    p.add_argument("--prefix", default="audio-data-contract/")
    p.add_argument("--workers", type=int, default=8, help="shards streamed at once")
    args = parser.parse_args(argv)
    if args.command == "plan":
        return plan(args)
    if args.command == "unpack":
        return unpack(args)
    return push(args)


if __name__ == "__main__":
    sys.exit(main())
