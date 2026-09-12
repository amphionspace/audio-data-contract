#!/usr/bin/env python3
"""Build portable speaker records from measured, byte-preserving extractions."""

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

import orjson
from extract import DATASETS, VERSION, archive_groups, paths, save, sha256, source_spec

from audio_data_contract import AudioRecord
from audio_data_contract.catalog import verify_artifact_file
from audio_data_contract.types import DatasetSpec, DatasetViewSpec


def rows(path):
    with path.open("rb") as stream:
        for line in stream:
            yield orjson.loads(line)


def lines(path):
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                yield number, line.strip().split()


def gzip_output(stack, path):
    raw = stack.enter_context(path.open("wb"))
    return stack.enter_context(gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                           compresslevel=1, mtime=0))


def audio_items(work, source):
    audio, metadata = [], []
    for name, artifacts in archive_groups(source):
        receipt = json.loads((work / "inventories" / (name + ".complete.json")).read_text())
        inventory = work / "inventories" / (name + ".jsonl")
        if sha256(inventory) != receipt["inventory_sha256"]:
            raise ValueError(f"extraction inventory changed: {name}")
        expected = [{k: a[k] for k in ("relative_path", "expected_bytes", "sha256")}
                    for a in artifacts]
        if receipt["inputs"] != expected:
            raise ValueError(f"source archive identity changed: {name}")
        count = 0
        for item in rows(inventory):
            path = work / item["path"]
            if not path.is_file() or path.stat().st_size != item["bytes"]:
                raise ValueError(f"missing or incomplete extracted file: {path}")
            (audio if "sample_rate" in item else metadata).append(item)
            count += 1
        if count != receipt["files"]:
            raise ValueError(f"extraction count mismatch: {name}")
    if not audio:
        raise ValueError("no extracted audio")
    return audio, metadata


def metadata_path(work, metadata, filename):
    matches = [work / item["path"] for item in metadata
               if Path(item["member"]).name == filename]
    if len(matches) != 1:
        raise ValueError(f"expected one metadata file {filename}: {matches}")
    return matches[0]


def cn_speaker(item):
    matches = re.findall(r"(?:^|/)(id\d+)(?:/|-)", item["member"])
    if len(matches) != 1:
        raise ValueError(f"unrecognized CN-Celeb speaker path: {item['member']}")
    return matches[0]


def annotate_audio(dataset, work, metadata, audio):
    """Use official splits and speaker metadata; never create a random split."""
    if dataset == "cnceleb1":
        train_speakers = {parts[0] for _, parts in
                          lines(metadata_path(work, metadata, "dev.lst"))}
        for item in audio:
            speaker = cn_speaker(item)
            member = item["member"]
            if "/eval/enroll/" in member:
                split = "test_enrollment"
            elif "/eval/test/" in member:
                split = "test"
            elif "/data/" in member:
                split = "train" if speaker in train_speakers else "source_eval"
            else:
                raise ValueError(f"unknown CN-Celeb1 audio: {member}")
            item.update(split=split, speaker=speaker)
    elif dataset == "cnceleb2":
        speakers = {parts[0] for _, parts in
                    lines(metadata_path(work, metadata, "spk.lst"))}
        for item in audio:
            speaker = cn_speaker(item)
            if speaker not in speakers:
                raise ValueError(f"speaker absent from official list: {speaker}")
            item.update(split="train", speaker=speaker)
    elif dataset == "3dspeaker":
        info = {}
        for split in ("train", "test"):
            path = metadata_path(work, metadata, split + "_utt2info.csv")
            with path.open() as stream:
                for row in csv.DictReader(stream):
                    key = row["Utt-id"]
                    if key in info:
                        raise ValueError(f"duplicate official utterance: {key}")
                    info[key] = (split, row)
        for item in audio:
            utterance = Path(item["member"]).stem
            split, row = info.pop(utterance)
            if item["archive"] != split + "_archive":
                raise ValueError(f"official split disagrees with audio: {utterance}")
            item.update(split=split, speaker=row["Spk-id"], labels={
                "utterance_id": utterance, "segment_id": row["Seg-id"],
                "device": row["Device"], "distance": row["Distance"],
                "dialect": row["Dialect"],
            })
        if info:
            raise ValueError(f"{len(info)} official utterances have no audio")
    elif dataset == "hi_mia":
        mappings = {}
        for split in ("train", "dev"):
            mappings[split] = dict(parts for _, parts in lines(
                metadata_path(work, metadata, split + "_filename_mapping.txt")))
        for item in audio:
            split = item["archive"].removesuffix("_archive")
            filename = Path(item["member"]).name
            canonical = mappings[split][filename] if split in mappings else filename
            speaker, point, mic, utterance = Path(canonical).stem.split("_")
            if not re.fullmatch(r"SV\d{4}", speaker):
                raise ValueError(f"unrecognized HI-MIA speaker: {filename}")
            item.update(split=split, speaker=speaker, labels={
                "canonical_filename": canonical, "point_id": point,
                "microphone_id": mic, "speaking_speed_code": utterance[0],
                "utterance_id": utterance[1:],
            })
    elif dataset == "chime6":
        for item in audio:
            item["split"] = item["archive"].removesuffix("_archive")
            item["session"] = Path(item["member"]).name.split("_")[0]
    else:
        raise ValueError(dataset)
    if dataset != "chime6":
        split_speakers = defaultdict(set)
        for item in audio:
            if item["split"] in {"train", "dev", "test"}:
                split_speakers[item["split"]].add(item["speaker"])
        names = list(split_speakers)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if split_speakers[a] & split_speakers[b]:
                    raise ValueError(f"speaker leakage between {a} and {b}")


def seconds(value):
    hours, minutes, secs = map(float, value.split(":"))
    return hours * 3600 + minutes * 60 + secs


class Builder:
    def __init__(self, root, work, final, dataset, stack, audio):
        self.root, self.work, self.final = root, work, final
        self.dataset, self.stack = dataset, stack
        self.audio = audio
        self.writers, self.counts, self.durations = {}, Counter(), Counter()
        self.speakers, self.seen = defaultdict(set), set()
        self.splits, self.rejects = {}, []
        self.by_id = {}
        for item in audio:
            relative = (final / item["path"]).relative_to(root).as_posix()
            item["cut_id"] = hashlib.sha256(("legacy_asr:" + relative).encode()).hexdigest()
            item["relative_path"] = relative
            if item["cut_id"] in self.by_id:
                raise ValueError(f"duplicate audio path: {relative}")
            self.by_id[item["cut_id"]] = item

    def ref(self, item, start=None, duration=None):
        result = {"dataset_id": self.dataset, "version": VERSION,
                  "split": item["split"], "cut_id": item["cut_id"]}
        if start is not None:
            if start < 0 or duration <= 0 or start + duration > item["duration"] + 1e-6:
                raise ValueError(f"segment outside audio: {item['member']}")
            result.update(start=start, duration=duration)
        return result

    def write(self, split, record, duration=0):
        AudioRecord.from_dict(record)
        identity = (split, record["id"])
        if identity in self.seen:
            raise ValueError(f"duplicate record ID: {identity}")
        self.seen.add(identity)
        for slot in record["audio_slots"]:
            ref = slot["ref"]
            item = self.by_id[ref["cut_id"]]
            if ref["split"] != item["split"]:
                raise ValueError("audio reference split mismatch")
        if split not in self.writers:
            self.writers[split] = gzip_output(self.stack, self.work / (split + ".jsonl.gz"))
        self.writers[split].write(orjson.dumps(record) + b"\n")
        self.counts[split] += 1
        self.durations[split] += duration
        if record.get("labels", {}).get("speaker_id"):
            self.speakers[split].add(record["labels"]["speaker_id"])

    def record(self, identity, task, slots, target, labels=None, metadata=None):
        return {"schema_version": "audio-record/1.0", "id": identity, "task": task,
                "audio_slots": slots, "target": target,
                "language": "en" if self.dataset == "chime6" else "zh",
                "labels": labels or {}, "metadata": metadata or {}}

    def utterances(self):
        for item in self.audio:
            split = item["split"]
            if split == "source_eval":
                continue
            speaker = self.dataset + ":" + item["speaker"]
            record = self.record(
                split + ":" + item["cut_id"], "speaker_identification",
                [{"name": "speech", "ref": self.ref(item)}], speaker,
                {"speaker_id": speaker, "source_speaker_id": item["speaker"],
                 **item.get("labels", {})},
                {"archive_artifact": item["archive"], "archive_member": item["member"]},
            )
            self.write(split, record, item["duration"])

    def pair(self, split, number, left, right, label, source, variant=""):
        if label not in {"0", "1", "target", "nontarget"}:
            raise ValueError(f"unknown official trial label: {label}")
        same = label in {"1", "target"}
        if same != (left["speaker"] == right["speaker"]):
            raise ValueError(f"trial label disagrees with speaker identities: {source}:{number}")
        record = self.record(
            f"{split}:{number}:{variant}", "speaker_verification",
            [{"name": "enrollment", "ref": self.ref(left)},
             {"name": "test", "ref": self.ref(right)}],
            "target" if same else "nontarget", {"same_speaker": same},
            {"source_file": source, "source_line": number, "channel_variant": variant},
        )
        self.write(split, record)
        self.splits[split] = {"group": "test", "task": "speaker_verification"}

    def index(self):
        output = gzip_output(self.stack, self.work / "audio-index.jsonl.gz")
        for item in self.audio:
            row = {k: item[k] for k in ("cut_id", "relative_path", "sample_rate", "channels",
                                        "num_frames", "duration", "split", "bytes")}
            row["root_alias"] = "legacy_asr"
            output.write(orjson.dumps(row) + b"\n")


def verification_trials(builder, work, metadata):
    dataset = builder.dataset
    if dataset == "cnceleb2":
        return
    if dataset == "cnceleb1":
        evaluation = {Path(item["member"]).stem: item for item in builder.audio
                      if item["split"] in {"test", "test_enrollment"}}
        enroll_path = metadata_path(work, metadata, "enroll.lst")
        enrollment = {parts[0]: evaluation[Path(parts[1]).stem]
                      for _, parts in lines(enroll_path)}
        test_path = metadata_path(work, metadata, "test.lst")
        listed = {evaluation[Path(parts[0]).stem]["cut_id"] for _, parts in lines(test_path)}
        actual = {item["cut_id"] for item in builder.audio if item["split"] == "test"}
        if listed != actual:
            raise ValueError("CN-Celeb1 evaluation list does not cover extracted test audio")
        path = metadata_path(work, metadata, "trials.lst")
        for number, (left, right, label) in lines(path):
            builder.pair("test_trials", number, enrollment[left],
                         evaluation[Path(right).stem], label, path.relative_to(work).as_posix())
    elif dataset == "3dspeaker":
        by_utterance = {Path(item["member"]).stem: item for item in builder.audio
                        if item["split"] == "test"}
        for condition in ("device", "distance", "dialect"):
            path = metadata_path(work, metadata, "trials_cross_" + condition)
            for number, (left, right, label) in lines(path):
                builder.pair("test_cross_" + condition, number, by_utterance[left],
                             by_utterance[right], label, path.relative_to(work).as_posix())
    elif dataset == "hi_mia":
        by_filename, templates = {}, defaultdict(dict)
        for item in builder.audio:
            if item["split"] != "test":
                continue
            filename = Path(item["member"]).name
            if filename in by_filename:
                raise ValueError(f"duplicate HI-MIA test filename: {filename}")
            by_filename[filename] = item
            fields = filename.split("_")
            mic, fields[2] = fields[2], "{}"
            templates["_".join(fields)][mic] = item
        for condition in ("1m", "mic"):
            path = metadata_path(work, metadata, "trials_" + condition)
            for number, (left, right, label) in lines(path):
                a = templates[left] if "{}" in left else {"fixed": by_filename[left]}
                b = templates[right] if "{}" in right else {"fixed": by_filename[right]}
                channels = (set(a) & set(b) if "{}" in left and "{}" in right
                            else set(a) if "{}" in left else set(b))
                if not channels:
                    raise ValueError(f"unresolved HI-MIA trial: {number}: {left} {right}")
                if "{}" in left and "{}" in right and set(a) != set(b):
                    raise ValueError(f"HI-MIA paired microphone sets differ: {number}")
                for channel in sorted(channels):
                    builder.pair("test_trials_" + condition, number,
                                 a[channel] if "{}" in left else a["fixed"],
                                 b[channel] if "{}" in right else b["fixed"], label,
                                 path.relative_to(work).as_posix(), channel)


def chime_records(builder, work, metadata):
    by_name = {Path(item["member"]).name: item for item in builder.audio}
    annotations = [item for item in metadata if item["archive"] == "transcriptions_repaired_archive"
                   and item["member"].endswith(".json")]
    for annotation in sorted(annotations, key=lambda a: a["member"]):
        path = work / annotation["path"]
        session = path.stem
        far = sorted([item for item in builder.audio if item["session"] == session
                      and re.fullmatch(session + r"_U\d+\.CH\d+\.wav",
                                       Path(item["member"]).name)], key=lambda a: a["member"])
        if not far:
            raise ValueError(f"no far-field audio for session: {session}")
        split = far[0]["split"]
        segments = []
        for number, row in enumerate(json.loads(path.read_text()), 1):
            start, end = seconds(row["start_time"]), seconds(row["end_time"])
            if row["session_id"] != session or not re.fullmatch(r"P\d+", row["speaker"]):
                raise ValueError(f"invalid session or speaker label: {path}:{number}")
            name = session + "_" + row["ref"] + ".CH1.wav" if "ref" in row else Path(far[0]["member"]).name
            reference = by_name[name]
            if start < 0 or end <= start or any(end > item["duration"] + 1e-6 for item in far):
                builder.rejects.append({"source_file": annotation["path"], "source_row": number,
                                        "reason": "invalid_or_out_of_bounds_timestamps", "annotation": row})
                continue
            speaker = "chime6:" + row["speaker"]
            segments.append({"start": start, "duration": end - start, "speaker_id": speaker,
                             "text": row["words"], "source_row": number})
            record = builder.record(
                f"{session}:{number}", "speaker_attributed_asr",
                [{"name": "speech", "ref": builder.ref(reference, start, end - start)}],
                row["words"], {"speaker_id": speaker, "session_id": session},
                {"source_file": annotation["path"], "source_row": number,
                 "source_annotation": row,
                 "reference_policy": "official_ref_channel_1" if "ref" in row else "first_farfield_channel"},
            )
            builder.write(split, record, end - start)
        record = builder.record(session, "speaker_diarization", [
            {"name": Path(item["member"]).stem, "ref": builder.ref(item)} for item in far
        ], "", {"session_id": session, "segments": segments},
            {"source_file": annotation["path"], "duration_basis": "one session, not summed microphones"})
        child = split + "_diarization"
        builder.write(child, record, min(item["duration"] for item in far))
        builder.splits[child] = {"group": split, "task": "speaker_diarization"}


def file_artifact(work, final, root, name, kind, filename, count=None):
    path = work / filename
    return {"name": name, "kind": kind, "root_alias": "legacy_asr",
            "relative_path": (final / filename).relative_to(root).as_posix(),
            "expected_bytes": path.stat().st_size, "sha256": sha256(path),
            "metadata": {} if count is None else {"record_count": count}}


def prepare_dataset(repo, root, dataset):
    work, final = paths(root, dataset)
    if final.exists():
        report = json.loads((final / "registration.json").read_text())
        spec = DatasetSpec.from_dict(report["dataset"])
        if spec.dataset_id != dataset or spec.version != VERSION:
            raise ValueError(f"published registration identity mismatch: {final}")
        for artifact in spec.artifacts:
            if artifact.kind != "source-directory":
                verify_artifact_file(artifact, root / artifact.relative_path)
        audio_items(final, source_spec(repo, dataset))
        return report
    state = json.loads((work / "state.json").read_text())
    if state["state"] != "extracted":
        raise ValueError(f"extraction is not complete: {dataset}: {state['state']}")
    source = source_spec(repo, dataset)
    audio, metadata = audio_items(work, source)
    print(dataset, "audio headers", len(audio), "metadata files", len(metadata), flush=True)
    annotate_audio(dataset, work, metadata, audio)
    with ExitStack() as stack:
        builder = Builder(root, work, final, dataset, stack, audio)
        builder.index()
        if dataset == "chime6":
            chime_records(builder, work, metadata)
        else:
            builder.utterances()
            verification_trials(builder, work, metadata)
    save(work / "excluded-annotations.json", builder.rejects)
    if dataset == "cnceleb1":
        builder.splits["test_enrollment"] = {"group": "test", "role": "enrollment"}
    # Read every compressed output to EOF before publishing; this checks gzip CRC
    # and on-disk counts in addition to the per-record validation during writing.
    for filename, expected in [(name + ".jsonl.gz", count) for name, count in builder.counts.items()] + [
        ("audio-index.jsonl.gz", len(audio)),
    ]:
        with gzip.open(work / filename, "rb") as stream:
            actual = sum(1 for _ in stream)
        if actual != expected:
            raise ValueError(f"output record count mismatch: {filename}: {actual} != {expected}")
    artifacts, splits = [], {}
    for split, count in builder.counts.items():
        artifacts.append(file_artifact(work, final, root, split, "audio-records",
                                       split + ".jsonl.gz", count))
        statistics = {"records": count}
        if builder.durations[split]:
            statistics.update(duration_hours=builder.durations[split] / 3600,
                              duration_basis=("sum of annotated segment durations; overlaps count separately"
                                              if dataset == "chime6" and not split.endswith("_diarization")
                                              else "sum of measured audio durations; one session per diarization record"))
        if builder.speakers[split]:
            statistics["speakers"] = len(builder.speakers[split])
        splits[split] = {**builder.splits.get(split, {}), "records_artifact": split,
                         "audio_index_artifact": "audio_index", "statistics": statistics}
    # Raw held-out copies stay indexed for provenance, outside training records.
    if dataset == "cnceleb1":
        splits["source_eval"] = {"group": "test", "audio_index_artifact": "audio_index",
                                 "role": "original_held_out_audio_not_training"}
    artifacts.append(file_artifact(work, final, root, "audio_index", "audio-index",
                                   "audio-index.jsonl.gz", len(audio)))
    artifacts.append(file_artifact(work, final, root, "excluded_annotations", "quality-report",
                                   "excluded-annotations.json", len(builder.rejects)))
    artifacts.append({"name": "extracted_source", "kind": "source-directory", "root_alias": "legacy_asr",
                      "relative_path": (final / "extracted").relative_to(root).as_posix(),
                      "metadata": {"audio_files": len(audio), "metadata_files": len(metadata),
                                   "audio_bytes": sum(item["bytes"] for item in audio)}})
    for name, _ in archive_groups(source):
        artifacts.append(file_artifact(work, final, root, "inventory_" + name,
                                       "extraction-inventory", "inventories/" + name + ".jsonl"))
    recipe = {"script": "scripts/speaker/prepare.py", "script_sha256": sha256(Path(__file__)),
              "extractor_sha256": sha256(Path(__file__).with_name("extract.py")),
              "version": VERSION, "source_version": source["version"],
              "audio_policy": "original bytes, sampling rate and channels; no resampling or denoising",
              "speaker_id_policy": "dataset_id:official_speaker_id",
              "trial_policy": "official pairs only; HI-MIA templates expanded over matching actual microphone IDs",
              "validation": {"all_records_validated": True, "all_audio_headers_measured": True,
                             "gzip_crc_and_counts": "passed", "duplicate_record_ids": 0,
                             "speaker_split_disjointness": "passed" if dataset != "chime6" else "not_applied"},
              "source_artifacts": [{k: a[k] for k in ("name", "sha256", "relative_path")}
                                   for a in source["artifacts"] if a.get("sha256")]}
    spec = {"schema_version": "dataset-catalog/1.0", "dataset_id": dataset, "version": VERSION,
            "languages": source["languages"], "tasks": (["speaker_diarization", "speaker_attributed_asr"]
                       if dataset == "chime6" else ["speaker_identification", "speaker_verification"]
                       if dataset != "cnceleb2" else ["speaker_identification"]),
            "artifacts": artifacts, "splits": splits, "recipe_parameters": recipe,
            "provenance": {"source_version": source["version"], "source": source["provenance"]["source"],
                           "preparation_status": "ready", "integrity": "verified",
                           "description": "已解包、实测音频头并生成通用说话人记录；保留官方划分和标注。",
                           "quality_status": "source_annotations_preserved_except_reported_invalid_timestamps",
                           "excluded_annotations": len(builder.rejects),
                           **{k: source["provenance"][k] for k in
                              ("license", "metadata_license", "license_note") if k in source["provenance"]},
                           "local_scan_date": "2026-09-12"}}
    view = {"schema_version": "dataset-view/1.0", "view_id": dataset + "/speaker", "version": VERSION,
            "source": {"dataset_id": dataset, "version": source["version"]},
            "result": {"dataset_id": dataset, "version": VERSION}, "materialization": "full",
            "lineage_status": "exact", "transforms": [{"name": "portable-speaker-records", "version": VERSION,
                "kind": "representation-conversion", "writes": ["audio_slots", "target", "labels", "metadata", "$membership"],
                "parameters": recipe}]}
    DatasetSpec.from_dict(spec)
    DatasetViewSpec.from_dict(view)
    state.update(state="prepared", updated_at=datetime.now(timezone.utc).isoformat())
    state["metadata"].update(phase="ready", audio_files=len(audio), records=dict(builder.counts),
                              excluded_annotations=len(builder.rejects))
    save(work / "state.json", state)
    artifacts.append(file_artifact(work, final, root, "preparation_state", "dataset-state", "state.json"))
    report = {"dataset": spec, "view": view, "completed_at": state["updated_at"]}
    save(work / "registration.json", report)
    final.parent.mkdir(parents=True, exist_ok=True)
    work.rename(final)
    print(dataset, "published", dict(builder.counts), flush=True)
    return report


def register(repo, report):
    dataset = report["dataset"]["dataset_id"]
    for directory, filename, field, key in [
        ("catalog", dataset + ".jsonl", "dataset", "dataset_id"),
        ("views", "speaker.jsonl", "view", "view_id"),
    ]:
        path = repo / directory / filename
        existing = list(rows(path)) if path.exists() else []
        row = report[field]
        matches = [item for item in existing if (item[key], item["version"]) == (row[key], row["version"])]
        if matches:
            if matches != [row]:
                raise ValueError(f"immutable registration differs: {row[key]}")
            continue
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(b"".join(orjson.dumps(item) + b"\n" for item in [*existing, row]))
        temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    root = Path(json.loads(args.roots.read_text())["legacy_asr"])
    report = prepare_dataset(args.repo, root, args.dataset)
    if args.register:
        register(args.repo, report)


if __name__ == "__main__":
    main()
