#!/usr/bin/env python3
"""Download a pinned language-expansion plan and record per-file verification.

Hugging Face plans require huggingface_hub; HTTP plans require aria2c. Plans and
mutable state live beside the downloaded data, outside the repository. Run one
process per dataset; interrupted runs resume through the verification journal.
"""

import argparse
import fcntl
import gzip
import hashlib
import json
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from audio_data_contract.state import DatasetState, write_state_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("dataset")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--aria2", default="aria2c")
    args = parser.parse_args()
    pause_file = args.plan.parent / "storage-quota-pause.json"
    if pause_file.exists() and json.loads(pause_file.read_text()).get("active", True):
        parser.exit(
            2,
            "Downloads are paused pending storage quota verification. "
            f"See {pause_file}.\n",
        )
    if args.workers < 1:
        parser.error("--workers must be positive")
    plan = json.loads(args.plan.read_text())[args.dataset]
    download_errors = (
        OSError, ValueError, RuntimeError, EOFError,
        subprocess.CalledProcessError, zipfile.BadZipFile,
    )
    if plan.get("repo"):
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import HfHubHTTPError, disable_progress_bars

        download_errors += (HfHubHTTPError,)
        disable_progress_bars()
    destination = Path(plan["destination"])
    destination.mkdir(parents=True, exist_ok=True)
    work = args.plan.parent / args.dataset
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / "download.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    journal = work / "verified.jsonl"
    verified = {}
    journal_text = journal.read_text() if journal.exists() else ""
    for line in journal_text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # A process may have stopped during the last append.
        verified[row["path"]] = row
    files = plan["files"]
    completed = {}
    for row in files:
        path = destination / row["path"]
        previous = verified.get(row["path"])
        if previous and path.is_file() and not Path(str(path) + ".aria2").exists():
            stat = path.stat()
            if (
                stat.st_size == row["size"] == previous["size"]
                and stat.st_mtime_ns == previous["mtime_ns"]
                and previous["algorithm"] == row["algorithm"]
                and previous.get("expected_digest", previous["digest"])
                == row["digest"]
            ):
                completed[row["path"]] = previous
    failures = {}

    def status(state):
        record = DatasetState(
            dataset_id=args.dataset,
            version=plan["version"],
            state=state,
            artifacts={
                "source": {
                    "path": str(destination),
                    "expected_files": len(files),
                    "verified_files": len(completed),
                    "expected_bytes": sum(r["size"] for r in files),
                    "verified_bytes": sum(r["size"] for r in completed.values()),
                }
            },
            metadata={
                "repo": plan.get("repo"),
                "revision": plan.get("revision"),
                "license": plan["license"],
                "scope": plan["scope"],
                "failures": failures,
                "verification_journal": str(journal),
                "integrity_method": (
                    "published file hashes, or archive CRC and expected size "
                    "with a locally recorded digest when no upstream hash is available"
                ),
            },
        )
        write_state_atomic(record, work / "state.json")

    def fetch(row):
        force = False
        for attempt in range(3):
            try:
                if plan.get("repo"):
                    path = Path(hf_hub_download(
                        plan["repo"],
                        row["path"],
                        repo_type="dataset",
                        revision=plan["revision"],
                        local_dir=destination,
                        force_download=force,
                    ))
                else:
                    path = destination / row["path"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    command = [
                        args.aria2, f"--continue={str(not force).lower()}",
                        "--file-allocation=none",
                        "--auto-file-renaming=false", "--max-concurrent-downloads=1",
                        "--split=1", "--max-connection-per-server=1",
                        "--connect-timeout=20", "--timeout=60", "--max-tries=5",
                        "--retry-wait=5", "--console-log-level=warn",
                        "--summary-interval=60", "--download-result=hide",
                        "--dir=" + str(path.parent), "--out=" + path.name,
                    ]
                    if force:
                        command.append("--allow-overwrite=true")
                    if row["digest"]:
                        algorithm = {"sha256": "sha-256"}.get(
                            row["algorithm"], row["algorithm"]
                        )
                        command += ["--check-integrity=true",
                                    f"--checksum={algorithm}={row['digest']}"]
                    subprocess.run(command + [row["url"]], check=True)
                    if Path(str(path) + ".aria2").exists():
                        raise ValueError("Download has an unfinished aria2 control file")
                stat = path.stat()
                if stat.st_size != row["size"]:
                    raise ValueError("Downloaded size differs from pinned metadata")
                # A complete file that fails content checks must be downloaded anew.
                force = True
                digest = hashlib.new(row["algorithm"])
                if plan.get("repo") and row["algorithm"] == "sha1":
                    digest.update(f"blob {stat.st_size}\0".encode())
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                        digest.update(block)
                if row["digest"] and digest.hexdigest() != row["digest"]:
                    raise ValueError("Downloaded hash differs from pinned metadata")
                if not row["digest"]:
                    if path.name.endswith(".zip"):
                        with zipfile.ZipFile(path) as archive:
                            if archive.testzip() is not None:
                                raise ValueError("Archive CRC verification failed")
                    elif path.name.endswith(".gz"):
                        with gzip.open(path, "rb") as archive:
                            while archive.read(8 * 1024 * 1024):
                                pass
                return {
                    "path": row["path"],
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "algorithm": row["algorithm"],
                    "digest": digest.hexdigest(),
                    "expected_digest": row["digest"],
                }
            except download_errors as exc:
                response = getattr(exc, "response", None)
                if response is not None and response.status_code in (401, 403):
                    raise
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))

    status("downloading")
    pending = [row for row in files if row["path"] not in completed]
    print(json.dumps({"dataset": args.dataset, "pending": len(pending)}), flush=True)
    with journal.open("a") as audit, ThreadPoolExecutor(args.workers) as pool:
        if journal_text and not journal_text.endswith("\n"):
            audit.write("\n")  # Separate a truncated append from new records.
            audit.flush()
        futures = {pool.submit(fetch, row): row for row in pending}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
                audit.write(json.dumps(result) + "\n")
                audit.flush()
                completed[row["path"]] = result
            except download_errors as exc:
                response = getattr(exc, "response", None)
                failures[row["path"]] = {
                    "type": type(exc).__name__,
                    "http_status": getattr(response, "status_code", None),
                }
            status("downloading")
            print(
                json.dumps(
                    {"verified": len(completed), "total": len(files),
                     "failures": len(failures), "file": row["path"]}
                ),
                flush=True,
            )
    status("partial" if failures else "verified")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
