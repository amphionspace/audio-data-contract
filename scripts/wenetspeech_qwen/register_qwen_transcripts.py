"""Register the Qwen3-ASR transcripts of the WenetSpeech dialect train sets as dataset versions plus views.

Every row of the source set was transcribed with Qwen3-ASR-1.7B (qwen_infer.py) and scored against its label
(score.py: per-utterance CER, SpeechIO TextNorm). One run writes, for one corpus,
- a "full" version: every transcribed row of the parent version, label text unchanged, with
  metadata.qwen_asr (Lhotse custom.qwen_asr) = hypothesis, language Qwen reported, ref_tokens, hyp_tokens, errors, cer;
  rows the service could not transcribe (audio over ~157 s) are dropped and counted;
- for Cantonese, a "kept" version completing the placeholder entry: the full version's rows with a non-empty label
  and CER < 30 %, the rule that produced wenetspeech_chuan@clean-qwen3-asr-v1-20261023.
Recordings stay the parent's; no audio is copied. Every written file is read back for counts, bytes and sha256.

    python scripts/wenetspeech_qwen/register_qwen_transcripts.py chuan --root /workspace/data \
        --catalog /workspace/data/registry/catalog --qwen qwen.jsonl --scored qwen-scored.jsonl \
        --output catalog/wenetspeech_chuan_qwen.yaml --views views/wenetspeech_chuan_qwen.yaml
"""

import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import zlib
from collections import Counter
from pathlib import Path

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact, verify_artifact_file
from audio_data_contract.declarations import read_declarations, write_declarations
from audio_data_contract.state import DatasetState, load_state, write_state_atomic

KEEP_CER_BELOW = 30  # percent; the rule behind wenetspeech_chuan@clean-qwen3-asr-v1-20261023 (six listening rounds)
FIELD = "qwen_asr"
LANGUAGE = re.compile(r"language (.*?)<asr_text>", re.DOTALL)
CER_EDGES = [("0", 0, 0), ("(0,5)", 0, 5), ("[5,10)", 5, 10), ("[10,20)", 10, 20), ("[20,30)", 20, 30),
             ("[30,50)", 30, 50), ("[50,100)", 50, 100), (">=100", 100, None)]
MODEL = "Qwen/Qwen3-ASR-1.7B (shared vLLM service)"
TOOLS = "scripts/wenetspeech_qwen/qwen_infer.py, scripts/wenetspeech_qwen/score.py"

# corpus -> parent (dataset, version), source artifact and row kind, version names, languages, text normalisation.
CORPORA = {
    "chuan": {
        "dataset": "wenetspeech_chuan", "parent": ("wenetspeech_chuan", "icefall-20260908"), "kind": "cuts",
        "artifact": "train_cuts_0", "full": "qwen3-asr-full-v1-20261023", "kept": None,
        "languages": ["zh"], "norm": "speechio-textnorm-zh", "to_language": "zh", "pilot": False,
        "corpus": "WenetSpeech-Chuan 川渝方言训练集", "labels": "机器标注，不带置信度",
        "reference_cer": "Qwen 在 WSC-Eval Easy / Hard 上自身 CER 为 12.1 / 21.1",
        "note": ("原标注里有多人只标一人、漏标语音、音乐、人声太轻太远的条目，CER 高不等于 Qwen 错；"
                 "已听审的规则见 wenetspeech_chuan@clean-qwen3-asr-v1-20261023。"),
    },
    "yue-clean": {
        "dataset": "wenetspeech_yue", "parent": ("wenetspeech_yue", "icefall-20260908"), "kind": "supervisions",
        "artifact": "train_sup_0", "recordings": ("wenetspeech_yue", "icefall-20260908", "train_rec_0"),
        "full": "clean-qwen3-asr-full-v1-20261024", "kept": "clean-qwen3-asr-v1-20261024",
        "languages": ["yue"], "norm": "speechio-textnorm-yue", "to_language": None, "pilot": False,
        "corpus": "WenetSpeech-Yue 粤语训练集 clean 部分",
        "labels": "发布方多系统融合（ROVER）的机器标注，每条置信度 ≥ 0.9",
        "reference_cer": "Qwen 在 WSYue-ASR-eval short 上自身 CER 为 6.2",
        "note": "粤语保留规则沿用川渝（CER < 30 %），未单独听审。",
    },
    "yue-rest": {
        "dataset": "wenetspeech_yue", "parent": ("wenetspeech_yue_all", "icefall-20260908"),
        "kind": "supervisions", "artifact": "train_sup_0",
        "recordings": ("wenetspeech_yue_all", "icefall-20260908", "train_rec_0"),
        "exclude": ("wenetspeech_yue", "icefall-20260908", "train_sup_0"),
        "full": "nonclean-qwen3-asr-full-v1-20261025", "kept": "nonclean-qwen3-asr-v1-20261025",
        "languages": ["yue"], "norm": "speechio-textnorm-yue", "to_language": None, "pilot": False,
        "corpus": "WenetSpeech-Yue 粤语训练集里 clean 以外的部分",
        "labels": "发布方多系统融合（ROVER）的机器标注，置信度 0.6–1.0",
        "reference_cer": "Qwen 在 WSYue-ASR-eval short 上自身 CER 为 6.2；试跑 2,000 条整体 13.2%，置信度越低差异越大",
        "note": "粤语保留规则沿用川渝（CER < 30 %），未单独听审。",
    },
    "wu-pilot": {
        "dataset": "wenetspeech_wu", "parent": ("wenetspeech_wu", "icefall-20260908"), "kind": "cuts",
        "artifact": "train_cuts_0", "full": "qwen3-asr-pilot-v1-20261025", "kept": None,
        "languages": ["zh"], "norm": "speechio-textnorm-zh", "to_language": "zh", "pilot": True,
        "corpus": "WenetSpeech-Wu 吴语训练集", "labels": "吴语写法的机器标注，带置信度和普通话译文",
        "reference_cer": "Qwen 在 WenetSpeech-Wu-Bench 上自身 CER 为 24.2",
        "note": "两边文字都很乱，核对价值低。",
    },
}
EMPTY_LABEL = "label empty after TextNorm"
PILOT_ROWS = 2000
PILOT_SEED = 42


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def read_back(path):
    """Full read of a written gzip: the CRC catches lost writes. Returns (rows, bytes, sha256)."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = sum(1 for _ in stream)
    return rows, path.stat().st_size, sha256(path)


def load_languages(qwen_path):
    """id -> (language Qwen reported, crc32 of the hypothesis); the last hypothesis row per id wins, as in score.py."""
    found = {}
    with open(qwen_path, encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "hypothesis" not in row:
                continue
            match = LANGUAGE.match(row["raw"])
            found[row["id"]] = (match.group(1).strip() if match else None, zlib.crc32(row["hypothesis"].encode()))
    return found


def cer_bucket(errors, ref_tokens):
    if not ref_tokens:
        return EMPTY_LABEL
    cer = 100 * errors / ref_tokens
    if cer == 0:
        return "0"
    return next(name for name, low, high in CER_EDGES[1:] if cer >= low and (high is None or cer < high))


class GzipOut:
    """gzip writer with a fixed mtime that writes to <name>.tmp and renames on close."""

    def __init__(self, destination):
        self.destination = destination
        self.temporary = destination.with_name(destination.name + ".tmp")
        self.raw = open(self.temporary, "wb")  # noqa: SIM115 - closed in close()
        self.writer = gzip.GzipFile(fileobj=self.raw, mode="wb", mtime=0, compresslevel=6)

    def write(self, line):
        self.writer.write(line.encode("utf-8"))

    def close(self):
        self.writer.close()
        self.raw.close()
        self.temporary.replace(self.destination)


def write_rows(spec, source, scored_path, languages, exclude_ids, out_full, out_kept):
    """One pass over the parent artifact: full rows, kept rows, and the facts counters."""
    facts, buckets, hours = Counter(), Counter(), Counter()
    cuts = spec["kind"] == "cuts"
    with gzip.open(source, "rt", encoding="utf-8") as reader, open(scored_path, encoding="utf-8") as scored:
        upcoming = json.loads(next(scored, "null"))
        for line in reader:
            row = json.loads(line)
            row_id = row["id"] if cuts else row["recording_id"]
            if row_id in exclude_ids:
                facts["parent rows outside this part"] += 1
                continue
            facts["source rows"] += 1
            hours["source"] += row["duration"] / 3600
            if upcoming is None or upcoming["id"] != row_id:
                facts["rows not transcribed"] += 1
                hours["not transcribed"] += row["duration"] / 3600
                continue
            supervision = row["supervisions"][0] if cuts else row
            if upcoming["ref"] != supervision["text"]:
                raise SystemExit(f"{row_id}: label differs from the scored reference")
            language, crc = languages[row_id]
            if crc != zlib.crc32(upcoming["hyp"].encode()):
                raise SystemExit(f"{row_id}: scored hypothesis differs from the transcription file")
            ref_tokens, errors = upcoming["ref_tokens"], upcoming["errors"]
            supervision.setdefault("custom", {})[FIELD] = {
                "hypothesis": upcoming["hyp"], "language": language, "ref_tokens": ref_tokens,
                "hyp_tokens": upcoming["hyp_tokens"], "errors": errors,
                "cer": round(100 * errors / ref_tokens, 4) if ref_tokens else None}
            text = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            out_full.write(text)
            hours["full"] += row["duration"] / 3600
            facts["rows"] += 1
            facts["ref tokens"] += ref_tokens
            facts["token errors"] += errors
            facts["qwen empty"] += upcoming["hyp_tokens"] == 0
            buckets[cer_bucket(errors, ref_tokens)] += 1
            if ref_tokens and errors * 100 < KEEP_CER_BELOW * ref_tokens:
                facts["kept rows"] += 1
                hours["kept"] += row["duration"] / 3600
                if out_kept:
                    out_kept.write(text)
            upcoming = json.loads(next(scored, "null"))
        if upcoming is not None:
            raise SystemExit(f"scored row {upcoming['id']} was not found in the parent artifact (order or part mismatch)")
    return facts, buckets, hours


def artifact_entry(name, kind, relative, path, count, extra):
    rows, size, digest = read_back(path)
    if rows != count:
        raise SystemExit(f"{path}: {rows} rows read back, {count} written")
    return {"name": name, "kind": kind, "root_alias": "aidc_data", "relative_path": relative,
            "expected_bytes": size, "sha256": digest, "metadata": {"record_count": rows, **extra}}


def write_state(state, path):
    write_state_atomic(state, path)
    os.chmod(path, 0o664)  # mkstemp creates 0600; the registry is shared


def finish_state(path, version, stage, metadata, state):
    """Complete a placeholder's state file through the legal transitions; the run directory is not published."""
    current = load_state(path)
    for step in {"prepared": ["downloaded", "verified", "prepared"], "partial": []}[state]:
        current = current.transition(step)
    meta = {k: v for k, v in current.metadata.items() if k != "run_dir"}
    meta.update(metadata, stage=stage)
    write_state(DatasetState(current.dataset_id, version, current.state, current.artifacts,
                                    current.updated_at, None, meta), path)


def breakdown(buckets):
    return {name: buckets[name] for name in [n for n, _, _ in CER_EDGES] + [EMPTY_LABEL]}


def declaration(cfg, source_spec, version, artifacts, recordings, facts, hours, description, kept, state_artifact):
    entry = {
        "schema_version": source_spec["schema_version"], "dataset_id": cfg["dataset"], "version": version,
        "languages": list(cfg["languages"]), "tasks": ["asr"], "aliases": [],
    }
    if cfg["parent"][0] != cfg["dataset"] and not kept:
        entry["derived_from"] = cfg["parent"][0]
    names = [a["name"] for a in artifacts]
    roles = {"cuts": names} if cfg["kind"] == "cuts" else {
        "recordings": [r["name"] for r in recordings], "supervisions": names}
    all_artifacts = ([state_artifact] if state_artifact else []) + copy.deepcopy(recordings) + artifacts
    if state_artifact:
        roles["preparation_state"] = [state_artifact["name"]]
    count = facts["kept rows" if kept else "rows"]
    entry["artifacts"] = all_artifacts
    entry["splits"] = {"train": {"artifacts": roles, "statistics": {
        "records": count, "duration_hours": round(hours["kept" if kept else "full"], 4),
        "duration_basis": "sum of row durations"}}}
    entry["recipe_parameters"] = {"adds": [f"custom.{FIELD}"], "check_model": "Qwen3-ASR-1.7B",
                                  "check_unit": "utterance", "text_normalization": cfg["norm"]}
    if kept:
        entry["recipe_parameters"]["keep_rule"] = (
            f"label non-empty after TextNorm and per-utterance CER vs Qwen < {KEEP_CER_BELOW} %")
    entry["provenance"] = {
        "preparation_status": "partial" if cfg["pilot"] else "prepared", "lineage_status": "exact",
        "materialization": "full", "source": f"{cfg['dataset'] if kept else cfg['parent'][0]}@"
        f"{cfg['full'] if kept else cfg['parent'][1]}",
        "description": description, "facts": {k: v for k, v in facts.items()}}
    if cfg["pilot"]:
        entry["provenance"]["ready_for_training"] = False
    return entry


def view(cfg, version, source, transforms):
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{cfg['dataset']}/qwen3-asr-{'kept' if version == cfg['kept'] else 'full'}",
        "version": version, "source": {"dataset_id": source[0], "version": source[1]},
        "result": {"dataset_id": cfg["dataset"], "version": version},
        "materialization": "full", "lineage_status": "exact", "transforms": transforms,
        "provenance": {"registered_at": "2026-11-03"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corpus", choices=sorted(CORPORA))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True, help="registry catalog directory (parents' artifacts)")
    parser.add_argument("--qwen", type=Path, required=True, help="qwen_infer.py output")
    parser.add_argument("--scored", type=Path, required=True, help="score.py output")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--placeholder", type=Path, help="existing catalog file holding the placeholder entry to complete")
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    cfg = CORPORA[args.corpus]
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.root / "registry/roots.json").read_text())
    dataset, (parent_dataset, parent_version) = cfg["dataset"], cfg["parent"]
    parent = catalog.get(parent_dataset, parent_version)
    source_artifact = parent.artifact(cfg["artifact"])
    source = resolve_artifact(catalog, parent_dataset, parent_version, cfg["artifact"], roots)
    verify_artifact_file(source_artifact, source)
    exclude_ids = set()
    if "exclude" in cfg:
        d, v, name = cfg["exclude"]
        path = resolve_artifact(catalog, d, v, name, roots)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            exclude_ids = {json.loads(line)["recording_id"] for line in stream}
    recordings = []
    if "recordings" in cfg:
        d, v, name = cfg["recordings"]
        recordings = [copy.deepcopy(next(a for a in catalog.get(d, v).to_dict()["artifacts"] if a["name"] == name))]

    versions = [cfg["full"]] + ([cfg["kept"]] if cfg["kept"] else [])
    version_dirs = {v: args.root / "datasets" / dataset / "versions" / v for v in versions}
    placeholder = None
    if cfg["kept"] and args.placeholder:
        placeholder = next(r for _, r in read_declarations(args.placeholder) if r["version"] == cfg["kept"])
    for v, directory in version_dirs.items():
        if any(p.name != "state.json" for p in directory.glob("*")):
            raise SystemExit(f"{directory} already holds data; versions are immutable")
        directory.mkdir(parents=True, exist_ok=True)

    languages = load_languages(args.qwen)
    stem = f"{dataset}_{'cuts' if cfg['kind'] == 'cuts' else 'supervisions'}_train"
    full_name = f"{stem}_qwen.jsonl.gz"
    kept_name = f"{stem}_qwen_cer_lt{KEEP_CER_BELOW}.jsonl.gz"
    full_path = version_dirs[cfg["full"]] / full_name
    kept_path = version_dirs[cfg["kept"]] / kept_name if cfg["kept"] else None
    out_full, out_kept = GzipOut(full_path), GzipOut(kept_path) if kept_path else None
    facts, buckets, hours = write_rows(cfg, source, args.scored, languages, exclude_ids, out_full, out_kept)
    out_full.close()
    if out_kept:
        out_kept.close()
    facts["rows not transcribed"] = facts.get("rows not transcribed", 0)
    if cfg["pilot"]:  # the pilot is a sample; "not transcribed" would only count the unsampled rest
        facts.pop("rows not transcribed")
        facts.pop("source rows")
    corpus_cer = 100 * facts["token errors"] / facts["ref tokens"]
    facts = Counter({**facts, "corpus CER": round(corpus_cer, 2)})
    stats = {"cer_share_rows": breakdown(buckets), "source_hours": round(hours["source"], 1)}

    kind = "lhotse-cuts" if cfg["kind"] == "cuts" else "lhotse-supervisions"
    prefix = "train_cuts" if cfg["kind"] == "cuts" else "train_supervisions"
    extra = {"qwen_field": f"custom.{FIELD}"}
    full_art = artifact_entry(f"{prefix}_qwen_0", kind, f"datasets/{dataset}/versions/{cfg['full']}/{full_name}",
                              full_path, facts["rows"], extra)
    declarations, views = [], []
    inputs = [{"file": p.name, "sha256": sha256(p)} for p in (args.qwen, args.scored)]
    request = {"temperature": 0, "max_tokens": 2048, "repetition_penalty": 1.1,
               "to_language": cfg["to_language"] or "not sent (language auto)"}
    share = f"{100 * facts['kept rows'] / facts['rows']:.1f}"
    pilot = (f"试跑：从 {parent_dataset}@{parent_version} 训练集按种子 {PILOT_SEED} 随机抽 {PILOT_ROWS} 条，"
             "不是全量，整体 CER 35.8 %，不可用于训练。") if cfg["pilot"] else None
    description = (
        f"{parent_dataset}@{parent_version} 里{cfg['corpus']}的"
        + ("随机抽样" if cfg["pilot"] else "全部可转写条目")
        + f"（{facts['rows']:,} 条 / {hours['full']:.1f} h），原标注（{cfg['labels']}）一字不改；"
        f"每条加 custom.{FIELD}：共享的 Qwen3-ASR-1.7B 的转写（hypothesis）、Qwen 报告的语种（language）和与原标注的字错误率"
        f"（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。"
        f"整体 CER {corpus_cer:.2f} %，{cfg['reference_cer']}；Qwen 空输出 {facts['qwen empty']:,} 条。"
        + (f"源 {facts['source rows']:,} 条里 {facts['rows not transcribed']:,} 条（"
           f"{hours['not transcribed']:.1f} h，超过约 157 s，服务拒收）没有转写，不在本版本内。"
           if facts.get("rows not transcribed") and not cfg["pilot"] else "")
        + (pilot or "") + cfg["note"] + "录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/。")
    state_artifact = None
    if cfg["pilot"]:
        state_artifact = {"name": "preparation_state", "kind": "dataset-state", "root_alias": "aidc_data",
                          "relative_path": f"datasets/{dataset}/versions/{cfg['full']}/state.json"}
        write_state(DatasetState(dataset, cfg["full"], "partial", {}, metadata={
            "owner": "mingdong", "stage": "pilot only, not for training",
            "note": "2,000 sampled rows; Qwen disagrees with the labels on most rows and both sides are noisy",
            "pilot_rows": facts["rows"], "corpus_cer": round(corpus_cer, 2)}), version_dirs[cfg["full"]] / "state.json")
    declarations.append(declaration(cfg, parent.to_dict(), cfg["full"], [full_art], recordings, facts, hours,
                                    description, False, state_artifact))
    annotate = {
        "name": "qwen3-asr-transcript", "version": f"v1-{cfg['full'][-8:]}", "kind": "annotate",
        "writes": [f"metadata.{FIELD}"],
        "parameters": {
            "model": MODEL, "request": request, "audio": "16 kHz PCM WAV read from the source tar at the row's byte range",
            "scoring": {"text_normalization": cfg["norm"], "unit": "one token per CJK character, punctuation dropped",
                        "cer": "100 * errors / ref_tokens, null when ref_tokens is 0"},
            "tool": TOOLS, "label_inputs": inputs, "corpus_cer": round(corpus_cer, 2),
            "qwen_empty_rows": facts["qwen empty"], "cer_share_rows": stats["cer_share_rows"]}}
    transforms = []
    if cfg["pilot"] or facts["rows not transcribed"]:
        transforms.append({
            "name": "transcribed-rows", "version": "v1", "kind": "filter", "writes": ["$membership"],
            "parameters": {"kept": (f"{PILOT_ROWS} rows sampled with random.Random({PILOT_SEED}).sample over the parent's rows"
                                    if cfg["pilot"] else "rows with a Qwen transcript; audio over about 157 s is refused by the service"),
                           "input_rows": None if cfg["pilot"] else facts["source rows"], "output_rows": facts["rows"]}})
    if "exclude" in cfg:
        transforms.insert(0, {
            "name": "outside-clean-part", "version": "v1", "kind": "filter", "writes": ["$membership"],
            "parameters": {"kept": "supervisions of wenetspeech_yue_all whose recording is not in wenetspeech_yue@icefall-20260908 train",
                           "parent_rows": facts["source rows"] + facts["parent rows outside this part"],
                           "rows": facts["source rows"]}})
    views.append(view(cfg, cfg["full"], cfg["parent"], transforms + [annotate]))
    result = {"full": {"rows": facts["rows"], "hours": round(hours["full"], 1)}}
    if cfg["kept"]:
        kept_art = artifact_entry(f"{prefix}_clean_0", kind,
                                  f"datasets/{dataset}/versions/{cfg['kept']}/{kept_name}", kept_path,
                                  facts["kept rows"], extra)
        state_art = copy.deepcopy(next(a for a in placeholder["artifacts"] if a["name"] == "preparation_state"))
        kept_description = (
            f"{cfg['corpus']}（{parent_dataset}@{parent_version}）用 Qwen3-ASR-1.7B 逐条核对后保留的部分：原标注规范化后非空且与 Qwen 的"
            f"字错误率 < {KEEP_CER_BELOW} % 的 {facts['kept rows']:,} 条 / {hours['kept']:.1f} h（占可转写 {facts['rows']:,} 条的 {share} %），"
            f"规则同 wenetspeech_chuan@clean-qwen3-asr-v1-20261023；原标注不改，不拿 Qwen 的文字替换。"
            f"每行保留 custom.{FIELD}（Qwen 转写、语种、CER），与 {dataset}@{cfg['full']} 中的相同；"
            f"被去掉的条目和全部转写见 {dataset}@{cfg['full']}。{cfg['note']}录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/。")
        entry = declaration(cfg, parent.to_dict(), cfg["kept"], [kept_art], recordings, facts, hours, kept_description,
                            True, state_art)
        entry["provenance"]["summary"] = placeholder["provenance"].get("summary", cfg["corpus"])
        entry["provenance"]["owner"] = placeholder["provenance"].get("owner", "mingdong")
        entry["splits"]["train"]["statistics"].update(
            records_before_filter=facts["rows"], hours_before_filter=round(hours["full"], 1))
        declarations.insert(0, entry)
        views.append(view(cfg, cfg["kept"], (dataset, cfg["full"]), [{
            "name": "cer-filter", "version": "v1", "kind": "filter", "writes": ["$membership"],
            "parameters": {
                "rule": f"ref_tokens > 0 and 100 * errors / ref_tokens < {KEEP_CER_BELOW}",
                "same_rule_as": "wenetspeech_chuan@clean-qwen3-asr-v1-20261023 (agreed after six listening rounds on Sichuanese)",
                "listening_review": "none for this corpus", "input_rows": facts["rows"], "output_rows": facts["kept rows"],
                "tool": "scripts/wenetspeech_qwen/register_qwen_transcripts.py"}}]))
        result["kept"] = {"rows": facts["kept rows"], "hours": round(hours["kept"], 1)}
        finish_state(version_dirs[cfg["kept"]] / "state.json", cfg["kept"],
                     "completed: kept rows (label CER vs Qwen < 30 %); full transcripts in " + cfg["full"],
                     {"transcribed": facts["rows"], "kept": facts["kept rows"], "corpus_cer": round(corpus_cer, 2),
                      "cer_share_rows": stats["cer_share_rows"]}, "prepared")
    # JSON round trip: entries sharing a list (languages, recordings) would otherwise be written as YAML anchors
    write_declarations(args.output, json.loads(json.dumps(declarations)))
    write_declarations(args.views, json.loads(json.dumps(views)))
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / f"{args.corpus}.json").write_text(
        json.dumps({"inputs": inputs, "facts": dict(facts), "hours": dict(hours), "result": result, "stats": stats},
                   ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"facts": dict(facts), "hours": dict(hours), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
