"""Register the diarization teacher labels of the 2026-10 distillation work as dataset versions plus views.

Every item attaches to the dataset the recordings already belong to (never a new *_labels id) and writes a new
immutable version under <root>/datasets/<dataset>/versions/<version>/. Recordings are referenced from the parent
version (artifact dicts copied), never copied. Teacher output is stored as audio-record/1.0 rows (see common.py);
Lhotse supervisions keep canonical fields. Every written file is read back for counts, bytes and sha256.

    python scripts/diarization_raw_labels/register_raw_labels.py ITEM \
        --root /workspace/data --catalog /workspace/data/registry/catalog \
        --runs /path/to/amphiondata --output catalog/diarization_raw_ITEM.yaml \
        --views views/diarization_raw_ITEM.yaml --record /path/to/record-dir

ITEM is one of: gigaspeech-census, ramc-gap, teacher-calibration, zh-meeting-review, real-meetings, wenetspeech-l,
emilia2-128k, emilia2-64k. --runs is the directory holding the original run directories (read only).
"""

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from common import (
    Writer,
    artifact,
    declaration,
    label_rows,
    make_dir,
    merged_rows,
    parent_artifacts,
    provenance,
    read_jsonl,
    record,
    save,
    scrub,
    transform,
    view,
    window_lookup,
    window_rows,
    winning_rows,
)

from audio_data_contract import load_catalog

LHOTSE_SUP = "lhotse-supervisions"
LHOTSE_REC = "lhotse-recordings"
RECORDS = "audio-records"


class Build:
    """One new dataset version: writes artifact files and collects the declaration pieces."""

    def __init__(self, args, catalog, dataset, version, parent):
        self.args, self.catalog = args, catalog
        self.dataset, self.version, self.parent = dataset, version, parent
        self.out = make_dir(args.root, dataset, version)
        self.artifacts, self.splits = [], defaultdict(lambda: defaultdict(list))
        self.facts, self.dropped = Counter(), Counter()
        self.ref = (dataset, parent, "train")

    def reference(self, names, split="train", dataset=None, version=None):
        for art in parent_artifacts(self.catalog, dataset or self.dataset, version or self.parent, names):
            self.artifacts.append(art)
            role = {LHOTSE_REC: "recordings", LHOTSE_SUP: "supervisions"}.get(art["kind"], "audio_index")
            self.splits[split][role].append(art["name"])

    def write(self, name, filename, rows, role="records", kind=RECORDS, split="train", metadata=None):
        writer = Writer(self.out, filename)
        for row in rows:
            writer.write(row)
        count = writer.close()
        self.artifacts.append(artifact(name, kind, self.dataset, self.version, filename, count, self.out, metadata))
        if role:  # role None: a plain artifact, listed in no split
            self.splits[split][role].append(name)
        self.facts[f"{name} rows"] = count
        return count

    def labels(self, name, filename, path, metadata_key, extra=None, split="train", id_of=None, dedupe=True,
               ref=None, language=None, lookup=None):
        counters = Counter()
        paths = [path] if isinstance(path, (str, Path)) else list(path)
        keep = winning_rows(paths) if dedupe else None
        rows = label_rows(paths, ref or self.ref, metadata_key, self.dropped, counters, extra, id_of, lookup, keep)
        if language:
            rows = ({**r, "language": language} for r in rows)
        count = self.write(name, filename, rows, split=split)
        for key, value in counters.items():
            self.facts[f"{name}: {key}"] = value
        return count

    def derived(self, name, filename, make_rows, paths, metadata_key, split="train", language=None):
        """windows / merged rows: make_rows is window_rows or merged_rows."""
        counters = Counter()
        rows = make_rows(paths, self.ref, metadata_key, self.dropped, counters)
        if language:
            rows = ({**r, "language": language} for r in rows)
        count = self.write(name, filename, rows, split=split)
        for key, value in counters.items():
            self.facts[f"{name}: {key}"] = value
        return count

    def splits_dict(self, statistics=None):
        out = {}
        for split, roles in self.splits.items():
            out[split] = {"artifacts": {role: list(names) for role, names in roles.items()}}
            if statistics and split in statistics:
                out[split]["statistics"] = statistics[split]
        return out


def run_config(path):
    """Teacher backend settings from a run.json, without the local input paths."""
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    for key in ("created", "argv", "inputs", "catalog", "segments"):
        config.pop(key, None)
    return scrub(config, Counter())


def finish(args, build, languages, tasks, parent, description, view_topic, transforms, status="prepared",
           ready=True, statistics=None, recipe=None, **extra):
    entry = declaration(build.dataset, build.version, languages, tasks, build.artifacts,
                        build.splits_dict(statistics),
                        provenance(f"{build.dataset}@{parent}", description, status, ready, build.facts, **extra),
                        recipe)
    return entry, view(build.dataset, view_topic, build.version, parent, transforms)


# ----------------------------------------------------------------------------------------------------------------
def gigaspeech_census(args, catalog):
    runs = Path(args.runs) / "gigaspeech-youtube-diarize-20261009"
    version = "youtube-diarize-census-v1-20261009"
    build = Build(args, catalog, "gigaspeech", version, "legacy-20260804")
    build.ref = ("gigaspeech", version, "train")
    build.write("youtube_xl_recordings", "youtube_xl_recordings.jsonl.gz",
                (scrub(r, build.dropped) for r in read_jsonl(runs / "inputs/youtube_xl_recordings.jsonl.gz")),
                role="recordings", kind=LHOTSE_REC, metadata={"description": "GigaSpeech XL 的 YOU* 录音（普查输入）"})
    census = {r["recording_id"]: {"speaker_census": {k: v for k, v in r.items() if k != "recording_id"}}
              for r in read_jsonl(runs / "speaker_counts.jsonl")}
    build.labels("local_moss_records", "local_moss_records.jsonl.gz", runs / "moss/labels.jsonl", "local_moss",
                 extra=census, dedupe=True, language="en")
    build.labels("qwen3_asr_en_records", "qwen3_asr_en_records.jsonl.gz", runs / "qwen/labels.jsonl", "qwen3_asr_en",
                 language="en")
    moss_cfg, qwen_cfg = run_config(runs / "moss/run.json"), run_config(runs / "qwen/run.json")
    f = build.facts
    description = (
        "GigaSpeech XL 全部 YouTube 录音（YOU*，21,472 条 / 11,765.9 h）的说话人数普查，只做了一小部分，占位登记，不要用于训练。"
        f"2026-10-09 用本机 MOSS-Transcribe-Diarize 0.9B 整条打说话人和文本，完成 {f['local_moss_records: status ok']} 条成功"
        f"（共 {f['local_moss_records rows']} 行，含失败待重试），约占计划 5%；Qwen3-ASR 文本校验只做了 "
        f"{f['qwen3_asr_en_records rows']} 条。用户决定先做中文，英文暂缓，没有继续。"
        "local_moss_records：每行一条录音，target 是按时间排序的 [说话人][起-止] 文本，metadata.local_moss 保留教师返回的分块、"
        "说话人链接、身份断点和 speaker_census（三种说话人数：global_labels 偏高、global_active、max_chunk_active）。"
        "qwen3_asr_en_records：Qwen3-ASR 对 MOSS 片段的转写（metadata.qwen3_asr_en）。"
        "audio_slots 指向本版本 youtube_xl_recordings 里的同名录音。脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["en"], ["diarization", "speaker_attributed_asr"], "legacy-20260804", description,
        "youtube-diarize-census",
        [transform("moss-speaker-census", "v1-20261009", "annotate", ["target", "metadata.local_moss"],
                   model="MOSS-Transcribe-Diarize 0.9B (official vLLM build, DP2)", backend=moss_cfg.get("backend"),
                   recordings_planned=21472, recordings_done=f["local_moss_records: status ok"],
                   stopped="user chose Chinese first; census paused 2026-10-09", counts="global_labels, global_active "
                   "(>=30 s), max_chunk_active (>=10 s in one 540 s chunk)"),
         transform("qwen3-asr-check", "v1-20261009", "annotate", ["metadata.qwen3_asr_en"],
                   model="Qwen3-ASR-1.7B", backend=qwen_cfg.get("backend"), recordings=f["qwen3_asr_en_records rows"])],
        status="partial", ready=False, statistics={"train": {"records": f["local_moss_records rows"]}})
    return [entry], [v]


# ----------------------------------------------------------------------------------------------------------------
def ramc_gap(args, catalog):
    runs = Path(args.runs) / "ramc-gap-labels-20261009"
    version = "gap-labels-v1-20261009"
    build = Build(args, catalog, "magicdata_ramc", version, "legacy-20260804")
    build.reference(["train_rec_0"])
    merge = runs / "merge-cer10"
    build.write("train_supervisions_gap_fills_0", "ramc_supervisions_gap_fills_cer10.jsonl.gz",
                (scrub(r, build.dropped) for r in read_jsonl(merge / "supervisions.jsonl.gz")),
                role="supervisions", kind=LHOTSE_SUP, metadata={"punctuated": False})
    build.labels("moss_records", "ramc_local_moss_records.jsonl.gz", runs / "moss/labels.jsonl", "local_moss",
                 language="zh")
    build.labels("qwen3_asr_records", "ramc_qwen3_asr_records.jsonl.gz", runs / "qwen/labels.jsonl", "qwen3_asr",
                 language="zh")
    build.derived("gap_merge_cer10_records", "ramc_gap_merge_cer10_records.jsonl.gz", merged_rows,
                  [merge / "merged.jsonl"], "gap_merge", language="zh")
    excluded = sum(1 for _ in read_jsonl(merge / "excluded.jsonl.gz"))
    if (excluded != build.facts["gap_merge_cer10_records: excluded"]
            or build.facts["gap_merge_cer10_records: usable"] != build.facts["train_supervisions_gap_fills_0 rows"]):
        raise SystemExit("merge-cer10 excluded.jsonl.gz / supervisions.jsonl.gz differ from merged.jsonl")
    build.facts["excluded intervals (in metadata.gap_merge.excluded)"] = excluded
    summary = json.loads((merge / "summary.json").read_text(encoding="utf-8"))
    build.facts["usable hours"] = summary["usable_hours"]
    build.facts["excluded hours"] = summary["excluded_hours"]
    moss_cfg, qwen_cfg = run_config(runs / "moss/run.json"), run_config(runs / "qwen/run.json")
    f = build.facts
    description = (
        "MagicData-RAMC train（289 段对话 / 149.65 h）原标注漏标语音的补全标注，原标注不改。2026-10-09 用本机 MOSS-Transcribe-Diarize 0.9B "
        "整段打说话人（540 s 切块、120 s 重叠），Qwen3-ASR-1.7B 只转写可能新增语音的片段，再对照原标注合并（文字错误率 ≤ 10%）。"
        f"train_supervisions_gap_fills_0：{f['train_supervisions_gap_fills_0 rows']} 条可用补全（{summary['usable_hours']} h，"
        "Lhotse supervision，说话人为原标注 ID，custom.diarize 记类别 fill / gap / overlap_other 和一致性检查），"
        f"只含补全，不含原标注；{f['excluded intervals (in metadata.gap_merge.excluded)']} 个不可用区间"
        f"（{summary['excluded_hours']} h，切窗口时应掩蔽）和未采纳的重叠记录在 gap_merge_cer10_records 的 metadata.gap_merge。"
        "moss_records / qwen3_asr_records 是两位教师的整段原始标签（每行一段对话，metadata.local_moss / metadata.qwen3_asr）。"
        "更宽松门槛的 merge/ 结果（5,484 条）可由 gap_merge_cer10_records 里保留的逐片段 cer 重算，没有单独登记。"
        "录音沿用 magicdata_ramc@legacy-20260804 train_rec_0，不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["zh"], ["diarization", "speaker_attributed_asr"], "legacy-20260804", description, "gap-labels",
        [transform("moss-diarize", "v1-20261009", "annotate", ["metadata.local_moss"],
                   model="MOSS-Transcribe-Diarize 0.9B", backend=moss_cfg.get("backend")),
         transform("qwen3-asr-check", "v1-20261009", "annotate", ["metadata.qwen3_asr"],
                   model="Qwen3-ASR-1.7B", backend=qwen_cfg.get("backend")),
         transform("gap-merge", "cer10-20261009", "annotate", ["target", "metadata.diarize", "metadata.gap_merge"],
                   max_text_cer=summary["settings"].get("max_text_cer"), settings=summary["settings"],
                   rule="amphiondata docs/multi-teacher-diarization.md (branch feat/multi-teacher-diarization)",
                   usable=f["train_supervisions_gap_fills_0 rows"], excluded=excluded,
                   excluded_reasons=summary["excluded_reasons"])],
        statistics={"train": {"gap_fill_supervisions": f["train_supervisions_gap_fills_0 rows"],
                              "recordings": f["moss_records rows"]}})
    return [entry], [v]


# ----------------------------------------------------------------------------------------------------------------
def teacher_calibration(args, catalog):
    runs = Path(args.runs) / "diarize-teacher-calibration-20261009"
    version = "teacher-calibration-v1-20261009"
    subsets = {"ramc": ("magicdata_ramc", "legacy-20260804", "zh", "RAMC train 6 条 / 3.17 h"),
               "alimeeting": ("alimeeting_sdm", "icefall-20260908", "zh", "AliMeeting train 远场 ch0 6 条 / 3.34 h"),
               "notsofar": ("notsofar_sdm", "icefall-20260908", "en", "NOTSOFAR train 单通道 ch0 39 场 / 4.02 h")}
    teachers = [("local-moss", "local_moss", "本机 MOSS-Transcribe-Diarize 0.9B"),
                ("moss-pro", "moss_pro", "MOSS Pro（moss-transcribe-diarize-pro）"),
                ("ali", "bailian", "百炼 qwen-audio-3.1-asr-flash"),
                ("qwen3-asr", "qwen3_asr", "Qwen3-ASR-1.7B 对本机 MOSS 片段的文本校验"),
                ("qwen3-asr-en", "qwen3_asr_en", "Qwen3-ASR-1.7B（to_language=en，NOTSOFAR 更正版）")]
    segments = defaultdict(list)
    for row in read_jsonl(runs / "analysis/segments.jsonl"):
        segments[row["subset"]].append(row)
    declarations, views = [], []
    for subset, (dataset, parent, language, label) in subsets.items():
        build = Build(args, catalog, dataset, version, parent)
        build.ref = (dataset, parent, "train")
        build.reference(["train_rec_0"])
        used = []
        for directory, key, _ in teachers:
            path = runs / directory / subset / "labels.jsonl"
            if path.exists():
                build.labels(f"{key}_records", f"{key}_records.jsonl.gz", path, key, language=language)
                used.append((directory, key))
        seg_rows = (record(f"{r['recording_id']}@{r['start']}-{r['end']}", build.ref, r["recording_id"],
                           {"teacher_agreement": {k: v for k, v in r.items() if k not in ("subset", "recording_id")}},
                           language=language, start=r["start"], duration=max(r["end"] - r["start"], 0.001))
                    for r in segments[subset])
        build.write("teacher_agreement_records", "teacher_agreement_records.jsonl.gz", seg_rows)
        names = {key: name for _, key, name in teachers}
        configs = {key: run_config(runs / d / subset / "run.json").get("backend") for d, key in used}
        f = build.facts
        description = (
            f"说话人日志老师校准（2026-10-09）：在有人工标注的 {label} 上比较本机 MOSS 0.9B、MOSS Pro、百炼 qwen-audio-3.1-asr-flash "
            "三个老师，并用 Qwen3-ASR 对本机 MOSS 的每个片段做文本校验；付费调用经用户批准，仅用于这次校准。"
            "每个 *_records 文件一个老师，每行一条录音，target 是按时间排序的 [说话人][起-止] 文本，教师返回的分块、说话人链接、身份断点"
            "留在 metadata.<老师>；teacher_agreement_records 每行一个人工标注片段，metadata.teacher_agreement 记各老师的说话人、边界和字错误率"
            "（analysis/segments.jsonl，用于确定多老师一致性过滤门槛）。"
            + ("NOTSOFAR 的 qwen3_asr_records 是第一版，误用 to_language=zh 把英文部分译成中文，已被 qwen3_asr_en_records 更正，保留原始输出。"
               if subset == "notsofar" else "")
            + f"录音沿用 {dataset}@{parent} train_rec_0（只用其中被抽中的录音），不复制音频。"
            "脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
        entry, v = finish(
            args, build, [language], ["diarization", "speaker_attributed_asr"], parent, description,
            "teacher-calibration",
            [transform(f"{key}-label", "v1-20261009", "annotate", [f"metadata.{key}"], backend=configs[key],
                       teacher=names[key])
             for _, key in used]
            + [transform("teacher-agreement", "v1-20261009", "annotate", ["metadata.teacher_agreement"],
                         rule="per human-labelled segment: speaker_ok, boundary error and CER of each teacher against "
                              "the human reference; tool amphiondata diarize analyze (scripts/analyze.py)",
                         segments=f["teacher_agreement_records rows"])],
            statistics={"train": {"recordings": f["local_moss_records rows"],
                                  "segments": f["teacher_agreement_records rows"]}})
        declarations.append(entry)
        views.append(v)
    return declarations, views


# ----------------------------------------------------------------------------------------------------------------
def review_record(ref, n, row):
    end = row.get("end", row["start"] + row.get("duration", 0.0))
    return record(f"{row['recording_id']}@{row['start']}-{end}#{n}", ref, row["recording_id"],
                  {"review_example": {k: v for k, v in row.items() if k != "recording_id"}}, language="zh",
                  start=row["start"], duration=max(end - row["start"], 0.001))


def zh_meeting_review(args, catalog):
    runs = Path(args.runs) / "zh-meeting-teacher-review-20261010"
    version = "teacher-review-v1-20261010"
    subsets = {"aishell4": ("aishell4", "icefall-20260908", ["train_rec_0", "train_rec_1", "train_rec_2"],
                            ["train_sup_0", "train_sup_1", "train_sup_2"], "AISHELL-4 train（186 场）"),
               "alimeeting": ("alimeeting_sdm", "icefall-20260908", ["train_rec_0"], ["train_sup_0"],
                              "AliMeeting train 远场（209 场）")}
    declarations, views = [], []
    for key, (dataset, parent, rec_names, sup_names, label) in subsets.items():
        build = Build(args, catalog, dataset, version, parent)
        build.reference(rec_names)
        corrections = json.loads((runs / f"corrections/{key}.json").read_text(encoding="utf-8"))
        source = {}
        for name in sup_names:
            art = next(a for a in catalog.get(dataset, parent).to_dict()["artifacts"] if a["name"] == name)
            for row in read_jsonl(Path(args.root) / art["relative_path"]):
                source[row["id"]] = row
        corrected = []
        for row in read_jsonl(runs / f"corrections/{key}_supervisions_corrected.jsonl.gz"):
            corrected.append(scrub(row, build.dropped))
        shifted = sum(1 for r in corrected if r["id"] in source and abs(r["start"] - source[r["id"]]["start"]) > 1e-6)
        removed = len(source) - sum(1 for r in corrected if r["id"] in source)
        added = sum(1 for r in corrected if r["id"] not in source)
        build.write("train_supervisions_corrected_0", f"{dataset}_supervisions_train_corrected.jsonl.gz", corrected,
                    role="supervisions", kind=LHOTSE_SUP, metadata={"punctuated": False})
        build.facts["source supervisions"] = len(source)
        build.facts["corrected supervisions with a shifted start"] = shifted
        build.facts["source supervisions removed (excluded meetings)"] = removed
        build.facts["supervisions not in the source"] = added
        merge = runs / f"merge-corrected/{key}"
        build.write("train_supervisions_gap_fills_0", f"{dataset}_supervisions_gap_fills.jsonl.gz",
                    (scrub(r, build.dropped) for r in read_jsonl(merge / "supervisions.jsonl.gz")),
                    role="supervisions", kind=LHOTSE_SUP, metadata={"punctuated": False})
        build.labels("moss_records", f"{key}_local_moss_records.jsonl.gz", runs / f"moss/{key}/labels.jsonl",
                     "local_moss", language="zh")
        build.labels("qwen3_asr_records", f"{key}_qwen3_asr_records.jsonl.gz", runs / f"qwen/{key}/labels.jsonl",
                     "qwen3_asr", language="zh")
        build.derived("gap_merge_records", f"{key}_gap_merge_records.jsonl.gz", merged_rows, [merge / "merged.jsonl"],
                      "gap_merge", language="zh")
        if (build.facts["gap_merge_records: excluded"] != sum(1 for _ in read_jsonl(merge / "excluded.jsonl.gz"))
                or build.facts["gap_merge_records: usable"] != build.facts["train_supervisions_gap_fills_0 rows"]):
            raise SystemExit(f"{key}: merge-corrected excluded/supervisions differ from merged.jsonl")
        offset_files = [("offsets_records", "time_offset", runs / f"offsets/{key}.jsonl")]
        if key == "alimeeting":
            offset_files.append(("near_far_lag_records", "near_far_lag", runs / "offsets/alimeeting-near-far.jsonl"))
        for name, field, path in offset_files:
            build.write(name, f"{key}_{name}.jsonl.gz",
                        (record(r["meeting"], build.ref, r["meeting"], {field: {k: v for k, v in r.items()
                                                                              if k != "meeting"}}, language="zh")
                         for r in read_jsonl(path)))
        excluded = json.loads((runs / f"corrections/{key}_excluded.json").read_text(encoding="utf-8"))
        excluded_reason = {x["meeting"]: x["reason"] for x in excluded}
        build.write("correction_decision_records", f"{key}_correction_decision_records.jsonl.gz",
                    (record(d["meeting"], build.ref, d["meeting"], {"correction_decision": {
                        **{k: v for k, v in d.items() if k != "meeting"},
                        **({"excluded": excluded_reason[d["meeting"]]} if d["meeting"] in excluded_reason else {})}},
                            language="zh")
                     for d in corrections["decisions"]))
        build.write("review_example_records", f"{key}_review_example_records.jsonl.gz",
                    (review_record(build.ref, n, r) for n, r in enumerate(read_jsonl(runs / f"review/{key}/examples.jsonl"))))
        build.write("excluded_meetings", f"{key}_excluded_meetings.jsonl.gz", excluded, role=None,
                    kind="metadata", metadata={"description": "整场排除出训练的会议及原因（标注与音频错位，未能可靠更正）；"
                                                              "同样的原因也写在 correction_decision_records 的 metadata.correction_decision.excluded"})
        review = json.loads((runs / f"review/{key}/summary.json").read_text(encoding="utf-8"))
        moss_cfg, qwen_cfg = run_config(runs / f"moss/{key}/run.json"), run_config(runs / f"qwen/{key}/run.json")
        f = build.facts
        description = (
            f"{label}的老师复核与时间更正（2026-10-10）：本机 MOSS-Transcribe-Diarize 0.9B 和 Qwen3-ASR-1.7B 对整场会议打标，"
            "与人工标注逐场对照，估计每场标注相对音频的时间偏移（包络滞后、MOSS 与人工配对偏移、AliMeeting 另有近场对远场 GCC-PHAT 滞后），"
            f"决定平移或整场排除，并写出更正后的参考标注。train_supervisions_corrected_0：更正后的 train 标注 {len(corrected)} 条"
            f"（源 {len(source)} 条，平移了 {shifted} 条的开始时间，去掉 {removed} 条，源里没有的 {added} 条），Lhotse 格式，字段同源版本；"
            "整场排除的会议不从标注里删除，切窗口时按 excluded_meetings 跳过。"
            f"excluded_meetings：{len(excluded)} 场整场排除（{corrections['excluded_hours']} h）及原因。"
            f"train_supervisions_gap_fills_0：老师补出的 {f['train_supervisions_gap_fills_0 rows']} 条漏标语音（fill / gap / overlap_other，"
            "说话人为原标注 ID，custom.diarize 记检查），不可用区间与未采纳片段在 gap_merge_records 的 metadata.gap_merge。"
            "moss_records / qwen3_asr_records 是两位教师的整场原始标签（metadata.local_moss / metadata.qwen3_asr）；"
            "offsets_records / near_far_lag_records / correction_decision_records 是逐场偏移估计和决定（metadata.time_offset / near_far_lag / "
            "correction_decision）；review_example_records 是文字差异等抽样证据。"
            f"录音沿用 {dataset}@{parent}，不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
        entry, v = finish(
            args, build, ["zh"], ["diarization", "speaker_attributed_asr"], parent, description, "teacher-review",
            [transform("moss-diarize", "v1-20261010", "annotate", ["metadata.local_moss"],
                       model="MOSS-Transcribe-Diarize 0.9B", backend=moss_cfg.get("backend"),
                       audio="far-field channel mean" if key == "alimeeting" else "source audio"),
             transform("qwen3-asr-check", "v1-20261010", "annotate", ["metadata.qwen3_asr"],
                       model="Qwen3-ASR-1.7B", backend=qwen_cfg.get("backend")),
             transform("time-offset-estimate", "v1-20261010", "annotate",
                       ["metadata.time_offset", *(["metadata.near_far_lag"] if key == "alimeeting" else []),
                        "metadata.correction_decision"],
                       thresholds=corrections["thresholds"], rule=corrections["rule"],
                       shifted_meetings=len(corrections["shifted_meetings"]), shifted_hours=corrections["shifted_hours"],
                       excluded_meetings=len(excluded), excluded_hours=corrections["excluded_hours"],
                       tool="amphiondata multispeaker corrections (scripts/corrections.py, offsets.py)"),
             transform("apply-corrections", "v1-20261010", "correct", ["audio_slots"],
                       source_supervisions=len(source), corrected_supervisions=len(corrected), shifted=shifted,
                       removed=removed, added=added),
             transform("gap-merge", "v1-20261010", "annotate", ["target", "metadata.diarize", "metadata.gap_merge"],
                       usable=f["train_supervisions_gap_fills_0 rows"], excluded=f["gap_merge_records: excluded"],
                       review_summary=review)],
            statistics={"train": {"recordings": f["moss_records rows"], "corrected_supervisions": len(corrected)}})
        declarations.append(entry)
        views.append(v)
    return declarations, views


# ----------------------------------------------------------------------------------------------------------------
def window_version(args, catalog, folder, dataset, parent, version):
    """Re-register a window set built with a local catalog.jsonl under its source dataset."""
    source_dir = Path(args.runs) / "real-meetings-20261008" / folder
    local = json.loads((source_dir / "catalog.jsonl").read_text(encoding="utf-8").splitlines()[0])
    build = Build(args, catalog, dataset, version, parent)
    prefix = folder
    audio_files = {}
    for base in ("train", "dev", "test"):
        index_path = source_dir / f"{prefix}-{base}-audio-index.jsonl.gz"
        if not index_path.exists():
            continue
        rows = []
        for row in read_jsonl(index_path):
            if row["root_alias"] != "aidc_data":
                src = source_dir / row["relative_path"]
                new_rel = f"datasets/{dataset}/versions/{version}/{row['relative_path']}"
                audio_files[src] = Path(args.root) / new_rel
                row = {**row, "root_alias": "aidc_data", "relative_path": new_rel, "bytes": src.stat().st_size}
            rows.append(row)
        build.write(f"{base}-audio-index", f"{prefix}-{base}-audio-index.jsonl.gz", rows, role="audio_index",
                    kind="audio-index", split=f"_{base}")
        build.facts[f"{base} recordings"] = len(rows)
    for src, dst in audio_files.items():  # derived mono audio that exists nowhere else: copy it, byte for byte
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        shutil.copyfile(src, tmp)
        tmp.replace(dst)
    build.facts["audio files copied"] = len(audio_files)
    statistics = {}
    excluded = list(read_jsonl(source_dir / "excluded-train-windows.jsonl.gz"))
    for split_name, split in local["splits"].items():
        base = split_name.split("_")[0]
        name = split["artifacts"]["records"][0]
        art = next(a for a in local["artifacts"] if a["name"] == name)
        counter = Counter()

        def rows(path=source_dir / art["relative_path"], split_name=split_name, counter=counter):
            for row in read_jsonl(path):
                for slot in row["audio_slots"]:
                    slot["ref"]["dataset_id"], slot["ref"]["version"] = dataset, version
                counter["rows"] += 1
                yield row

        build.write(name, f"{prefix}-{split_name}.jsonl.gz", rows(), split=split_name)
        build.splits[split_name]["audio_index"].append(f"{base}-audio-index")
        # the four window sizes re-cut the same audio, so their durations must not be added up as dataset hours
        statistics[split_name] = {k: v for k, v in split.get("statistics", {}).items() if k != "duration_hours"}
    for sp in [k for k in build.splits if k.startswith("_")]:
        del build.splits[sp]
    if excluded:  # windows dropped at export time (they are not in the records); a plain artifact, in no split role
        build.write("train_excluded_windows", f"{prefix}-train-excluded-windows.jsonl.gz", excluded, role=None,
                    kind="metadata",
                    metadata={"description": "导出时已丢弃的训练窗口及原因（整窗目标超过上下文、空转写），不在 records 里"})
    return build, local, statistics, excluded


def real_meetings(args, catalog):
    declarations, views = [], []
    version = "meeting-windows-v1-20261008"
    # chime6
    build, local, statistics, excluded = window_version(args, catalog, "chime6", "chime6",
                                                        "speaker-records-v1-20260912", version)
    runs = Path(args.runs) / "real-meetings-20261008"
    corrections = (Path(args.corrections) if args.corrections else None)
    if corrections is None:
        raise SystemExit("--corrections chime6-corrections.json is required")
    shutil.copyfile(corrections, build.out / "chime6-corrections.json")
    build.artifacts.append(artifact("annotation_corrections", "metadata", "chime6", version, "chime6-corrections.json",
                                    None, build.out, {"schema": "chime6-annotation-corrections/1.0"}))
    build.splits["test_annotations"]["annotations"].append("annotation_corrections")

    def alignment_rows():
        for row in read_jsonl(runs / "chime6-test-corrections/align/alignments/000000.jsonl.gz"):
            if row["audio"]["root_alias"] == "evidence":
                row["audio"] = {"root_alias": "aidc_data",
                                "relative_path": f"datasets/chime6/versions/{version}/audio/test/S21_U01.wav"}
            yield row

    build.write("test_correction_alignments", "chime6-test-correction-alignments.jsonl.gz", alignment_rows(),
                role="annotations", kind="metadata", split="test_annotations",
                metadata={"description": "CHiME-6 eval S21 第 1959 行（start>end）的强制对齐复核，三次运行，结论见 annotation_corrections"})
    f = build.facts
    meta = local["provenance"]
    description = (
        "CHiME-6 真实会议的说话人归属 ASR 窗口（aligned_utterance_timestamps_v1）：人工标注的说话人和时间，"
        f"{meta['channel_policy']}；转写为官方文字原样，只去空白，保留 [noise]、[laughs]、[inaudible] 标记。按 30 / 120 / 300 / 600 s 切窗，"
        "每个 split 的 records 一行一个窗口，turns 在 metadata。训练集上整窗目标超过上下文的 113 个窗口和空转写的 4 个窗口列在 "
        f"train_excluded_windows（导出时已丢弃，不在 records 里）。标注更正 annotation_corrections：eval S21 第 1959 行开始晚于结束，强制对齐不可靠，整行排除，"
        "复核对齐结果在 test_correction_alignments。"
        f"音频是 U01 阵列 4 路的平均（16 kHz 单声道），源数据集里没有，已按原字节复制 {f['audio files copied']} 个文件到本版本 audio/ 下，"
        "由 *-audio-index 引用。没有清洗通过标记，也没有伪造。脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["en"], ["speaker_attributed_asr"], "speaker-records-v1-20260912", description, "meeting-windows",
        [transform("window-sot", "real-meetings-v1-20261008", "annotate", ["target", "metadata.turns"],
                   source=meta["source"], source_version=meta["source_version"], annotation=meta["annotation"],
                   channel_policy=meta["channel_policy"], transcript_policy=meta["transcript_policy"],
                   window_seconds=[30, 120, 300, 600], tool="amphiondata multispeaker window export"),
         transform("annotation-corrections", "chime6-corrections-v1", "correct", ["metadata.excluded_annotations"],
                   file_sha256="336d9c51326362379e364ddb1c128bac518b120647616699bafe56f0d7f11f3c",
                   excluded_rows=1, forced_aligner="Qwen3-ForcedAligner-0.6B"),
         transform("exclude-windows", "v1-20261008", "filter", ["$membership"],
                   listed=len(excluded), reasons=dict(Counter(r["reason"] for r in excluded)))],
        statistics=statistics)
    declarations.append(entry)
    views.append(v)
    # notsofar_sdm
    build, local, statistics, excluded = window_version(args, catalog, "notsofar_sdm", "notsofar_sdm",
                                                        "icefall-20260908", version)
    meta = local["provenance"]
    description = (
        "NOTSOFAR-1 真实会议（单通道 SC 设备 ch0，每个设备算一条录音，因为设备间采样不同步）的说话人归属 ASR 窗口"
        "（aligned_utterance_timestamps_v1）：人工标注的说话人和时间，转写为源清单文字，只去空白。按 30 / 120 / 300 / 600 s 切窗，"
        "每个 split 的 records 一行一个窗口，turns 在 metadata；train / dev / test 都有。音频由 audio-index 指向源数据集里的 ch0.wav，"
        "不复制。没有窗口被排除。脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["en"], ["speaker_attributed_asr"], "icefall-20260908", description, "meeting-windows",
        [transform("window-sot", "real-meetings-v1-20261008", "annotate", ["target", "metadata.turns"],
                   source=meta["source"], source_version=meta["source_version"], annotation=meta["annotation"],
                   channel_policy=meta["channel_policy"], transcript_policy=meta["transcript_policy"],
                   window_seconds=[30, 120, 300, 600], tool="amphiondata multispeaker window export")],
        statistics=statistics)
    declarations.append(entry)
    views.append(v)
    return declarations, views


# ----------------------------------------------------------------------------------------------------------------
def batch_paths(root, pattern):
    paths = sorted(Path(root).glob(pattern))
    if not paths:
        raise SystemExit(f"no files match {root}/{pattern}")
    return paths


def labels_description(build, items):
    """'name：n 行' fragments for the description."""
    return "；".join(f"{name} {build.facts[f'{name} rows']:,} 行" for name in items)


def emilia2_128k(args, catalog):
    runs = Path(args.runs) / "emilia2-zh-dialogue-diarize-20261010"
    parent = "moss-transcribe-diarize-0.9B"
    version = "teacher-labels-v1-20261010"
    build = Build(args, catalog, "emilia2_zh_dialogue_diarize", version, parent)
    build.ref = ("emilia2_zh_dialogue_diarize", parent, "train_120s")
    build.reference(["train-audio-index"], split="train_120s")
    split = "train_120s"
    final_windows = batch_paths(runs, "export/window-merge-v7/b*/windows.jsonl.gz")
    lookup = window_lookup(final_windows)
    local = batch_paths(runs, "local-moss/b[0-9][0-9][0-9]/labels.jsonl")
    build.labels("local_moss_records", "local_moss_records.jsonl.gz", local, "local_moss", split=split, dedupe=True,
                 language="zh")
    build.labels("moss_pro_recording_records", "moss_pro_recording_records.jsonl.gz",
                 batch_paths(runs, "moss-pro/b[0-9][0-9][0-9]/labels.jsonl"), "moss_pro", split=split, language="zh")
    build.labels("pro4plus_records", "pro4plus_records.jsonl.gz", runs / "pro4plus/labels/labels.jsonl", "moss_pro",
                 split=split, language="zh", lookup=lookup)
    selection = {r["id"].removeprefix("emilia2_zh_dialogue-train_120s-"):
                 {"selection": {"speakers": r["speakers"], "max_sim": r["max_sim"]}}
                 for r in read_jsonl(runs / "prosim06/selection.jsonl")}
    build.labels("prosim06_records", "prosim06_records.jsonl.gz", runs / "prosim06/labels/labels.jsonl", "moss_pro",
                 split=split, language="zh", lookup=lookup, extra=selection)
    build.labels("pro_audit_records", "pro_audit_records.jsonl.gz", runs / "pro-audit/labels/labels.jsonl", "moss_pro",
                 split=split, language="zh", lookup=lookup)
    build.labels("qwen3_asr_records", "qwen3_asr_records.jsonl.gz",
                 batch_paths(runs, "qwen3-asr-local/b[0-9][0-9][0-9]/labels.jsonl"), "qwen3_asr", split=split,
                 dedupe=True, language="zh")
    build.labels("qwen3_asr_pro_records", "qwen3_asr_pro_records.jsonl.gz",
                 batch_paths(runs, "qwen3-asr/b[0-9][0-9][0-9]/labels.jsonl"), "qwen3_asr", split=split,
                 language="zh")
    build.derived("merge_local_records", "merge_local_records.jsonl.gz", merged_rows,
                  batch_paths(runs, "merge-local/b[0-9][0-9][0-9]/merged.jsonl"), "merge_local", split=split,
                  language="zh")
    build.derived("window_check_records", "window_check_final_records.jsonl.gz", window_rows, final_windows,
                  "window_check", split=split, language="zh")
    cfg = {n: run_config(runs / d / "run.json").get("backend") for n, d in
           (("local_moss", "local-moss/b000"), ("moss_pro", "pro4plus/labels"), ("qwen3_asr", "qwen3-asr-local/b000"))}
    f = build.facts
    description = (
        "Emilia2 中文多人对话（m4a-128k 子集，zh、≥120 秒，78,994 条 / 8,097 h）说话人日志流水线的全部教师原始标签和窗口核对结果，"
        "是 moss-transcribe-diarize-0.9B / -pro4plus / -pro4plus-sim06 三个训练版本的上游，本身不是训练集。"
        f"local_moss_records：本机 MOSS-Transcribe-Diarize 0.9B 整条标注，{f['local_moss_records rows']:,} 条录音"
        f"（其中 {f['local_moss_records: status ok']:,} 条成功），每行 metadata.local_moss 含分块、说话人链接和身份断点；"
        f"qwen3_asr_records：Qwen3-ASR 对本地 MOSS 片段的逐段转写（{f['qwen3_asr_records rows']:,} 条录音，只做了前几批）；"
        f"merge_local_records：第一版逐片段文字核对的合并结果（{f['merge_local_records rows']:,} 条录音，metadata.merge_local 含 usable / excluded 片段和各项检查，"
        "同批的 supervisions.jsonl.gz 与 excluded.jsonl.gz 是它的逐行拆分，已逐批核对一致，没有重复登记）；"
        f"moss_pro_recording_records：MOSS Pro 对前 4 批的整条标注（积分用完中断，{f['moss_pro_recording_records: status ok']} 条成功）；"
        f"pro4plus_records（{f['pro4plus_records rows']:,} 个窗口片段，≥4 人窗口）、prosim06_records（{f['prosim06_records rows']:,} 个，"
        "2–3 人且声纹相似 ≥0.6，metadata.selection 记人数和相似度）、pro_audit_records（1,500 个随机抽样窗口）是 MOSS Pro 对窗口片段的标注，"
        "时间相对窗口起点，audio_slots 带窗口的 start/duration；"
        f"window_check_records：最终窗口核对结果（{f['window_check_records rows']:,} 个窗口，kept = 通过，reasons = 拒绝原因，cer / speaker_split，"
        "primary_text 和 Qwen3-ASR 的 check_text，labels_from 标明本地 0.9B 还是 Pro），是 sim06 版本的上一层，含被拒窗口。"
        "audio_slots 指向 emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B 的 train_120s 音频索引（FLAC 16 kHz），"
        f"其中只有通过粗筛并切出窗口的 {53965:,} 条录音有音频文件，其余录音只剩标签。"
        "未登记：逐块原始响应 raw/（标签文件已含全部分段）、window-plan 与中间窗口核对版本 v1–v6（可由最终版本和标签重算）、"
        "listen-review。脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["zh"], ["diarization", "speaker_attributed_asr"], parent, description, "teacher-labels",
        [transform("local-moss-diarize", "v1-20261010", "annotate", ["target", "metadata.local_moss"],
                   model="MOSS-Transcribe-Diarize 0.9B", backend=cfg["local_moss"], recordings=f["local_moss_records rows"]),
         transform("qwen3-asr-segment-check", "v1-20261011", "annotate", ["metadata.qwen3_asr", "metadata.merge_local"],
                   model="Qwen3-ASR-1.7B", backend=cfg["qwen3_asr"], rule="per-segment text check, superseded by the window check"),
         transform("moss-pro-relabel", "v1-20261012", "annotate", ["metadata.moss_pro"],
                   model="moss-transcribe-diarize-pro", backend=cfg["moss_pro"],
                   selection="pro4plus: kept windows with >= 4 local speakers; prosim06: kept 2-3 speaker windows "
                             "with max ERes2NetV2 cosine >= 0.6; pro-audit: 1,500 random windows",
                   tool="amphiondata scripts merge_pro4plus.py / merge_prosim06.py"),
         transform("window-check", "v1-20261028", "annotate", ["metadata.window_check", "$membership"],
                   window_seconds=[30, 120], max_text_cer=15, max_speaker_split=0.2, text_check_model="Qwen3-ASR",
                   windows=f["window_check_records rows"], kept=f["window_check_records: kept"],
                   rejected=f["window_check_records: rejected"])],
        status="prepared", ready=False,
        statistics={split: {"records": sum(v for k, v in f.items() if k.endswith(" rows"))}},
        superseded_note="intermediate teacher labels; train with the window versions, not this one")
    return [entry], [v]


def emilia2_64k(args, catalog):
    runs = Path(args.runs) / "emilia2-64k-zh-dialogue-diarize-20261015"
    parent = "moss-transcribe-diarize-0.9B-m4a64k"
    version = "teacher-labels-v1-20261015"
    build = Build(args, catalog, "emilia2_zh_dialogue_diarize", version, parent)
    build.ref = ("emilia2_zh_dialogue_diarize", parent, "train_120s")
    build.reference(["train-audio-index"], split="train_120s")
    split = "train_120s"
    local = batch_paths(runs, "local-moss/b[0-9][0-9][0-9]/labels.jsonl")
    build.labels("local_moss_records", "local_moss_records.jsonl.gz", local, "local_moss", split=split, dedupe=True,
                 language="zh")
    build.derived("window_check_records", "window_check_records.jsonl.gz", window_rows,
                  batch_paths(runs, "merge-window/b[0-9][0-9][0-9]/windows.jsonl.gz"), "window_check", split=split,
                  language="zh")
    cfg = run_config(runs / "local-moss/b000/run.json").get("backend")
    f = build.facts
    description = (
        "Emilia2 m4a-64k 中文对话（≥120 秒，46,615 条 / 3,895 h）的本机 MOSS-Transcribe-Diarize 0.9B 原始整条标签和窗口核对结果，"
        "是 moss-transcribe-diarize-0.9B-m4a64k 训练版本的上游，本身不是训练集。"
        f"local_moss_records：{f['local_moss_records rows']:,} 条录音（成功 {f['local_moss_records: status ok']:,}），"
        "metadata.local_moss 含分块、说话人链接和身份断点；"
        f"window_check_records：窗口核对结果 {f['window_check_records rows']:,} 个（通过 {f['window_check_records: kept']:,}，"
        f"拒绝 {f['window_check_records: rejected']:,}），含被拒窗口及原因、Qwen3-ASR 整窗文字 check_text、字错误率和说话人拆分比例。"
        "audio_slots 指向 emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-m4a64k 的音频索引（FLAC 16 kHz），"
        "只有切出窗口的录音有音频文件。未登记：逐块原始响应 raw/、Qwen3-ASR 窗口原始响应（文字已在 check_text）、window-plan、"
        "upstream-shorts（Emilia2 自带短句，来源数据的抽取，不是标签）、backup-m4a-paths（m4a 路径备份，不是标签）。"
        "脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["zh"], ["diarization", "speaker_attributed_asr"], parent, description, "teacher-labels",
        [transform("local-moss-diarize", "v1-20261015", "annotate", ["target", "metadata.local_moss"],
                   model="MOSS-Transcribe-Diarize 0.9B", backend=cfg, recordings=f["local_moss_records rows"]),
         transform("window-check", "v1-20261015", "annotate", ["metadata.window_check", "$membership"],
                   window_seconds=[30, 120], max_text_cer=15, max_speaker_split=0.2, text_check_model="Qwen3-ASR",
                   windows=f["window_check_records rows"], kept=f["window_check_records: kept"],
                   rejected=f["window_check_records: rejected"])],
        status="prepared", ready=False,
        statistics={split: {"records": f["local_moss_records rows"] + f["window_check_records rows"]}})
    return [entry], [v]


def wenetspeech_l(args, catalog):
    runs = Path(args.runs) / "wenetspeech-l-diarize-20261012"
    parent = "moss-transcribe-diarize-0.9B"
    version = "teacher-labels-v1-20261012"
    build = Build(args, catalog, "wenetspeech_diarize", version, parent)
    build.ref = ("wenetspeech", "legacy-20260804", "train")
    build.reference(["train_rec_0"], dataset="wenetspeech", version="legacy-20260804")
    windows = batch_paths(runs, "merge-window/b[0-9][0-9][0-9]/windows.jsonl.gz")
    build.write("train_supervisions_windows_0", "wenetspeech_l_diarize_window_supervisions.jsonl.gz",
                (scrub(r, build.dropped) for p in batch_paths(runs, "merge-window/b[0-9][0-9][0-9]/supervisions.jsonl.gz")
                 for r in read_jsonl(p)), role="supervisions", kind=LHOTSE_SUP, metadata={"punctuated": False})
    build.labels("local_moss_records", "local_moss_records.jsonl.gz",
                 batch_paths(runs, "local-moss/b[0-9][0-9][0-9]/labels.jsonl"), "local_moss", dedupe=True,
                 language="zh")
    build.labels("qwen3_asr_window_records", "qwen3_asr_window_records.jsonl.gz",
                 batch_paths(runs, "qwen3-asr-window/b[0-9][0-9][0-9]/labels.jsonl"), "qwen3_asr_window", dedupe=True,
                 language="zh")
    build.derived("window_check_records", "window_check_records.jsonl.gz", window_rows, windows, "window_check",
                  language="zh")
    lookup = window_lookup(windows)
    build.labels("pilot_local_moss_records", "pilot_local_moss_records.jsonl.gz", runs / "pilot/local-moss/labels.jsonl",
                 "local_moss", language="zh")
    build.labels("pilot_moss_pro_records", "pilot_moss_pro_records.jsonl.gz", runs / "pilot/moss-pro/labels.jsonl",
                 "moss_pro", language="zh", lookup=lookup)
    cfg = {n: run_config(runs / d / "run.json").get("backend") for n, d in
           (("local_moss", "local-moss/b000"), ("qwen3_asr", "qwen3-asr-window/b000"), ("moss_pro", "pilot/moss-pro"))}
    summaries = [json.loads((p.parent / "summary.json").read_text(encoding="utf-8")) for p in windows]
    kept_windows = sum(x["kept_windows"] for x in summaries)
    kept_hours = sum(x["kept_window_hours"] for x in summaries)
    f = build.facts
    description = (
        "占位登记，未完成，不转正、不进训练：WenetSpeech L 长音频（≥120 秒，51,358 条 / 22,174 h）的说话人日志伪标签。"
        "2026-10-14 用户决定停止全量打标，只保留前 41 批（共 52 批）的整条本机 MOSS-Transcribe-Diarize 0.9B 标注和粗筛结果，"
        "Qwen3-ASR 整窗核对 b000–b040 都做完，但不并入训练、不发布为可用训练版本；是否改为定向打标要看音色相近数据的效果再定。"
        f"train_supervisions_windows_0：通过整窗核对的 {kept_windows:,} 个窗口（{kept_hours:,.0f} h）的片段，共 "
        f"{f['train_supervisions_windows_0 rows']:,} 条 Lhotse supervision，说话人为 <录音>#S<编号>，custom.window_check 记窗口和字错误率；"
        f"window_check_records：全部 {f['window_check_records rows']:,} 个窗口的核对结果（含被拒窗口和原因、Qwen3-ASR 的 check_text）；"
        f"local_moss_records：{f['local_moss_records rows']:,} 条录音的整条标注；qwen3_asr_window_records：Qwen3-ASR 整窗识别；"
        f"pilot_*：试跑 100 条录音的本地标注和 MOSS Pro 对 {f['pilot_moss_pro_records rows']} 个窗口片段的标注（用于定门槛）。"
        "已知局限：WenetSpeech 没有带说话人的上游标注，做不了说话人检查；试跑中好窗口比例 71%，不合格窗口多半是说话人分错，文字核对管不住。"
        "录音沿用 wenetspeech@legacy-20260804 train_rec_0。未登记：逐块原始响应 raw/、window-plan、远端对齐检查 remote-compare。"
        "脚本 scripts/diarization_raw_labels/register_raw_labels.py。")
    entry, v = finish(
        args, build, ["zh"], ["diarization", "speaker_attributed_asr"], parent, description, "teacher-labels",
        [transform("local-moss-diarize", "v1-20261012", "annotate", ["target", "metadata.local_moss"],
                   model="MOSS-Transcribe-Diarize 0.9B", backend=cfg["local_moss"],
                   recordings=f["local_moss_records rows"], batches="b000-b040 of 52"),
         transform("qwen3-asr-window", "v1-20261012", "annotate", ["metadata.qwen3_asr_window"],
                   model="Qwen3-ASR-1.7B", backend=cfg["qwen3_asr"],
                   note="b030-b040 re-run on a second server with max_completion_tokens 4096 (2026-10-21)"),
         transform("window-check", "v1-20261012", "annotate", ["target", "metadata.window_check", "$membership"],
                   overrides=["target"], window_seconds=[30, 120], max_text_cer=15, windows=f["window_check_records rows"],
                   kept=f["window_check_records: kept"], rejected=f["window_check_records: rejected"],
                   speaker_check="none (WenetSpeech has no speaker-labelled upstream)"),
         transform("pilot-moss-pro", "v1-20261012", "annotate", ["metadata.moss_pro"], model="moss-transcribe-diarize-pro",
                   backend=cfg["moss_pro"], windows=f["pilot_moss_pro_records rows"])],
        status="partial", ready=False,
        statistics={"train": {"kept_windows": kept_windows, "kept_window_hours": round(kept_hours, 1)}},
        stopped="2026-10-14 user stopped the full run; labelled b000-b040 of 52 batches")
    return [entry], [v]


ITEMS = {"gigaspeech-census": gigaspeech_census, "ramc-gap": ramc_gap, "teacher-calibration": teacher_calibration,
         "zh-meeting-review": zh_meeting_review, "real-meetings": real_meetings, "wenetspeech-l": wenetspeech_l,
         "emilia2-128k": emilia2_128k, "emilia2-64k": emilia2_64k}

HEADERS = {
    "gigaspeech-census": "GigaSpeech XL YouTube 录音说话人数普查的教师标签（占位登记，只做了约 5%，不进训练）",
    "ramc-gap": "MagicData-RAMC train 漏标补全：两位教师的整段标签、补全 supervisions 和不可用区间",
    "teacher-calibration": "说话人日志老师校准：三个老师和 Qwen3-ASR 在 RAMC、AliMeeting、NOTSOFAR 样本上的标签与逐片段对比",
    "zh-meeting-review": "AISHELL-4 与 AliMeeting 老师复核：教师标签、逐场时间偏移、更正后的 supervisions 和整场排除",
    "real-meetings": "CHiME-6 与 NOTSOFAR 真实会议的说话人归属 ASR 窗口（30 / 120 / 300 / 600 秒）及标注更正",
    "wenetspeech-l": "WenetSpeech L 长音频说话人日志教师标签与整窗核对结果（占位登记，2026-10-14 停止打标，不进训练）",
    "emilia2-128k": "Emilia2 m4a-128k 中文对话说话人日志流水线的全部教师原始标签和窗口核对结果（上游中间产物，不进训练）",
    "emilia2-64k": "Emilia2 m4a-64k 中文对话的本机 MOSS 原始标签和窗口核对结果（上游中间产物，不进训练）",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("item", choices=sorted(ITEMS))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, help="chime6-corrections.json (real-meetings only)")
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    declarations, views = ITEMS[args.item](args, catalog)
    save(args.output, args.views, declarations, views, HEADERS[args.item])
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / f"{args.item}.json").write_text(
        json.dumps({d["dataset_id"] + "@" + d["version"]: d["provenance"]["facts"] for d in declarations},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for d in declarations:
        print(d["dataset_id"], d["version"], json.dumps(d["provenance"]["facts"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
