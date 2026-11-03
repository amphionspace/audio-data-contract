#!/usr/bin/env python3
"""Register the dual-engine (Qwen3-ASR + MOSS) clean verdicts of the 2026-10-09 runs as <source>@clean-dual-qwen-moss-v1-20261009.

Same pipeline, rule set and row format as the 2026-10-08 versions of primewords, aishell3, aidatatang, magicdata and
magicdata_ramc (catalog/zh_source_clean.yaml): every source supervision keeps its row, `text` is the source transcript
(restored fillers may carry punctuation) and custom.clean holds pass, reason, action, engine_status, per-engine and
cross-engine CER, the review flag and the MOSS speaker turns. Records are never dropped; readers filter on
custom.clean.pass (require_clean_pass). Engine results, rejected rows and the review lists go to evidence/.

Complete runs (aishell2, kespeech, common_voice_zh, talcs, cs_dialogue, cs_dialogue_mix) are registered after every row
of the clean manifests is compared with the source supervisions (same ids in the same order, only text and custom.clean
differ; a rewritten text keeps the source transcript in custom.original_text). The emilia_zh run stopped at 4.4M of 9.8M utterances before any verdict was written; its raw engine outputs are
registered as a partial placeholder that must not be trained on.

Each --run is NAME=DIR, where DIR holds inputs.json and one directory per dataset as written by `amphion-data clean`
(scripts/zh_source_clean/run_clean.py).

    python scripts/zh_source_clean/register_clean_dual.py --root /workspace/data \
        --run batch1=<zh-source-clean-run> --run batch2=<zh-source-clean-batch2-run> \
        --output catalog/zh_source_clean_20261009.yaml --views views/zh_source_clean_20261009.yaml \
        --record /workspace/data/migration/register-clean-dual-v1-20261009
"""

import argparse
import gzip
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from audio_data_contract import load_catalog
from audio_data_contract.declarations import write_declarations

VERSION = "clean-dual-qwen-moss-v1-20261009"
PARENT = "icefall-20260908"
# dataset -> run name; emilia_zh is the placeholder
DATASETS = {
    "aishell2": "batch1", "kespeech": "batch1", "common_voice_zh": "batch1",
    "talcs": "batch2", "cs_dialogue": "batch2", "cs_dialogue_mix": "batch2",
}
PLACEHOLDER = {"emilia_zh": "batch2"}
QWEN, MOSS = "Qwen3-ASR-1.7B", "MOSS-Transcribe-Diarize"
CODE = "amphiondata 3e1e324 (configs/experiments/zh-source-clean-qwen-moss.toml)"
CLEAN_PARAMS = {
    "threshold": 50.0, "agree_threshold": 30.0, "min_tokens": 2, "replace_engine": QWEN,
    "max_replace_ratio": 3.0, "rewrite_agree_threshold": 10.0, "max_hyp_ratio": 3.0,
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def count_lines(path):
    """Full read-back: the gzip CRC catches lost writes."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return sum(1 for _ in stream)


def artifact(root, name, kind, path, **metadata):
    entry = {"name": name, "kind": kind, "root_alias": "aidc_data",
             "relative_path": str(Path(path).relative_to(root)),
             "expected_bytes": Path(path).stat().st_size, "sha256": sha256(path)}
    if metadata:
        entry["metadata"] = metadata
    return entry


DECLARATIONS_ONLY = False  # --declarations-only: rebuild catalog and views from the files already registered


def publish(tmp_writer, destination):
    """Write through `<file>.tmp`, then rename."""
    if DECLARATIONS_ONLY:
        if not destination.is_file():
            raise SystemExit(f"{destination} is missing")
        return
    temporary = destination.with_name(destination.name + ".tmp")
    tmp_writer(temporary)
    temporary.replace(destination)


def copy_file(source, destination):
    publish(lambda tmp: shutil.copyfile(source, tmp), destination)


def gzip_file(source, destination):
    def write(tmp):
        with open(source, "rb") as reader, open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as out:
            shutil.copyfileobj(reader, out, 1 << 22)
    publish(write, destination)


def source_artifacts(root, entry, cuts=False):
    """Recordings (or cuts) of the clean input as catalog artifacts pointing at the registered source files."""
    block = entry["cuts"] if cuts else entry["recordings"]
    parts = block.get("sources") or [block]
    name = "train_cuts" if cuts else "train_recordings"
    kind = "lhotse-cuts" if cuts else "lhotse-recordings"
    artifacts = []
    for index, part in enumerate(parts):
        path = Path(part["path"])
        if sha256(path) != part["sha256"]:
            raise SystemExit(f"{path}: sha256 differs from inputs.json")
        suffix = f"_{index}" if len(parts) > 1 else ""
        artifacts.append(artifact(root, name + suffix, kind, path, record_count=count_lines(path),
                                  shared_with=f"{entry['dataset_id']}@{PARENT}"))
    return artifacts


def source_rows(entry):
    for part in entry["supervisions"].get("sources") or [entry["supervisions"]]:
        with gzip.open(part["path"], "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def audit(entry, annotated, plain):
    """Compare every clean row with its source row; returns the statistics of custom.clean."""
    stats = {"total": 0, "pass": 0, "reject": 0, "pass_seconds": 0.0, "seconds": 0.0, "text_changed": 0, "plain_text_changed": 0,
             "by_reason": Counter(), "by_action": Counter(), "moss_speakers": Counter(),
             "engine_status": {QWEN: Counter(), MOSS: Counter()}}
    with gzip.open(annotated, "rt", encoding="utf-8") as ann, gzip.open(plain, "rt", encoding="utf-8") as pln:
        for source, a_line, p_line in zip(source_rows(entry), ann, pln, strict=True):
            row, plain_row = json.loads(a_line), json.loads(p_line)
            if row["id"] != source["id"] or plain_row["id"] != source["id"]:
                raise SystemExit(f"{entry['dataset_id']}: id order differs at {source['id']}")
            for other in (row, plain_row):
                if {k: v for k, v in other.items() if k not in ("text", "custom")} != \
                        {k: v for k, v in source.items() if k not in ("text", "custom")}:
                    raise SystemExit(f"{entry['dataset_id']}: {source['id']} differs from the source beyond text/custom")
                if {k: v for k, v in other["custom"].items() if k not in ("clean", "original_text")} != \
                        (source.get("custom") or {}):
                    raise SystemExit(f"{entry['dataset_id']}: {source['id']} custom differs beyond clean")
            # restore_disfluency keeps the source transcript in custom.original_text; the no-punctuation manifest
            # additionally drops marks and apostrophes from every text.
            if row["text"] != source["text"] and row["custom"].get("original_text") != source["text"]:
                raise SystemExit(f"{entry['dataset_id']}: {source['id']} text changed without original_text")
            clean = row["custom"]["clean"]
            if clean != plain_row["custom"]["clean"]:
                raise SystemExit(f"{entry['dataset_id']}: {source['id']} clean differs between the two manifests")
            stats["total"] += 1
            stats["seconds"] += source["duration"]
            stats["text_changed"] += row["text"] != source["text"]
            stats["plain_text_changed"] += plain_row["text"] != source["text"]
            stats["by_action"][clean["action"]] += 1
            speakers = (clean.get("speakers") or {}).get("count")  # absent when MOSS gave no valid output
            stats["moss_speakers"]["no output" if speakers is None else "3+" if speakers >= 3 else str(speakers)] += 1
            for engine, status in clean["engine_status"].items():
                stats["engine_status"][engine][status] += 1
            if clean["pass"]:
                stats["pass"] += 1
                stats["pass_seconds"] += source["duration"]
            else:
                stats["reject"] += 1
            stats["by_reason"][clean["reason"]] += 1
    if stats["total"] != entry["supervision_count"]:
        raise SystemExit(f"{entry['dataset_id']}: {stats['total']} rows, inputs.json says {entry['supervision_count']}")
    return stats


def register_complete(dataset, run, root, language):
    entry = json.loads((run / "inputs.json").read_text())[dataset]
    out = run / dataset
    workdir = next((out / "workdir").glob("*"))
    final = root / "datasets" / dataset / "versions" / VERSION
    if DECLARATIONS_ONLY:
        annotated = final / "supervisions" / f"{dataset}_supervisions_train.jsonl.gz"
        plain = final / "supervisions" / f"{dataset}_supervisions_train_no_punc.jsonl.gz"
        report = json.loads((final / "evidence" / "filter_report.json").read_text())
    else:
        manifest = json.loads((out / "run_manifest.json").read_text())["artifacts"]
        annotated, plain = out / Path(manifest["manifest"]).name, out / Path(manifest["manifest_non_punc"]).name
        report = json.loads((workdir / "filtered" / "filter_report.json").read_text())
    stats = audit(entry, annotated, plain)
    if (report["total"], report["kept"], report["rejected"]) != (stats["total"], stats["pass"], stats["reject"]):
        raise SystemExit(f"{dataset}: filter_report disagrees with custom.clean")
    if not DECLARATIONS_ONLY:
        if final.exists():
            raise SystemExit(f"{final} exists; versions are immutable")
        (final / "supervisions").mkdir(parents=True)
        (final / "evidence").mkdir()
    ann_dest = final / "supervisions" / f"{dataset}_supervisions_train.jsonl.gz"
    plain_dest = final / "supervisions" / f"{dataset}_supervisions_train_no_punc.jsonl.gz"
    copy_file(annotated, ann_dest)
    copy_file(plain, plain_dest)
    report.pop("source", None)  # points into the run directory
    report_dest = final / "evidence" / "filter_report.json"
    publish(lambda tmp: tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n"), report_dest)
    evidence = {
        "engine_results": workdir / "results.jsonl", "rejected": workdir / "filtered" / "rejected.jsonl",
        "content_review": workdir / "content_review.jsonl", "replaced_review": workdir / "replaced_review.jsonl",
    }
    artifacts = source_artifacts(root, entry)
    counts = {}
    for name, source in [("train_supervisions", ann_dest), ("train_supervisions_no_punc", plain_dest)]:
        counts[name] = count_lines(source)
        extra = {"punctuated": False} if name.endswith("no_punc") else {
            "text": "source transcript with custom.clean; restored fillers may carry punctuation"}
        artifacts.append(artifact(root, name, "lhotse-supervisions", source, record_count=counts[name],
                                  pass_count=stats["pass"], **extra))
    for name, source in evidence.items():
        destination = final / "evidence" / f"{name}.jsonl.gz"
        gzip_file(source, destination)
        counts[name] = count_lines(destination)
        artifacts.append(artifact(root, name, "quality-report", destination, record_count=counts[name]))
    artifacts.append(artifact(root, "filter_report", "json-metadata", report_dest))
    if counts["train_supervisions"] != stats["total"] or counts["train_supervisions_no_punc"] != stats["total"] \
            or counts["engine_results"] != stats["total"] or counts["rejected"] != stats["reject"]:
        raise SystemExit(f"{dataset}: read-back counts {counts} disagree with {stats['total']}/{stats['reject']}")
    return entry, stats, artifacts, language


def declaration_complete(dataset, entry, stats, artifacts, languages):
    recordings = [a["name"] for a in artifacts if a["kind"] in ("lhotse-recordings", "lhotse-cuts")]
    reasons = dict(stats["by_reason"].most_common())
    too_short = reasons.get("too_short", 0)
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": VERSION,
        "languages": languages, "tasks": ["asr"], "aliases": [], "artifacts": artifacts,
        "splits": {"train": {
            "artifacts": {"recordings": recordings, "supervisions": ["train_supervisions"],
                          "clean_no_punc_supervisions": ["train_supervisions_no_punc"]},
            "statistics": {
                "supervisions": stats["total"], "pass": stats["pass"], "reject": stats["reject"], "by_reason": reasons,
                "hours_before_filter": round(stats["seconds"] / 3600, 4),
                "duration_hours": round(stats["pass_seconds"] / 3600, 4),
                "duration_basis": "sum of supervision durations with custom.clean.pass=true"}}},
        "recipe_parameters": {
            "source_version": PARENT, "source_split": "train",
            "engines": [
                {"name": QWEN, "backend": "vllm 0.18.0", "request": {"to_language": "zh", "temperature": 0.0, "repetition_penalty": 1.1}},
                {"name": MOSS, "backend": "vllm 0.23.1rc1.dev949+g68b4a1d58", "request": {"temperature": 0.0},
                 "prompt": "vLLM default diarization prompt"}],
            "filter_rules": "consensus-v6", "rewrite_rules": "wenetspeech-faithful-v5", "params": CLEAN_PARAMS,
            "writes": ["text", "custom.clean", "custom.original_text"], "filters": "custom.clean.pass=false"},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{PARENT}",
            "description": (
                f"{dataset}@{PARENT} 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗"
                "（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean"
                "（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 "
                f"require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：{stats['total']} 条中 pass "
                f"{stats['pass']}、reject {stats['reject']}。少于 2 个字的 too_short 共 {too_short} 条按规则不经引擎直接 pass。"
                f"restore_disfluency 改写了 {stats['text_changed']} 条的 text（原文留在 custom.original_text）；无标点清单"
                f"另把 {stats['plain_text_changed']} 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。"
                "脚本 scripts/zh_source_clean/register_clean_dual.py。"),
            "facts": {
                "rows": stats["total"], "hours": round(stats["seconds"] / 3600, 4),
                "by_action": dict(stats["by_action"]), "moss_speaker_count": dict(sorted(stats["moss_speakers"].items())),
                "engine_status": {e: dict(c) for e, c in stats["engine_status"].items()},
                "rows with text changed": stats["text_changed"],
                "rows with text changed in the no-punctuation manifest": stats["plain_text_changed"], "code": CODE}},
    }


def view_complete(dataset, entry, stats):
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/clean", "version": VERSION,
        "source": {"dataset_id": dataset, "version": PARENT}, "result": {"dataset_id": dataset, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "clean-dual-qwen-moss", "version": "consensus-v6+wenetspeech-faithful-v5", "kind": "annotate",
            "writes": ["target", "metadata.clean", "metadata.original_text"], "overrides": ["target"],
            "parameters": {
                "engines": [QWEN, MOSS], "params": CLEAN_PARAMS, "code": CODE,
                "input_supervisions": [{"file": Path(p["path"]).name, "sha256": p["sha256"]}
                                       for p in (entry["supervisions"].get("sources") or [entry["supervisions"]])],
                "rows": stats["total"], "pass": stats["pass"], "reject": stats["reject"],
                "target_changed_rows": stats["text_changed"], "rows_dropped": 0,
                "text_variants": ["train_supervisions: source transcript, restored fillers may carry punctuation",
                                  "train_supervisions_no_punc: marks and apostrophes removed"],
                "tool": "scripts/zh_source_clean/run_clean.py"}}],
        "provenance": {"registered_at": "2026-11-03"},
    }


def register_placeholder(dataset, run, root):
    entry = json.loads((run / "inputs.json").read_text())[dataset]
    workdir = next((run / dataset / "workdir").glob("*"))
    ids = set()
    with gzip.open(entry["supervisions"]["path"], "rt", encoding="utf-8") as stream:
        for line in stream:
            ids.add(json.loads(line)["id"])
    if len(ids) != entry["supervision_count"]:
        raise SystemExit(f"{dataset}: {len(ids)} supervision ids, inputs.json says {entry['supervision_count']}")
    final = root / "datasets" / dataset / "versions" / VERSION
    if not DECLARATIONS_ONLY:
        if final.exists():
            raise SystemExit(f"{final} exists; versions are immutable")
        (final / "evidence").mkdir(parents=True)
    artifacts = source_artifacts(root, entry, cuts=True)
    facts = {"source supervisions": len(ids)}
    for engine, name in [(QWEN, "engine_results_partial_qwen"), (MOSS, "engine_results_partial_moss")]:
        destination = final / "evidence" / f"{name}.jsonl.gz"
        seen, dropped = set(), 0

        def write(tmp, engine=engine, seen=seen):
            nonlocal dropped
            with open(workdir / f"_infer_{engine}.jsonl", encoding="utf-8") as reader, open(tmp, "wb") as raw, \
                    gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as out:
                for line in reader:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:  # the run was killed in the middle of a write
                        dropped += 1
                        continue
                    if row["id"] not in ids or row["id"] in seen:
                        raise SystemExit(f"{dataset}: {engine} output id {row['id']} unknown or repeated")
                    seen.add(row["id"])
                    out.write(line.encode("utf-8") if line.endswith("\n") else (line + "\n").encode("utf-8"))
        if DECLARATIONS_ONLY:
            # the registered file was written without truncated lines (facts.json of the first run: 0 dropped)
            with gzip.open(destination, "rt", encoding="utf-8") as stream:
                for line in stream:
                    row_id = json.loads(line)["id"]
                    if row_id not in ids or row_id in seen:
                        raise SystemExit(f"{dataset}: {engine} output id {row_id} unknown or repeated")
                    seen.add(row_id)
        else:
            publish(write, destination)
        count = count_lines(destination)
        if count != len(seen):
            raise SystemExit(f"{dataset}: {engine} read-back {count} != {len(seen)}")
        facts[f"{engine} utterances"] = count
        facts[f"{engine} truncated lines dropped"] = dropped
        artifacts.append(artifact(root, name, "quality-report", destination, record_count=count))
    return entry, facts, artifacts


def declaration_placeholder(dataset, facts, artifacts):
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": VERSION,
        "languages": ["zh"], "tasks": ["asr"], "aliases": [], "artifacts": artifacts,
        "splits": {"train": {
            "artifacts": {"cuts": ["train_cuts"]},
            "statistics": {"supervisions": facts["source supervisions"]}}},
        "recipe_parameters": {"source_version": PARENT, "source_split": "train", "engines": [QWEN, MOSS],
                              "filter_rules": "consensus-v6", "rewrite_rules": "wenetspeech-faithful-v5", "params": CLEAN_PARAMS},
        "provenance": {
            "preparation_status": "partial", "ready_for_training": False, "lineage_status": "exact",
            "materialization": "full", "source": f"{dataset}@{PARENT}",
            "description": (
                f"占位，不可训练。{dataset}@{PARENT} 的 {facts['source supervisions']} 条监督片段做 Qwen3-ASR-1.7B 与 MOSS 双引擎清洗，"
                f"运行在 Qwen {facts[f'{QWEN} utterances']} 条、MOSS {facts[f'{MOSS} utterances']} 条处中断（2026-10-10），"
                "没有写出任何 custom.clean 判决，也没有 pass / reject 结果。这里只登记两个引擎已完成部分的原始输出"
                "（evidence/engine_results_partial_*.jsonl.gz，每行 id、raw、language、hypothesis，id 即源监督片段 id），"
                "其余约一半片段没有输出。使用前须续跑引擎并出判决，再另立新版本；任务和配方不得引用本版本。"
                "脚本 scripts/zh_source_clean/register_clean_dual.py。"),
            "facts": {**facts, "code": CODE}},
    }


def view_placeholder(dataset, entry, facts):
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/clean", "version": VERSION,
        "source": {"dataset_id": dataset, "version": PARENT}, "result": {"dataset_id": dataset, "version": VERSION},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "clean-dual-qwen-moss-partial", "version": "consensus-v6+wenetspeech-faithful-v5", "kind": "annotate",
            "writes": ["metadata.clean_engine_outputs"],
            "parameters": {
                "engines": [QWEN, MOSS], "code": CODE, "status": "partial: raw engine outputs only, no verdicts",
                "input_supervisions": [{"file": Path(entry["supervisions"]["path"]).name, "sha256": entry["supervisions"]["sha256"]}],
                "utterances_done": {QWEN: facts[f"{QWEN} utterances"], MOSS: facts[f"{MOSS} utterances"]},
                "source_supervisions": facts["source supervisions"], "rows_dropped": 0}}],
        "provenance": {"registered_at": "2026-11-03", "ready_for_training": False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("catalog"))
    parser.add_argument("--run", action="append", required=True, help="NAME=DIR (batch1, batch2)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--catalog-header", help="comment written as the first line of --output")
    parser.add_argument("--views-header", help="comment written as the first line of --views")
    parser.add_argument("--declarations-only", action="store_true",
                        help="rebuild catalog and views from the registered files; writes no data")
    args = parser.parse_args()
    global DECLARATIONS_ONLY
    DECLARATIONS_ONLY = args.declarations_only
    runs = {name: Path(path) for name, path in (item.split("=", 1) for item in args.run)}
    catalog = load_catalog(args.catalog)
    declarations, views, record = [], [], {}
    for dataset, run_name in DATASETS.items():
        languages = list(catalog.get(dataset, PARENT).to_dict()["languages"])
        entry, stats, artifacts, languages = register_complete(dataset, runs[run_name], args.root, languages)
        declarations.append(declaration_complete(dataset, entry, stats, artifacts, languages))
        views.append(view_complete(dataset, entry, stats))
        record[dataset] = {"rows": stats["total"], "pass": stats["pass"], "reject": stats["reject"]}
        print(dataset, record[dataset], flush=True)
    for dataset, run_name in PLACEHOLDER.items():
        entry, facts, artifacts = register_placeholder(dataset, runs[run_name], args.root)
        declarations.append(declaration_placeholder(dataset, facts, artifacts))
        views.append(view_placeholder(dataset, entry, facts))
        record[dataset] = facts
        print(dataset, facts, flush=True)
    # JSON round trip: entries sharing an object would otherwise be written as YAML anchors
    write_declarations(args.output, json.loads(json.dumps(declarations)))
    write_declarations(args.views, json.loads(json.dumps(views)))
    for path, header in ((args.output, args.catalog_header), (args.views, args.views_header)):
        if header:
            path.write_text(f"# {header}\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    if args.declarations_only:  # the counts of the original registration must still hold
        if json.loads((args.record / "facts.json").read_text()) != json.loads(json.dumps(record)):
            raise SystemExit("recomputed counts differ from facts.json of the original registration")
        return
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "facts.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
