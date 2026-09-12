#!/usr/bin/env python3
"""Extract the five pinned speaker corpora and measure original audio headers."""

import argparse
import fcntl
import hashlib
import json
import shutil
import subprocess
import tarfile
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import soundfile as sf

VERSION = "speaker-records-v1-20260912"
DATASETS = ("cnceleb1", "cnceleb2", "3dspeaker", "hi_mia", "chime6")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def paths(root, dataset):
    return (root / dataset / "work" / VERSION,
            root / dataset / "views" / "speaker" / VERSION)


def source_spec(repo, dataset):
    rows = [json.loads(line) for line in
            (repo / "catalog" / (dataset + ".jsonl")).read_text().splitlines()]
    return next(row for row in rows if row["version"] != VERSION)


def archive_groups(source):
    parts = [a for a in source["artifacts"] if a["kind"] == "source-archive-part"]
    result = []
    if parts:
        result.append(("audio_archive", sorted(parts, key=lambda a: a["relative_path"])))
    for artifact in source["artifacts"]:
        if artifact["kind"] not in {"source-archive", "repaired-source-archive"}:
            continue
        if source["dataset_id"] == "chime6" and artifact["name"] == "transcriptions_archive":
            continue
        result.append((artifact["name"], [artifact]))
    # Small annotations first, allowing inspection while large audio is extracted.
    return sorted(result, key=lambda group: sum(a["expected_bytes"] for a in group[1]))


def extract_archive(root, work, name, artifacts):
    receipt = work / "inventories" / (name + ".complete.json")
    inventory = work / "inventories" / (name + ".jsonl")
    inputs = [{k: a[k] for k in ("relative_path", "expected_bytes", "sha256")}
              for a in artifacts]
    for item in inputs:
        source = root / item["relative_path"]
        if source.stat().st_size != item["expected_bytes"]:
            raise ValueError(f"source archive size changed: {item['relative_path']}")
        if sha256(source) != item["sha256"]:
            raise ValueError(f"source archive sha256 changed: {item['relative_path']}")
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        if previous["inputs"] != inputs or sha256(inventory) != previous["inventory_sha256"]:
            raise ValueError(f"completed extraction inventory changed: {name}")
        return previous
    destination = work / "extracted" / name
    if not destination.resolve().is_relative_to(work.resolve()):
        raise ValueError(f"extraction destination escapes work directory: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    inventory.parent.mkdir(parents=True, exist_ok=True)
    files = audio_files = extracted_bytes = 0
    previous_report = time.monotonic()
    process = None
    with ExitStack() as stack:
        if len(inputs) == 1:
            compressed = stack.enter_context((root / inputs[0]["relative_path"]).open("rb"))
        else:
            process = stack.enter_context(subprocess.Popen(
                ["cat", *[str(root / a["relative_path"]) for a in inputs]],
                stdout=subprocess.PIPE,
            ))
            compressed = stack.enter_context(process.stdout)
        archive = stack.enter_context(tarfile.open(fileobj=compressed, mode="r|gz"))
        output = stack.enter_context(inventory.open("w"))
        for member in archive:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in member.name:
                raise ValueError(f"unsafe archive path: {member.name}")
            path = destination.joinpath(*relative.parts)
            if not path.resolve().is_relative_to(destination.resolve()):
                raise ValueError(f"archive path escapes extraction directory: {member.name}")
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.is_symlink():
                    raise ValueError(f"unexpected symlink in work directory: {path}")
                with archive.extractfile(member) as source, path.open("wb") as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
                if path.stat().st_size != member.size:
                    raise ValueError(f"incomplete extraction: {member.name}")
                item = {"archive": name, "member": member.name, "bytes": member.size,
                        "path": path.relative_to(work).as_posix()}
                if path.suffix.lower() in {".wav", ".flac"}:
                    info = sf.info(path)
                    if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
                        raise ValueError(f"invalid audio header: {path}")
                    item.update(sample_rate=info.samplerate, channels=info.channels,
                                num_frames=info.frames, duration=info.frames / info.samplerate)
                    audio_files += 1
                output.write(json.dumps(item, ensure_ascii=False) + "\n")
                files += 1
                extracted_bytes += member.size
            else:
                raise ValueError(f"unsupported archive member: {member.name} {member.type}")
            # Streaming tarfile otherwise retains a TarInfo for every audio file.
            archive.members.clear()
            if time.monotonic() - previous_report >= 30:
                print(json.dumps({"archive": name, "files": files, "audio_files": audio_files,
                                  "extracted_bytes": extracted_bytes}), flush=True)
                previous_report = time.monotonic()
    if process is not None and process.wait() != 0:
        raise RuntimeError("failed to read concatenated CN-Celeb2 parts")
    result = {"inputs": inputs, "files": files, "audio_files": audio_files,
              "extracted_bytes": extracted_bytes, "inventory_sha256": sha256(inventory)}
    save(receipt, result)
    print("extracted", name, files, "files", audio_files, "audio", flush=True)
    return result


def extract_dataset(repo, root, dataset):
    work, final = paths(root, dataset)
    if final.exists():
        raise FileExistsError(f"immutable prepared version already exists: {final}")
    work.mkdir(parents=True, exist_ok=True)
    with (work / "extract.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = source_spec(repo, dataset)
        state = {"schema_version": "dataset-state/1.0", "dataset_id": dataset,
                 "version": VERSION, "state": "partial", "metadata": {"phase": "extracting"}}
        save(work / "state.json", state)
        results = {}
        try:
            for name, artifacts in archive_groups(source):
                results[name] = extract_archive(root, work, name, artifacts)
            state.update(state="extracted", updated_at=datetime.now(timezone.utc).isoformat())
            state["metadata"].update(phase="audio_headers_measured", archives=results)
            save(work / "state.json", state)
        except Exception as error:
            state.update(state="failed", error=str(error))
            save(work / "state.json", state)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--roots", type=Path, required=True)
    args = parser.parse_args()
    root = Path(json.loads(args.roots.read_text())["legacy_asr"])
    extract_dataset(args.repo, root, args.dataset)


if __name__ == "__main__":
    main()
