#!/usr/bin/env python3
"""ts_asr_real meeting-v5: meeting-v4 without the segments whose annotation misses speech (meeting_quarantine.py's text
check, which needs a plain-ASR transcript per segment and so could not run when meeting-v4 was built).

Input: ``source/meeting-v5-20261125/qc/asr.jsonl``, AmphionASR 11.17 (deployment package) in plain-ASR mode, temperature
0, one row per base segment (``-mix``) and enrollment of meeting-v4. Rule as in meeting_quarantine.py: where only the
segment's speaker is annotated, a run of at least ``MISSING_RUN`` consecutive transcript characters that the annotation
lacks (letters, digits and CJK only) means the annotation left out speech. A rejected segment loses every request on it,
in every control (paired through metadata.base). Records keep their meeting-v4 IDs and audio, so results on meeting-v4
carry over record by record; ``quarantine.jsonl`` lists each rejected segment.

    python scripts/ts_real/meeting_text_check.py --roots /workspace/data/registry/roots.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("meeting_quarantine", HERE / "meeting_quarantine.py")
quarantine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(quarantine)
DATASET_ID, REPO = quarantine.DATASET_ID, quarantine.REPO
SOURCE = "meeting-v4-20261125"
VERSION = "meeting-v5-20261125"


def segment_key(record):
    base = record["metadata"].get("base")
    if base is not None:
        return base["recording"], base["segment_index"]
    return record["labels"]["recording"], record["metadata"]["segment_index"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[DATASET_ID])
    if (data_root / "versions" / VERSION).exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    spec = next(s for s in yaml.safe_load((REPO / "catalog" / f"{DATASET_ID}.yaml").read_text()) if s["version"] == SOURCE)
    splits = tuple(sorted(spec["splits"]))
    records = {split: quarantine.read_jsonl(data_root / "versions" / SOURCE / "records" / f"{split}.jsonl.gz")
               for split in splits}
    transcripts = {r["cut_id"]: r["text"] for r in quarantine.read_jsonl(data_root / "source" / VERSION / "qc" / "asr.jsonl")}
    segments = {}
    for rows in records.values():
        for r in rows:
            if r["metadata"].get("base") is None:
                lab = r["labels"]
                segments.setdefault(segment_key(r), {
                    "cut_id": r["audio_slots"][1]["ref"]["cut_id"], "owner": lab["segment_speaker"],
                    "corpus": lab["corpus"], "utts": r["metadata"]["window_utts"], "recording": lab["recording"],
                    "start": lab["window_start_s"], "duration": lab["duration_s"]})
    missing = [s["cut_id"] for s in segments.values() if s["cut_id"] not in transcripts]
    if missing:
        raise ValueError(f"{len(missing)} segments of {SOURCE} have no transcript, e.g. {missing[:3]}")
    rejected = {}
    for key, s in sorted(segments.items()):
        why = quarantine.reasons(s, transcripts[s["cut_id"]], None)
        if why:
            rejected[key] = {"cut_id": s["cut_id"], "corpus": s["corpus"], "recording": s["recording"], "start": s["start"],
                             "duration": s["duration"], "speaker": s["owner"], "transcript": transcripts[s["cut_id"]],
                             "annotation": "".join(u["text"] for u in s["utts"]), "reasons": why}
    # derive() drops by mixture cut id; the controls' own mixtures (headsets, noise) share the base segment's key.
    drop = {r["audio_slots"][1]["ref"]["cut_id"] for rows in records.values() for r in rows if segment_key(r) in rejected}
    quarantine.SPLITS = splits
    artifacts, split_decl, dropped = quarantine.derive(data_root, SOURCE, VERSION, records, drop,
                                                       "；去掉了文本核对判定标注漏字的段")
    kept = {split: split_decl[split]["statistics"]["records"] for split in splits}
    out = data_root / "source" / VERSION
    with open(out / "quarantine.jsonl", "w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(q, ensure_ascii=False) + "\n" for q in rejected.values())
    report = {"source": f"{DATASET_ID}@{SOURCE}", "segments": len(segments), "rejected_segments": len(rejected),
              "by_corpus": dict(Counter(q["corpus"] for q in rejected.values())),
              "by_recording": dict(Counter(q["recording"] for q in rejected.values())),
              "dropped_records": dict(dropped), "records": kept, "rule": {"missing_run": quarantine.MISSING_RUN}}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    declaration = {"schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
                   "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl, "provenance": {
                       "summary": spec["provenance"]["summary"], "status": "complete", "synthetic": "none",
                       "description": (
                           f"{DATASET_ID}@{SOURCE} 去掉文本核对判定标注漏字的段（该段在所有对照里的全部请求），其余记录、ID 与音频不变"
                           f"（音频索引指向 {SOURCE} 的文件）。核对同 meeting_quarantine.py：AmphionASR 11.17 交付包普通识别模式"
                           f"（temperature 0）转写每段，段内只标了一个人时，转写里有连续 ≥{quarantine.MISSING_RUN} 个字标注里没有"
                           "（只比字母、数字和汉字），判为标注漏了说话。输入在 source/<版本>/qc/，去掉的段与原因见 quarantine.jsonl，"
                           "统计见 report.json。说话人核对已在 meeting-v4 生成时做过。只用于评测，不进训练。"
                           "生成脚本 scripts/ts_real/meeting_text_check.py。"),
                       "sources": [f"{DATASET_ID}@{SOURCE}"]}}
    if args.no_register:
        return
    quarantine.register(SOURCE, VERSION, declaration)
    print("registered", VERSION, kept, flush=True)


if __name__ == "__main__":
    main()
