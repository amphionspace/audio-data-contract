#!/usr/bin/env python3
"""Put the original evaluation audio of each set under ``<data_root>/source/<name>/``.

The downloads (Hugging Face via hf-mirror, Zenodo for the two archives the HF copy lacks) live in a
staging directory; see ``sources.py`` for what comes from where. Archives are extracted keeping their
member paths; parquet packagings are written out at the SpoofRadar sample path, with each row's label
and notes kept in ``parquet-labels.jsonl.gz``. A finished set gets ``.extracted.json``; rerunning skips it.

    python scripts/speech_deepfake_bench/extract.py --staging /workspace/data/staging/speech_deepfake_bench \
        --roots /workspace/data/registry/roots.json [NAME ...]

Needs ``zip`` on PATH (to join split zips) and pyarrow. The data disk creates only ~150 files a
second in one directory however many writers there are, so files are written by several workers and
sets can be extracted in parallel runs (one name each).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import fnmatch
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import SOURCES, SR

ROOT_ALIAS = "speech_deepfake_bench"
WRITERS = 16


def write_file(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def protocol_ids(data_root, name):
    with (data_root / "source" / "protocols" / SR / f"{name}.csv").open(newline="") as stream:
        return [row["sample_id"] for row in csv.DictReader(stream)]


def extract_parquet(spec, staging, data_root, name, dest):
    import pyarrow.parquet as pq

    wanted = {os.path.basename(sample): sample for sample in protocol_ids(data_root, name)}
    repo = staging / spec["parquet"]
    written, labels = 0, []
    with cf.ThreadPoolExecutor(WRITERS) as pool:
        for path in sorted(glob.glob(str(repo / "data" / "test-*.parquet"))):
            parquet = pq.ParquetFile(path)
            for group in range(parquet.num_row_groups):
                table = parquet.read_row_group(group, columns=["path", "audio", "label", "notes"])
                jobs = []
                for row in table.to_pylist():
                    sample = wanted.get(os.path.basename(row["path"]))
                    if sample is None:
                        continue
                    jobs.append(pool.submit(write_file, dest / sample, row["audio"]["bytes"]))
                    labels.append({"path": sample, "label": row["label"], "notes": row["notes"]})
                    written += 1
                for job in jobs:
                    job.result()
    with gzip.open(dest / "parquet-labels.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in labels:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    if (repo / "protocols").is_dir():
        shutil.copytree(repo / "protocols", dest / "protocols", dirs_exist_ok=True)
    if written != len(wanted):
        raise ValueError(f"{name}: wrote {written} of {len(wanted)} protocol files")
    return written


def single_zip(archive, staging):
    """A zip readable by zipfile: split volumes are joined first (zip -s 0 for .z01..., cat for .001...)."""
    if archive.with_suffix(".z01").exists():
        merged = staging / "merged" / archive.name
        if not merged.exists():
            merged.parent.mkdir(parents=True, exist_ok=True)
            partial = merged.with_suffix(".partial.zip")  # zip wants a .zip output name
            subprocess.run(["zip", "-q", "-s", "0", str(archive), "--out", str(partial)], check=True)
            partial.rename(merged)
        return merged
    if archive.suffix == ".001":
        merged = staging / "merged" / archive.stem
        if not merged.exists():
            merged.parent.mkdir(parents=True, exist_ok=True)
            parts = sorted(glob.glob(str(archive.with_suffix(".*"))))
            with open(str(merged) + ".tmp", "wb") as out:
                for part in parts:
                    with open(part, "rb") as stream:
                        shutil.copyfileobj(stream, out, 1 << 24)
            Path(str(merged) + ".tmp").rename(merged)
        return merged
    return archive


def extract_archives(spec, staging, dest):
    """zipfile with several writer threads (each its own handle); members are overwritten, so a rerun repairs."""
    import threading
    import zipfile

    for archive in spec["archives"]:
        path = single_zip(staging / archive, staging)
        with zipfile.ZipFile(path) as zf:
            names = [i.filename for i in zf.infolist() if not i.is_dir() and (
                not spec.get("include") or any(fnmatch.fnmatch(i.filename, p) for p in spec["include"]))]
        for name in names:
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"unsafe member {name}")
        local = threading.local()

        def copy(name, path=path, local=local):
            if not hasattr(local, "zf"):
                local.zf = zipfile.ZipFile(path)
            write_file(dest / name, local.zf.read(name))

        with cf.ThreadPoolExecutor(WRITERS) as pool:
            for _ in pool.map(copy, names, chunksize=64):
                pass


def extract_tars(spec, staging, dest):
    for pattern in spec["tars"]:
        parts = sorted(glob.glob(str(staging / pattern)))
        if not parts:
            raise FileNotFoundError(pattern)
        cat = subprocess.Popen(["cat", *parts], stdout=subprocess.PIPE, bufsize=1 << 24)
        with tarfile.open(fileobj=cat.stdout, mode="r|gz") as tar, cf.ThreadPoolExecutor(WRITERS) as pool:
            jobs = []
            for member in tar:
                if not member.isfile() or (spec.get("include") and not any(
                        fnmatch.fnmatch(member.name, p) for p in spec["include"])):
                    continue
                if os.path.isabs(member.name) or ".." in member.name.split("/"):
                    raise ValueError(f"unsafe member {member.name}")
                jobs.append(pool.submit(write_file, dest / member.name, tar.extractfile(member).read()))
                if len(jobs) > 4096:
                    for job in jobs:
                        job.result()
                    jobs = []
            for job in jobs:
                job.result()
        if cat.wait():
            raise RuntimeError(f"cat {pattern} failed")


def extract_hf_files(spec, data_root, name, dest):
    """Fetch the protocol's files one by one from an unpacked Hugging Face copy, sha256-checked."""
    import hashlib
    import http.client
    import ssl
    import time
    import urllib.error
    import urllib.request

    endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
    ctx = ssl.create_default_context(cafile="/etc/ssl/certs/ca-certificates.crt")
    # The local proxy (if set) first, a direct connection as the alternate: direct connections to the
    # mirror's addresses come and go on this network.
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    openers = [urllib.request.build_opener(urllib.request.ProxyHandler(p), urllib.request.HTTPSHandler(context=ctx))
               for p in (*([{"https": proxy}] if proxy else []), {})]
    src = spec["hf_files"]

    def get(url, timeout, attempt=0):
        # Short timeouts: a direct connection to one of the mirror's addresses sometimes hangs.
        opener = openers[attempt % len(openers)]
        return opener.open(urllib.request.Request(url, headers={"User-Agent": "curl/8"}), timeout=timeout)

    listing, url = [], f"{endpoint}/api/datasets/{src['repo']}/tree/main/{src['prefix']}{src['path']}?recursive=1"
    while url:
        for attempt in range(20):
            try:
                with get(url, timeout=15, attempt=attempt) as response:
                    page = json.load(response)
                    link = response.headers.get("Link", "")
                break
            except OSError as exc:
                print(f"{name}: listing retry {attempt + 1}: {exc}", flush=True)
                if attempt == 19:
                    raise
                time.sleep(min(30, 2 * (attempt + 1)))
        listing += page
        if len(listing) % 20000 < len(page):
            print(f"{name}: listed {len(listing)}", flush=True)
        url = link.split(";")[0].strip("<> ") if 'rel="next"' in link else None
        if url:  # the mirror sometimes hands out next-page links on huggingface.co itself
            url = url.replace("https://huggingface.co/", endpoint.rstrip("/") + "/", 1)
    hub = {x["path"][len(src["prefix"]):]: x for x in listing if x["type"] == "file"}
    wanted = protocol_ids(data_root, name)
    missing = [s for s in wanted if s not in hub]
    if missing:
        raise ValueError(f"{name}: {len(missing)} protocol files not on the Hub, e.g. {missing[:3]}")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    # The mirror answers a file with a redirect to the Hub's CDN; ask the mirror (proxy first), then
    # fetch the CDN URL directly, which is fast here.
    resolvers = [urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler(p),
                                             urllib.request.HTTPSHandler(context=ctx))
                 for p in (*([{"https": proxy}] if proxy else []), {})]

    def download(sample, attempt):
        url = f"{endpoint}/datasets/{src['repo']}/resolve/main/{src['prefix']}{sample}"
        request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        try:
            with resolvers[attempt % len(resolvers)].open(request, timeout=30) as response:
                return response.read()  # served without a redirect
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            location = exc.headers["Location"]
        with get(location, timeout=60, attempt=len(openers) - 1 - attempt % len(openers)) as response:
            return response.read()

    def fetch(sample):
        entry, target = hub[sample], dest / sample
        digest = (entry.get("lfs") or {}).get("oid")
        if target.exists() and target.stat().st_size == entry["size"]:
            return
        for attempt in range(20):
            try:
                data = download(sample, attempt)
                if len(data) != entry["size"] or (digest and hashlib.sha256(data).hexdigest() != digest):
                    raise OSError(f"{sample}: size or sha256 differs from the Hub")
                write_file(target, data)
                return
            except (OSError, http.client.HTTPException):
                time.sleep(min(60, 3 * (attempt + 1)))
        raise OSError(f"{sample}: gave up")

    with cf.ThreadPoolExecutor(128) as pool:
        for done, _ in enumerate(pool.map(fetch, wanted), 1):
            if done % 10000 == 0:
                print(f"{name}: {done}/{len(wanted)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("names", nargs="*", help="sets to extract (default: all)")
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[ROOT_ALIAS])
    for name in args.names or SOURCES:
        spec = SOURCES[name]
        dest = data_root / "source" / name
        marker = dest / ".extracted.json"
        if marker.exists():
            print(f"{name}: already extracted")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        if "parquet" in spec:
            extract_parquet(spec, args.staging, data_root, name, dest)
        elif "hf_files" in spec:
            extract_hf_files(spec, data_root, name, dest)
        elif "archives" in spec:
            extract_archives(spec, args.staging, dest)
        else:
            extract_tars(spec, args.staging, dest)
        marker.write_text(json.dumps({"origin": spec["origin"]}, ensure_ascii=False, indent=1) + "\n")
        print(f"{name}: extracted", flush=True)


if __name__ == "__main__":
    main()
