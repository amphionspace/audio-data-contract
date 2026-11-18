#!/usr/bin/env python3
"""ts_asr_real meeting-v2: meeting-v1 without the segments whose annotation the automatic checks reject.

Two checks ran on every segment of ``meeting-v1-20261117`` (inputs under ``source/meeting-v2-20261117/qc/``):

* text: a plain-ASR transcript of the segment (AmphionASR 11.06 delivery package, ``asr`` mode, temperature 0).
  Where only the segment's speaker is annotated, a run of at least ``MISSING_RUN`` consecutive transcript characters
  that the annotation lacks means the annotation left out speech (both sides keep only letters, digits and CJK);
* speaker: the ECAPA embedding of the segment's solo part against every speaker's meeting profile (the voice-check
  profiles of the build). With at least ``SPEAKER_SOLO`` s of solo speech, another speaker beating the labelled one by
  ``SPEAKER_MARGIN`` or more means the label is wrong. Shorter solo parts give noisy embeddings and are not judged.

A rejected segment loses all its requests (a present target's reference may be incomplete, an absent target may be
the unannotated voice). Records keep their meeting-v1 IDs and audio (the index points at meeting-v1's files), so the
two versions compare record by record; ``quarantine.jsonl`` lists each rejected segment with its reason.

    python scripts/ts_real/meeting_quarantine.py --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import unicodedata
from collections import Counter
from pathlib import Path

import yaml

from audio_data_contract import load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

REPO = Path(__file__).resolve().parents[2]
DATASET_ID = "ts_asr_real"
SOURCE = "meeting-v1-20261117"
VERSION = "meeting-v2-20261117"
SPLITS = ("meeting-aishell4-neg", "meeting-aishell4-pos")
MISSING_RUN = 3  # consecutive transcript characters the annotation lacks
SPEAKER_SOLO = 3.0  # s of solo speech needed to judge the speaker
SPEAKER_MARGIN = 0.1  # cosine by which another speaker's profile beats the labelled one


def read_jsonl(path):
    with (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else open(path, encoding="utf-8")) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def chars(text):
    """Letters, digits and CJK ideographs of ``text`` (NFKC), so punctuation and spaces never count."""
    return "".join(c for c in unicodedata.normalize("NFKC", text) if c.isalnum())


def longest_missing_run(reference, hypothesis):
    """Longest run of consecutive ``hypothesis`` characters inserted against ``reference`` on a minimum-edit path."""
    n, m = len(reference), len(hypothesis)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(cost[i - 1][j] + 1, cost[i][j - 1] + 1,
                             cost[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]))
    i, j, run, best = n, m, 0, 0
    while i or j:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]):
            i, j, run = i - 1, j - 1, 0
        elif j and cost[i][j] == cost[i][j - 1] + 1:
            j, run = j - 1, run + 1
            best = max(best, run)
        else:
            i, run = i - 1, 0
    return best


def reasons(segment, transcript, speaker_check):
    """Why a segment is rejected ([] when it is kept)."""
    out = []
    owner = segment["owner"]
    utts = segment["utts"]
    if transcript is not None and all(u["speaker"].endswith(":" + owner) for u in utts):
        run = longest_missing_run(chars("".join(u["text"] for u in utts)), chars(transcript))
        if run >= MISSING_RUN:
            out.append({"reason": "annotation_missing_speech", "missing_run": run})
    if (speaker_check is not None and speaker_check["solo_s"] >= SPEAKER_SOLO
            and speaker_check["best_other_sim"] - speaker_check["owner_sim"] >= SPEAKER_MARGIN):
        out.append({"reason": "speaker_label", "owner_sim": speaker_check["owner_sim"],
                    "best_other": speaker_check["best_other"], "best_other_sim": speaker_check["best_other_sim"]})
    return out


def derive(data_root, source, version, records, drop, split_note):
    """Write ``version`` from ``source``: its records except those whose mixture is in ``drop``.

    Records keep their IDs and audio (the index rows are ``source``'s, so they point at the same files); ``split_note``
    is appended to each split's provenance. Returns (artifacts, split declarations, dropped records per split)."""
    target = data_root / "versions" / version
    index = {row["cut_id"]: row for row in read_jsonl(data_root / "versions" / source / "audio-index.jsonl.gz")}
    kept, used, dropped = {}, set(), Counter()
    for split, rows in records.items():
        kept[split] = []
        for r in rows:
            cut = r["audio_slots"][1]["ref"]["cut_id"]
            if cut in drop:
                dropped[split] += 1
                continue
            for slot in r["audio_slots"]:
                slot["ref"]["version"] = version
                used.add(slot["ref"]["cut_id"])
            kept[split].append(r)
    synth = _synth()
    artifacts, split_decl = [], {}
    rows = [index[c] for c in sorted(used)]
    synth.write_jsonl_gz(target / "audio-index.jsonl.gz", rows)
    artifacts.append({"name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
                      "relative_path": f"versions/{version}/audio-index.jsonl.gz",
                      "sha256": synth.sha256_file(target / "audio-index.jsonl.gz"), "metadata": {"record_count": len(rows)}})
    source_spec = yaml.safe_load((REPO / "catalog" / f"{DATASET_ID}.yaml").read_text())
    source_spec = next(s for s in source_spec if s["version"] == source)
    for split in SPLITS:
        path = target / "records" / f"{split}.jsonl.gz"
        synth.write_jsonl_gz(path, kept[split])
        artifacts.append({"name": f"{split}-records", "kind": "audio-records", "root_alias": DATASET_ID,
                          "relative_path": f"versions/{version}/records/{split}.jsonl.gz", "sha256": synth.sha256_file(path),
                          "metadata": {"record_count": len(kept[split])}})
        seconds = sum(r["audio_slots"][1]["ref"]["duration"] for r in kept[split])
        split_decl[split] = {"artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]}, "task": "ts_asr",
                             "statistics": {"records": len(kept[split]), "duration_hours": round(seconds / 3600, 4),
                                            "duration_basis": "Mixture duration"},
                             "provenance": {"description": source_spec["splits"][split]["provenance"]["description"]
                                            + split_note}}
    return artifacts, split_decl, dropped


def register(source, version, declaration):
    """Append ``declaration`` to the catalog and mark ``source`` superseded by it (other rows stay byte for byte)."""
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    text = path.read_text()
    marker = f"  version: {source}\n"
    head, tail = text.split(marker, 1)
    # Only the version's top-level provenance sits at this indent (its splits' provenance is deeper).
    tail = tail.replace("\n  provenance:\n", f"\n  provenance:\n    superseded_by: {DATASET_ID}@{version}\n", 1)
    new_text = head + marker + tail + yaml.safe_dump([declaration], allow_unicode=True, sort_keys=False, width=512)
    specs = [s for s in load_catalog(REPO / "catalog") if not (s.dataset_id == DATASET_ID and s.version == source)]
    validate_catalog([*specs, *(DatasetSpec.from_dict(d) for d in yaml.safe_load(new_text)
                                if d["version"] in (source, version))])
    path.write_text(new_text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[DATASET_ID])
    source, target = data_root / "versions" / SOURCE, data_root / "versions" / VERSION
    if target.exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    qc = data_root / "source" / VERSION / "qc"
    transcripts = {r["cut_id"]: r["text"] for r in read_jsonl(qc / "asr.jsonl")}
    speaker = {r["cut_id"]: r for r in read_jsonl(qc / "speaker.jsonl")}
    records = {split: read_jsonl(source / "records" / f"{split}.jsonl.gz") for split in SPLITS}
    segments = {}
    for rows in records.values():
        for r in rows:
            cut = r["audio_slots"][1]["ref"]["cut_id"]
            segments.setdefault(cut, {"owner": r["labels"]["segment_speaker"], "utts": r["metadata"]["window_utts"],
                                      "recording": r["labels"]["recording"], "start": r["labels"]["window_start_s"],
                                      "duration": r["labels"]["duration_s"]})
    if set(segments) - set(transcripts) or set(segments) - set(speaker):
        raise ValueError("QC inputs do not cover every segment of " + SOURCE)
    rejected = {}
    for cut, segment in sorted(segments.items()):
        why = reasons(segment, transcripts[cut], speaker[cut])
        if why:
            rejected[cut] = {"cut_id": cut, "recording": segment["recording"], "start": segment["start"],
                             "duration": segment["duration"], "speaker": segment["owner"],
                             "transcript": transcripts[cut], "annotation": "".join(u["text"] for u in segment["utts"]),
                             "reasons": why}
    artifacts, split_decl, dropped = derive(data_root, SOURCE, VERSION, records, rejected, "；去掉了自动核对判定标注有误的段")
    kept = {split: split_decl[split]["statistics"]["records"] for split in SPLITS}
    by_reason = Counter(w["reason"] for q in rejected.values() for w in q["reasons"])
    out = data_root / "source" / VERSION
    with open(out / "quarantine.jsonl", "w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(q, ensure_ascii=False) + "\n" for q in rejected.values())
    report = {"source": f"{DATASET_ID}@{SOURCE}", "segments": len(segments), "rejected_segments": len(rejected),
              "by_reason": dict(by_reason), "by_recording": dict(Counter(q["recording"] for q in rejected.values())),
              "dropped_records": dict(dropped), "records": kept,
              "rule": {"missing_run": MISSING_RUN, "speaker_solo_s": SPEAKER_SOLO, "speaker_margin": SPEAKER_MARGIN}}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    declaration = {"schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
                   "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl, "provenance": {
                       "summary": "目标说话人评测：AISHELL-4 整场会议逐段发送", "status": "complete", "synthetic": "none",
                       "description": (
                           f"{DATASET_ID}@{SOURCE} 去掉自动核对判定标注有误的段（该段上的全部请求），其余记录、ID 与音频不变"
                           f"（音频索引指向 {SOURCE} 的文件）。核对两项，输入在 source/{VERSION}/qc/："
                           f"文本：AmphionASR 11.06 交付包普通识别模式转写每段，段内只标了一个人时，转写里有连续 ≥{MISSING_RUN} 个字"
                           "标注里没有（只比字母、数字和汉字），判为标注漏了说话；"
                           f"说话人：段内独自说话 ≥{SPEAKER_SOLO:g} 秒时，段的 ECAPA 声纹与会上另一人的平均声纹比与标注的人高 ≥{SPEAKER_MARGIN:g}，"
                           "判为标错人（独自说话更短的段声纹不可靠，不判）。去掉的段与原因见 source/<版本>/quarantine.jsonl，"
                           "统计见 source/<版本>/report.json。多人同时说话的段只做了说话人核对。"
                           "只用于评测，不进训练。生成脚本 scripts/ts_real/meeting_quarantine.py。"),
                       "sources": [f"{DATASET_ID}@{SOURCE}"]}}
    if args.no_register:
        return
    register(SOURCE, VERSION, declaration)
    print("registered", VERSION, kept, flush=True)


def _synth():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ts_benchmark_build", REPO / "scripts" / "ts_benchmark" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    main()
