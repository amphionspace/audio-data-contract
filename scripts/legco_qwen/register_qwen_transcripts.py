"""Register the Qwen3-ASR transcripts of the LegCo-Speech train set: a full version and the kept version (placeholder).

Inputs come from the run directory: qwen_infer.py output, score.py output (one row per transcribed supervision, in
parent order) and rule_v2.py output (same order). Writes
- legco_speech@qwen3-asr-full-v1-20261103: every transcribed supervision of legco_speech@icefall-20260908, label text
  unchanged, with custom.qwen_asr = hypothesis, language, ref_tokens, hyp_tokens, errors, cer, errors_v2, keep_reason;
- legco_speech@qwen3-asr-v1-20261103 (completes the placeholder): the rows rule_v2.py keeps.
Recordings stay the parent's; no audio is copied. Written files are read back for counts, bytes and sha256.
Helpers are shared with scripts/wenetspeech_qwen/register_qwen_transcripts.py.

    PYTHONPATH=src python scripts/legco_qwen/register_qwen_transcripts.py --root /workspace/data \
        --catalog /workspace/data/registry/catalog --run <run dir> \
        --placeholder catalog/legco_speech_qwen.yaml --output catalog/legco_speech_qwen.yaml \
        --views views/legco_speech_qwen.yaml
"""

import argparse
import copy
import gzip
import json
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wenetspeech_qwen"))
from register_qwen_transcripts import (
    FIELD,
    MODEL,
    GzipOut,
    artifact_entry,
    breakdown,
    cer_bucket,
    finish_state,
    load_languages,
    sha256,
)

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact, verify_artifact_file
from audio_data_contract.declarations import read_declarations, write_declarations

DATASET = "legco_speech"
PARENT = ("legco_speech", "icefall-20260908")
FULL, KEPT = "qwen3-asr-full-v1-20261103", "qwen3-asr-v1-20261103"
NORM = "speechio-textnorm-yue"
TOOLS = "scripts/legco_qwen/qwen_infer.py, scripts/legco_qwen/score.py, scripts/legco_qwen/rule_v2.py"
KEEP_RULE = ("label non-empty after TextNorm and (duration < 2 s, not judged; or CER vs Qwen < 30 % after unifying "
             "噉->咁 and 呢->咧 and not counting insertions at the start or end of the hypothesis)")
NOTE = ("清单里每条 supervision 的 start 都是 0，但段文件比 duration 长 0–1 s、语音偏后：Qwen 转写整段文件，按 supervision 截音频训练会有错位。"
        "同声传译段的原标注是中文译文、音频是英文，这类段多被规则丢弃。")


def write_rows(source, scored_path, rule_path, languages, out_full, out_kept):
    facts, buckets, hours, reasons = Counter(), Counter(), Counter(), Counter()
    with gzip.open(source, "rt", encoding="utf-8") as reader, open(scored_path, encoding="utf-8") as scored, \
            open(rule_path, encoding="utf-8") as rules:
        upcoming = json.loads(next(scored, "null"))
        rule = json.loads(next(rules, "null"))
        for line in reader:
            row = json.loads(line)
            row_id = row["recording_id"]
            facts["source rows"] += 1
            hours["source"] += row["duration"] / 3600
            if upcoming is None or upcoming["id"] != row_id:
                facts["rows not transcribed"] += 1
                hours["not transcribed"] += row["duration"] / 3600
                continue
            if upcoming["ref"] != row["text"]:
                raise SystemExit(f"{row_id}: label differs from the scored reference")
            if rule is None or rule["id"] != row_id:
                raise SystemExit(f"{row_id}: rule_v2 output out of step with the scored rows")
            language, crc = languages[row_id]
            if crc != zlib.crc32(upcoming["hyp"].encode()):
                raise SystemExit(f"{row_id}: scored hypothesis differs from the transcription file")
            ref_tokens, errors = upcoming["ref_tokens"], upcoming["errors"]
            row.setdefault("custom", {})[FIELD] = {
                "hypothesis": upcoming["hyp"], "language": language, "ref_tokens": ref_tokens,
                "hyp_tokens": upcoming["hyp_tokens"], "errors": errors,
                "cer": round(100 * errors / ref_tokens, 4) if ref_tokens else None,
                "errors_v2": rule["errors_v2"], "keep_reason": rule["reason"]}
            text = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            out_full.write(text)
            hours["full"] += row["duration"] / 3600
            facts["rows"] += 1
            facts["ref tokens"] += ref_tokens
            facts["token errors"] += errors
            facts["qwen empty"] += upcoming["hyp_tokens"] == 0
            buckets[cer_bucket(errors, ref_tokens)] += 1
            reasons[rule["reason"]] += 1
            if rule["keep"]:
                facts["kept rows"] += 1
                hours["kept"] += row["duration"] / 3600
                out_kept.write(text)
            upcoming = json.loads(next(scored, "null"))
            rule = json.loads(next(rules, "null"))
        if upcoming is not None or rule is not None:
            raise SystemExit("scored or rule rows left over (order or part mismatch)")
    return facts, buckets, hours, reasons


def entry(parent, version, artifacts, recordings, statistics, description, facts, source, state_artifact=None, keep=False):
    roles = {"recordings": [r["name"] for r in recordings], "supervisions": [a["name"] for a in artifacts]}
    if state_artifact:
        roles["preparation_state"] = [state_artifact["name"]]
    result = {
        "schema_version": parent["schema_version"], "dataset_id": DATASET, "version": version, "languages": ["yue"],
        "tasks": ["asr"], "aliases": [],
        "artifacts": ([state_artifact] if state_artifact else []) + copy.deepcopy(recordings) + artifacts,
        "splits": {"train": {"artifacts": roles, "statistics": statistics}},
        "recipe_parameters": {"adds": [f"custom.{FIELD}"], "check_model": "Qwen3-ASR-1.7B", "check_unit": "utterance",
                              "text_normalization": NORM},
        "provenance": {"preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
                       "source": source, "description": description, "facts": dict(facts)}}
    if keep:
        result["recipe_parameters"]["keep_rule"] = KEEP_RULE
    return result


def view(version, source, transforms):
    return {"schema_version": "dataset-view/1.0", "view_id": f"{DATASET}/qwen3-asr-{'kept' if version == KEPT else 'full'}",
            "version": version, "source": {"dataset_id": source[0], "version": source[1]},
            "result": {"dataset_id": DATASET, "version": version}, "materialization": "full",
            "lineage_status": "exact", "transforms": transforms, "provenance": {"registered_at": "2026-11-08"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True, help="registry catalog directory (parents' artifacts)")
    parser.add_argument("--run", type=Path, required=True, help="run directory with out/qwen.jsonl, qwen-scored, rule-v2")
    parser.add_argument("--placeholder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    args = parser.parse_args()
    qwen, scored, rules = (args.run / "out" / n for n in ("qwen.jsonl", "qwen-scored.jsonl", "rule-v2.jsonl"))
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    parent = catalog.get(*PARENT)
    source = resolve_artifact(catalog, *PARENT, "train_sup_0", roots)
    verify_artifact_file(parent.artifact("train_sup_0"), source)
    recordings = [copy.deepcopy(next(a for a in parent.to_dict()["artifacts"] if a["name"] == "train_rec_0"))]
    placeholder = next(r for _, r in read_declarations(args.placeholder) if r["version"] == KEPT)
    dirs = {v: args.root / "datasets" / DATASET / "versions" / v for v in (FULL, KEPT)}
    for directory in dirs.values():
        if any(p.name != "state.json" for p in directory.glob("*")):
            raise SystemExit(f"{directory} already holds data; versions are immutable")
        directory.mkdir(parents=True, exist_ok=True)

    full_name, kept_name = "legco_speech_supervisions_train_qwen.jsonl.gz", "legco_speech_supervisions_train_qwen_kept.jsonl.gz"
    out_full, out_kept = GzipOut(dirs[FULL] / full_name), GzipOut(dirs[KEPT] / kept_name)
    facts, buckets, hours, reasons = write_rows(source, scored, rules, load_languages(qwen), out_full, out_kept)
    out_full.close()
    out_kept.close()
    corpus_cer = round(100 * facts["token errors"] / facts["ref tokens"], 2)
    facts = Counter({**facts, "corpus CER": corpus_cer})
    for reason, count in sorted(reasons.items()):
        facts[f"rule_v2: {reason}"] = count
    extra = {"qwen_field": f"custom.{FIELD}"}
    full_art = artifact_entry("train_supervisions_qwen_0", "lhotse-supervisions",
                              f"datasets/{DATASET}/versions/{FULL}/{full_name}", dirs[FULL] / full_name, facts["rows"], extra)
    kept_art = artifact_entry("train_supervisions_kept_0", "lhotse-supervisions",
                              f"datasets/{DATASET}/versions/{KEPT}/{kept_name}", dirs[KEPT] / kept_name,
                              facts["kept rows"], extra)
    share = f"{100 * hours['kept'] / hours['full']:.1f}"
    full_desc = (
        f"legco_speech@icefall-20260908 里 LegCo-Speech（香港立法会）粤语训练集的全部可转写条目（{facts['rows']:,} 条 / {hours['full']:.1f} h），"
        f"原标注（繁体口语粤语，像机器转写）一字不改；每条加 custom.{FIELD}：共享的 Qwen3-ASR-1.7B 对整段文件的转写（hypothesis）、语种（language）、"
        f"与原标注的字错误率（SpeechIO TextNorm，ref_tokens / hyp_tokens / errors / cer 百分数），以及保留规则 v2 的调整后错误数 errors_v2 和判定 keep_reason。"
        f"整体 CER {corpus_cer:.2f} %，Qwen 在 WSYue-ASR-eval short 上自身 CER 为 6.2。源 {facts['source rows']:,} 条里 {facts['rows not transcribed']:,} 条"
        f"（{hours['not transcribed']:.1f} h）是解不开的坏 Ogg 文件，没有转写，不在本版本内。{NOTE}录音沿用父版本，不复制音频。脚本 scripts/legco_qwen/。")
    kept_desc = (
        f"LegCo-Speech 粤语训练集（legco_speech@icefall-20260908）用 Qwen3-ASR-1.7B 逐条核对后保留的部分：{facts['kept rows']:,} 条 / {hours['kept']:.1f} h"
        f"（占可转写时长的 {share} %）。规则 v2（被拒样本抽查后定）：两边统一 噉/咁、呢/咧，Qwen 开头结尾多出的邻段字不计，不到 2 s 的段不判、保留，"
        f"其余调整后 CER < 30 % 保留；原标注规范化后为空的纯语气词段不保留。原标注不改，不拿 Qwen 的文字替换。每行的 custom.{FIELD} 与 "
        f"{DATASET}@{FULL} 中相同；被去掉的条目和全部转写见该版本。{NOTE}录音沿用父版本，不复制音频。脚本 scripts/legco_qwen/。")
    state_art = copy.deepcopy(next(a for a in placeholder["artifacts"] if a["name"] == "preparation_state"))
    parent_dict = parent.to_dict()
    kept_entry = entry(parent_dict, KEPT, [kept_art], recordings, {
        "records": facts["kept rows"], "duration_hours": round(hours["kept"], 4), "duration_basis": "sum of row durations",
        "records_before_filter": facts["rows"], "hours_before_filter": round(hours["full"], 1)},
        kept_desc, facts, f"{DATASET}@{FULL}", state_art, keep=True)
    kept_entry["provenance"]["summary"] = "香港立法会粤语（LegCo-Speech）；Qwen 核对版"
    kept_entry["provenance"]["owner"] = placeholder["provenance"].get("owner", "mingdong")
    full_entry = entry(parent_dict, FULL, [full_art], recordings, {
        "records": facts["rows"], "duration_hours": round(hours["full"], 4), "duration_basis": "sum of row durations"},
        full_desc, facts, f"{PARENT[0]}@{PARENT[1]}")
    inputs = [{"file": p.name, "sha256": sha256(p)} for p in (qwen, scored, rules)]
    annotate = {"name": "qwen3-asr-transcript", "version": "v1-20261103", "kind": "annotate", "writes": [f"metadata.{FIELD}"],
                "parameters": {"model": MODEL, "request": {"temperature": 0, "max_tokens": 2048, "repetition_penalty": 1.1,
                                                           "to_language": "not sent (language auto)"},
                               "audio": "whole Ogg Opus segment file as sent; ffmpeg-decoded 16 kHz mono FLAC when the service cannot decode it",
                               "scoring": {"text_normalization": NORM, "unit": "one token per CJK character, punctuation dropped"},
                               "tool": TOOLS, "label_inputs": inputs, "corpus_cer": corpus_cer,
                               "cer_share_rows": breakdown(buckets)}}
    views = [
        view(FULL, PARENT, [{"name": "transcribed-rows", "version": "v1", "kind": "filter", "writes": ["$membership"],
                             "parameters": {"kept": "rows with a Qwen transcript; corrupt Ogg files neither the service nor ffmpeg decode are left out",
                                            "input_rows": facts["source rows"], "output_rows": facts["rows"]}}, annotate]),
        view(KEPT, (DATASET, FULL), [{"name": "keep-rule-v2", "version": "v1", "kind": "filter", "writes": ["$membership"],
                                      "parameters": {"rule": KEEP_RULE, "tool": "scripts/legco_qwen/rule_v2.py",
                                                     "listening_review": "rejected rows read as text before and after the rule change (run README)",
                                                     "input_rows": facts["rows"], "output_rows": facts["kept rows"]}}])]
    finish_state(dirs[KEPT] / "state.json", KEPT, f"completed: kept rows (rule v2); full transcripts in {FULL}",
                 {"transcribed": facts["rows"], "kept": facts["kept rows"], "corpus_cer": corpus_cer,
                  "cer_share_rows": breakdown(buckets), "rule_v2": dict(reasons)}, "prepared")
    write_declarations(args.output, json.loads(json.dumps([kept_entry, full_entry])))
    write_declarations(args.views, json.loads(json.dumps(views)))
    print(json.dumps({"facts": dict(facts), "hours": dict(hours)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
