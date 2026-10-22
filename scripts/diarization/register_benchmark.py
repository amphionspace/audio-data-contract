"""Freeze and register the six local diarization benchmark slices, without relabeling."""

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import soundfile as sf
from ruamel.yaml import YAML

from audio_data_contract.types import AudioRecord

VERSION = "diarization-benchmark-v1-20261021"
ALIAS = "diarization_benchmark"
DATASETS = {
    "aishell4": ("aishell4", 20, "zh"),
    "alimeeting": ("alimeeting", 20, "zh"),
    "alimeeting_2023test": ("alimeeting", 20, "zh"),
    "ami_near": ("ami", 20, "en"),
    "ramc": ("magicdata_ramc", 43, "zh"),
    "voxconverse": ("voxconverse", 232, "und"),
}


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))



def merged_roots(path, output):
    """Preserve other datasets and reject alias conflicts before copying data."""
    roots = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(roots, dict) or any(
        not isinstance(value, str) for value in roots.values()
    ):
        raise ValueError(f"invalid roots mapping: {path}")
    if ALIAS in roots and roots[ALIAS] != str(output):
        raise ValueError(f"root alias {ALIAS!r} already points to {roots[ALIAS]!r}")
    return {**roots, ALIAS: str(output)}


def write_roots(path, roots):
    """Publish a complete configuration without truncating the existing file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(json.dumps(roots, indent=2) + "\n")
        temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    source, output, repo = (p.resolve() for p in (args.source, args.output, args.repo))
    roots_path = repo / "roots.json"
    roots = merged_roots(roots_path, output)
    if output.exists():
        raise ValueError(f"refusing to overwrite snapshot: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".building-", dir=output.parent))
    rows = [json.loads(line) for line in (source / "test.jsonl").read_text().splitlines()]
    specs, views, all_manifest, warnings = [], [], [], []
    identities = set()
    for group, (dataset, expected, language) in DATASETS.items():
        selected = sorted((r for r in rows if r["dataset"] == group),
                          key=lambda r: r["recording_id"])
        if len(selected) != expected:
            raise ValueError(f"{group}: expected {expected}, got {len(selected)}")
        # AliMeeting's two releases must have distinct version identities.
        version = VERSION + ("-2023test" if group == "alimeeting_2023test" else "")
        folder = work / group
        (folder / "audio").mkdir(parents=True)
        (folder / "rttm").mkdir()
        records, index, inventory, manifests = [], [], [], []
        for row in selected:
            rid = row["recording_id"]
            identity = f"{group}:{rid}"
            if identity in identities or Path(rid).name != rid:
                raise ValueError(f"invalid or duplicate ID: {identity}")
            identities.add(identity)
            paths = {}
            for key, subdir, ext in (("audio_filepath", "audio", ".wav"),
                                     ("rttm_filepath", "rttm", ".rttm")):
                # Only the known old root is migrated; arbitrary paths are rejected.
                original = Path(row[key])
                old_root = source.parent / "diarization_data"
                relative = original.relative_to(old_root)
                src = source / relative
                dst = folder / subdir / (rid + ext)
                shutil.copyfile(src, dst)
                paths[key] = dst
                inventory.append({"relative_path": dst.relative_to(work).as_posix(),
                                  "source_relative_path": relative.as_posix(),
                                  "bytes": dst.stat().st_size, "sha256": digest(dst)})
            info = sf.info(paths["audio_filepath"])
            duration = info.frames / info.samplerate
            if info.channels != 1 or info.samplerate != 16000:
                raise ValueError(f"unexpected audio format: {identity}: {info}")
            if abs(duration - row["duration"]) > 0.001:
                raise ValueError(f"duration mismatch: {identity}")
            segments = []
            for number, line in enumerate(paths["rttm_filepath"].read_text().splitlines(), 1):
                if not line.strip():
                    continue
                fields = line.split()
                if len(fields) != 10 or fields[0] != "SPEAKER" or fields[1] != rid:
                    raise ValueError(f"invalid RTTM: {identity}:{number}: {line}")
                start, length = float(fields[3]), float(fields[4])
                if not all(math.isfinite(v) for v in (start, length)) or start < 0 or length <= 0:
                    raise ValueError(f"invalid segment: {identity}:{number}")
                if start + length > duration + 0.001:
                    warnings.append({"recording": identity, "line": number,
                                     "issue": "reference_end_exceeds_audio",
                                     "end": start + length, "audio_duration": duration})
                segments.append({"start": start, "duration": length,
                                 "speaker_id": fields[7]})
            speakers = len({s["speaker_id"] for s in segments})
            if not segments or speakers != row["num_speakers"]:
                raise ValueError(f"speaker count mismatch: {identity}")
            wav = paths["audio_filepath"].relative_to(work).as_posix()
            rttm = paths["rttm_filepath"].relative_to(work).as_posix()
            record = {
                "schema_version": "audio-record/1.0", "id": identity,
                "task": "speaker_diarization", "audio_slots": [{"name": "speech", "ref": {
                    "dataset_id": dataset, "version": version, "split": "test",
                    "cut_id": rid, "channel": 0}}], "target": "", "language": language,
                "labels": {"session_id": rid, "segments": segments, "num_speakers": speakers},
                "metadata": {"benchmark_slice": group, "reference_rttm": {
                    "root_alias": ALIAS, "relative_path": rttm},
                    "uem": None, "source_manifest_row": row},
            }
            AudioRecord.from_dict(record)
            records.append(record)
            index.append({"cut_id": rid, "root_alias": ALIAS, "relative_path": wav,
                          "sample_rate": info.samplerate, "channels": info.channels,
                          "num_frames": info.frames, "duration": duration, "split": "test",
                          "bytes": paths["audio_filepath"].stat().st_size})
            fixed = dict(row, audio_filepath=str(output / wav), rttm_filepath=str(output / rttm))
            manifests.append(fixed)
            all_manifest.append(fixed)
        jsonl(folder / "records.jsonl", records)
        jsonl(folder / "audio-index.jsonl", index)
        jsonl(folder / "files.jsonl", inventory)
        jsonl(folder / "test.jsonl", manifests)
        artifacts = []
        for name, kind, filename, count in (
            ("test", "audio-records", "records.jsonl", expected),
            ("audio_index", "audio-index", "audio-index.jsonl", expected),
            ("file_inventory", "file-inventory", "files.jsonl", expected * 2),
            ("legacy_manifest", "jsonl-manifest", "test.jsonl", expected),
        ):
            path = folder / filename
            artifacts.append({"name": name, "kind": kind, "root_alias": ALIAS,
                              "relative_path": path.relative_to(work).as_posix(),
                              "expected_bytes": path.stat().st_size, "sha256": digest(path),
                              "metadata": {"record_count": count}})
        specs.append({"schema_version": "dataset-catalog/2.0", "dataset_id": dataset,
                      "version": version, "languages": [language], "tasks": ["speaker_diarization"],
                      "artifacts": artifacts, "splits": {"test": {"task": "speaker_diarization",
                          "artifacts": {"records": ["test"], "audio_index": ["audio_index"],
                                        "file_inventory": ["file_inventory"]},
                          "statistics": {"recordings": expected,
                              "duration_hours": sum(i["duration"] for i in index) / 3600,
                              "duration_basis": "sum of measured whole-recording durations"}}},
                      "provenance": {"status": "ready", "benchmark_slice": group,
                          "source_benchmark": "amphion-diarization/diarization-benchmark@20261019",
                          "source_manifest_sha256": digest(source / "test.jsonl"),
                          "lineage_status": "inferred", "description":
                              "Frozen local evaluation slice; audio and RTTM bytes copied unchanged. "
                              "Not a claim of official release equivalence or training disjointness.",
                          "rttm_origin": selected[0].get("rttm_origin", "unconfirmed"),
                          "source_channel": selected[0].get("source_channel", "unconfirmed"),
                          "audio_preparation": selected[0].get("audio_preparation", "unconfirmed"),
                          "official_release_and_split_equivalence": "unconfirmed",
                          "scoring_protocol": "Historical collar=0 reported by request; "
                              "scorer version, no-UEM extent and overlap policy unconfirmed.",
                          "reference_policy": "Preserve all RTTM segments, including any reported bounds issues.",
                          "limitations_document": "docs/datasets/diarization-benchmark.md"}})
        views.append({"schema_version": "dataset-view/1.0",
                      "view_id": group + "/diarization-benchmark", "version": VERSION,
                      "source": {"dataset_id": dataset, "version": version},
                      "result": {"dataset_id": dataset, "version": version},
                      "materialization": "full", "lineage_status": "inferred",
                      "transforms": [{"name": "freeze-local-rttm", "version": VERSION,
                          "kind": "representation-conversion", "writes": ["audio_slots", "labels", "metadata"],
                          "parameters": {"script": "scripts/diarization/register_benchmark.py",
                              "script_sha256": digest(Path(__file__)),
                              "audio_and_rttm_policy": "byte-preserving copy"}}]})
        print(f"prepared {group}: {expected}", flush=True)
    jsonl(work / "test.jsonl", all_manifest)
    report = {"recordings": len(all_manifest), "files": len(all_manifest) * 2,
              "excluded_slice": "ami (16 far-field recordings)", "warnings": warnings,
              "checks": ["all audio headers", "all audio and RTTM SHA-256",
                         "RTTM syntax and speaker counts", "unique recording IDs", "AudioRecord validation"]}
    (work / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    os.rename(work, output)
    for path in output.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    output.chmod(0o555)
    yaml = YAML()
    yaml.width = 4096
    with (repo / "catalog/diarization_benchmark.yaml").open("w") as stream:
        yaml.dump(specs, stream)
    with (repo / "views/diarization_benchmark.yaml").open("w") as stream:
        yaml.dump(views, stream)
    if merged_roots(roots_path, output) != roots:
        raise ValueError("roots.json changed during preparation; refusing to overwrite")
    write_roots(roots_path, roots)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
