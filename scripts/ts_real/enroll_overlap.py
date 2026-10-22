#!/usr/bin/env python3
"""Label how much of each enrollment crop someone else speaks in, as derived versions of the real-conversation sets.

The TS client sends only the first 3 s of an enrollment. ``build.py`` allowed 20% of the whole 3-6 s utterance to
be overlapped, so in ``ts_asr_real@v2-20261013`` (and ``ts_asr_nearfar@v1-20261014``, which reuses its AliMeeting
enrollments) that overlap could fill much of the 3 s: 205 of 2,072 records had >= 0.5 s of another speaker in it,
and the model then transcribed that speaker when they talked in the window. Such an enrollment is a real
degradation, but it was scored as a clean one. This writes, with the same audio:

* ``ts_asr_real@v3-20261022`` and ``ts_asr_nearfar@v2-20261022``: every record gets ``labels.enroll_others_s``
  (annotated speech of anyone else in the crop; MOSS pseudo labels for Emilia2) and ``labels.enroll_condition``
  (``clean`` below ``build.ENROLL_CROP_OTHERS_MAX``, else ``others_speech``). ``others_speech`` records move to a
  split of their own, ``<split>-enrollmix``, so clean-enrollment scores no longer include them.
* ``REPICKED``: three AISHELL-4 positives whose enrollment sounds like another speaker of the meeting (voice check,
  ERes2NetV2: closer to that speaker's profile than to the target's own speech in the window). Each gets another
  eligible utterance of the target that passes the check, cut like ``build.py`` does; the old one is kept in
  ``metadata.enrollment_replaced``.
* ``DROPPED``: a positive where no utterance of the target passes the check (the window has only 2.1 s of the
  target, all overlapped), so who the target is cannot be confirmed.

Record IDs and window audio stay as they were; audio refs point at the derived version, whose audio index reuses
the original rows plus the three new enrollments.

    python scripts/ts_real/enroll_overlap.py --roots /workspace/data/registry/roots.json
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

import yaml

# ts_real/build.py imports ts_benchmark/build.py as ``build``; load it under its own name so the two do not clash.
_spec = importlib.util.spec_from_file_location("ts_real_build", Path(__file__).with_name("build.py"))
real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real)

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

synth = real.synth
REPO = Path(__file__).resolve().parents[2]
SR = real.SR
DERIVED = {
    ("ts_asr_real", "v2-20261013"): "v3-20261022",
    ("ts_asr_nearfar", "v1-20261014"): "v2-20261022",
}
# Found by the 2026-10-22 enrollment QC (ERes2NetV2 cosine of the 3 s crop; "window" = the target's speech in
# the window nobody overlaps, which the reference transcribes). Replacements: eligible per build.py, nobody in
# the crop, the highest margin of window-target over every other speaker of the recording.
REPICKED = {
    "real-aishell4-2spk-pos:0022": {"start": 816.136, "end": 821.471,
                                    "check": "old: window 0.383 < SPK0969 0.527; new: window 0.691, best other 0.237"},
    "real-aishell4-2spk-pos:0043": {"start": 665.630, "end": 671.630,
                                    "check": "old: window 0.215 < SPK0956 0.633; new: window 0.794, best other 0.268"},
    "real-aishell4-3plus-pos:0000": {"start": 1976.412, "end": 1979.557,
                                     "check": "old: window 0.481 < SPK0918 0.828; new: window 0.725, best other 0.310"},
}
DROPPED = {
    "real-aishell4-3plus-pos:0024": "enrollment closer to SPK1001 (0.813) than to the target's window speech (0.610), "
                                    "and so is every eligible utterance of the target (19); target unconfirmed",
}


def annotations(catalog, roots):
    """{corpus: {recording: entry}} with the annotation each set was cut from (build.py's own loaders)."""
    recipe = real.RECIPE
    out = {}
    for name, spec in recipe["corpora"].items():
        if spec.get("kind") == "emilia2":
            out[name] = real.load_emilia2(spec, catalog, roots, random.Random(f"{recipe['seed']}:{name}:recordings"))
        else:
            out[name] = real.load_corpus(spec, catalog, roots)
    return out


def speaker_of(record):
    return record["metadata"]["target_speaker"].split(":", 1)[1]


def derive(dataset, version, catalog, roots, corpora, args):
    derived = DERIVED[(dataset, version)]
    data_root = Path(roots[dataset])
    if (data_root / "versions" / derived).exists() or (data_root / "source" / derived).exists():
        raise FileExistsError(f"refusing to replace {dataset}@{derived}")
    spec = next(s for s in catalog if s.dataset_id == dataset and s.version == version)
    index = {}
    for path in resolve_split(catalog, dataset, version, next(iter(spec.splits)), "audio_index", roots):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            index.update((row["cut_id"], row) for row in map(json.loads, stream))
    splits, index_rows, report = {}, {}, defaultdict(lambda: defaultdict(int))
    for split in spec.splits:
        for path in resolve_split(catalog, dataset, version, split, "records", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for record in map(json.loads, stream):
                    if record["id"] in DROPPED:
                        report[split]["dropped"] += 1
                        continue
                    record = copy.deepcopy(record)
                    corpus = record["labels"]["corpus"]
                    enroll = record["metadata"]["enrollment"]
                    new_audio = None
                    if record["id"] in REPICKED:
                        pick = REPICKED[record["id"]]
                        record["metadata"]["enrollment_replaced"] = {**enroll, "reason": pick["check"]}
                        enroll = {"recording": enroll["recording"], "start": pick["start"], "end": pick["end"]}
                        record["metadata"]["enrollment"] = enroll
                        new_audio = real.cut(corpora[corpus], enroll["recording"], enroll["start"], enroll["end"])
                        report[split]["repicked"] += 1
                    seconds, others = real.crop_others(corpora[corpus][enroll["recording"]], speaker_of(record), enroll["start"])
                    condition = "clean" if seconds < real.ENROLL_CROP_OTHERS_MAX else "others_speech"
                    record["labels"].update(enroll_others_s=seconds, enroll_condition=condition)
                    record["metadata"]["enroll_others"] = others
                    target_split = split if condition == "clean" else f"{split}-enrollmix"
                    record["labels"]["scenario"] = target_split
                    if "split" in record["metadata"]:
                        record["metadata"]["split"] = target_split
                    for slot in record["audio_slots"]:
                        slot["ref"].update(version=derived, split=target_split)
                        cut = slot["ref"]["cut_id"]
                        if slot["name"] == "enrollment" and new_audio is not None:
                            cut = f"{cut}-repick"
                            relative = f"audio/{target_split}/{cut}.wav"
                            synth.write_wav(data_root / "source" / derived / relative, new_audio)
                            index_rows[cut] = {"cut_id": cut, "relative_path": f"source/{derived}/{relative}",
                                               "num_frames": len(new_audio), "duration": round(len(new_audio) / SR, 4),
                                               "sha256": synth.sha256_file(data_root / "source" / derived / relative),
                                               "root_alias": dataset, "sample_rate": SR, "channels": 1}
                            slot["ref"].update(cut_id=cut, duration=index_rows[cut]["duration"])
                        else:
                            index_rows[cut] = index[cut]
                    splits.setdefault(target_split, []).append(record)
                    report[split][condition] += 1
    for name, records in splits.items():
        records.sort(key=lambda r: r["id"])
        synth.write_jsonl_gz(data_root / "versions" / derived / "records" / f"{name}.jsonl.gz", records)
    synth.write_jsonl_gz(data_root / "versions" / derived / "audio-index.jsonl.gz", sorted(index_rows.values(), key=lambda e: e["cut_id"]))
    (data_root / "source" / derived).mkdir(parents=True, exist_ok=True)
    (data_root / "source" / derived / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def relative(*parts):
        return "/".join(("versions", derived, *parts))

    artifacts = [{"name": "audio-index", "kind": "audio-index", "root_alias": dataset,
                  "relative_path": relative("audio-index.jsonl.gz"),
                  "sha256": synth.sha256_file(data_root / relative("audio-index.jsonl.gz")),
                  "metadata": {"record_count": len(index_rows)}}]
    split_decl = {}
    for name in sorted(splits, key=lambda n: (n.removesuffix("-enrollmix"), n.endswith("-enrollmix"))):
        records = splits[name]
        path = relative("records", f"{name}.jsonl.gz")
        artifacts.append({"name": f"{name}-records", "kind": "audio-records", "root_alias": dataset,
                          "relative_path": path, "sha256": synth.sha256_file(data_root / path),
                          "metadata": {"record_count": len(records)}})
        seconds = sum(next(s for s in r["audio_slots"] if s["name"] == "mixture")["ref"]["duration"] for r in records)
        base = spec.splits[name.removesuffix("-enrollmix")]
        note = (f"；注册前 3 秒里他人说话不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒（labels.enroll_condition = others_speech）"
                if name.endswith("-enrollmix") else "")
        split_decl[name] = {"artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
                            "task": "ts_asr",
                            "statistics": {"records": len(records), "duration_hours": round(seconds / 3600, 4),
                                           "duration_basis": "Mixture duration"},
                            "provenance": {"description": f"{base.provenance['description']}{note}"}}
    old = spec.provenance
    declaration = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": derived,
        "languages": list(spec.languages), "tasks": list(spec.tasks), "artifacts": artifacts, "splits": split_decl,
        "provenance": {
            "status": "complete", "synthetic": old["synthetic"],
            "description": f"{dataset}@{version} 的修正版，窗口和混合音频不变：每条记录加注册前 3 秒里他人说话的秒数"
                           f"（labels.enroll_others_s），不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒的记为注册含他人声"
                           "（enroll_condition = others_speech）并移入同名加 -enrollmix 的划分；"
                           + ("AISHELL-4 有 3 条目标在场样本的注册其实是同场另一个人，改取目标的另一条语句，"
                              "1 条无法确认目标而删除。" if dataset == "ts_asr_real" else "")
                           + "生成脚本 scripts/ts_real/enroll_overlap.py。",
            "sources": [*old.get("sources", []), f"{dataset}@{version}"],
        },
    }
    print(dataset, derived, {s: dict(c) for s, c in report.items()}, flush=True)
    if args.no_register:
        return
    path = REPO / "catalog" / f"{dataset}.yaml"
    rows = list(yaml.safe_load(path.read_text()))
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", dataset, derived, sum(map(len, splits.values())), "records")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    catalog = load_catalog(args.catalog)
    corpora = annotations(catalog, roots)
    for dataset, version in DERIVED:
        derive(dataset, version, catalog, roots, corpora, args)


if __name__ == "__main__":
    main()
