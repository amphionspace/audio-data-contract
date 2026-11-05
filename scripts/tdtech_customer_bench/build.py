#!/usr/bin/env python3
"""Register the td-tech (鼎桥) customer recordings from EvalHub as an ASR evaluation dataset.

The recordings are the customer's own audio (mail/Wiki baseline 2026-09-30) that EvalHub published
as ``asr/dingqiao-asr-quality@20261016-machine01`` (general recognition) and
``asr/dingqiao-asr-police-cmd@20261020-jyjy-v6-human04`` (police PTT commands). Their copies sit
unchanged under ``source/evalhub/<category>_<id>@<version>/`` (``files.json`` checked on build), and
the records point at those wavs.

- ``general``: only recordings where two of three transcripts agree at CER 0 under amphion-eval's
  native scoring: EvalHub's machine reference (Qwen-audio-3.1 or MOSS), FireRedASR2-AED and
  MiMo-V2.5-ASR (``agree.py`` writes ``source/agreement.json``). Machine references, not human gold.
- ``police-cmd``: all 137 recordings. The reference is the term the speaker read (recording group,
  aligned to 警言警语 V6.0); 39 of them were confirmed by listening (``reference_kind: human``).
- ``police-cmd-builtin`` (from v3): the ``police-cmd`` records again, each sent with the whole shipped
  hotword pool of audiollm-go (main-td ``builtin-hotwords-20261102.txt``, 1296 terms, in file order;
  copied with its source commit to ``source/audiollm-go/``), in hotword_bench layout. v2 had
  ``police-cmd-hw300`` instead (35 terms plus 265 random police terms; see git history).
- ``owner`` (from v4): EvalHub ``target-speaker/dingqiao-ts@20261014``, the 6 test clips whose
  enrollment recordings came in the same archive; enrollment is the near-field recording. A person
  listened and chose the owner among the local MOSS speakers (or none); the owner's text is, per turn,
  what two of the four machine transcripts agree on. Results in ``source/listening-review-20261105.json``.
- ``hotword`` (from v4): EvalHub ``hotword/dingqiao-hotword-quality@20261016-machine01`` (2 clips of
  person names), reference text confirmed by listening, sent with the five names of the customer's
  demo. v4 left 黄静飞/黄敬飞 out (spelling unknown); from v5 the customer's spelling 黄晋飞
  (``source/customer-names-20261105.json``) fixes the text and joins the list.

    python scripts/tdtech_customer_bench/build.py --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import soundfile as sf
import yaml

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

DATASET_ID = "tdtech_customer_bench"
ROOT_ALIAS = DATASET_ID
VERSION = "v5-20261105"
SAMPLE_RATE = 16000
GENERAL = "asr_dingqiao-asr-quality@20261016-machine01"
POLICE = "asr_dingqiao-asr-police-cmd@20261020-jyjy-v6-human04"
HOTWORD_SPLIT = "police-cmd-builtin"
HOTWORD_LIST = "builtin"
POOL = "source/audiollm-go/builtin-hotwords-20261102.txt"
POOL_SHA256 = "5ad6238e2677dfd128d2e5e3f3e8b529b0e1e12dd0d2c8dd9b86305d180ba0c1"
OWNER = "target-speaker_dingqiao-ts@20261014"
HOTWORD = "hotword_dingqiao-hotword-quality@20261016-machine01"
REVIEW = "source/listening-review-20261105.json"
NAMES = "source/customer-names-20261105.json"
DEMO_LIST = "demo"
SPLITS = {
    "general": (
        GENERAL,
        (
            "通用识别（远场、长语音、PTT、警务 badcase 等客户录音）：EvalHub 机器参考（Qwen-audio-3.1 / MOSS）、"
            "FireRedASR2-AED、MiMo-V2.5-ASR 三份转写中有两份在原生打分口径下逐字一致才保留，参考取一致的那份"
            "（含 EvalHub 参考时取 EvalHub 的文本），未经人工听审。"
        ),
    ),
    "police-cmd": (
        POLICE,
        (
            "警务指令（PTT 短句）客户录音：参考为录音分组对应的指令词（按《警言警语 V6.0》对齐），"
            "其中 39 条经人工听原音确认（reference_kind: human），其余为按术语表对齐的机器参考。"
        ),
    ),
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl_gz(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def check_files(directory):
    """Every file EvalHub listed in files.json is present with its sha256."""
    listed = json.loads((directory / "files.json").read_text(encoding="utf-8"))
    files = listed.get("files", listed)
    entries = files.items() if isinstance(files, dict) else ((f["path"], f["sha256"]) for f in files)
    for relative, digest in entries:
        digest = digest["sha256"] if isinstance(digest, dict) else digest
        if sha256_file(directory / relative) != digest:
            raise ValueError(f"{directory / relative}: sha256 differs from files.json")


def index_entry(path, relative_path, cut_id):
    info = sf.info(path)
    if info.samplerate != SAMPLE_RATE or info.channels != 1:
        raise ValueError(f"{path}: expected 16 kHz mono, got {info.samplerate} Hz x{info.channels}")
    return {
        "cut_id": cut_id,
        "root_alias": ROOT_ALIAS,
        "relative_path": relative_path,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "num_frames": info.frames,
        "duration": round(info.frames / info.samplerate, 4),
        "sha256": sha256_file(path),
    }


def evalhub_ref(directory_name):
    category, rest = directory_name.split("_", 1)
    return f"{category}/{rest}"


def builtin_pool(data_root):
    """audiollm-go's shipped hotword pool, one term per line, as shipped."""
    path = data_root / POOL
    if sha256_file(path) != POOL_SHA256:
        raise ValueError(f"{path}: not the pool this version was built from")
    words = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(set(words)) != len(words):
        raise ValueError(f"{path}: duplicate terms")
    return words


def hotword_copy(records, words):
    """The police-cmd records once more, each sent with the pool; ``hotwords`` is the term spoken."""
    return [AudioRecord.from_dict({
        **record, "id": record["id"].replace("police-cmd", HOTWORD_SPLIT, 1), "task": "asr_hotwords",
        "hotwords": [record["labels"]["term"]],
        "labels": {**record["labels"], "scenario": HOTWORD_SPLIT, "hotword_list_size": len(words),
                   "term_in_pool": record["labels"]["term"] in words},
        "metadata": {**record["metadata"], "bias_lists": {HOTWORD_LIST: words},
                     "distractor_kinds": {w: "builtin" for w in words if w != record["labels"]["term"]}},
    }).to_dict() for record in records]


def evalhub_rows(data_root, directory_name):
    directory = data_root / "source" / "evalhub" / directory_name
    check_files(directory)
    return [json.loads(line) for line in (directory / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]


def slot(name, split, entry):
    return {"name": name, "purpose": name, "ref": {
        "dataset_id": DATASET_ID, "version": VERSION, "split": split,
        "cut_id": entry["cut_id"], "duration": entry["duration"]}}


def owner_records(data_root, review, index):
    """Clips the listener settled; enrollment is the group's near-field recording."""
    records = []
    for row in evalhub_rows(data_root, OWNER):
        if row["id"] not in review:
            continue
        decided = review[row["id"]]
        if decided["choice"] == "听不出":
            raise ValueError(f"{row['id']}: owner not settled by listening")
        group = row["labels"]["enroll_group"]
        enroll = f"source/evalhub/{OWNER}/{row['speaker_audio']['near']}"
        mixture = f"source/evalhub/{OWNER}/{row['audio']}"
        enroll_entry = index.setdefault(f"enroll-{group}-near",
                                        index_entry(data_root / enroll, enroll, f"enroll-{group}-near"))
        mixture_entry = index.setdefault(row["id"], index_entry(data_root / mixture, mixture, row["id"]))
        records.append(AudioRecord.from_dict({
            "schema_version": "audio-record/1.0",
            "id": f"owner:{row['id']}",
            "task": "ts_asr",
            "audio_slots": [slot("enrollment", "owner", enroll_entry), slot("mixture", "owner", mixture_entry)],
            "target": decided["target"],
            "language": "zh",
            "labels": {"scenario": "owner", "display_name": row["labels"]["display_name"],
                       "enroll_group": group, "target_present": bool(decided["target"]),
                       "reference_kind": "human_speaker_machine_text"},
            "metadata": {"evalhub": {"ref": evalhub_ref(OWNER), "sample_id": row["id"]},
                         "listening": decided, "source_audio_sha256": row["source"]["audio_sha256"]},
        }).to_dict())
    if len(records) != len(review):
        raise ValueError("listening review names clips missing from the EvalHub manifest")
    return records


def hotword_records(data_root, review, names, spelling, index):
    records = []
    for row in evalhub_rows(data_root, HOTWORD):
        decided = review[row["id"]]
        if decided["choice"] != "一致":
            raise ValueError(f"{row['id']}: reference not confirmed by listening")
        relative = f"source/evalhub/{HOTWORD}/{row['audio']}"
        entry = index.setdefault(row["id"], index_entry(data_root / relative, relative, row["id"]))
        target = decided["target"]
        for heard, written in spelling.items():
            target = target.replace(heard, written)
        gold = [name for name in names if name in target]
        records.append(AudioRecord.from_dict({
            "schema_version": "audio-record/1.0",
            "id": f"hotword:{row['id']}",
            "task": "asr_hotwords",
            "audio_slots": [slot("primary", "hotword", entry)],
            "target": target,
            "language": "zh",
            "hotwords": gold,
            "labels": {"scenario": "hotword", "display_name": row["labels"]["display_name"],
                       "reference_kind": "human"},
            "metadata": {"evalhub": {"ref": evalhub_ref(HOTWORD), "sample_id": row["id"]},
                         "listening": decided, "customer_spelling": spelling,
                         "bias_lists": {DEMO_LIST: list(names)},
                         "distractor_kinds": {w: DEMO_LIST for w in names if w not in gold},
                         "source_audio_sha256": row["labels"]["source_audio_sha256"]},
        }).to_dict())
    return records


def build(data_root, agreement, pool, review, names):
    version_dir = data_root / "versions" / VERSION
    if (version_dir / "records").exists():
        raise FileExistsError(f"refusing to replace registered version: {version_dir}")
    index, by_split, dropped = {}, {}, []
    for split, (directory_name, _) in SPLITS.items():
        directory = data_root / "source" / "evalhub" / directory_name
        check_files(directory)
        for line in (directory / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            check = agreement[row["id"]]
            if check["dataset"] != directory_name:
                raise ValueError(f"{row['id']}: agreement entry is for {check['dataset']}")
            if split == "general" and not check["agreed_by"]:
                dropped.append({"id": row["id"], "duration": row.get("duration"),
                                "errors": check["errors"], "reference_tokens": check["reference_tokens"]})
                continue
            relative = f"source/evalhub/{directory_name}/{row['audio']}"
            entry = index.setdefault(row["id"], index_entry(data_root / relative, relative, row["id"]))
            labels = row.get("labels") or {}
            record_labels = {
                "scenario": labels.get("scenario"),
                "display_name": labels.get("display_name"),
                "reference_kind": labels.get("reference_kind"),
                "reference_source": labels.get("reference_source"),
                "agreed_by": check["agreed_by"],
            }
            if split == "police-cmd":
                record_labels["term"] = labels.get("term")
                record_labels["reference_audit_status"] = labels.get("reference_audit_status")
            if split == "general":
                # One general sample is marked verified in EvalHub although its text is the
                # Qwen pre-annotation; here every general reference counts as machine-agreed.
                record_labels["reference_kind"] = "machine_two_of_three"
            record = AudioRecord.from_dict({
                "schema_version": "audio-record/1.0",
                "id": f"{split}:{row['id']}",
                "task": "asr",
                "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                    "dataset_id": DATASET_ID, "version": VERSION, "split": split,
                    "cut_id": entry["cut_id"], "duration": entry["duration"]}}],
                "target": " ".join(check["reference"].split()),
                "language": "zh",
                "labels": {k: v for k, v in record_labels.items() if v is not None},
                "metadata": {
                    "evalhub": {"ref": evalhub_ref(directory_name), "sample_id": row["id"],
                                "annotation_status": (row.get("annotation") or {}).get("status")},
                    "transcripts": check["texts"],
                    "transcript_errors": check["errors"],
                    "source_audio_sha256": labels.get("source_audio_sha256"),
                },
            }).to_dict()
            by_split.setdefault(split, []).append(record)
    by_split[HOTWORD_SPLIT] = hotword_copy(by_split["police-cmd"], pool)
    by_split["owner"] = owner_records(data_root, review["owner"], index)
    by_split["hotword"] = hotword_records(data_root, review["hotword"], names["names"], names["spelling"], index)
    for split, rows in by_split.items():
        write_jsonl_gz(version_dir / "records" / f"{split}.jsonl.gz", rows)
    write_jsonl_gz(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    (version_dir / "general-dropped.json").write_text(
        json.dumps(dropped, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return by_split, index


def declaration(by_split, index, data_root):
    def relative(*parts):
        return "/".join(("versions", VERSION, *parts))

    artifacts = [{
        "name": "audio-index", "kind": "audio-index", "root_alias": ROOT_ALIAS,
        "relative_path": relative("audio-index.jsonl.gz"),
        "sha256": sha256_file(data_root / relative("audio-index.jsonl.gz")),
        "metadata": {"record_count": len(index)},
    }]
    splits = {}
    for split, rows in by_split.items():
        path = relative("records", f"{split}.jsonl.gz")
        artifacts.append({
            "name": f"{split}-records", "kind": "audio-records", "root_alias": ROOT_ALIAS,
            "relative_path": path, "sha256": sha256_file(data_root / path),
            "metadata": {"record_count": len(rows)},
        })
        seconds = sum(r["audio_slots"][-1]["ref"]["duration"] for r in rows)
        present = sum(r["labels"]["target_present"] for r in rows) if split == "owner" else 0
        if split in SPLITS:
            description = SPLITS[split][1]
        elif split == "owner":
            description = (f"机主识别（目标说话人转写）客户录音 {len(rows)} 段（{present} 段机主说话，其余机主没说话、参考为空），"
                      "注册音用同组近场录音。机主是谁由人工听审确定；机主说的文字每句取本机 MOSS、MOSS-pro、百炼、"
                      "Qwen3-ASR 中至少两份一致的转写，文字未经人工逐字校对（reference_kind: human_speaker_machine_text）。")
        elif split == "hotword":
            description = (f"人名热词客户录音 {len(rows)} 段，参考文本经人工听审确认。每条带客户 Demo 的人名表"
                        f"（{'、'.join(rows[0]['metadata']['bias_lists'][DEMO_LIST])}）；“黄晋飞”的写法由客户确认"
                        "（听审时与“黄静飞/黄敬飞”同音分不出）。")
        else:
            description = (
            "警务指令（出厂内置热词表）：音频和参考与 police-cmd 相同，每条带 audiollm-go main-td 出厂内置热词表"
            f"（builtin-hotwords-20261102.txt，{rows[0]['labels']['hotword_list_size']} 条，按文件顺序）整表；"
            f"{len({r['hotwords'][0] for r in rows})} 个指令词中 "
            f"{len({r['hotwords'][0] for r in rows if r['labels']['term_in_pool']})} 个在表里"
            "（不在表里的条目 labels.term_in_pool 为 false）。")
        basis = "mixture duration" if split == "owner" else "recording duration"
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "task": rows[0]["task"],
            "statistics": {"records": len(rows), "duration_hours": round(seconds / 3600, 4),
                           "duration_basis": basis},
            "provenance": {"description": description},
        }
        if split == HOTWORD_SPLIT:  # same audio as police-cmd: not a top-level split, not counted twice
            splits[split]["group"] = "police-cmd"
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "languages": ["zh"],
        "tasks": sorted({s["task"] for s in splits.values()}),
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "status": "complete",
            "synthetic": "none",
            "summary": "鼎桥客户真实录音的语音识别评测，仅评测",
            "run_dir": "/workspace/data/runs/tdtech-customer-v4",
            "description": "鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），"
                           "只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，"
                           "难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认；"
                           "警务指令另有一份带 audiollm-go 出厂内置热词表（1296 条）的副本（police-cmd-builtin），音频相同。"
                           "v4 加机主识别（6 段，机主由人工听审确定，文字取多模型一致转写）和人名热词（2 段，参考经人工听审）；"
                           "角色分离的多模型打标一致率太低（约 12%），不进本版本。v5 按客户确认把人名“黄晋飞”写进参考和人名表，其余与 v4 相同。",
            "sources": [*(f"EvalHub {evalhub_ref(name)}" for name, _ in SPLITS.values()),
                        "audiollm-go main-td providers/common/rag/vocabulary/builtin-hotwords-20261102.txt",
                        f"EvalHub {evalhub_ref(OWNER)}", f"EvalHub {evalhub_ref(HOTWORD)}",
                        f"人工听审 {REVIEW}", f"客户确认人名 {NAMES}"],
        },
    }


def register(repository, spec):
    path = repository / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    # A placeholder registered while the version was being prepared gives way to the real entry.
    rows = [r for r in rows if not (r["version"] == spec["version"] and r["provenance"].get("status") == "building")]
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    current = [s for s in load_catalog(repository / "catalog")
               if not (s.dataset_id == DATASET_ID and s.version == spec["version"])]
    validate_catalog([*current, DatasetSpec.from_dict(spec)])
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512),
                    encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roots", type=Path, required=True)
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[ROOT_ALIAS])
    agreement = json.loads((data_root / "source" / "agreement.json").read_text())["samples"]
    review = json.loads((data_root / REVIEW).read_text(encoding="utf-8"))
    names = json.loads((data_root / NAMES).read_text(encoding="utf-8"))
    by_split, index = build(data_root, agreement, builtin_pool(data_root), review, names)
    register(Path(__file__).resolve().parents[2], declaration(by_split, index, data_root))
    print({s: len(r) for s, r in by_split.items()}, f"audio files: {len(index)}")


if __name__ == "__main__":
    main()
