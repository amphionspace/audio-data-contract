#!/usr/bin/env python3
"""Register the word-level forced alignments of five zh source corpora as <dataset>@alignment-v1-20261008 plus views.

The alignments were produced on 2026-10-08 by amphiondata (main, 6daabaf "feat: add source alignment and timestamped
meeting data") with Qwen3-ForcedAligner-0.6B on <dataset>@icefall-20260908 train. Every aligned utterance is one
supervision of the new version:
- id / recording_id / start / duration / channel / text / language of the aligned source row (text as aligned);
- custom.alignment (canonical metadata.alignment): {status, items [{text, start, end}], issues, time_reference,
  unit, audio_duration, language}. status is "aligned" or "needs_review"; times are seconds from the start of the
  source segment (time_reference "source_segment_start"); items with zero length stay in the row and are counted in
  issues.
Recordings stay the clean-dual version's (same recording ids as the aligned rows); no audio is copied. Every written
file is read back for counts, bytes and sha256.

    python scripts/label_registration/register_alignments.py --root /workspace/data \
        --catalog catalog --alignments DIR/zh-source-alignment-20261008 \
        --output catalog/zh_source_alignment.yaml --views views/zh_source_alignment.yaml
"""

import argparse
import copy
import glob
import gzip
import json
from pathlib import Path

from common import (
    artifact,
    new_version_dir,
    write_declaration_file,
    write_json,
    write_jsonl_gz,
)

from audio_data_contract import load_catalog

VERSION = "alignment-v1-20261008"
PARENT = "icefall-20260908"
CLEAN = "clean-dual-qwen-moss-v1-20261008"
RECORDINGS = {  # dataset -> recordings artifact of the clean version (same recording ids as the aligned rows)
    "aidatatang": "all_recordings",
    "aishell3": "train_recordings",
    "magicdata": "train_recordings",
    "magicdata_ramc": "train_recordings",
    "primewords": "train_recordings",
}
TOOL = "amphiondata main 6daabaf (forced-alignment-plan/1.0 pipeline)"


def aligned_rows(directory):
    for path in sorted(glob.glob(f"{directory}/alignments/*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                yield {
                    "id": row["source_id"],
                    "recording_id": row["recording_id"],
                    "start": row["start"],
                    "duration": row["duration"],
                    "channel": row["channel"],
                    "text": row["text"],
                    "language": row["language"],
                    "custom": {"alignment": row["alignment"]},
                }


def counted(rows, tally):
    for row in rows:
        alignment = row["custom"]["alignment"]
        tally["rows"] += 1
        tally[alignment["status"]] += 1
        tally["words"] += len(alignment["items"])
        tally["hours"] += row["duration"] / 3600
        yield row


def register(dataset, args, catalog):
    source = catalog.get(dataset, PARENT).to_dict()
    clean = catalog.get(dataset, CLEAN).to_dict()
    directory = Path(args.alignments) / dataset
    progress = json.loads((directory / "progress.json").read_text())
    config = json.loads((directory / "alignment-config.json").read_text())
    plan = json.loads((directory / "plan.json").read_text())
    out = new_version_dir(args.root, dataset, VERSION)
    tally = {"rows": 0, "aligned": 0, "needs_review": 0, "words": 0, "hours": 0.0}
    name = f"{dataset}_supervisions_train_alignment.jsonl.gz"
    count, size, digest = write_jsonl_gz(out / name, counted(aligned_rows(directory), tally))
    if count != progress["total_records"] or count != tally["rows"]:
        raise SystemExit(f"{dataset}: wrote {count}, plan has {progress['total_records']}")
    if (tally["aligned"], tally["needs_review"]) != (
        progress["counts"]["aligned"], progress["counts"]["needs_review"]
    ):
        raise SystemExit(f"{dataset}: status counts differ from progress.json")
    summary = {
        "dataset": f"{dataset}@{PARENT}", "split": plan["split"], "tool": TOOL,
        "aligner": {**config, "model": "Qwen3-ForcedAligner-0.6B"},
        "plan_shards": len(plan["shards"]), "records": count, "counts": progress["counts"],
        "issues": progress["issues"], "version_selection": plan["version_selection"],
    }
    summary_size, summary_digest = write_json(out / "alignment_summary.json", summary)
    recordings = copy.deepcopy(
        next(a for a in clean["artifacts"] if a["name"] == RECORDINGS[dataset])
    )
    recordings["name"] = "train_recordings"
    supervisions = artifact(
        "train_supervisions_alignment_0", "lhotse-supervisions", dataset, VERSION, name, size, digest,
        record_count=count, alignment_status=progress["counts"],
    )
    evidence = artifact(
        "alignment_summary", "json-metadata", dataset, VERSION, "alignment_summary.json",
        summary_size, summary_digest,
    )
    facts = {
        "rows": count, "aligned": tally["aligned"], "needs_review": tally["needs_review"],
        "words": tally["words"], **{f"issues {k}": v for k, v in progress["issues"].items()},
    }
    declaration = {
        "schema_version": source["schema_version"], "dataset_id": dataset, "version": VERSION,
        "languages": list(source["languages"]), "tasks": ["asr"], "aliases": [],
        "artifacts": [recordings, supervisions, evidence],
        "splits": {"train": {
            "artifacts": {"recordings": ["train_recordings"], "supervisions": [supervisions["name"]],
                          "alignment_summary": ["alignment_summary"]},
            "statistics": {"records": count, "duration_hours": round(tally["hours"], 4),
                           "duration_basis": "sum of supervision durations"},
        }},
        "recipe_parameters": {"adds": ["custom.alignment"], "rows": "all rows of the parent train split"},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{PARENT}",
            "description": (
                f"{dataset}@{PARENT} train 全部 {count} 句的词级强制对齐（2026-10-08，Qwen3-ForcedAligner-0.6B，"
                f"amphiondata main 6daabaf）。custom.alignment 含 status（aligned {tally['aligned']} 句 / "
                f"needs_review {tally['needs_review']} 句，后者有零时长或越界的词）、items（每个字或词的文本和起止秒，"
                "从该句开头算起）、issues、time_reference、unit、audio_duration。文本是对齐时所用的原标注文本；"
                f"录音沿用 {dataset}@{CLEAN} 的 train 录音，不复制音频。"
                "脚本 scripts/label_registration/register_alignments.py。"),
            "facts": facts,
        },
    }
    view = {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/alignment", "version": VERSION,
        "source": {"dataset_id": dataset, "version": PARENT},
        "result": {"dataset_id": dataset, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "forced-alignment", "version": "v1-20261008", "kind": "annotate",
            "writes": ["metadata.alignment"],
            "parameters": {
                "model": "Qwen3-ForcedAligner-0.6B", "model_config_sha256": config["model_config_sha256"],
                "qwen_asr_version": config["qwen_asr_version"], "dtype": config["dtype"],
                "attention": config["attention"], "tool": TOOL, "plan_sha256": config["plan_sha256"],
                "plan_schema": plan["schema_version"], "split": plan["split"], "records": count,
                "aligned": tally["aligned"], "needs_review": tally["needs_review"], "issues": progress["issues"],
                "summary_sha256": summary_digest, "label_sha256": digest,
                "script": "scripts/label_registration/register_alignments.py",
            },
        }],
        "provenance": {"registered_at": "2026-11-03"},
    }
    print(dataset, json.dumps(facts, ensure_ascii=False), flush=True)
    return declaration, view


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--alignments", type=Path, required=True, help="directory with one subdirectory per dataset")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    pairs = [register(dataset, args, catalog) for dataset in RECORDINGS]
    write_declaration_file(args.output, [d for d, _ in pairs], "五个中文来源语料的词级强制对齐")
    write_declaration_file(args.views, [v for _, v in pairs], "五个中文来源语料词级强制对齐的 view")


if __name__ == "__main__":
    main()
