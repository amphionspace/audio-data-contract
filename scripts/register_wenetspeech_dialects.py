#!/usr/bin/env python3
"""Register the WenetSpeech Chuan/Wu/Yue lhotse manifests kept under DATA-TTS.

The legacy and icefall catalog versions point at the old multilingual root
(/ai_sds_wuzz/MULTILINGUAL_DATA/zh/). On aidc the same files live under
<root>/DATA-TTS/. This script checks each manifest against its .sha256 sidecar,
rewrites path fields of recordings and cuts manifests (deterministic gzip), and
writes registry declarations with root_alias aidc_data. Supervisions are
registered in place.

No audio is copied or unpacked. WenetSpeech-Yue training audio stays in
part_XX.tar; its file sources become the fixed dd byte-range template read
from each tar's member offsets. Chuan/Wu tar -xOf members become the same
template, because tar -xOf scans every header of a ~24 GB tar per read.

    python scripts/register_wenetspeech_dialects.py --root /workspace/data \
        --output /workspace/data/registry/catalog/wenetspeech_dialects.yaml \
        --record /workspace/data/migration/wenetspeech-dialects-20261011
"""

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import shlex
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cos_relocate import relocate_item

from audio_data_contract.declarations import (
    declaration_files,
    read_declarations,
    write_declarations,
)

LOCAL = "DATA-TTS/"
OUTPUT = "datasets/wenetspeech_dialects/source/data-tts-relocated-20261011/"
OLD = "/ai_sds_wuzz/MULTILINGUAL_DATA/zh/"
YUE_AUDIO = OLD + "WenetSpeech-Yue/audio/"
DATASETS = {"wenetspeech_chuan", "wenetspeech_wu", "wenetspeech_yue", "wenetspeech_yue_all"}
REWRITE = {"lhotse-recordings", "lhotse-cuts"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def check_original(path):
    expected = path.with_name(path.name + ".sha256").read_text().split()[0]
    if sha256(path) != expected:
        raise SystemExit(f"sha256 mismatch against sidecar: {path}")
    return path


def tar_members(archive):
    with tarfile.open(archive, "r:") as stream:
        members = [m for m in stream if m.isfile()]
    index = {m.name: (m.offset_data, m.size) for m in members}
    if len(index) != len(members):
        # tar -xOf prints every copy of a repeated name; one dd range cannot.
        raise SystemExit(f"duplicate member names in {archive}")
    return archive, index


def to_dd(item, index):
    """Turn Yue audio/part_XX/NAME.wav files and Chuan/Wu tar -xOf members into dd ranges."""
    if isinstance(item, list):
        for child in item:
            to_dd(child, index)
    if not isinstance(item, dict):
        return item
    for source in item.get("sources", []):
        if source["type"] == "file" and source["source"].startswith(YUE_AUDIO):
            part, name = source["source"][len(YUE_AUDIO):].split("/")
            archive = f"{OLD}WenetSpeech-Yue/{part}.tar"
        elif source["type"] == "command" and source["source"].startswith("tar -xOf "):
            _, _, archive, name = shlex.split(source["source"])
        else:
            continue
        offset, size = index[archive][name]
        source["type"] = "command"
        source["source"] = shlex.join([
            "dd", f"if={archive}", "iflag=skip_bytes,count_bytes",
            f"skip={offset}", f"count={size}", "status=none"])
    for value in item.values():
        if isinstance(value, (dict, list)):
            to_dd(value, index)
    return item


def rewrite(root, relative, index):
    source = root / LOCAL / relative
    target = root / OUTPUT / relative
    files, members, ranges = set(), set(), set()

    def resolve(value):
        if not value.startswith(OLD):
            raise ValueError(f"unmapped path in {relative}: {value}")
        return str(root / LOCAL / value[len(OLD):])

    def collect(item):
        if isinstance(item, list):
            for child in item:
                collect(child)
        if not isinstance(item, dict):
            return
        for audio in item.get("sources", []):
            tokens = shlex.split(audio["source"])
            if audio["type"] == "file":
                files.add(audio["source"])
            elif tokens[0] == "tar":
                members.add((tokens[2], tokens[3]))
            else:
                ranges.add((tokens[1][3:], int(tokens[3][5:]), int(tokens[4][6:])))
        for value in item.values():
            if isinstance(value, (dict, list)):
                collect(value)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    count = 0
    with gzip.open(source, "rt", encoding="utf-8") as lines, temporary.open("wb") as raw:
        compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
        out = io.TextIOWrapper(compressed, encoding="utf-8")
        for line in lines:
            if line.strip():
                item = relocate_item(to_dd(json.loads(line), index), resolve)
                collect(item)
                out.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                count += 1
        out.flush()
        out.detach()
        compressed.close()
    temporary.replace(target)
    fact = {"path": str(target.relative_to(root)), "bytes": target.stat().st_size,
            "sha256": sha256(target), "records": count}
    return fact, files, members, ranges


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parent.parent / "catalog")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    root = args.root

    specs = [row for path in declaration_files(args.catalog) for _, row in read_declarations(path)
             if row["dataset_id"] in DATASETS]
    artifacts = [a for spec in specs for a in spec["artifacts"]]
    if any(a["root_alias"] != "multilingual" or not a["relative_path"].startswith("zh/") for a in artifacts):
        raise SystemExit("expected multilingual zh/ artifacts only")
    relatives = sorted({a["relative_path"][3:] for a in artifacts})
    rewritten = sorted({a["relative_path"][3:] for a in artifacts if a["kind"] in REWRITE})

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(check_original, [root / LOCAL / r for r in relatives]))
        tars = [archive for pattern in ("WenetSpeech-Yue/part_*.tar", "WenetSpeech-Chuan/audios*/*.tar",
                                        "WenetSpeech-Wu/audios/*.tar")
                for archive in sorted((root / LOCAL).glob(pattern))]
        index = {OLD + str(archive.relative_to(root / LOCAL)): members
                 for archive, members in pool.map(tar_members, tars)}
    print(json.dumps({"checked_manifests": len(relatives), "tars": len(index),
                      "members": sum(map(len, index.values()))}), flush=True)

    facts, files, members, ranges = {}, set(), set(), set()
    for relative in rewritten:
        fact, *refs = rewrite(root, relative, index)
        facts[relative] = fact
        for found, new in zip((files, members, ranges), refs):
            found.update(new)
        print(json.dumps({"rewritten": relative, "records": fact["records"]}), flush=True)

    missing = []
    with ThreadPoolExecutor(64) as pool:
        missing += [p for p, ok in zip(sorted(files), pool.map(os.path.isfile, sorted(files))) if not ok]
        wanted = {}
        for archive, member in members:
            wanted.setdefault(archive, set()).add(member)
        for archive, found in pool.map(tar_members, map(Path, sorted(wanted))):
            missing += [f"{archive}:{m}" for m in sorted(wanted[str(archive)] - found.keys())]
    sizes = {}
    for archive, offset, size in ranges:
        sizes.setdefault(archive, os.path.getsize(archive))
        if offset < 0 or size <= 0 or offset + size > sizes[archive]:
            missing.append(f"{archive}:{offset}+{size}")
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "relocated-manifests.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1) + "\n")
    (args.record / "missing-references.json").write_text(json.dumps(missing, ensure_ascii=False, indent=1) + "\n")
    if missing:
        raise SystemExit(f"{len(missing)} references are missing; see {args.record}")

    output = []
    for spec in specs:
        spec = copy.deepcopy(spec)
        for artifact in spec["artifacts"]:
            relative = artifact["relative_path"][3:]
            path = root / LOCAL / relative
            fact = facts.get(relative) or {"path": LOCAL + relative, "bytes": path.stat().st_size,
                                           "sha256": path.with_name(path.name + ".sha256").read_text().split()[0]}
            artifact["root_alias"] = "aidc_data"
            artifact["relative_path"] = fact["path"]
            artifact["expected_bytes"] = fact["bytes"]
            artifact["sha256"] = fact["sha256"]
        for split in spec.get("splits", {}).values():
            basis = split.get("statistics", {}).get("duration_basis")
            if basis:
                split["statistics"]["duration_basis"] = basis.replace("multilingual:zh/", "aidc_data:" + LOCAL)
        spec.setdefault("provenance", {})["relocated_from"] = "aidc_data:" + LOCAL
        output.append(spec)
    write_declarations(args.output, output)
    summary = {"versions": len(output), "artifacts": len(artifacts), "rewritten_manifests": len(rewritten),
               "files": len(files), "tar_members": len(members), "dd_ranges": len(ranges), "missing": 0}
    (args.record / "verification.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
