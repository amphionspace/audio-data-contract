#!/usr/bin/env python3
"""Download and prepare RealMAN ASR audio (one channel, official splits).

Requires requests, aria2c, 7zz, and the dependencies of
prepare_farfield_manifests.py. Original multi-channel archives are retained.
"""

import argparse
import fcntl
import fnmatch
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

REVISION = "fea47505cae8041f4b652b0954ba61c77d2b6df1"
PATTERNS = (
    "train/ma_speech/*",
    "val/ma_noisy_speech/*",
    "test/ma_noisy_speech/*",
    "transcriptions.trn",
    "dataset_info/*",
    "train/*.csv",
    "val/*.csv",
    "test/*.csv",
)


def download_complete(corpus, row, verified):
    path = corpus / row["path"]
    if (
        not path.is_file()
        or path.stat().st_size != row["size"]
        or path.with_name(path.name + ".aria2").exists()
    ):
        return False
    digest = row.get("lfs", {}).get("oid")
    if digest and row["path"] not in verified:
        actual = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                actual.update(block)
        if actual.hexdigest() != digest:
            return False
        verified.add(row["path"])
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-r", "--root", type=Path, default=Path("/ai_sds_wuzz/DATA_ASR")
    )
    parser.add_argument(
        "-l", "--lhotse-root", type=Path, default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE")
    )
    parser.add_argument("-a", "--aria2", default="aria2c")
    parser.add_argument("-s", "--seven-zip", default="7zz")
    parser.add_argument("--retry-delay", type=int, default=60)
    args = parser.parse_args()
    if args.retry_delay < 1:
        parser.error("--retry-delay must be positive")
    corpus = args.root.resolve() / "RealMAN"
    corpus.mkdir(parents=True, exist_ok=True)
    lock = (corpus / ".download.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = corpus / "preparation_status.json"

    def status(phase, **details):
        state = {"phase": phase, "revision": REVISION, **details}
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(state_path)
        print(json.dumps(state), flush=True)

    try:
        plan_path = corpus / "asr_download.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            if plan["revision"] != REVISION or plan["repo"] != "AISHELL/RealMAN":
                raise RuntimeError(
                    "Existing download plan has a different revision/repository"
                )
            files = plan["files"]
        else:
            while True:
                try:
                    response = requests.get(
                        f"https://huggingface.co/api/datasets/AISHELL/RealMAN/tree/{REVISION}"
                        "?recursive=true&limit=1000",
                        timeout=60,
                    )
                    response.raise_for_status()
                    break
                except requests.RequestException as exc:
                    if (
                        exc.response is not None
                        and 400 <= exc.response.status_code < 500
                        and exc.response.status_code not in (408, 429)
                    ):
                        raise
                    status("retry_wait", stage="listing", error_type=type(exc).__name__)
                    time.sleep(args.retry_delay)
            if response.links.get("next"):
                raise RuntimeError("Repository listing is paginated")
            files = [
                row
                for row in response.json()
                if row["type"] == "file"
                and any(fnmatch.fnmatch(row["path"], pattern) for pattern in PATTERNS)
            ]
            plan_path.write_text(
                json.dumps(
                    {"repo": "AISHELL/RealMAN", "revision": REVISION, "files": files},
                    indent=2,
                )
                + "\n"
            )
        if not files:
            raise RuntimeError("Empty RealMAN download plan")
        status("verifying_downloads", files=len(files))
        verified = set()
        attempt = 0
        retry_pending = set()
        while True:
            pending = []
            for row in files:
                if row["path"] in retry_pending or not download_complete(
                    corpus, row, verified
                ):
                    pending.append(row)
            if not pending:
                break
            attempt += 1
            lines = []
            for row in pending:
                path = corpus / row["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                lines.extend(
                    [
                        f"https://huggingface.co/datasets/AISHELL/RealMAN/resolve/{REVISION}/{row['path']}",
                        f"  dir={path.parent}",
                        f"  out={path.name}",
                    ]
                )
                if row.get("lfs", {}).get("oid"):
                    lines.append("  checksum=sha-256=" + row["lfs"]["oid"])
            url_list = corpus / "asr_urls.txt"
            url_list.write_text("\n".join(lines) + "\n")
            status(
                "downloading", attempt=attempt, pending=len(pending), total=len(files)
            )
            result = subprocess.run(
                [
                    args.aria2,
                    f"--input-file={url_list}",
                    "--continue=true",
                    "--check-integrity=true",
                    "--file-allocation=none",
                    "--auto-file-renaming=false",
                    "--max-concurrent-downloads=8",
                    "--split=8",
                    "--max-connection-per-server=8",
                    "--min-split-size=16M",
                    "--connect-timeout=20",
                    "--timeout=60",
                    "--max-tries=5",
                    "--retry-wait=5",
                    "--summary-interval=60",
                    "--console-log-level=warn",
                    "--download-result=hide",
                    f"--save-session={corpus / 'remaining_downloads.txt'}",
                    "--save-session-interval=60",
                ],
                check=False,
            )
            retry_pending = (
                {row["path"] for row in pending} if result.returncode else set()
            )
            if result.returncode:
                # aria2: network/server/checksum failures are resumable; local
                # configuration, filesystem and process errors require repair.
                if result.returncode not in {
                    1,
                    2,
                    3,
                    5,
                    6,
                    7,
                    8,
                    19,
                    21,
                    22,
                    24,
                    26,
                    29,
                    32,
                }:
                    result.check_returncode()
                status(
                    "retry_wait",
                    attempt=attempt,
                    exit_code=result.returncode,
                    delay_seconds=args.retry_delay,
                )
                time.sleep(args.retry_delay)
        archives = [row for row in files if row["path"].endswith(".rar")]
        for index, row in enumerate(archives, 1):
            archive = corpus / row["path"]
            split = Path(row["path"]).parts[0]
            destination = corpus / "asr_mono" / split
            destination.mkdir(parents=True, exist_ok=True)
            done = archive.with_suffix(".asr-extracted.json")
            if done.exists():
                continue
            status("extracting", archive=row["path"], index=index, total=len(archives))
            subprocess.run(
                [
                    args.seven_zip,
                    "x",
                    str(archive),
                    f"-o{destination}",
                    "-y",
                    "-bsp0",
                    "-bso0",
                    "-r",
                    "-i!*_CH0.flac",
                ],
                check=True,
            )
            done.write_text(
                json.dumps({"revision": REVISION, "archive": row["path"]}) + "\n"
            )
        counts = {
            part: len(list((corpus / "asr_mono" / part).rglob("*_CH0.flac")))
            for part in ("train", "val", "test")
        }
        if not all(counts.values()):
            raise RuntimeError(f"Missing extracted audio: {counts}")
        (corpus / "asr_mono/.complete.json").write_text(
            json.dumps(
                {"revision": REVISION, "archives": len(archives), "counts": counts},
                indent=2,
            )
            + "\n"
        )
        status("preparing_manifests", counts=counts)
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("prepare_farfield_manifests.py")),
                "-d",
                "realman",
                "-r",
                str(args.root),
                "-l",
                str(args.lhotse_root),
            ],
            check=True,
        )
        status(
            "ready",
            counts=counts,
            summary=str(
                args.lhotse_root / "RealMAN/data/manifests/realman_summary.json"
            ),
        )
    except Exception as exc:
        status("failed", error_type=type(exc).__name__, message=str(exc))
        raise


if __name__ == "__main__":
    main()
