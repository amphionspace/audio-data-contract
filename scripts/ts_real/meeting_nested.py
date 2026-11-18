#!/usr/bin/env python3
"""ts_asr_real meeting-v3: meeting-v2 without the segments that lie inside another speaker's utterance.

meeting-v1 cut one segment per speaker turn, so a short interjection inside someone else's longer utterance became
a segment of its own while the longer speaker's segment holds the same audio. The speaker-enroll service never sends
those: its MOSS segments follow one timeline and never overlap (0 of 300 adjacent segments in the badcase bundle
``tsasr-cross-speaker-output-20261116``), and only 4 of its 344 segments lie half or more inside one utterance of a
person other than the segment's main talker, none 70% or more. meeting-v2 had 686 such segments (10.6%), 351 of
them wholly inside; AmphionASR 11.06 output something for 28.9% of their absent requests against 5.1% elsewhere on
the downstream's 12 meetings, 35% of all its false alarms there.

A segment goes when one utterance of another speaker covers ``INSIDE_OTHER`` or more of it; all its requests go
with it. The interjection itself stays covered: it lies inside the longer speaker's segment, which is sent to the
interjecting person's box as a present request when the whole utterance falls in it. Records keep their IDs and
audio (the index points at meeting-v1's files); ``nested.jsonl`` lists each dropped segment.

    python scripts/ts_real/meeting_nested.py --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

_spec = importlib.util.spec_from_file_location("meeting_quarantine", Path(__file__).resolve().parent / "meeting_quarantine.py")
quarantine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(quarantine)
DATASET_ID, SPLITS, derive, read_jsonl, register = (quarantine.DATASET_ID, quarantine.SPLITS, quarantine.derive,
                                                    quarantine.read_jsonl, quarantine.register)

SOURCE = "meeting-v2-20261117"
VERSION = "meeting-v3-20261117"
INSIDE_OTHER = 0.5  # share of a segment one utterance of another speaker covers; see the module docstring


def inside_other(owner, duration, utts):
    """Largest share of the segment covered by one utterance of someone other than ``owner``.

    ``utts`` are the record's ``metadata.window_utts``: already clipped to the segment."""
    return max((u["duration"] for u in utts if u["speaker"] != f"aishell4:{owner}"), default=0.0) / duration


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[DATASET_ID])
    if (data_root / "versions" / VERSION).exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    records = {split: read_jsonl(data_root / "versions" / SOURCE / "records" / f"{split}.jsonl.gz") for split in SPLITS}
    segments, nested = set(), {}
    for rows in records.values():
        for r in rows:
            cut, lab = r["audio_slots"][1]["ref"]["cut_id"], r["labels"]
            segments.add(cut)
            share = inside_other(lab["segment_speaker"], lab["duration_s"], r["metadata"]["window_utts"])
            if share >= INSIDE_OTHER and cut not in nested:
                nested[cut] = {"cut_id": cut, "recording": lab["recording"], "start": lab["window_start_s"],
                               "duration": lab["duration_s"], "speaker": lab["segment_speaker"],
                               "inside_other": round(share, 3)}
    artifacts, split_decl, dropped = derive(data_root, SOURCE, VERSION, records, nested, "；去掉了落在别人话里的插话段")
    kept = {split: split_decl[split]["statistics"]["records"] for split in SPLITS}
    out = data_root / "source" / VERSION
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "nested.jsonl", "w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(q, ensure_ascii=False) + "\n" for q in sorted(nested.values(), key=lambda q: q["cut_id"]))
    report = {"source": f"{DATASET_ID}@{SOURCE}", "segments": len(segments), "dropped_segments": len(nested),
              "wholly_inside": sum(q["inside_other"] >= 1.0 for q in nested.values()),
              "by_recording": dict(Counter(q["recording"] for q in nested.values())),
              "dropped_records": dict(dropped), "records": kept, "rule": {"inside_other": INSIDE_OTHER}}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    declaration = {"schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
                   "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl, "provenance": {
                       "summary": "目标说话人评测：AISHELL-4 整场会议逐段发送", "status": "complete", "synthetic": "none",
                       "description": (
                           f"{DATASET_ID}@{SOURCE} 去掉落在别人话里的插话段（该段上的全部请求），其余记录、ID 与音频不变"
                           f"（音频索引指向 meeting-v1-20261117 的文件）。按人分段时，别人长句中间的短插话也成了单独一段，"
                           "同一段音频被发两次；下游 speaker-enroll 的 MOSS 分段沿一条时间轴、互不重叠，不会这样发。"
                           f"规则：段内另一个人的某一句话占本段时长 ≥{INSIDE_OTHER:g}，就去掉这段（下游 badcase 包 344 段里只有 4 段达到，"
                           "没有一段达到 0.7）。插话本身仍在外层长段里，作为插话人在场的请求保留。"
                           "去掉的段见 source/<版本>/nested.jsonl，统计见 source/<版本>/report.json。"
                           "只用于评测，不进训练。生成脚本 scripts/ts_real/meeting_nested.py。"),
                       "sources": [f"{DATASET_ID}@{SOURCE}"]}}
    if args.no_register:
        return
    register(SOURCE, VERSION, declaration)
    print("registered", VERSION, kept, flush=True)


if __name__ == "__main__":
    main()
