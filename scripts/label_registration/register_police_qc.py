"""Register the ASR quality-check verdicts of the single-term police sets as new versions plus views.

police_terms_single@v1-20261022 (test) and police_terms_single_train@v1-20261023 (train) were synthesised with
Qwen3-TTS, transcribed by the shared Qwen3-ASR-1.7B and checked by pinyin alignment of the transcript against the
term (amphiondata feat/police-terms-single[-train], scripts/synthetic/run_police_terms_single.py `asr` / `qc`).
Each new version keeps every supervision of its parent (text unchanged) and writes
- custom.qc: the verdict of that recording: {take, duration, hypothesis, syllables, substituted, extra, missing,
  chars_exact, pass, reason}; reason is absent for "pass", else extra_speech / missing_speech / runaway;
- custom.firered_crosscheck (test only): {hypothesis, would_reject: true, applied: false} for recordings the
  FireRedASR2-AED cross-check flagged; the cross-check was tried and not adopted (it disagreed with listening).
Rows that were synthesised and checked but never shipped (rejected by the check, or beyond the per-term quota) have no
recording in the parent, so their verdicts go to the quality-report artifact `qc_not_shipped` (one row per id:
{id, term, qc, asr_hypothesis, firered_crosscheck}); qc is null for ids that were transcribed but not scored.

    python scripts/label_registration/register_police_qc.py --root /workspace/data --catalog catalog \
        --test-run DIR/police-terms-single-20261022 --train-run DIR/police-terms-single-train-20261023 \
        --output catalog/police_terms_qc.yaml --views views/police_terms_qc.yaml
"""

import argparse
import copy
import gzip
import json
from pathlib import Path

from common import artifact, new_version_dir, write_declaration_file, write_jsonl_gz

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact

ROOTS_FILE = "registry/roots.json"
SETS = {  # dataset -> (parent, new version, split, run-dir option)
    "police_terms_single": ("v1-20261022", "qc-v1-20261022", "test", "test_run"),
    "police_terms_single_train": ("v1-20261023", "qc-v1-20261023", "train", "train_run"),
}
CODE = {
    "police_terms_single": "amphiondata feat/police-terms-single scripts/synthetic/run_police_terms_single.py",
    "police_terms_single_train": "amphiondata feat/police-terms-single-train scripts/synthetic/run_police_terms_single.py --split train",
}


def read_jsonl(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def load_run(run):
    run = Path(run)
    qc = {r["id"]: {k: v for k, v in r.items() if k not in ("id", "term")} for r in read_jsonl(run / "qc.jsonl")}
    terms = {r["id"]: r["term"] for r in read_jsonl(run / "qc.jsonl")}
    asr = {r["id"]: r["hypothesis"] for r in read_jsonl(run / "asr.jsonl")}
    firered_path = run / "firered-crosscheck-rejected.jsonl"
    firered = {r["id"]: r["hypothesis"] for r in read_jsonl(firered_path)} if firered_path.exists() else {}
    if set(qc) - set(asr):
        raise SystemExit(f"{run}: qc ids without an asr row")
    return qc, terms, asr, firered


def register(dataset, args, catalog, roots):
    parent, version, split, option = SETS[dataset]
    qc, terms, asr, firered = load_run(getattr(args, option))
    source = catalog.get(dataset, parent).to_dict()
    path = resolve_artifact(catalog, dataset, parent, f"{split}_supervisions", roots)
    out = new_version_dir(args.root, dataset, version)
    shipped, tally = set(), {"pass": 0, "firered flagged": 0}

    def supervisions():
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["id"] not in qc:
                    raise SystemExit(f"{dataset}: shipped row {row['id']} has no qc verdict")
                shipped.add(row["id"])
                verdict = qc[row["id"]]
                tally["pass"] += bool(verdict["pass"])
                custom = {**(row.get("custom") or {}), "qc": verdict}
                if row["id"] in firered:
                    custom["firered_crosscheck"] = {
                        "hypothesis": firered[row["id"]], "would_reject": True, "applied": False}
                    tally["firered flagged"] += 1
                row["custom"] = custom
                yield row

    name = f"{dataset}_supervisions_{split}_qc.jsonl.gz"
    count, size, digest = write_jsonl_gz(out / "manifests" / name, supervisions())
    rest = [
        {"id": i, "term": terms.get(i), "qc": qc.get(i), "asr_hypothesis": asr.get(i),
         "firered_crosscheck": firered.get(i)}
        for i in sorted(set(qc) | set(asr) | set(firered)) if i not in shipped
    ]
    rest_count, rest_size, rest_digest = write_jsonl_gz(out / "evidence" / "qc_not_shipped.jsonl.gz", rest)
    facts = {
        "supervisions": count, "qc verdicts": len(qc), "asr rows": len(asr), "not shipped": rest_count,
        "not shipped, qc failed": sum(1 for r in rest if r["qc"] and not r["qc"]["pass"]),
        "not shipped, qc passed (beyond quota)": sum(1 for r in rest if r["qc"] and r["qc"]["pass"]),
        "not shipped, asr only": sum(1 for r in rest if r["qc"] is None),
        "shipped with qc pass": tally["pass"],
    }
    if firered:
        facts["firered flagged (shipped)"] = tally["firered flagged"]
        facts["firered flagged (not shipped)"] = sum(1 for r in rest if r["firered_crosscheck"])
    recordings = copy.deepcopy(next(a for a in source["artifacts"] if a["name"] == f"{split}_recordings"))
    report = copy.deepcopy(next(a for a in source["artifacts"] if a["name"] == "report"))
    sup = artifact(f"{split}_supervisions_qc", "lhotse-supervisions", dataset, version,
                   f"manifests/{name}", size, digest, record_count=count)
    evidence = artifact("qc_not_shipped", "quality-report", dataset, version, "evidence/qc_not_shipped.jsonl.gz",
                        rest_size, rest_digest, record_count=rest_count)
    statistics = copy.deepcopy(source["splits"][split]["statistics"])
    declaration = {
        "schema_version": source["schema_version"], "dataset_id": dataset, "version": version,
        "languages": list(source["languages"]), "tasks": list(source["tasks"]), "aliases": [],
        "artifacts": [recordings, sup, report, evidence],
        "splits": {split: {
            "artifacts": {"recordings": [recordings["name"]], "supervisions": [sup["name"]],
                          "report": ["report"], "qc_not_shipped": ["qc_not_shipped"]},
            "statistics": statistics,
        }},
        "recipe_parameters": {"adds": ["custom.qc"] + (["custom.firered_crosscheck"] if firered else [])},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{parent}",
            "description": (
                f"{dataset}@{parent} 的 {count} 条录音，加上逐条质检结果：custom.qc 是共享 Qwen3-ASR-1.7B 转写后与术语按拼音"
                "对齐得到的多出/缺少/替换音节数、是否字全对、是否通过及未通过原因。"
                + ("custom.firered_crosscheck 标出 FireRedASR2-AED 交叉核对会拒绝的录音（试过未采用）。" if firered else "")
                + f"合成并检查过但没有入选的 {rest_count} 条（被检查拒绝、超出每术语名额或只转写未打分）在证据文件 "
                "qc_not_shipped 里，每条一行，没有录音。录音和文本沿用父版本。"
                "脚本 scripts/label_registration/register_police_qc.py。"),
            "facts": facts,
        },
    }
    view = {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/qc", "version": version,
        "source": {"dataset_id": dataset, "version": parent},
        "result": {"dataset_id": dataset, "version": version},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "asr-pinyin-qc", "version": version.removeprefix("qc-"), "kind": "annotate",
            "writes": ["metadata.qc"] + (["metadata.firered_crosscheck"] if firered else []),
            "parameters": {
                "asr_model": "Qwen3-ASR-1.7B (shared vLLM server)",
                "rule": "pinyin alignment without tones (NFKC, punctuation removed, digits spelled out); "
                        "extra / missing syllables or reaching the code limit fail, substitutions only pass",
                "failure_reasons": ["extra_speech", "missing_speech", "runaway"],
                "firered_crosscheck": "FireRedASR2-AED, flagged rows kept as labels, not applied" if firered else None,
                "tool": CODE[dataset], "counts": facts,
                "label_sha256": {"supervisions": digest, "qc_not_shipped": rest_digest},
                "script": "scripts/label_registration/register_police_qc.py",
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
    parser.add_argument("--test-run", type=Path, required=True)
    parser.add_argument("--train-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / ROOTS_FILE).read_text())
    pairs = [register(dataset, args, catalog, roots) for dataset in SETS]
    write_declaration_file(args.output, [d for d, _ in pairs], "警务单说术语集的 ASR 质检结果")
    write_declaration_file(args.views, [v for _, v in pairs], "警务单说术语集 ASR 质检结果的 view")


if __name__ == "__main__":
    main()
