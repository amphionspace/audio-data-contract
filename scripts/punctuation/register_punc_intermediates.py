#!/usr/bin/env python3
"""Register the written-punctuation intermediates as new versions of their source datasets.

The punctuation work (amphiondata docs/written-punctuation.md) produced three label sets that belong to many source
corpora. Each is registered per SOURCE dataset, rows keyed by the source supervision id, `text` unchanged:

- <d>@punc-teacher-v1-20261029 (Mandarin) and <d>@punc-teacher-v1-20261102 (English): the Qwen3.8-27B teacher output on
  the 100k-utterance teacher sets that trained the Qwen3-4B students. custom.punctuation_teacher = {text, ok, input}
  (ok: the output equals the input once marks are removed; input: the unpunctuated text the model was given),
  custom.punctuation_hint = {qwen} (the Qwen3-ASR transcript shown to the Mandarin teacher). The 2,000 Mandarin
  held-out utterances also carry custom.punctuation_student = {text, ok}, the student-v1 output used to compare it with
  the teacher.
- <d>@punc-gold-v1-20261029: the 200 hand-written reference punctuations of the Mandarin pilot (spec v1, compact
  commas). custom.punctuation_gold = {text}, custom.punctuation_hint = {qwen, firered}.

Rows are the source supervisions, kept in source order with every other field unchanged; recordings are the source's.
Teacher rows that cannot be mapped to a registered supervision id are not registered; they are listed in
--record/unmapped.json (English `ami-<hash>` window texts, whose ids are not supervision ids of any registered dataset).

    python scripts/punctuation/register_punc_intermediates.py --root /workspace/data --catalog catalog \
        --zh-teacher-input teacher_input.jsonl --zh-teacher-output teacher_out.jsonl \
        --zh-holdout-input holdout_input.jsonl --zh-holdout-output holdout_S1.jsonl \
        --en-teacher-input teacher_input.jsonl --en-teacher-output teacher_out.jsonl \
        --gold-input pilot.jsonl --gold gold.jsonl \
        --output catalog/punc_teacher_v1.yaml --views views/punc_teacher_v1.yaml \
        --record /workspace/data/migration/register-punc-intermediates-v1
"""

import argparse
import contextlib
import copy
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from audio_data_contract import load_catalog
from audio_data_contract.declarations import write_declarations

ZH_MARKS = "，。？！、：；“”《》"
ZH_HALF = str.maketrans({",": "，", "?": "？", "!": "！", ":": "：", ";": "；"})
EN_MARKS = ",.?!;:"
ID_PATTERN = re.compile(r'"id":"([^"]*)"')
TEACHER_PROMPT = "amphiondata src/amphiondata/enrichment/{module}.py SYSTEM at {commit}"
# teacher-set source name -> (dataset, parent version, supervision artifacts, recording artifacts), relative to --root
SOURCES = {
    "wenetspeech": ("wenetspeech_clean", "clean-v3-pass-20261027",
                    ["datasets/wenetspeech_clean/versions/clean-v3-pass-20261027/supervisions/train.jsonl.gz"],
                    ["datasets/wenetspeech/source/cos-backup-20261011/relocated/LHOTSE/WenetSpeech/data/manifests/wenetspeech_recordings_L.jsonl.gz"]),
    "kespeech": ("kespeech", "icefall-20260908",
                 [f"datasets/kespeech/versions/legacy-20260804/train_sup_{i}/kespeech-asr_supervisions_train_phase{i + 1}.jsonl.gz" for i in (0, 1)],
                 [f"datasets/kespeech/versions/legacy-20260804/train_rec_{i}/kespeech-asr_recordings_train_phase{i + 1}.jsonl.gz" for i in (0, 1)]),
    "aishell2": ("aishell2", "icefall-20260908",
                 ["datasets/aishell2/versions/legacy-20260804/train_sup_0/aishell2_supervisions_train.jsonl.gz"],
                 ["datasets/aishell2/versions/legacy-20260804/train_rec_0/aishell2_recordings_train.jsonl.gz"]),
    "aishell": ("aishell", "icefall-20260908",
                ["datasets/aishell/versions/legacy-20260804/train_sup_0/aishell_supervisions_train.jsonl.gz"],
                ["datasets/aishell/versions/legacy-20260804/train_rec_0/aishell_recordings_train.jsonl.gz"]),
    "magicdata_ramc": ("magicdata_ramc", "icefall-20260908",
                       ["datasets/magicdata_ramc/versions/legacy-20260804/train_sup_0/magicdata_ramc_supervisions_train.jsonl.gz"],
                       ["datasets/magicdata_ramc/versions/legacy-20260804/train_rec_0/magicdata_ramc_recordings_train.jsonl.gz"]),
    "alimeeting_sdm": ("alimeeting_sdm", "icefall-20260908",
                       ["datasets/alimeeting_sdm/versions/icefall-20260908/train_sup_0/alimeeting_sdm_supervisions_train.jsonl.gz"],
                       ["datasets/alimeeting_sdm/versions/icefall-20260908/train_rec_0/alimeeting_sdm_recordings_train.jsonl.gz"]),
    "aishell4": ("aishell4", "icefall-20260908",
                 ["datasets/aishell4/versions/legacy-20260804/train_sup_0/aishell4_supervisions_train_L.jsonl.gz",
                  "datasets/aishell4/versions/icefall-20260908/train_sup_1/aishell4_supervisions_train_M.jsonl.gz",
                  "datasets/aishell4/versions/icefall-20260908/train_sup_2/aishell4_supervisions_train_S.jsonl.gz"],
                 ["datasets/aishell4/versions/legacy-20260804/train_rec_0/aishell4_recordings_train_L.jsonl.gz",
                  "datasets/aishell4/versions/icefall-20260908/train_rec_1/aishell4_recordings_train_M.jsonl.gz",
                  "datasets/aishell4/versions/icefall-20260908/train_rec_2/aishell4_recordings_train_S.jsonl.gz"]),
    "vitw_far_field": ("vitw_far_field", "icefall-20260908",
                       ["datasets/vitw_far_field/versions/icefall-20260908/train_sup_0/vitw_supervisions_far_field.jsonl.gz"],
                       ["datasets/vitw_far_field/versions/icefall-20260908/train_rec_0/vitw_recordings_far_field.jsonl.gz"]),
    "realman": ("realman", "icefall-20260908",
                ["datasets/realman/versions/icefall-20260908/train_sup_0/realman_supervisions_train.jsonl.gz"],
                ["datasets/realman/versions/icefall-20260908/train_rec_0/realman_recordings_train.jsonl.gz"]),
    "gigaspeech": ("gigaspeech", "legacy-20260804",
                   ["datasets/gigaspeech/versions/legacy-20260804/train_sup_0/gigaspeech_supervisions_XL.jsonl.gz"],
                   ["datasets/gigaspeech/versions/legacy-20260804/train_rec_0/gigaspeech_recordings_XL.jsonl.gz"]),
    "common_voice_en": ("common_voice_en", "legacy-20260804",
                        ["datasets/common_voice_en/versions/legacy-20260804/train_sup_0/cv-en_supervisions_train_cleaned.jsonl.gz"],
                        ["datasets/common_voice_en/versions/legacy-20260804/train_rec_0/cv-en_recordings_train.jsonl.gz"]),
    "librispeech": ("librispeech", "legacy-20260804",
                    [f"datasets/librispeech/versions/legacy-20260804/train_sup_{i}/librispeech_supervisions_{name}.jsonl.gz"
                     for i, name in enumerate(["train-clean-100", "train-clean-360", "train-other-500"])],
                    [f"datasets/librispeech/versions/legacy-20260804/train_rec_{i}/librispeech_recordings_{name}.jsonl.gz"
                     for i, name in enumerate(["train-clean-100", "train-clean-360", "train-other-500"])]),
}
CACHE = {}
DECLARATIONS_ONLY = False  # --declarations-only: rebuild catalog and views from the files already registered


def sha256(path):
    path = str(path)
    if path not in CACHE:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1 << 22), b""):
                digest.update(block)
        CACHE[path] = digest.hexdigest()
    return CACHE[path]


def jsonl(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def label_zh(text):
    return "".join(c for c in text.strip().translate(ZH_HALF) if c not in ZH_MARKS)


def label_en(text):
    return re.sub(r"\s+", " ", "".join(c for c in text if c not in EN_MARKS).lower()).strip()


def count_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:  # full read-back: the gzip CRC catches lost writes
        return sum(1 for _ in stream)


def artifact(root, name, kind, path, **metadata):
    entry = {"name": name, "kind": kind, "root_alias": "aidc_data", "relative_path": str(Path(path).relative_to(root)),
             "expected_bytes": Path(path).stat().st_size, "sha256": sha256(path)}
    if metadata:
        entry["metadata"] = metadata
    return entry


def parent_rows(root, relatives, wanted):
    """Rows of the parent supervision files whose id is wanted, in file order."""
    for relative in relatives:
        with gzip.open(root / relative, "rt", encoding="utf-8") as stream:
            for line in stream:
                if wanted.isdisjoint(ID_PATTERN.findall(line)):
                    continue
                row = json.loads(line)
                if row["id"] in wanted:
                    yield row


def registered_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def recording_ids(root, relatives):
    ids = set()
    for relative in relatives:
        with gzip.open(root / relative, "rt", encoding="utf-8") as stream:
            ids.update(json.loads(line)["id"] for line in stream if line.strip())
    return ids


class LabelSet:
    """One registered label kind: its version, per-source extras keyed by supervision id, and its inputs."""

    def __init__(self, topic, version, language, extras, inputs, label_of):
        self.topic, self.version, self.language, self.extras = topic, version, language, extras
        self.inputs, self.label_of = inputs, label_of
        self.extras_keys = {SOURCES[s][0]: extras_kinds(e) for s, e in extras.items() if s in SOURCES}
        self.unmapped = Counter()
        self.unmapped_ids = []


def teacher_set(version, language, input_path, output_path, holdout=None):
    rows, outputs = jsonl(input_path), {r["id"]: r for r in jsonl(output_path)}
    if set(outputs) != {r["id"] for r in rows}:
        raise SystemExit(f"{output_path}: ids differ from {input_path}")
    student = {r["id"]: r for r in jsonl(holdout[1])} if holdout else {}
    held = {r["id"]: r for r in jsonl(holdout[0])} if holdout else {}
    if holdout and (set(student) != set(held) or not set(held) <= set(outputs)):
        raise SystemExit("holdout outputs and inputs disagree, or the holdout is not inside the teacher set")
    extras = {}
    for row in rows:
        out = outputs[row["id"]]
        extra = {"punctuation_teacher": {"text": out["text"], "ok": out["ok"], "input": row["label"]}}
        if row.get("qwen"):
            extra["punctuation_hint"] = {"qwen": row["qwen"]}
        if row["id"] in student:
            extra["punctuation_student"] = {"text": student[row["id"]]["text"], "ok": student[row["id"]]["ok"]}
        extras.setdefault(row["source"], {})[row["id"]] = extra
    inputs = {"teacher_input": input_path, "teacher_output": output_path}
    if holdout:
        inputs.update(holdout_input=holdout[0], holdout_student_output=holdout[1])
    return LabelSet("punc-teacher", version, language, extras, inputs, label_zh if language == "zh" else label_en)


def gold_set(version, pilot_path, gold_path):
    pilot, gold = jsonl(pilot_path), {r["id"]: r for r in jsonl(gold_path)}
    if set(gold) != {r["id"] for r in pilot}:
        raise SystemExit("gold ids differ from the pilot ids")
    extras = {}
    for row in pilot:
        extra = {"punctuation_gold": {"text": gold[row["id"]]["text"]},
                 "punctuation_hint": {"qwen": row.get("qwen"), "firered": row.get("firered")}}
        extras.setdefault(row["source"], {})[row["id"]] = extra
    # pilot labels are already stripped of marks (gold_v1.py), the parent text is not
    return LabelSet("punc-gold", version, "zh", extras, {"pilot": pilot_path, "gold": gold_path}, label_zh)


def register(label_set, root, catalog, facts_out):
    declarations, views = [], []
    for source, wanted_extras in label_set.extras.items():
        if source not in SOURCES:
            label_set.unmapped[source] += len(wanted_extras)
            label_set.unmapped_ids += sorted(wanted_extras)
            continue
        dataset, parent, sup_files, rec_files = SOURCES[source]
        catalog.get(dataset, parent)  # the parent version must be registered
        recordings = recording_ids(root, rec_files)
        out_dir = root / "datasets" / dataset / "versions" / label_set.version
        if not DECLARATIONS_ONLY:
            if out_dir.exists():
                raise SystemExit(f"{out_dir} exists; versions are immutable")
            out_dir.mkdir(parents=True)
        destination = out_dir / f"{dataset}_supervisions_{label_set.topic.replace('-', '_')}.jsonl.gz"
        temporary = destination.with_name(destination.name + ".tmp")
        facts, seen, seconds = Counter(), set(), 0.0
        wanted = set(wanted_extras)
        with contextlib.ExitStack() as stack:
            if DECLARATIONS_ONLY:
                writer = None
                rows = registered_rows(destination)
            else:
                raw = stack.enter_context(open(temporary, "wb"))
                writer = stack.enter_context(gzip.GzipFile(fileobj=raw, mode="wb", mtime=0))
                rows = parent_rows(root, sup_files, wanted)
            for row in rows:
                if row["id"] in seen:
                    raise SystemExit(f"{dataset}: duplicate supervision id {row['id']}")
                seen.add(row["id"])
                extra = wanted_extras[row["id"]]
                if DECLARATIONS_ONLY:  # the registered row must carry exactly these labels
                    if {k: row["custom"].get(k) for k in extra} != extra:
                        raise SystemExit(f"{dataset}: registered row {row['id']} differs from the label files")
                else:
                    clash = set(extra) & set(row.get("custom") or {})
                    if clash:
                        raise SystemExit(f"{dataset}: {row['id']} already has custom {sorted(clash)}")
                facts["rows"] += 1
                seconds += float(row["duration"])
                facts["recording missing from the recordings"] += row["recording_id"] not in recordings
                teacher, gold = extra.get("punctuation_teacher"), extra.get("punctuation_gold")
                if teacher:
                    facts["rows whose input differs from the parent text"] += teacher["input"] != label_set.label_of(row["text"])
                    facts["rows ok (output keeps the input)"] += bool(teacher["ok"])
                    facts["ok flag differs from recomputation"] += bool(teacher["ok"]) != (
                        label_set.label_of(teacher["text"]) == teacher["input"])
                if gold:
                    facts["gold differs from the parent text beyond marks"] += label_set.label_of(gold["text"]) != label_set.label_of(row["text"])
                facts["rows with held-out student output"] += "punctuation_student" in extra
                if writer:
                    row["custom"] = {**(row.get("custom") or {}), **extra}
                    writer.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        if not DECLARATIONS_ONLY:
            temporary.replace(destination)
        count = count_lines(destination)
        missing = sorted(wanted - seen)
        label_set.unmapped[source] += len(missing)
        label_set.unmapped_ids += missing
        if count != facts["rows"] or facts["recording missing from the recordings"]:
            raise SystemExit(f"{dataset}: read-back {count} rows vs {facts['rows']}; facts {dict(facts)}")
        facts["labels without a parent row (not registered)"] = len(missing)
        recording_artifacts = []
        for index, relative in enumerate(rec_files):
            entry = artifact(root, f"train_rec_{index}", "lhotse-recordings", root / relative,
                             record_count=count_lines(root / relative), shared_with=f"{dataset}@{parent}")
            recording_artifacts.append(entry)
        supervisions = artifact(root, f"train_supervisions_{label_set.topic.replace('-', '_')}", "lhotse-supervisions",
                                destination, record_count=count, punctuated=False)
        declarations.append(declaration(label_set, dataset, parent, catalog, recording_artifacts, supervisions, facts, seconds))
        views.append(view(label_set, dataset, parent, facts, extras_kinds(wanted_extras)))
        facts_out[f"{label_set.topic}@{label_set.version}:{dataset}"] = dict(facts)
        print(label_set.version, dataset, dict(facts), flush=True)
    return declarations, views


def extras_kinds(extras):
    return sorted({key for extra in extras.values() for key in extra})


def declaration(label_set, dataset, parent, catalog, recordings, supervisions, facts, seconds):
    source = catalog.get(dataset, parent).to_dict()
    kind = label_set.topic
    if kind == "punc-teacher":
        what = (
            f"Qwen3.8-27B 老师给 {facts['rows']} 句加的{'书面化' if label_set.language == 'zh' else '英文'}标点（"
            f"{facts['rows ok (output keeps the input)']} 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和"
            "模型看到的无标点输入 input"
            + ("；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写" if label_set.language == "zh" else "")
            + (f"；其中 {facts['rows with held-out student output']} 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student"
               if facts["rows with held-out student output"] else "")
            + "。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/"
            + ("build_teacher_set.py" if label_set.language == "zh" else "build_teacher_set_en.py") + "。")
    else:
        what = (f"普通话标点试点的 {facts['rows']} 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，"
                "custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。")
    return {
        "schema_version": source["schema_version"], "dataset_id": dataset, "version": label_set.version,
        "languages": list(source["languages"]), "tasks": ["asr"], "aliases": [],
        "artifacts": copy.deepcopy(recordings) + [supervisions],
        "splits": {"train": {
            "artifacts": {"recordings": [r["name"] for r in recordings], "supervisions": [supervisions["name"]]},
            "statistics": {"records": facts["rows"], "duration_hours": round(seconds / 3600, 4),
                           "duration_basis": "sum of supervision durations"}}},
        "recipe_parameters": {"adds": ["custom." + k for k in sorted(label_set.extras_keys[dataset])],
                              "rows": "labelled utterances only"},
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{parent}",
            "description": (
                f"{dataset}@{parent} 的 train 监督片段里的 {what}只含这些句子，text 与父版本相同，不是标点后的文本；"
                "录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。"
                "脚本 scripts/punctuation/register_punc_intermediates.py。"),
            "facts": dict(facts)},
    }


def view(label_set, dataset, parent, facts, kinds):
    inputs = [{"file": Path(path).name, "role": role, "sha256": sha256(path)} for role, path in label_set.inputs.items()]
    zh = label_set.language == "zh"
    if label_set.topic == "punc-teacher":
        params = {
            "model": "Qwen3.8-27B", "server": "vLLM 0.18, temperature 0, thinking off",
            "prompt": TEACHER_PROMPT.format(module="written_punctuation" if zh else "written_punctuation_en",
                                            commit="55313b6" if zh else "7812522"),
            "texts_per_request": 8, "spec": "GB/T 15834 written style, compact commas" if zh else "en-v1: , . ? ! ; :, truecase",
            "ok": "output equals the input once marks are removed" if zh else "output equals the input once lowercased and marks are removed",
            "tool": "amphiondata scripts/punctuation/" + ("punc_llm.py" if zh else "punc_llm_en.py"),
            "sampling": "amphiondata scripts/punctuation/" + ("build_teacher_set.py" if zh else "build_teacher_set_en.py"),
            "label_inputs": inputs, "rows": facts["rows"]}
        if zh:
            params["hint"] = "Qwen3-ASR-1.7B transcript: stored cleaning transcript for WenetSpeech, transcribe_hints.py for the others"
        writes = ["$membership", "metadata.punctuation_teacher"]
        writes += ["metadata.punctuation_hint"] if "punctuation_hint" in kinds else []
        writes += ["metadata.punctuation_student"] if "punctuation_student" in kinds else []
        name, version = "punctuation-teacher", label_set.version.removeprefix("punc-teacher-")
        if "punctuation_student" in kinds:
            params["student"] = "Qwen3-4B-Instruct-2507 LoRA r=16, 1 epoch on the 96,201 ok teacher rows outside the held-out 2,000"
    else:
        params = {"reference": "hand-written to spec v1 (compact commas); removing the marks gives the unpunctuated label",
                  "sample": "amphiondata pilot: 120 WenetSpeech clean-v3 + 80 other Mandarin training utterances",
                  "hints": "Qwen3-ASR-1.7B and FireRedPunc punctuated transcripts", "label_inputs": inputs, "rows": facts["rows"]}
        writes = ["$membership", "metadata.punctuation_gold", "metadata.punctuation_hint"]
        name, version = "punctuation-gold", label_set.version.removeprefix("punc-gold-")
    return {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/{label_set.topic}", "version": label_set.version,
        "source": {"dataset_id": dataset, "version": parent}, "result": {"dataset_id": dataset, "version": label_set.version},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{"name": name, "version": version, "kind": "annotate", "writes": writes, "parameters": params}],
        "provenance": {"registered_at": "2026-11-03"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("catalog"))
    for name in ("zh-teacher-input", "zh-teacher-output", "zh-holdout-input", "zh-holdout-output", "en-teacher-input",
                 "en-teacher-output", "gold-input", "gold"):
        parser.add_argument(f"--{name}", type=Path, required=True)
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
    catalog = load_catalog(args.catalog)
    sets = [
        teacher_set("punc-teacher-v1-20261029", "zh", args.zh_teacher_input, args.zh_teacher_output,
                    (args.zh_holdout_input, args.zh_holdout_output)),
        gold_set("punc-gold-v1-20261029", args.gold_input, args.gold),
        teacher_set("punc-teacher-v1-20261102", "en", args.en_teacher_input, args.en_teacher_output),
    ]
    declarations, views, facts, unmapped = [], [], {}, {}
    for label_set in sets:
        found_declarations, found_views = register(label_set, args.root, catalog, facts)
        declarations += found_declarations
        views += found_views
        unmapped[label_set.version] = {"by_source": dict(label_set.unmapped), "ids": label_set.unmapped_ids}
    # JSON round trip: entries sharing an object would otherwise be written as YAML anchors
    write_declarations(args.output, json.loads(json.dumps(declarations)))
    write_declarations(args.views, json.loads(json.dumps(views)))
    for path, header in ((args.output, args.catalog_header), (args.views, args.views_header)):
        if header:
            path.write_text(f"# {header}\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    if args.declarations_only:  # the counts of the original registration must still hold
        if json.loads((args.record / "facts.json").read_text()) != facts \
                or json.loads((args.record / "unmapped.json").read_text()) != json.loads(json.dumps(unmapped)):
            raise SystemExit("recomputed counts differ from the record of the original registration")
        return
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1) + "\n")
    (args.record / "unmapped.json").write_text(json.dumps(unmapped, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
