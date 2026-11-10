"""Register the Step-Audio2-Wu-ASR transcripts of the WenetSpeech-Wu train set: a full version and the kept version.

Inputs come from the run directory: step_infer.py output (out/full.jsonl) and score.py output (out/full-scored.jsonl,
one row per cut, in parent order). Writes
- wenetspeech_wu@stepaudio2-wu-asr-full-v1-20261109: every cut of wenetspeech_wu@icefall-20260908 train, label text
  unchanged, with supervisions[0].custom.step_audio2_asr = hypothesis, truncated, ref_tokens, hyp_tokens, errors, cer;
- wenetspeech_wu@stepaudio2-wu-asr-v1-20261109 (completes the placeholder): label non-empty after TextNorm, generation
  not truncated, CER < 30 %.
Recordings stay inside the parent's cuts (byte ranges into the source tars); no audio is copied. Written files are read
back for counts, bytes and sha256. Helpers are shared with scripts/wenetspeech_qwen/register_qwen_transcripts.py.

    PYTHONPATH=src python scripts/wenetspeech_wu_step/register_step_transcripts.py --root /workspace/data \
        --catalog /workspace/data/registry/catalog --run <run dir> \
        --placeholder catalog/wenetspeech_wu_qwen.yaml --output catalog/wenetspeech_wu_step.yaml \
        --views views/wenetspeech_wu_step.yaml
"""

import argparse
import copy
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wenetspeech_qwen"))
from register_qwen_transcripts import (
    GzipOut,
    artifact_entry,
    breakdown,
    cer_bucket,
    finish_state,
    sha256,
)

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact, verify_artifact_file
from audio_data_contract.declarations import read_declarations, write_declarations

DATASET = "wenetspeech_wu"
PARENT = ("wenetspeech_wu", "icefall-20260908")
FULL, KEPT = "stepaudio2-wu-asr-full-v1-20261109", "stepaudio2-wu-asr-v1-20261109"
FIELD = "step_audio2_asr"
NORM = "speechio-textnorm-zh"
KEEP_CER_BELOW = 30
MODEL = "ASLP-lab WenetSpeech-Wu-Speech-Understanding/stepaudio2-ASR (LoRA r=8) on stepfun-ai/Step-Audio-2-mini"
TOOLS = "scripts/wenetspeech_wu_step/step_infer.py, scripts/wenetspeech_wu_step/score.py"
KEEP_RULE = f"label non-empty after TextNorm, generation not truncated, and per-utterance CER vs Step-Audio2-Wu-ASR < {KEEP_CER_BELOW} %"
NOTE = ("Step-Audio2-Wu-ASR 在 WenetSpeech-Wu 上训练过，与原标注的一致程度可能偏高。"
        "误杀按 Wu-Bench 人工标注估计：Wu-Bench 上 Step 自身落到 CER ≥ 30 % 的时长占 8.4 %，训练集为 22.2 %，"
        "据此被丢的部分约 38 % 其实标注是对的（偏粗，可能高估）；分歧集中在原标注低置信度的条目。")


def load_hypotheses(path):
    """id -> (hypothesis, truncated); the last row per id wins, as in score.py."""
    found = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "hypothesis" in row:
                found[row["id"]] = (row["hypothesis"], row["truncated"])
    return found


def write_rows(source, scored_path, hypotheses, out_full, out_kept):
    facts, buckets, hours = Counter(), Counter(), Counter()
    with gzip.open(source, "rt", encoding="utf-8") as reader, open(scored_path, encoding="utf-8") as scored:
        upcoming = json.loads(next(scored, "null"))
        for line in reader:
            row = json.loads(line)
            facts["source rows"] += 1
            hours["source"] += row["duration"] / 3600
            if upcoming is None or upcoming["id"] != row["id"]:
                raise SystemExit(f"{row['id']}: no scored row (every cut was transcribed)")
            supervision = row["supervisions"][0]
            if upcoming["ref"] != supervision["text"]:
                raise SystemExit(f"{row['id']}: label differs from the scored reference")
            hypothesis, truncated = hypotheses[row["id"]]
            if hypothesis != upcoming["hyp"]:
                raise SystemExit(f"{row['id']}: scored hypothesis differs from the transcription file")
            ref_tokens, errors = upcoming["ref_tokens"], upcoming["errors"]
            supervision.setdefault("custom", {})[FIELD] = {
                "hypothesis": hypothesis, "truncated": truncated, "ref_tokens": ref_tokens,
                "hyp_tokens": upcoming["hyp_tokens"], "errors": errors,
                "cer": round(100 * errors / ref_tokens, 4) if ref_tokens else None}
            text = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            out_full.write(text)
            hours["full"] += row["duration"] / 3600
            facts["rows"] += 1
            facts["ref tokens"] += ref_tokens
            facts["token errors"] += errors
            facts["step empty"] += upcoming["hyp_tokens"] == 0
            facts["truncated"] += truncated
            buckets[cer_bucket(errors, ref_tokens)] += 1
            if ref_tokens and not truncated and errors * 100 < KEEP_CER_BELOW * ref_tokens:
                facts["kept rows"] += 1
                hours["kept"] += row["duration"] / 3600
                out_kept.write(text)
            upcoming = json.loads(next(scored, "null"))
        if upcoming is not None:
            raise SystemExit(f"scored row {upcoming['id']} was not found in the parent artifact (order mismatch)")
    return facts, buckets, hours


def entry(parent, version, artifacts, statistics, description, facts, source, state_artifact=None, keep=False):
    roles = {"cuts": [a["name"] for a in artifacts]}
    if state_artifact:
        roles["preparation_state"] = [state_artifact["name"]]
    result = {
        "schema_version": parent["schema_version"], "dataset_id": DATASET, "version": version, "languages": ["zh"],
        "tasks": ["asr"], "aliases": [], "artifacts": ([state_artifact] if state_artifact else []) + artifacts,
        "splits": {"train": {"artifacts": roles, "statistics": statistics}},
        "recipe_parameters": {"adds": [f"custom.{FIELD}"], "check_model": "Step-Audio2-Wu-ASR", "check_unit": "utterance",
                              "text_normalization": NORM},
        "provenance": {"preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
                       "source": source, "description": description, "facts": dict(facts)}}
    if keep:
        result["recipe_parameters"]["keep_rule"] = KEEP_RULE
    return result


def view(version, source, transforms):
    return {"schema_version": "dataset-view/1.0",
            "view_id": f"{DATASET}/stepaudio2-wu-asr-{'kept' if version == KEPT else 'full'}",
            "version": version, "source": {"dataset_id": source[0], "version": source[1]},
            "result": {"dataset_id": DATASET, "version": version}, "materialization": "full",
            "lineage_status": "exact", "transforms": transforms, "provenance": {"registered_at": "2026-11-10"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True, help="registry catalog directory (parents' artifacts)")
    parser.add_argument("--run", type=Path, required=True, help="run directory with out/full.jsonl and out/full-scored.jsonl")
    parser.add_argument("--placeholder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    args = parser.parse_args()
    hyps, scored = args.run / "out" / "full.jsonl", args.run / "out" / "full-scored.jsonl"
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    parent = catalog.get(*PARENT)
    source = resolve_artifact(catalog, *PARENT, "train_cuts_0", roots)
    verify_artifact_file(parent.artifact("train_cuts_0"), source)
    placeholder = next(r for _, r in read_declarations(args.placeholder) if r["version"] == KEPT)
    dirs = {v: args.root / "datasets" / DATASET / "versions" / v for v in (FULL, KEPT)}
    for directory in dirs.values():
        if any(p.name != "state.json" for p in directory.glob("*")):
            raise SystemExit(f"{directory} already holds data; versions are immutable")
        directory.mkdir(parents=True, exist_ok=True)

    full_name = "wenetspeech_wu_cuts_train_stepaudio2.jsonl.gz"
    kept_name = f"wenetspeech_wu_cuts_train_stepaudio2_cer_lt{KEEP_CER_BELOW}.jsonl.gz"
    out_full, out_kept = GzipOut(dirs[FULL] / full_name), GzipOut(dirs[KEPT] / kept_name)
    facts, buckets, hours = write_rows(source, scored, load_hypotheses(hyps), out_full, out_kept)
    out_full.close()
    out_kept.close()
    corpus_cer = round(100 * facts["token errors"] / facts["ref tokens"], 2)
    facts = Counter({**facts, "corpus CER": corpus_cer})
    extra = {"step_field": f"supervisions[0].custom.{FIELD}"}
    full_art = artifact_entry("train_cuts_stepaudio2_0", "lhotse-cuts", f"datasets/{DATASET}/versions/{FULL}/{full_name}",
                              dirs[FULL] / full_name, facts["rows"], extra)
    kept_art = artifact_entry("train_cuts_clean_0", "lhotse-cuts", f"datasets/{DATASET}/versions/{KEPT}/{kept_name}",
                              dirs[KEPT] / kept_name, facts["kept rows"], extra)
    share = f"{100 * hours['kept'] / hours['full']:.1f}"
    full_desc = (
        f"wenetspeech_wu@icefall-20260908 里 WenetSpeech-Wu 吴语训练集的全部条目（{facts['rows']:,} 条 / {hours['full']:.1f} h），"
        f"原标注（吴语写法的机器标注，带置信度和普通话译文）一字不改；每条 supervision 加 custom.{FIELD}：Step-Audio2-Wu-ASR"
        f"（ASLP-lab 在 Step-Audio-2-mini 上微调的吴语 ASR，贪心解码）的转写（hypothesis）、是否达到生成上限被截断（truncated，多为重复输出）"
        f"和与原标注的字错误率（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。"
        f"整体 CER {corpus_cer:.2f} %，Step 在 WenetSpeech-Wu-Bench 抽样 1,000 条上自身 CER 为 12.3（Qwen3-ASR 24.2）；"
        f"空输出 {facts['step empty']:,} 条，截断 {facts['truncated']:,} 条。{NOTE}录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_wu_step/。")
    kept_desc = (
        f"WenetSpeech-Wu 吴语训练集（wenetspeech_wu@icefall-20260908）用 Step-Audio2-Wu-ASR 逐条核对后保留的部分：原标注规范化后非空、"
        f"生成未截断且字错误率 < {KEEP_CER_BELOW} % 的 {facts['kept rows']:,} 条 / {hours['kept']:.1f} h（占全部时长的 {share} %）。"
        f"原标注不改，不拿 Step 的文字替换。每行的 custom.{FIELD} 与 {DATASET}@{FULL} 中相同；被去掉的条目和全部转写见该版本。"
        f"{NOTE}录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_wu_step/。")
    state_art = copy.deepcopy(next(a for a in placeholder["artifacts"] if a["name"] == "preparation_state"))
    parent_dict = parent.to_dict()
    kept_entry = entry(parent_dict, KEPT, [kept_art], {
        "records": facts["kept rows"], "duration_hours": round(hours["kept"], 4), "duration_basis": "sum of row durations",
        "records_before_filter": facts["rows"], "hours_before_filter": round(hours["full"], 1)},
        kept_desc, facts, f"{DATASET}@{FULL}", state_art, keep=True)
    kept_entry["provenance"]["summary"] = "吴语（WenetSpeech-Wu）；Step 核对版"
    kept_entry["provenance"]["owner"] = placeholder["provenance"].get("owner", "mingdong")
    full_entry = entry(parent_dict, FULL, [full_art], {
        "records": facts["rows"], "duration_hours": round(hours["full"], 4), "duration_basis": "sum of row durations"},
        full_desc, facts, f"{PARENT[0]}@{PARENT[1]}")
    inputs = [{"file": p.name, "sha256": sha256(p)} for p in (hyps, scored)]
    annotate = {"name": "stepaudio2-wu-asr-transcript", "version": "v1-20261109", "kind": "annotate",
                "writes": [f"metadata.{FIELD}"],
                "parameters": {"model": MODEL,
                               "decoding": {"prompt": "语音说了什么", "greedy": True,
                                            "max_new_tokens": "duration * 10 + 32"},
                               "audio": "16 kHz PCM WAV read from the source tar at the cut's byte range",
                               "scoring": {"text_normalization": NORM, "unit": "one token per CJK character, punctuation dropped",
                                           "cer": "100 * errors / ref_tokens, null when ref_tokens is 0"},
                               "tool": TOOLS, "label_inputs": inputs, "corpus_cer": corpus_cer,
                               "cer_share_rows": breakdown(buckets)}}
    views = [
        view(FULL, PARENT, [annotate]),
        view(KEPT, (DATASET, FULL), [{"name": "cer-filter", "version": "v1", "kind": "filter", "writes": ["$membership"],
                                      "parameters": {"rule": KEEP_RULE,
                                                     "false_reject_estimate": ("about 38 % of dropped hours, from Step's own "
                                                                               "CER >= 30 % share on human-labelled Wu-Bench (run README)"),
                                                     "listening_review": "none (reviewer does not understand Wu); estimate from Wu-Bench instead",
                                                     "input_rows": facts["rows"], "output_rows": facts["kept rows"],
                                                     "tool": "scripts/wenetspeech_wu_step/register_step_transcripts.py"}}])]
    finish_state(dirs[KEPT] / "state.json", KEPT,
                 f"completed: kept rows (label CER vs Step-Audio2-Wu-ASR < {KEEP_CER_BELOW} %, not truncated); full transcripts in {FULL}",
                 {"transcribed": facts["rows"], "kept": facts["kept rows"], "kept_hours": round(hours["kept"], 1),
                  "corpus_cer": corpus_cer, "cer_share_rows": breakdown(buckets)}, "prepared")
    write_declarations(args.output, json.loads(json.dumps([kept_entry, full_entry])))
    write_declarations(args.views, json.loads(json.dumps(views)))
    print(json.dumps({"facts": dict(facts), "hours": dict(hours)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
