"""Register the MagicData-RAMC speaker-identity labels as magicdata_ramc@speaker-identity-v1-20261028 plus a view.

RAMC gives each speaker of a new conversation a new ID, so one person can sit under several IDs and some train IDs
sound like dev/test speakers (generator: scripts/ts_robust/ramc_voice_identities.py, ERes2NetV2 cosine >= 0.60).
The version keeps every row of magicdata_ramc@clean-dual-pass-20261027 train supervisions unchanged and adds
custom.speaker_identity = {"same_voice": [{"speaker", "cosine"}, ...], "heldout_match": {"unit", "cosine"} | null}:
the other IDs this speaker shares a voice with, and the dev/test unit a train ID matches. The generator's output
(identities.json, report.json) and the evidence behind the threshold (suspects.json: cosine distributions and
cross-recording pairs; heldout_match.json: train speakers matching held-out units per threshold) are copied into the
version directory as artifacts. Unit embeddings (.npz) are features, not labels, and are not registered.

    python scripts/label_registration/register_ramc_identity.py --root /workspace/data \
        --catalog catalog --identities-dir IDENTITIES_DIR --evidence-dir EVIDENCE_DIR \
        --output catalog/ramc_speaker_identity.yaml --views views/ramc_speaker_identity.yaml
"""

import argparse
import gzip
import hashlib
import json
import shutil
from collections import defaultdict
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

DATASET, PARENT, VERSION = "magicdata_ramc", "clean-dual-pass-20261027", "speaker-identity-v1-20261028"
PREFIX = "magicdata_ramc:"
GENERATOR = "scripts/ts_robust/ramc_voice_identities.py"
EVIDENCE = [
    ("identities", "json-metadata", "identities.json", "identities-dir"),
    ("identities_report", "json-metadata", "report.json", "identities-dir"),
    ("suspects", "quality-report", "suspects.json", "evidence-dir"),
    ("heldout_match", "quality-report", "heldout_match.json", "evidence-dir"),
]


def identity_index(identities):
    same = defaultdict(list)
    for a, b, cosine in identities["same_voice"]:
        same[a.removeprefix(PREFIX)].append({"speaker": b.removeprefix(PREFIX), "cosine": cosine})
        same[b.removeprefix(PREFIX)].append({"speaker": a.removeprefix(PREFIX), "cosine": cosine})
    drop = {k.removeprefix(PREFIX): {"unit": v[0], "cosine": v[1]} for k, v in identities["drop"].items()}
    return {k: sorted(v, key=lambda x: x["speaker"]) for k, v in same.items()}, drop


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--identities-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    spec = catalog.get(DATASET, PARENT)
    source = resolve_artifact(catalog, DATASET, PARENT, "train_supervisions", roots)
    verify_artifact_file(spec.artifact("train_supervisions"), source)
    identities = json.loads((args.identities_dir / "identities.json").read_text())
    same, drop = identity_index(identities)
    out = new_version_dir(args.root, DATASET, VERSION)
    facts = {"rows": 0, "rows with same-voice partners": 0, "rows matching a dev/test voice": 0}
    speakers = set()

    def rows():
        with gzip.open(source, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                speaker = row["speaker"]
                label = {"same_voice": same.get(speaker, []), "heldout_match": drop.get(speaker)}
                row["custom"] = {**(row.get("custom") or {}), "speaker_identity": label}
                facts["rows"] += 1
                facts["rows with same-voice partners"] += bool(label["same_voice"])
                facts["rows matching a dev/test voice"] += label["heldout_match"] is not None
                speakers.add(speaker)
                yield row

    name = "magicdata_ramc_supervisions_train_speaker_identity.jsonl.gz"
    count, size, digest = write_jsonl_gz(out / name, rows())
    if count != facts["rows"] or count != spec.artifact("train_supervisions").metadata["record_count"]:
        raise SystemExit(f"row count mismatch {count} {facts}")
    artifacts = [
        artifact("train_supervisions_speaker_identity", "lhotse-supervisions", DATASET, VERSION, name, size, digest,
                 record_count=count, punctuated=False)
    ]
    inputs = {}
    for art_name, kind, filename, which in EVIDENCE:
        origin = getattr(args, which.replace("-", "_")) / filename
        temporary = out / f"{filename}.tmp"
        shutil.copyfile(origin, temporary)
        temporary.replace(out / filename)
        inputs[filename] = sha256(out / filename)
        artifacts.append(artifact(art_name, kind, DATASET, VERSION, filename, (out / filename).stat().st_size,
                                  inputs[filename]))
    parent = spec.to_dict()
    recordings = next(a for a in parent["artifacts"] if a["name"] == "train_recordings")
    facts.update({"speakers": len(speakers), "speakers with same-voice partners": len(same),
                  "same-voice pairs": len(identities["same_voice"]),
                  "train speakers matching a dev/test voice": len(drop)})
    declaration = {
        "schema_version": parent["schema_version"], "dataset_id": DATASET, "version": VERSION,
        "languages": ["zh"], "tasks": ["asr"], "aliases": [],
        "artifacts": [recordings] + artifacts,
        "splits": {"train": {
            "artifacts": {"recordings": ["train_recordings"], "supervisions": ["train_supervisions_speaker_identity"],
                          "quality_reports": ["suspects", "heldout_match"],
                          "metadata": ["identities", "identities_report"]},
            "statistics": {"records": count, "duration_hours": parent["splits"]["train"]["statistics"]["duration_hours"],
                           "duration_basis": "sum of supervision durations of the kept rows"},
        }},
        "recipe_parameters": {"adds": ["custom.speaker_identity"], "rows": "all rows of the parent"},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{DATASET}@{PARENT}",
            "description": (
                f"{DATASET}@{PARENT} 全部 {count} 条训练分段，文本等字段与父版本相同，新增 custom.speaker_identity："
                "MagicData-RAMC 每段对话给说话人发新编号，同一个人会挂在几个编号下，部分 train 编号的声纹也与 dev/test 说话人相同。"
                f"same_voice 列出与本编号声纹相似度 ≥ 0.60 的其他编号（{len(identities['same_voice'])} 对，涉及 {len(same)} 个编号），"
                f"heldout_match 记与本编号声纹相同的 dev/test 单元（{len(drop)} 个 train 编号），没有则为 null。"
                "identities.json / report.json 是生成器输出，suspects.json（同编号与不同编号的相似度分布、跨录音疑似同人对）和"
                "heldout_match.json（各阈值下与 dev/test 匹配的 train 编号）是阈值依据。声纹单元嵌入（.npz）是特征不是标注，不登记。"
                f"录音沿用父版本，不复制音频。脚本 scripts/label_registration/register_ramc_identity.py，生成器 {GENERATOR}。"),
            "facts": facts,
        },
    }
    view = {
        "schema_version": "dataset-view/1.0", "view_id": f"{DATASET}/speaker-identity", "version": VERSION,
        "source": {"dataset_id": DATASET, "version": PARENT},
        "result": {"dataset_id": DATASET, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "ramc-speaker-identity", "version": "v1-20261028", "kind": "annotate",
            "writes": ["metadata.speaker_identity"],
            "parameters": {
                "model": "ERes2NetV2 (iic/speech_eres2netv2_sv_zh-cn_16k-common)",
                "unit": "mean embedding per (speaker, recording) over up to 6 clean-pass utterances of 2-8 s",
                "threshold_cosine": identities["threshold"], "seed": 20261028,
                "held_out": identities["held_out"], "train": identities["train"],
                "tool": GENERATOR, "tool_sha256": hashlib.sha256(
                    Path(__file__).resolve().parents[1].joinpath("ts_robust/ramc_voice_identities.py").read_bytes()
                ).hexdigest(),
                "label_inputs": inputs, "counts": facts,
            }}],
        "provenance": {"registered_at": "2026-11-03"},
    }
    write_declaration_file(args.output, [declaration], "magicdata_ramc 说话人身份标注（同声纹编号、与 dev/test 声纹相同的编号）")
    write_declaration_file(args.views, [view], "magicdata_ramc 说话人身份标注的 view")
    print(json.dumps(facts, ensure_ascii=False))


if __name__ == "__main__":
    main()
