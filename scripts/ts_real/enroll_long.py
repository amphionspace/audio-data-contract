#!/usr/bin/env python3
"""Store 10 s enrollments in the real-conversation sets, for a client that sends 5 s (production since 2026-10-22).

Derived versions, same windows, mixtures and record IDs:

* ``ts_asr_real@v4-20261022`` from ``v3-20261022``: each enrollment keeps its utterance and appends other utterances
  of the same speaker up to ``build.ENROLL_STORE`` (``build.enrollment_pieces``: outside the window, nobody else
  annotated in them, random order from the record's own stream, as ``build.py`` now does for new versions).
  ``metadata.enrollment_pieces`` lists the spans, ``labels.enroll_seconds`` the stored length.
  ``labels.enroll_others_s`` / ``enroll_condition`` are recomputed over the first ``build.ENROLL_CROP`` (5 s), and
  records move between ``<split>`` and ``<split>-enrollmix`` accordingly.
* ``ts_asr_nearfar@v3-20261022`` from ``v2-20261022``: the same spans as its ``ts_asr_real`` source record, cut from
  far-field channel 0 (``ef``) or from the speaker's headset (``en``); the labels follow the source record.

    python scripts/ts_real/enroll_long.py --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import copy
import gzip
import importlib.util
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


real = _load("ts_real_build", "build.py")  # imports ts_benchmark/build.py itself as ``build``
near_far = _load("ts_real_near_far", "near_far.py")
overlap = _load("ts_real_enroll_overlap", "enroll_overlap.py")
synth = real.synth
REPO = HERE.parents[1]
SR = real.SR
SUFFIX = "-enrollmix"
REAL = ("ts_asr_real", "v3-20261022", "v4-20261022")
NEARFAR = ("ts_asr_nearfar", "v2-20261022", "v3-20261022")


def read_version(catalog, roots, dataset, version):
    spec = next(s for s in catalog if s.dataset_id == dataset and s.version == version)
    records = []
    for split in spec.splits:
        for path in resolve_split(catalog, dataset, version, split, "records", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                records += [(split, r) for r in map(json.loads, stream)]
    return spec, records


def relabel(record, derived, seconds, others, pieces, audio, data_root, dataset):
    """Point the record at ``derived`` with the stored enrollment written as a new cut; returns (split, row)."""
    condition = "clean" if seconds < real.ENROLL_CROP_OTHERS_MAX else "others_speech"
    split = record["labels"]["scenario"].removesuffix(SUFFIX) + ("" if condition == "clean" else SUFFIX)
    record["labels"].update(scenario=split, enroll_seconds=round(len(audio) / SR, 3), enroll_others_s=seconds,
                            enroll_condition=condition)
    record["metadata"].update(enroll_others=others, enrollment_pieces=[[round(s, 3), round(e, 3)] for s, e in pieces])
    if "split" in record["metadata"]:
        record["metadata"]["split"] = split
    row = None
    for slot in record["audio_slots"]:
        slot["ref"].update(version=derived, split=split)
        if slot["name"] == "enrollment":
            cut = slot["ref"]["cut_id"].removesuffix("-repick") + "-long"
            relative = f"audio/{split}/{cut}.wav"
            synth.write_wav(data_root / "source" / derived / relative, audio)
            row = {"cut_id": cut, "relative_path": f"source/{derived}/{relative}", "num_frames": len(audio),
                   "duration": round(len(audio) / SR, 4), "sha256": synth.sha256_file(data_root / "source" / derived / relative),
                   "root_alias": dataset, "sample_rate": SR, "channels": 1}
            slot["ref"].update(cut_id=cut, duration=row["duration"])
    return split, row


def write_version(dataset, version, derived, spec, splits, rows, data_root, note, args):
    for name, records in splits.items():
        records.sort(key=lambda r: r["id"])
        synth.write_jsonl_gz(data_root / "versions" / derived / "records" / f"{name}.jsonl.gz", records)
    synth.write_jsonl_gz(data_root / "versions" / derived / "audio-index.jsonl.gz", sorted(rows.values(), key=lambda e: e["cut_id"]))

    def relative(*parts):
        return "/".join(("versions", derived, *parts))

    artifacts = [{"name": "audio-index", "kind": "audio-index", "root_alias": dataset,
                  "relative_path": relative("audio-index.jsonl.gz"),
                  "sha256": synth.sha256_file(data_root / relative("audio-index.jsonl.gz")),
                  "metadata": {"record_count": len(rows)}}]
    split_decl = {}
    for name in sorted(splits, key=lambda n: (n.removesuffix(SUFFIX), n.endswith(SUFFIX))):
        records = splits[name]
        path = relative("records", f"{name}.jsonl.gz")
        artifacts.append({"name": f"{name}-records", "kind": "audio-records", "root_alias": dataset, "relative_path": path,
                          "sha256": synth.sha256_file(data_root / path), "metadata": {"record_count": len(records)}})
        seconds = sum(next(s for s in r["audio_slots"] if s["name"] == "mixture")["ref"]["duration"] for r in records)
        base = spec.splits[name.removesuffix(SUFFIX)].provenance["description"].split("；")[0]
        mixed = (f"；注册前 {real.ENROLL_CROP:g} 秒里他人说话不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒"
                 "（labels.enroll_condition = others_speech）") if name.endswith(SUFFIX) else ""
        split_decl[name] = {"artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]}, "task": "ts_asr",
                            "statistics": {"records": len(records), "duration_hours": round(seconds / 3600, 4),
                                           "duration_basis": "Mixture duration"},
                            "provenance": {"description": base + mixed}}
    old = spec.provenance
    declaration = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": derived,
        "languages": list(spec.languages), "tasks": list(spec.tasks), "artifacts": artifacts, "splits": split_decl,
        "provenance": {"status": "complete", "synthetic": old["synthetic"],
                       "description": f"{dataset}@{version} 的 5 秒注册版，窗口和混合音频不变：{note}生成脚本 scripts/ts_real/enroll_long.py。",
                       "sources": [*old.get("sources", []), f"{dataset}@{version}"]},
    }
    report = {name: len(records) for name, records in sorted(splits.items())}
    (data_root / "source" / derived).mkdir(parents=True, exist_ok=True)
    (data_root / "source" / derived / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(dataset, derived, report, flush=True)
    if args.no_register:
        return
    path = REPO / "catalog" / f"{dataset}.yaml"
    rows_yaml = list(yaml.safe_load(path.read_text()))
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows_yaml, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", dataset, derived, sum(map(len, splits.values())), "records", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    catalog = load_catalog(args.catalog)
    for dataset, _, derived in (REAL, NEARFAR):
        root = Path(roots[dataset])
        if (root / "versions" / derived).exists() or (root / "source" / derived).exists():
            raise FileExistsError(f"refusing to replace {dataset}@{derived}")
    corpora = overlap.annotations(catalog, roots)

    dataset, version, derived = REAL
    data_root = Path(roots[dataset])
    spec, records = read_version(catalog, roots, dataset, version)
    splits, rows, by_id = defaultdict(list), {}, {}
    # Grouped by recording so an Emilia2 window is decoded once (build.cut keeps the last one).
    for _, record in sorted(records, key=lambda x: (x[1]["metadata"]["enrollment"]["recording"], x[1]["id"])):
        record = copy.deepcopy(record)
        labels, enroll = record["labels"], record["metadata"]["enrollment"]
        recording, speaker = enroll["recording"], overlap.speaker_of(record)
        entry = corpora[labels["corpus"]][recording]
        lo, hi = ((labels["window_start_s"], labels["window_start_s"] + labels["duration_s"])
                  if recording == labels["recording"] else (-1e9, -1e9))
        pieces = real.enrollment_pieces(entry, speaker, (enroll["start"], enroll["end"]), lo, hi,
                                        random.Random(f"{record['id']}:enroll-pieces"))
        audio = real.cut_pieces(corpora[labels["corpus"]], recording, pieces)
        seconds, others = real.pieces_others(entry, speaker, pieces)
        split, row = relabel(record, derived, seconds, others, pieces, audio, data_root, dataset)
        rows[row["cut_id"]] = row
        mix = next(s["ref"]["cut_id"] for s in record["audio_slots"] if s["name"] == "mixture")
        rows[mix] = old_index(catalog, roots, dataset, version)[mix]
        splits[split].append(record)
        by_id[record["id"]] = (recording, speaker, pieces, seconds, others)
    write_version(dataset, version, derived, spec, splits, rows, data_root,
                  f"注册保留原第一句，后接同一人在窗口外、无他人重叠的其他语句，共存 {real.ENROLL_STORE:g} 秒（labels.enroll_seconds，"
                  f"metadata.enrollment_pieces）；他人说话秒数改按前 {real.ENROLL_CROP:g} 秒计（labels.enroll_others_s），"
                  f"不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒的在 -enrollmix 划分。", args)

    dataset, version, derived = NEARFAR
    data_root = Path(roots[dataset])
    spec, records = read_version(catalog, roots, dataset, version)
    splits, rows = defaultdict(list), {}
    for _, record in sorted(records, key=lambda x: x[1]["id"]):
        record = copy.deepcopy(record)
        recording, speaker, pieces, seconds, others = by_id[record["metadata"]["source_record"]]
        if record["labels"]["enroll_domain"] == "near":
            path = near_far.NEAR_DIR / f"{recording}_N_SPK{speaker}.wav"
            audio = np.concatenate([near_far.cut_near(path, s, e) for s, e in pieces])[: int(real.ENROLL_STORE * SR)]
        else:
            audio = real.cut_pieces(corpora["alimeeting"], recording, pieces)
        split, row = relabel(record, derived, seconds, others, pieces, audio, data_root, dataset)
        rows[row["cut_id"]] = row
        mix = next(s["ref"]["cut_id"] for s in record["audio_slots"] if s["name"] == "mixture")
        rows[mix] = old_index(catalog, roots, dataset, version)[mix]
        splits[split].append(record)
    write_version(dataset, version, derived, spec, splits, rows, data_root,
                  f"注册与其 ts_asr_real@{REAL[2]} 源样本同样的语句片段（远场取通道 0，近场取本人头戴麦），共存 "
                  f"{real.ENROLL_STORE:g} 秒；他人说话秒数按前 {real.ENROLL_CROP:g} 秒计，不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒的在 -enrollmix 划分。",
                  args)


_INDEX = {}


def old_index(catalog, roots, dataset, version):
    """Audio index rows of the source version (mixtures are reused as they are)."""
    if (dataset, version) not in _INDEX:
        spec = next(s for s in catalog if s.dataset_id == dataset and s.version == version)
        rows = {}
        for path in resolve_split(catalog, dataset, version, next(iter(spec.splits)), "audio_index", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                rows.update((row["cut_id"], row) for row in map(json.loads, stream))
        _INDEX[(dataset, version)] = rows
    return _INDEX[(dataset, version)]


if __name__ == "__main__":
    main()
