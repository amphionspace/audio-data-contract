#!/usr/bin/env python3
"""Register the context-correction benchmark as AudioRecords.

Inputs are the outputs of generate.py, voices.py, tts.py, qc.py and mine.py in
the version's source directory. Splits:

- ``synthetic`` (asr): synthesized pairs whose two items both pass QC;
- ``synthetic_ts`` (ts_asr): the same pairs no longer than ``ts_max_seconds``, with
  a real enrollment clip of the cloned speaker (single-speaker items only);
- v2 names the synthetic splits after ``synthetic_split`` (``synthetic_indep`` / ``synthetic_indep_ts``)
  and lists its mined corpora in ``mined_corpora`` (their mining settings stay in recipe.yaml);
- ``mined_real`` (asr): mined real recordings that pass QC;
- ``quarantine`` (asr): items with audio that failed QC (kept, not scored).

``<source>/excluded-recordings.txt`` lists the mined source recordings (``corpus:recording_id``);
training sets built from those corpora must leave them out.

Every record has ``labels.context_correction`` (segments, kind, category, pair,
breakdown fields, CoT supervision) which ``ae open-audio-llm ts-asr`` scores. With ``train_overlap`` in
the recipe it also carries ``train_overlap`` (seen / unseen): a tested spelling (2+ characters) or an
explanation (4+ characters) that occurs in an explained training transcript makes the item seen.

The new version is added to the repository's ``catalog/``; the published registry copy is synced from the merged
pull request (it is not a mirror of ``catalog/``, so it is never overwritten wholesale).

    python scripts/context_correction/build.py --source <source dir>
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl, write_jsonl

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROOT_ALIAS = "aidc_data"
DATA_ROOT = Path("/workspace/data")
SR = 16000
SPLITS = {
    "synthetic": ("asr", "合成音频：成对题目（correct 指向少见写法，confirm 指向常用写法），两条都通过质检才收录"),
    "synthetic_ts": ("ts_asr", "同一批合成题目中不超过 TS 时长上限的部分，配被克隆说话人的另一条真实语句作注册音频"),
    "synthetic_indep": ("asr", "独立合成题：出题和复核模型、说法、题型、场景、TTS、音色都不与训练数据重合；成对，两条都通过质检才收录"),
    "synthetic_indep_ts": ("ts_asr", "同一批独立合成题中不超过 TS 时长上限的单人题，配被克隆说话人的另一条真实语句作注册音频"),
    "mined_real": ("asr", "从真实语料挖掘的录音：LLM 扫描、两个 LLM 各自写出按上下文修正的转写且一致、只改写法不改读音"),
    "quarantine": ("asr", "有音频但未通过质检的条目（读错、说明没听清、超长），保留原因，不参与打分"),
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def index_entry(path: Path, cut_id: str) -> dict:
    info = sf.info(path)
    if info.samplerate != SR or info.channels != 1:
        raise ValueError(f"{path}: expected 16 kHz mono, got {info.samplerate} Hz x{info.channels}")
    return {"cut_id": cut_id, "root_alias": ROOT_ALIAS, "relative_path": str(path.relative_to(DATA_ROOT)),
            "sample_rate": SR, "channels": 1, "num_frames": info.frames,
            "duration": round(info.frames / SR, 4), "sha256": sha256_file(path)}


def label_of(item: dict, source: str) -> dict:
    review = item.get("review") or {}
    # one reviewer: the review row; several (v2): {model: review row}
    review = review["reviewer"] if "reviewer" in review else ", ".join(sorted(review))
    return {
        "segments": item["segments"], "kind": item["kind"], "category": item["category"],
        "subtype": item.get("subtype"), "pair_id": item.get("pair_id"), "position": item.get("position"),
        "distance": item.get("distance"), "entity_type": item.get("entity_type"), "scenario": item.get("scenario"),
        "source": source, "marked_text": item["marked_text"], "reason": item.get("reason", ""),
        "cot": item["cot"], **({"reviewer": review} if review else {}),
    }


def han(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", text)


def explained_training_text(refs: dict) -> str:
    """Every training transcript that carries an explanation: the synthetic training records and each real
    record the spelling clean flagged (its transcript, and the corrected one where the clean changed it)."""
    texts = [r["target"] for path in refs["synthetic_records"] for r in read_jsonl(Path(path))]
    clean = Path(refs["clean"])
    texts += [r["text"] for path in sorted(clean.glob("*/positives.jsonl")) for r in read_jsonl(path)]
    texts += [r["corrected"] for path in sorted(clean.glob("*/decisions.jsonl")) for r in read_jsonl(path)
              if r.get("corrected")]
    if not texts:
        raise ValueError(f"no explained training text under {refs}")
    return "\n".join(han(t) for t in texts)


def overlap_of(segments: list[dict], blob: str) -> dict:
    target = any(len(han(s["text"])) >= 2 and han(s["text"]) in blob for s in segments if s["role"] == "target")
    evidence = any(len(han(s["text"])) >= 4 and han(s["text"]) in blob for s in segments if s["role"] == "evidence")
    return {"train_overlap": "seen" if target or evidence else "unseen",
            "train_overlap_target": target, "train_overlap_evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    version_dir = DATA_ROOT / "datasets" / dataset_id / "versions" / version
    if version_dir.exists():
        raise FileExistsError(f"refusing to replace registered version: {version_dir}")
    source = args.source
    synthetic = recipe.get("synthetic_split", "synthetic")
    reviewers = ", ".join(s["model"] for s in recipe["llm"].get("reviewers") or [recipe["llm"]["reviewer"]])
    blob = explained_training_text(recipe["train_overlap"]) if "train_overlap" in recipe else None
    voices = {v["voice_id"]: v for v in read_jsonl(source / "voices.jsonl")}
    index: dict[str, dict] = {}

    def ref(cut_id, split):
        return {"dataset_id": dataset_id, "version": version, "split": split, "cut_id": cut_id,
                "duration": index[cut_id]["duration"]}

    def add_audio(path, cut_id):
        index.setdefault(cut_id, index_entry(Path(path), cut_id))

    # enrollment clips are copied in so the dataset does not depend on the voice corpora's layout
    enroll_dir = source / "enrollment"
    for voice in voices.values():
        destination = enroll_dir / f"{voice['voice_id']}.wav"
        if not destination.exists():
            import numpy as np
            import soxr

            wav, sr = sf.read(voice["enrollment"]["path"], dtype="float32", always_2d=True)
            wav = wav.mean(axis=1)
            if sr != SR:
                wav = soxr.resample(wav, sr, SR)
            destination.parent.mkdir(parents=True, exist_ok=True)
            sf.write(destination, np.clip(wav, -1, 1), SR, subtype="PCM_16")
        add_audio(destination, f"enrollment-{voice['voice_id']}")

    by_split = defaultdict(list)
    stats = Counter()

    def make(item, clip, qc, split, task, source_name, extra_meta, overlap=None):
        add_audio(clip["path"], item["id"])
        slots = [{"name": "primary", "purpose": "primary", "ref": ref(item["id"], split)}]
        if task == "ts_asr":
            enroll = f"enrollment-{clip['voice_id']}"
            slots = [{"name": "enrollment", "purpose": "enrollment", "ref": ref(enroll, split)},
                     {"name": "mixture", "purpose": "mixture", "ref": ref(item["id"], split)}]
        labels = {"context_correction": {**label_of(item, source_name), **(overlap or {})}}
        if split == "quarantine":
            labels["qc_issues"] = qc["issues"] if qc else ["no QC result"]
        record = AudioRecord.from_dict({
            "schema_version": "audio-record/1.0",
            "id": f"{version}:{split}:{item['id']}",
            "task": task, "audio_slots": slots, "target": item["text"], "language": "zh",
            "labels": labels,
            "metadata": {"qc_hypothesis": (qc or {}).get("hypothesis"), "qc_pinyin_error": (qc or {}).get("pinyin_error"),
                         "qc_model": (qc or {}).get("qc_model"), **extra_meta},
        }).to_dict()
        by_split[split].append(record)

    # synthetic pairs: keep a pair only when both items pass QC, and per subtype only the first
    # ``target`` such pairs in generation order (items.jsonl order); the rest is not used
    items = read_jsonl(source / "items.jsonl")
    clips = {c["id"]: c for c in read_jsonl(source / "tts.jsonl")}
    qc = {r["id"]: r for r in read_jsonl(source / "qc.jsonl")}
    targets = {sub: n for entry in recipe["categories"].values() for sub, n in entry["subtypes"].items()}
    taken = Counter()
    pairs = defaultdict(list)
    for item in items:
        pairs[item["pair_id"]].append(item)
    for members in pairs.values():
        subtype = members[0]["subtype"]
        # both items of a pair share the tag of the correct item (the one that carries the explanation)
        correct = next((m for m in members if m["kind"] == "correct"), members[0])
        overlap = overlap_of(correct["segments"], blob) if blob is not None else None
        if taken[subtype] >= targets[subtype]:
            stats[f"unused accepted pair: {subtype}"] += 1
            continue
        if any(m["id"] not in clips for m in members):
            stats["pair without audio"] += 1
            continue
        passed = len(members) == 2 and all(qc.get(m["id"], {}).get("pass") for m in members)
        taken[subtype] += passed
        for member in members:
            clip = clips[member["id"]]
            voice = voices[clip["voice_id"]]
            meta = {"voice_id": clip["voice_id"], "speaker": voice["speaker"], "voice_corpus": voice["corpus"],
                    "gender": voice.get("gender"), "tts_model": clip.get("tts_model"),
                    "generator": recipe["llm"]["generator"]["model"], "reviewer": reviewers}
            if not passed:
                make(member, clip, qc.get(member["id"]), "quarantine", "asr", synthetic, meta, overlap)
                continue
            make(member, clip, qc[member["id"]], synthetic, "asr", synthetic, meta, overlap)
        # a dialogue item has two voices, so it has no single target speaker for TS
        if passed and not any(m.get("turns") for m in members) and all(
                clips[m["id"]]["duration"] <= recipe["ts_max_seconds"] for m in members):
            for member in members:
                clip = clips[member["id"]]
                make(member, clip, qc[member["id"]], f"{synthetic}_ts", "ts_asr", synthetic,
                     {"voice_id": clip["voice_id"], "enrollment_utt": voices[clip["voice_id"]]["enrollment"]["utt_id"]},
                     overlap)

    # mined real recordings; their source recordings must stay out of any training set
    held_out = set()
    excluded = dict(recipe.get("excluded_mined") or {})  # item id -> why the spot check found it wrong
    for corpus in recipe.get("mined_corpora") or recipe["mining"]["corpora"]:
        root = source / "mined" / corpus
        mined_clips = {c["id"]: c for c in read_jsonl(root / "clips.jsonl")}
        mined_qc = {r["id"]: r for r in read_jsonl(root / "qc.jsonl")}
        for item in read_jsonl(root / "items.jsonl"):
            check = mined_qc.get(item["id"])
            if item["id"] in excluded:
                check = {**(check or {}), "pass": False,
                         "issues": [*(check or {}).get("issues", []), f"spot check: {excluded.pop(item['id'])}"]}
            split = "mined_real" if check and check["pass"] else "quarantine"
            held_out.add(f"{corpus}:{item['source_recording']}")
            make(item, mined_clips[item["id"]], check, split, "asr", f"mined:{corpus}",
                 {"corpus": corpus, "source_recording": item["source_recording"],
                  "source_start": item["source_start"], "corpus_transcript": item["corpus_transcript"],
                  "corpus_transcript_correct": item["corpus_transcript_correct"]},
                 overlap_of(item["segments"], blob) if blob is not None else None)
    if excluded:
        raise ValueError(f"excluded_mined names items that were not mined: {sorted(excluded)}")

    for split, rows in by_split.items():
        write_jsonl(version_dir / "records" / f"{split}.jsonl.gz", rows)
    (source / "excluded-recordings.txt").write_text("".join(f"{r}\n" for r in sorted(held_out)), encoding="utf-8")
    write_jsonl(version_dir / "audio-index.jsonl.gz", sorted(index.values(), key=lambda e: e["cut_id"]))
    spec = declaration(recipe, by_split, index, version_dir)
    if not args.no_register:
        register(spec)
    print({s: len(r) for s, r in by_split.items()}, dict(stats), f"audio files: {len(index)}")
    print("pairs per subtype:", dict(taken), "targets:", targets)


def declaration(recipe, by_split, index, version_dir):
    version, dataset_id = recipe["version"], recipe["dataset_id"]

    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": ROOT_ALIAS,
                "relative_path": str(path.relative_to(DATA_ROOT)), "sha256": sha256_file(path),
                "metadata": {"record_count": count}}

    artifacts = [artifact("audio-index", "audio-index", version_dir / "audio-index.jsonl.gz", len(index))]
    splits = {}
    for split, rows in sorted(by_split.items()):
        task, description = SPLITS[split]
        artifacts.append(artifact(f"{split}-records", "audio-records",
                                  version_dir / "records" / f"{split}.jsonl.gz", len(rows)))
        slot = -1  # primary, or the mixture of a TS record
        seconds = sum(r["audio_slots"][slot]["ref"]["duration"] for r in rows)
        splits[split] = {
            "artifacts": {"records": [f"{split}-records"], "audio_index": ["audio-index"]},
            "task": task,
            "statistics": {"records": len(rows), "duration_hours": round(seconds / 3600, 4),
                           "duration_basis": "recognized clip (mixture for ts_asr)"},
            "provenance": {"description": description},
        }
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": ["zh"], "tasks": sorted({SPLITS[s][0] for s in by_split}),
        "artifacts": artifacts, "splits": splits,
        "provenance": {
            "status": "complete", "synthetic": "partial",
            "description": " ".join(recipe["catalog"]["description"].split()),
            "sources": recipe["catalog"]["sources"],
        },
    }


def register(spec):
    path = REPO / "catalog" / f"{spec['dataset_id']}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == spec["version"] for r in rows):
        raise FileExistsError(f"version already registered: {spec['version']}")
    current = load_catalog(REPO / "catalog")
    validate_catalog([*current, DatasetSpec.from_dict(spec)])
    path.write_text(yaml.safe_dump([*rows, spec], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")


if __name__ == "__main__":
    main()
