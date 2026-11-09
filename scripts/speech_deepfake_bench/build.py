#!/usr/bin/env python3
"""Register the SpoofRadar v1.0 and Speech-DF-Arena evaluation sets as ``speech_deepfake_bench``.

Run ``extract.py`` first. Every protocol entry is matched to its file under ``source/<name>/`` (see
``sources.py``); a protocol entry without exactly one file, or a file no entry uses, stops the build.

Labels (``target``: ``bonafide`` / ``spoof``): SpoofRadar withholds them, so they come from DF-Arena's
protocol where it lists the clip, else from the release's own layout (FoR and XMAD ``real/``, LibriSeVoc
``gt/``, SpoofCeleb attack ``a00``). Every record is checked against that layout (also DFADD ``*_BONAFIDE/``
and SONAR ``real_samples/``) and against labels the release ships: the parquet packagings, In-the-Wild
``meta.csv``, the ADD keys (2022 from Zenodo under ``labels/``, 2023 ``label.txt`` in the archives).

Splits shared by both boards hold SpoofRadar's list (DF-Arena's is the same clips). The two boards differ
only on FoR (DF-Arena drops 106 fakes: ``for-norm-dfarena``) and LibriSeVoc (DF-Arena uses all 92,407
clips: ``librisevoc-all``; SpoofRadar the 18,487-clip test split).

    python scripts/speech_deepfake_bench/build.py --roots /workspace/data/registry/roots.json \
        [--eval-sets /workspace/data/datasets/speech_deepfake_bench/eval-sets]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

import soundfile as sf
import yaml

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import DFA, SOURCES, SR

DATASET_ID = "speech_deepfake_bench"
ROOT_ALIAS = DATASET_ID
VERSION = "v1-20261103"
TASK = "deepfake_detection"
AUDIO = (".wav", ".flac", ".mp3")
XMAD_LANGUAGES = {"ar", "de", "en", "es", "ro", "ru", "zh"}


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


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def key(spec, path):
    parts = [spec.get("aliases", {}).get(p, p) for p in path.replace("\\", "/").split("/")]
    if spec.get("stem"):
        parts[-1] = os.path.splitext(parts[-1])[0]
    return "/".join(parts[-spec["depth"]:])


def audio_files(dest):
    for directory, subdirs, files in os.walk(dest):
        subdirs[:] = [d for d in subdirs if d not in ("protocols", "metadata", "__MACOSX")]
        for name in files:
            if name.lower().endswith(AUDIO) and not name.startswith("._"):
                yield os.path.relpath(os.path.join(directory, name), dest)


def rule_label(name, sample):
    """The label a release's own layout gives, or None where it says nothing."""
    parts = sample.split("/")
    if name in ("FoR", "XMAD-Bench"):
        return {"real": "bonafide", "fake": "spoof"}[parts[-2]]
    if name == "LibriSeVoc":
        return "bonafide" if parts[-2] == "gt" else "spoof"
    if name == "SpoofCeleb":
        return "bonafide" if parts[-3] == "a00" else "spoof"
    if name == "DFADD":
        return "bonafide" if "BONAFIDE" in sample else "spoof"
    if name == "SONAR":
        return "bonafide" if parts[-2] == "real_samples" else "spoof"
    return None


def release_labels(name, dest):
    """{key: label} from labels the release itself ships, keyed like the protocol entries."""
    spec = SOURCES[name]
    out = {}
    if (dest / "parquet-labels.jsonl.gz").exists():
        with gzip.open(dest / "parquet-labels.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                out[key(spec, row["path"])] = ("bonafide", "spoof")[row["label"]]
    # ADD official keys: the 2022 ones from Zenodo (labels/), the 2023 ones inside the archives.
    keys = [*(dest / "labels").glob("*_label.txt"), *(dest.rglob("label.txt") if name.startswith("ADD") else [])]
    for labels in sorted(keys):
        for line in labels.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts:
                out[key(spec, parts[0])] = {"genuine": "bonafide", "fake": "spoof"}[parts[1]]
    if name == "In-the-Wild":
        (meta,) = list(dest.rglob("meta.csv"))
        for row in read_csv(meta):
            out[key(spec, row["file"])] = {"bona-fide": "bonafide", "spoof": "spoof"}[row["label"]]
    return out


def subset(name, sample):
    parts = sample.split("/")
    if name in ("LibriSeVoc", "SONAR", "DFADD"):
        return parts[0]
    if name == "Codecfake":
        return parts[1]
    if name == "XMAD-Bench":
        return "/".join(parts[:2])
    if name == "SpoofCeleb":
        return parts[2]
    return None


def language(name, sample):
    if name == "XMAD-Bench":
        return sample.split("/")[0]
    if name == "Codecfake":
        # Codecfake re-synthesizes AISHELL-3 (speaker ids SSBxxxx) and VCTK (pNNN) speech.
        return "zh" if "_SSB" in os.path.basename(sample) else "en"
    return SOURCES[name].get("language")


def match(name, data_root):
    """Protocol entries of one set, each with its file and label, by split."""
    spec = SOURCES[name]
    dest = data_root / "source" / name
    if not (dest / ".extracted.json").exists():
        raise FileNotFoundError(f"{name}: run extract.py first")
    files = {}
    for relative in audio_files(dest):
        k = key(spec, relative)
        if k in files:
            raise ValueError(f"{name}: two files share key {k}: {files[k]}, {relative}")
        files[k] = relative
    sr = [row["sample_id"] for row in read_csv(data_root / "source" / "protocols" / SR / f"{name}.csv")]
    dfa = {}
    if spec.get("dfa"):
        for row in read_csv(data_root / "source" / "protocols" / DFA / spec["dfa"]):
            dfa[key(spec, row["file_name"])] = (row["file_name"], row["label"])
    shipped = release_labels(name, dest)
    used, splits = set(), {}

    def entry(k, sample, sr_id, dfa_id, label):
        if k not in files:
            raise ValueError(f"{name}: no file for {sr_id or dfa_id}")
        for other in (rule_label(name, sample), shipped.get(k)):
            if other is not None and other != label:
                raise ValueError(f"{name}: {sr_id or dfa_id} labelled {label}, the release says {other}")
        used.add(files[k])
        return {"file": files[k], "key": k, "label": label, "sample": sample,
                "protocols": {p: i for p, i in ((SR, sr_id), (DFA, dfa_id)) if i}}

    rows = []
    for sample in sr:
        k = key(spec, sample)
        dfa_id, label = dfa.get(k, (None, None))
        label = label or rule_label(name, sample) or shipped.get(k)
        if label is None:
            raise ValueError(f"{name}: no label for {sample}")
        rows.append(entry(k, sample, sample, dfa_id, label))
    splits[spec["split"]] = rows
    sr_by_key = {key(spec, s): s for s in sr}
    if spec.get("dfa_split"):
        # DF-Arena's own list; a clip SpoofRadar also lists keeps SpoofRadar's id too.
        splits[spec["dfa_split"]] = [
            entry(k, sr_by_key.get(k, k), sr_by_key.get(k), dfa_id, label)
            for k, (dfa_id, label) in dfa.items()
        ]
    elif dfa and set(dfa) != set(sr_by_key):
        raise ValueError(f"{name}: DF-Arena lists {len(set(dfa) - set(sr_by_key))} clips SpoofRadar does not, "
                         f"and misses {len(set(sr_by_key) - set(dfa))}")
    stray = sorted(set(files.values()) - used)
    if stray:
        raise ValueError(f"{name}: {len(stray)} files no protocol uses, e.g. {stray[:3]}")
    return splits


def index_entry(relative_path):
    path, relative = relative_path
    info = sf.info(path)
    return {
        "cut_id": relative.removeprefix("source/").replace("/", ":", 1),
        "root_alias": ROOT_ALIAS,
        "relative_path": relative,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "num_frames": info.frames,
        "duration": round(info.frames / info.samplerate, 4),
        "sha256": sha256_file(path),
    }


def build(data_root, workers):
    version_dir = data_root / "versions" / VERSION
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace registered version: {version_dir}")
    matched = {name: match(name, data_root) for name in SOURCES}
    wanted = sorted({f"source/{name}/{row['file']}" for name, splits in matched.items()
                     for rows in splits.values() for row in rows})
    print(f"indexing {len(wanted)} audio files", flush=True)
    index = {}
    with cf.ProcessPoolExecutor(workers) as pool:
        for n, entry in enumerate(pool.map(index_entry, ((data_root / r, r) for r in wanted), chunksize=256)):
            index[entry["relative_path"]] = entry
            if n % 100000 == 0:
                print(f"  {n}", flush=True)
    by_split = {}
    for name, splits in matched.items():
        for split, rows in splits.items():
            records = []
            for row in rows:
                entry = index[f"source/{name}/{row['file']}"]
                # SpoofRadar's sample id; DF-Arena-only splits use the match key (its ids are absolute paths).
                ident = row["key"] if split == SOURCES[name].get("dfa_split") else row["protocols"][SR]
                labels = {"source": name}
                if subset(name, row["sample"]):
                    labels["subset"] = subset(name, row["sample"])
                record = {
                    "schema_version": "audio-record/1.0",
                    "id": f"{split}:{ident}",
                    "task": TASK,
                    "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                        "dataset_id": DATASET_ID, "version": VERSION, "split": split,
                        "cut_id": entry["cut_id"], "duration": entry["duration"]}}],
                    "target": row["label"],
                    "labels": labels,
                    "metadata": {"protocols": row["protocols"]},
                }
                lang = language(name, row["sample"])
                if lang:
                    record["language"] = lang
                records.append(AudioRecord.from_dict(record).to_dict())
            if len({r["id"] for r in records}) != len(records):
                raise ValueError(f"{split}: duplicate record ids")
            by_split[split] = (name, records)
            write_jsonl_gz(version_dir / "records" / f"{split}.jsonl.gz", records)
    write_jsonl_gz(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    return by_split, index


# SpoofRadar's order; (display name, what the set is) for the eval sets.
SETS = {
    "ASVspoof2019-LA": ("ASVspoof 2019 LA", "ASVspoof 2019 逻辑访问评测集：英文朗读，TTS 与语音转换伪造（A07–A19）"),
    "ASVspoof2021-LA": ("ASVspoof 2021 LA", "ASVspoof 2021 逻辑访问评测集：2019 的攻击经电话信道和编解码传输"),
    "ASVspoof2021-DF": ("ASVspoof 2021 DF", "ASVspoof 2021 深度伪造评测集：经多种有损压缩（mp3/m4a/ogg 等）的伪造语音"),
    "ASVspoof5-Eval": ("ASVspoof 5", "ASVspoof 5 评测集：众包录音，更新的 TTS/VC 攻击和对抗攻击"),
    "ADD2022-T1": ("ADD 2022 低质量", "ADD 2022 赛道 1：中文，含噪声和低质量条件的伪造语音"),
    "ADD2022-T3": ("ADD 2022 攻防博弈", "ADD 2022 赛道 3.2 第二轮：中文，参赛队伍生成的伪造语音"),
    "ADD2023-R1": ("ADD 2023 第一轮", "ADD 2023 赛道 1.2 第一轮评测：中文伪造语音检测"),
    "ADD2023-R2": ("ADD 2023 第二轮", "ADD 2023 赛道 1.2 第二轮评测：中文，攻击来源更多、鲁棒性要求更高"),
    "FoR": ("Fake-or-Real", "Fake-or-Real（for-norm 版）测试集：英文，早期商用与开源 TTS"),
    "Codecfake": ("Codecfake", "Codecfake 测试集 C1–C7（版本 1）：中英文，神经编解码器重合成的语音"),
    "LibriSeVoc": ("LibriSeVoc", "LibriSeVoc：LibriTTS 语句经 6 种神经声码器重合成"),
    "DFADD": ("DFADD", "DFADD 测试集：VCTK 说话人，扩散和流匹配 TTS（GradTTS、MatchaTTS、NaturalSpeech2、P-Flow、StyleTTS2）"),
    "SONAR": ("SONAR", "SONAR：9 个前沿 TTS 平台与模型（OpenAI、VALL-E、VoiceBox 等）生成的语音和真人语音"),
    "In-the-Wild": ("In-the-Wild", "In-the-Wild：网上收集的名人、政治人物真假语音，真实信道"),
    "XMAD-Bench": ("XMAD-Bench", "XMAD-Bench 测试集：7 种语言（阿、德、英、西、罗、俄、中），说话人、生成方法和真人来源都与训练集不同"),
    "SpoofCeleb": ("SpoofCeleb", "SpoofCeleb 评测集：VoxCeleb1 真实场景语音，23 种 TTS 生成"),
}
GROUPS = [
    ("ASVspoof", ["ASVspoof2019-LA", "ASVspoof2021-LA", "ASVspoof2021-DF", "ASVspoof5-Eval"],
     "ASVspoof 挑战赛系列（英文）"),
    ("ADD", ["ADD2022-T1", "ADD2022-T3", "ADD2023-R1", "ADD2023-R2"], "ADD 中文伪造语音检测挑战赛"),
    ("其他公开集", ["FoR", "Codecfake", "LibriSeVoc", "DFADD", "SONAR", "In-the-Wild", "XMAD-Bench", "SpoofCeleb"],
     "各论文发布的伪造语音数据，覆盖编解码器、声码器、扩散 TTS、商用平台和真实信道"),
]
BOARDS = {
    # name -> (sets, split overrides, description of the board)
    "spoofradar": (list(SETS), {}, "SpoofRadar v1.0（tefficlabs.com/spoofradar）的 16 个评测集"),
    "df-arena": ([s for s in SETS if s not in ("XMAD-Bench", "SpoofCeleb")],
                 {"FoR": "for-norm-dfarena", "LibriSeVoc": "librisevoc-all"},
                 "Speech-DF-Arena（Hugging Face Speech-Arena-2025/Speech-DF-Arena）的 14 个评测集"),
}


def split_counts(records):
    counts = Counter(r["target"] for r in records)
    return counts["bonafide"], counts["spoof"]


def split_description(split, name, records):
    bonafide, spoof = split_counts(records)
    boards = [b for b, (sets, over, _) in BOARDS.items()
              if name in sets and over.get(name, SOURCES[name]["split"]) == split]
    return (f"{SETS[name][1]}。{len(records):,} 条（真人 {bonafide:,} / 伪造 {spoof:,}），"
            f"用于 {'、'.join(boards)}；音频为原始文件：{SOURCES[name]['origin']}。")


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
    for split, (name, records) in by_split.items():
        path = relative("records", f"{split}.jsonl.gz")
        artifacts.append({
            "name": f"{split}-records", "kind": "audio-records", "root_alias": ROOT_ALIAS,
            "relative_path": path, "sha256": sha256_file(data_root / path),
            "metadata": {"record_count": len(records)},
        })
        seconds = sum(r["audio_slots"][0]["ref"]["duration"] for r in records)
        bonafide, spoof = split_counts(records)
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "task": TASK,
            "statistics": {"records": len(records), "bonafide": bonafide, "spoof": spoof,
                           "duration_hours": round(seconds / 3600, 4), "duration_basis": "recording duration"},
            "provenance": {"description": split_description(split, name, records)},
        }
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "languages": ["en", "zh", "ar", "de", "es", "ro", "ru"],
        "tasks": [TASK],
        "artifacts": artifacts,
        "splits": splits,
        "provenance": {
            "status": "complete",
            "synthetic": "partial",
            "summary": "伪造语音检测评测集（SpoofRadar、DF-Arena）",
            "description": (
                "SpoofRadar v1.0 与 Speech-DF-Arena 两个伪造语音检测排行榜使用的 16 个公开评测集，只用于评测，不进训练。"
                "每条记录的 target 为 bonafide（真人）或 spoof（伪造），metadata.protocols 保留两个榜单 protocol 中的原始样本 ID，"
                "可直接生成提交用的打分文件。官方 protocol 原样保存在 source/protocols/。各数据集许可证不同"
                "（ADD、Codecfake 为 CC BY-NC-ND 4.0，XMAD-Bench 为 CC BY-NC-SA 4.0），仅限内部研究评测，不得再分发。"
            ),
            "sources": [f"{name}: {SOURCES[name]['origin']}" for name in SETS],
            "leaderboards": ["https://tefficlabs.com/spoofradar#leaderboard",
                             "https://huggingface.co/spaces/Speech-Arena-2025/Speech-DF-Arena"],
        },
    }


def register(repository, spec):
    path = repository / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    current = load_catalog(repository / "catalog")
    validate_catalog([*current, DatasetSpec.from_dict(spec)])
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512),
                    encoding="utf-8")


def write_eval_sets(out, by_split):
    """The amphion-eval data configs, one per leaderboard (publish with ae eval-sets publish)."""
    out.mkdir(parents=True, exist_ok=True)
    for board, (sets, overrides, about) in BOARDS.items():
        evaluation = []
        for name in sets:
            split = overrides.get(name, SOURCES[name]["split"])
            _, records = by_split[split]
            bonafide, spoof = split_counts(records)
            source = {"dataset_id": DATASET_ID, "version": VERSION, "split": split, "task": TASK, "label": name}
            lang = SOURCES[name].get("language")
            if lang in ("en", "zh"):
                source["tags"] = [lang]
            source["display"] = SETS[name][0]
            source["description"] = f"{SETS[name][1]}；{len(records):,} 条（真人 {bonafide:,} / 伪造 {spoof:,}）"
            evaluation.append(source)
        config = {
            "task": "deepfake",
            "groups": [
                {"name": group, "labels": [n for n in names if n in sets], "aggregate": "macro", "description": text}
                for group, names, text in GROUPS
            ],
            "evaluation": evaluation,
        }
        (out / f"{board}.yaml").write_text(
            f"# {about}；按 EER 打分。\n" + yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=512),
            encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--eval-sets", type=Path, help="also write the amphion-eval data configs here")
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()
    data_root = Path(json.loads(args.roots.read_text())[ROOT_ALIAS])
    by_split, index = build(data_root, args.workers)
    register(Path(__file__).resolve().parents[2], declaration(by_split, index, data_root))
    if args.eval_sets:
        write_eval_sets(args.eval_sets, by_split)
    print({s: len(r) for s, (_, r) in by_split.items()}, f"audio files: {len(index)}")


if __name__ == "__main__":
    main()
