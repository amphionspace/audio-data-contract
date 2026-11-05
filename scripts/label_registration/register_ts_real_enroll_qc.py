"""Register the enrollment checks of ts_real_train as three label-carrier versions plus views.

Each version copies the records of a punctuated parent version (ts_real_train@v*-utts-punc-20261102) unchanged and
adds metadata.enrollment_check:
- target-absent records of the AliMeeting / AISHELL-4 / RAMC / AliMeeting-EN splits (scripts in this directory:
  scan_enrolled_in_window.py): {"enrolled_speaker_talk_seconds": s}, the seconds the enrolled speaker really talks in
  the window (0.0 when the check found nothing). A target-absent record with s > 0 is not absent;
- Emilia2 single-speaker records (qc_ts_real_train_v3.py in scripts/ts_robust): {"cosine": c, "expected":
  "same_speaker" | "different_speaker", "pair_cosines": [same, different]}, the ERes2NetV2 cosine of this record's
  enrollment with its window and both cosines of the pair (qc.json, keyed by labels.pair).
The ts_real_train@v2-20261018 RAMC split was checked too (v2-20261018--ramc.tsv) but the punctuated v2 parent has no
RAMC split, so it is not carried. Audio indexes stay the parent's. These versions only carry labels; training recipes
keep pinning the parent versions.

    python scripts/label_registration/register_ts_real_enroll_qc.py --root /workspace/data --catalog catalog \
        --neg-dir NEG_OUT_DIR --pair-qc qc.json --output catalog/ts_real_enroll_qc.yaml \
        --views views/ts_real_enroll_qc.yaml
"""

import argparse
import gzip
import json
from pathlib import Path

from common import (
    artifact,
    new_version_dir,
    sha256,
    write_declaration_file,
    write_jsonl_gz,
)

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact, verify_artifact_file

DATASET = "ts_real_train"
# new version -> (parent, scan version prefix of the TSVs)
VERSIONS = {
    "v1-20261017-utts-enroll-qc-20261021": ("v1-20261017-utts-punc-20261102", "v1-20261017-utts"),
    "v2-20261018-enroll-qc-20261021": ("v2-20261018-utts-punc-20261102", "v2-20261018"),
    "v3-20261020-enroll-qc-20261021": ("v3-20261020-utts-punc-20261102", "v3-20261020"),
}
SAME_FLOOR, DIFF_CEILING = 0.746, 0.493  # thresholds the v3 builder took from the pairs (emilia2_1spk speaker_check)


def load_talk_seconds(neg_dir, prefix, split):
    path = neg_dir / f"{prefix}--{split}.tsv"
    return {k: float(v) for k, v in (line.split("\t") for line in path.read_text().splitlines() if line)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--neg-dir", type=Path, required=True)
    parser.add_argument("--pair-qc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    pair_qc = json.loads(args.pair_qc.read_text())
    scan_report = json.loads((args.neg_dir / "report.json").read_text())
    declarations, views = [], []
    for version, (parent, prefix) in VERSIONS.items():
        spec = catalog.get(DATASET, parent)
        source = spec.to_dict()
        out = new_version_dir(args.root, DATASET, version)
        artifacts = [a for a in source["artifacts"] if a["kind"] == "audio-index"]
        splits, facts, checked, tsv_inputs = {}, {}, [], {}
        for split, info in source["splits"].items():
            records_name = info["artifacts"]["records"][0]
            path = resolve_artifact(catalog, DATASET, parent, records_name, roots)
            verify_artifact_file(spec.artifact(records_name), path)
            has_tsv = (args.neg_dir / f"{prefix}--{split}.tsv").exists()
            talks = load_talk_seconds(args.neg_dir, prefix, split) if has_tsv else {}
            counts = {"records": 0, "target-absent checked": 0, "enrolled speaker talks in window": 0,
                      "pair cosines": 0}

            def rows(path=path, talks=talks, counts=counts, has_tsv=has_tsv):
                with gzip.open(path, "rt", encoding="utf-8") as stream:
                    for line in stream:
                        row = json.loads(line)
                        counts["records"] += 1
                        labels = row["labels"]
                        check = None
                        if has_tsv and labels.get("target_present") is False:
                            seconds = talks.pop(row["id"], 0.0)
                            check = {"enrolled_speaker_talk_seconds": seconds}
                            counts["target-absent checked"] += 1
                            counts["enrolled speaker talks in window"] += seconds > 0
                        elif labels.get("corpus") == "emilia2":
                            same, different = pair_qc[str(labels["pair"])]
                            present = labels["target_present"]
                            check = {"cosine": same if present else different,
                                     "expected": "same_speaker" if present else "different_speaker",
                                     "pair_cosines": [same, different]}
                            counts["pair cosines"] += 1
                        if check:
                            row["metadata"] = {**row.get("metadata", {}), "enrollment_check": check}
                        yield row

            name = f"records_{split}.jsonl.gz"
            count, size, digest = write_jsonl_gz(out / "records" / name, rows())
            if count != counts["records"] or talks:
                raise SystemExit(f"{version}/{split}: count {count} {counts}, unmatched TSV ids {len(talks)}")
            if has_tsv:
                tsv_inputs[f"{prefix}--{split}.tsv"] = sha256(args.neg_dir / f"{prefix}--{split}.tsv")
            records_artifact = artifact(f"{split}_records_enroll_qc", "audio-records", DATASET, version,
                                        f"records/{name}", size, digest, record_count=count,
                                        source=spec.artifact(records_name).relative_path)
            artifacts.append(records_artifact)
            splits[split] = {
                "artifacts": {"records": [records_artifact["name"]], "audio_index": info["artifacts"]["audio_index"]},
                "task": "ts_asr", "statistics": {"records": count}, "provenance": {"preparation_status": "prepared"},
            }
            facts[split] = counts
            checked.append(split)
        has_pairs = any(f["pair cosines"] for f in facts.values())
        if has_pairs:
            pair_name = "pair_cosines.json"
            (out / pair_name).write_bytes(args.pair_qc.read_bytes())
            artifacts.append(artifact("pair_cosines", "quality-report", DATASET, version, pair_name,
                                      (out / pair_name).stat().st_size, sha256(out / pair_name),
                                      pairs=len(pair_qc)))
        declarations.append({
            "schema_version": source["schema_version"], "dataset_id": DATASET, "version": version,
            "languages": list(source["languages"]), "tasks": ["ts_asr"], "aliases": [],
            "artifacts": artifacts, "splits": splits,
            "recipe_parameters": {"adds": ["metadata.enrollment_check"], "rows": "all records of the parent"},
            "provenance": {
                "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
                "source": f"{DATASET}@{parent}",
                "description": (
                    f"{DATASET}@{parent} 的全部记录（{', '.join(checked)}），内容与父版本相同，新增 metadata.enrollment_check："
                    + ("目标缺席记录给出注册说话人在窗口内实际说话的秒数（enrolled_speaker_talk_seconds，大于 0 说明这条并不缺席，"
                       "因为 AliMeeting / AISHELL-4 / RAMC 的说话人编号跨会议通用，从别的会议取的注册人可能也在本窗口里说话）；"
                       if any(f["target-absent checked"] for f in facts.values()) else "")
                    + ("Emilia2 单人配对给出注册音频与窗口的 ERes2NetV2 余弦（cosine，expected 为应该相同还是不同的说话人）"
                       f"和整对的两个余弦，另附 pair_cosines.json（{len(pair_qc)} 对），构建时按 same_floor {SAME_FLOOR} / "
                       f"diff_ceiling {DIFF_CEILING} 剔除了 225 对。" if has_pairs else "")
                    + "音频索引沿用父版本，不复制音频；本版本只带标注，训练配方仍引用父版本。"
                    "脚本 scripts/label_registration/register_ts_real_enroll_qc.py，检查工具 "
                    "scripts/label_registration/scan_enrolled_in_window.py、scripts/ts_robust/qc_ts_real_train_v3.py。"),
                "facts": {s: dict(f) for s, f in facts.items()},
            },
        })
        parameters = {
            "model": "ERes2NetV2 (iic/speech_eres2netv2_sv_zh-cn_16k-common)" if has_pairs else "none (transcript overlap)",
            "tools": ["scripts/label_registration/scan_enrolled_in_window.py", "scripts/ts_robust/qc_ts_real_train_v3.py"],
            "talk_seconds_inputs_sha256": tsv_inputs,
            "counts": {s: dict(f) for s, f in facts.items()},
            "scan_report": {k: v for k, v in scan_report.items() if k.startswith(prefix + "/")},
        }
        if has_pairs:
            parameters.update({"pair_cosines_sha256": sha256(args.pair_qc), "same_floor": SAME_FLOOR,
                               "diff_ceiling": DIFF_CEILING})
        views.append({
            "schema_version": "dataset-view/1.0", "view_id": f"{DATASET}/enroll-qc", "version": version,
            "source": {"dataset_id": DATASET, "version": parent},
            "result": {"dataset_id": DATASET, "version": version},
            "materialization": "full", "lineage_status": "exact",
            "transforms": [{"name": "enrollment-check", "version": "v1-20261021", "kind": "annotate",
                            "writes": ["metadata.enrollment_check"], "parameters": parameters}],
            "provenance": {"registered_at": "2026-11-03"},
        })
        print(version, json.dumps(facts, ensure_ascii=False), flush=True)
    write_declaration_file(args.output, declarations, "ts_real_train 注册音频质检（注册人是否在窗口内说话、说话人相似度）")
    write_declaration_file(args.views, views, "ts_real_train 注册音频质检的 view")


if __name__ == "__main__":
    main()
