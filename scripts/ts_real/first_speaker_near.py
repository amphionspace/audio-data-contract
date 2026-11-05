#!/usr/bin/env python3
"""Near-field mixtures and speaker-similarity labels for the first-speaker windows (ts_asr_nearfar firstother-v2).

Derived from ``firstother-v1-20261104`` (``first_speaker.py``): same windows, enrollments, degradation parameters and
record IDs, so every v2 record pairs with its v1 record.

* The ``-mf`` cells are kept as they are (their audio files are reused from v1).
* New ``en-mn`` and ``ed-mn`` cells: the v1 ``en`` / ``ed`` enrollment, with the mixture taken from the headsets of
  the window's speakers, summed and scaled to the RMS of the far-field mixture (``near_far.near_mixture`` restricted to
  the speakers in the window). The internally returned TS-ASR badcase pairs a noisy, dull voiceprint with a clean
  close-talk session; ``ed-mn`` is that pairing, ``en-mn`` its clean-enrollment control.
* Every record gets ``labels.target_sim``, ``impostor_sim``, ``sim_margin`` (= target - impostor) and ``opener_sim``:
  ECAPA cosine between the first ``build.ENROLL_CROP`` seconds of the enrollment (what the client sends) and each
  window speaker's solo speech in that record's own mixture (their annotated speech where nobody else is annotated,
  pieces of at least ``SOLO_PIECE_MIN`` s, concatenated, at most ``SOLO_MAX`` s; a speaker with less than ``SOLO_MIN``
  s of it gets no score). ``impostor_sim`` is the maximum over the window speakers other than the target (all of
  them for a target-absent record); ``target_sim`` and ``sim_margin`` are empty for target-absent records;
  ``opener_sim`` is the score of the first speaker of the window when that is not the target.
* Positive records with ``sim_margin <= HARD_MARGIN`` are also listed in ``<kind>-<cell>-pos-hard`` (same audio and
  record index, a subset of the positive split).

    python scripts/ts_real/first_speaker_near.py --roots /workspace/data/registry/roots.json \\
        --embed-python /workspace/workspace/mingdong/miniconda3/envs/k2/bin/python
"""

from __future__ import annotations

import argparse
import copy
import gzip
import importlib.util
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


first = _load("ts_real_first_speaker", "first_speaker.py")
real, near_far, voice, synth = first.real, first.near_far, first.voice, first.synth
REPO = HERE.parents[1]
SR = real.SR
DATASET_ID = first.DATASET_ID
SOURCE = first.VERSION
VERSION = "firstother-v2-20261105"
NEAR_CELLS = {"en-mn": "en-mf", "ed-mn": "ed-mf"}  # new cell: the v1 cell whose enrollment it reuses
SOLO_PIECE_MIN = 0.3  # seconds; shorter gaps between other speakers carry little voice
SOLO_MIN = 1.0  # seconds of solo speech a speaker needs to be scored
SOLO_MAX = 20.0
HARD_MARGIN = 0.30  # badcase: target margin 0.25 (enrollment vs. the target's solo speech in the mixture)
HARD = "-hard"


def solo_pieces(utts, speaker, duration):
    """[(start, end)] relative to the window: ``speaker``'s annotated speech with nobody else annotated."""
    others = sorted((u["start"], u["start"] + u["duration"]) for u in utts if u["speaker"] != speaker)
    out = []
    for u in utts:
        if u["speaker"] != speaker:
            continue
        s, e = u["start"], min(u["start"] + u["duration"], duration)
        for a, b in others:
            if b <= s or a >= e:
                continue
            if a - s >= SOLO_PIECE_MIN:
                out.append((s, a))
            s = max(s, b)
        if e - s >= SOLO_PIECE_MIN:
            out.append((s, e))
    return out


def speaker_vectors(embed, mix, utts):
    """{speaker: unit vector of their solo speech in ``mix``} for speakers with at least SOLO_MIN s of it."""
    out = {}
    for speaker in sorted({u["speaker"] for u in utts}):
        pieces = solo_pieces(utts, speaker, len(mix) / SR)
        if sum(e - s for s, e in pieces) < SOLO_MIN:
            continue
        audio = np.concatenate([mix[round(s * SR):round(e * SR)] for s, e in pieces])[: int(SOLO_MAX * SR)]
        out[speaker] = embed(audio)
    return out


def similarity_labels(enroll_vector, vectors, target, opener, present):
    sims = {spk: round(float(enroll_vector @ v), 3) for spk, v in vectors.items()}
    impostors = [v for spk, v in sims.items() if spk != target]
    labels = {"impostor_sim": max(impostors) if impostors else None,
              "target_sim": sims.get(target) if present else None,
              "opener_sim": sims.get(opener) if opener != target else None}
    labels["sim_margin"] = (round(labels["target_sim"] - labels["impostor_sim"], 3)
                            if labels["target_sim"] is not None and labels["impostor_sim"] is not None else None)
    return labels, sims


def window_near_mixture(recording, start, n, speakers, far_rms):
    """Sum of the headsets of ``speakers`` over the window, scaled to ``far_rms`` (``near_far.near_mixture``)."""
    total = sum(near_far.cut_near(near_far.NEAR_DIR / f"{recording}_N_SPK{spk}.wav", start, start + n / SR)
                for spk in speakers)
    total = total[:n] * (far_rms / near_far.rms(total[:n]))
    peak = float(np.abs(total).max())
    return (total * (near_far.PEAK_LIMIT / peak) if peak > near_far.PEAK_LIMIT else total).astype(np.float32)


def read_source(catalog, roots):
    spec = next(s for s in catalog if s.dataset_id == DATASET_ID and s.version == SOURCE)
    records = {}
    for split in spec.splits:
        for path in resolve_split(catalog, DATASET_ID, SOURCE, split, "records", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                records[split] = [json.loads(line) for line in stream]
    (index_path,) = resolve_split(catalog, DATASET_ID, SOURCE, next(iter(spec.splits)), "audio_index", roots)
    with gzip.open(index_path, "rt", encoding="utf-8") as stream:
        index = {row["cut_id"]: row for row in map(json.loads, stream)}
    return spec, records, index


def slot(record, name):
    return next(s for s in record["audio_slots"] if s["name"] == name)["ref"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--embed-python", type=Path, required=True, help="Python with onnxruntime and torchaudio")
    parser.add_argument("--speaker-model", type=Path, default=Path(real.SPEAKER_MODEL))
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    data_root = Path(roots[DATASET_ID])
    out_root = data_root / "source" / VERSION
    if (data_root / "versions" / VERSION).exists() or out_root.exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    spec, source, index = read_source(load_catalog(args.catalog), roots)
    embed = voice.Embedder(args.embed_python, args.speaker_model)
    crop = int(real.ENROLL_CROP * SR)

    def audio(cut_id):
        return sf.read(data_root / index[cut_id]["relative_path"], dtype="float32")[0]

    splits, rows = defaultdict(list), {}
    by_window = defaultdict(dict)  # (kind, index) -> {(cell, pos|neg): record}
    for name, records in source.items():
        for record in records:
            labels = record["labels"]
            by_window[(labels["first_speaker"], record["metadata"]["index"])][(labels["cell"], labels["kind"])] = record
    unscored = Counter()
    for (first_speaker, number), cells in sorted(by_window.items()):
        some = next(iter(cells.values()))
        labels, meta = some["labels"], some["metadata"]
        kind = next(k for k, v in first.KINDS.items() if v == first_speaker)
        utts = meta["window_utts"]
        speakers = sorted({u["speaker"].split(":", 1)[1] for u in utts})
        far_mix = audio(slot(some, "mixture")["cut_id"])
        near_mix = window_near_mixture(labels["recording"], labels["window_start_s"], len(far_mix), speakers,
                                       near_far.rms(far_mix))
        mix_cut = f"{kind}-mn-{number:04d}-mix"
        relative = f"audio/{kind}-mn/{mix_cut}.wav"
        synth.write_wav(out_root / relative, near_mix)
        rows[mix_cut] = {"cut_id": mix_cut, "relative_path": f"source/{VERSION}/{relative}", "num_frames": len(near_mix),
                         "duration": round(len(near_mix) / SR, 4), "sha256": synth.sha256_file(out_root / relative),
                         "root_alias": DATASET_ID, "sample_rate": SR, "channels": 1}
        vectors = {"far": speaker_vectors(embed, far_mix, utts), "near": speaker_vectors(embed, near_mix, utts)}
        opener = f"alimeeting:{labels['opener_speaker']}"
        targets = {}
        for (cell, pk), record in sorted(cells.items()):
            targets[(cell, pk)] = (record, cell)
        for new, old in NEAR_CELLS.items():
            for pk in ("pos", "neg"):
                targets[(new, pk)] = (cells[(old, pk)], new)
        for (cell, pk), (src, _) in sorted(targets.items()):
            record = copy.deepcopy(src)
            near = cell.endswith("-mn")
            name = src["labels"]["scenario"].replace(f"-{src['labels']['cell']}-", f"-{cell}-")
            record["id"] = f"{name}:{record['metadata']['index']:04d}"
            record["labels"].update(scenario=name, cell=cell, mix_domain="near" if near else "far")
            record["metadata"]["split"] = name
            if near:
                record["metadata"]["source_record"] = src["id"]
                record["labels"]["mixture_rms_dbfs"] = round(float(20 * np.log10(near_far.rms(near_mix) + 1e-9)), 2)
            for ref in (s["ref"] for s in record["audio_slots"]):
                ref.update(version=VERSION, split=name)
                if near and ref["cut_id"] == slot(src, "mixture")["cut_id"]:
                    ref.update(cut_id=mix_cut, duration=rows[mix_cut]["duration"])
                elif ref["cut_id"] not in rows:
                    rows[ref["cut_id"]] = index[ref["cut_id"]]
            enroll_vector = embed(audio(slot(record, "enrollment")["cut_id"])[:crop])
            present = pk == "pos"
            target = record["metadata"]["target_speaker"]
            sims, per_speaker = similarity_labels(enroll_vector, vectors["near" if near else "far"], target, opener, present)
            record["labels"].update(sims)
            record["metadata"]["speaker_sims"] = per_speaker
            if present and sims["target_sim"] is None:
                unscored[cell] += 1
            splits[name].append(record)
            if present and sims["sim_margin"] is not None and sims["sim_margin"] <= HARD_MARGIN:
                hard = copy.deepcopy(record)
                hard["id"] = f"{name}{HARD}:{record['metadata']['index']:04d}"
                hard["labels"]["scenario"] = hard["metadata"]["split"] = name + HARD
                for ref in (s["ref"] for s in hard["audio_slots"]):
                    ref["split"] = name + HARD
                splits[name + HARD].append(hard)
        if number % 25 == 0:
            print(kind, number, flush=True)
    embed.close()

    def median(values):
        values = [v for v in values if v is not None]
        return round(statistics.median(values), 3) if values else None

    report = {"records": {n: len(r) for n, r in sorted(splits.items())}, "unscored_targets": dict(unscored),
              "hard_margin": HARD_MARGIN, "medians": {}}
    for name, records in sorted(splits.items()):
        if not name.endswith(HARD):
            report["medians"][name] = {k: median([r["labels"][k] for r in records])
                                       for k in ("target_sim", "impostor_sim", "sim_margin", "opener_sim")}
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)

    for name, records in splits.items():
        records.sort(key=lambda r: r["id"])
        synth.write_jsonl_gz(data_root / "versions" / VERSION / "records" / f"{name}.jsonl.gz", records)
    synth.write_jsonl_gz(data_root / "versions" / VERSION / "audio-index.jsonl.gz", sorted(rows.values(), key=lambda e: e["cut_id"]))

    def rel(*parts):
        return "/".join(("versions", VERSION, *parts))

    artifacts = [{"name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
                  "relative_path": rel("audio-index.jsonl.gz"),
                  "sha256": synth.sha256_file(data_root / rel("audio-index.jsonl.gz")), "metadata": {"record_count": len(rows)}}]
    cell_text = {"en-mn": "；注册取本人头戴麦（干净），混合取窗口内各说话人头戴麦之和（电平对齐远场混合）",
                 "ed-mn": "；注册取本人头戴麦并加噪、限带（与 ed-mf 同一文件），混合取窗口内各说话人头戴麦之和（电平对齐远场混合）"}
    split_decl = {}
    for name in sorted(splits, key=lambda n: (n.removesuffix(HARD), n.endswith(HARD))):
        records = splits[name]
        path = rel("records", f"{name}.jsonl.gz")
        artifacts.append({"name": f"{name}-records", "kind": "audio-records", "root_alias": DATASET_ID, "relative_path": path,
                          "sha256": synth.sha256_file(data_root / path), "metadata": {"record_count": len(records)}})
        base = name.removesuffix(HARD)
        cell = records[0]["labels"]["cell"]
        if cell in cell_text:
            mf = base.replace(f"-{cell}-", f"-{NEAR_CELLS[cell]}-")
            text = spec.splits[mf].provenance["description"].split("；")[0] + cell_text[cell] + "；" + (
                "目标在场" if records[0]["labels"]["kind"] == "pos" else "目标缺席")
        else:
            text = spec.splits[base].provenance["description"]
        if name.endswith(HARD):
            text += f"；只含 sim_margin ≤ {HARD_MARGIN} 的记录（同名划分的子集）"
        seconds = sum(slot(r, "mixture")["duration"] for r in records)
        split_decl[name] = {"artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]}, "task": "ts_asr",
                            "statistics": {"records": len(records), "duration_hours": round(seconds / 3600, 4),
                                           "duration_basis": "Mixture duration"},
                            "provenance": {"description": text}}
    old = spec.provenance
    declaration = {
        "schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION,
        "languages": list(spec.languages), "tasks": list(spec.tasks), "artifacts": artifacts, "splits": split_decl,
        "provenance": {
            "summary": old.get("summary"), "status": "complete", "synthetic": old["synthetic"],
            "description": (
                f"{DATASET_ID}@{SOURCE} 的近场混合与声纹相似度版，窗口、注册、劣化参数和记录 ID 与 v1 相同，可逐条对照。"
                "内部返回的 TS-ASR badcase 的注册比会话更吵（会话是安静的近讲录音），而 v1 的混合是远场通道 0、带混响，"
                "所以新增 en-mn、ed-mn：注册同 en-mf、ed-mf，混合取窗口内各说话人头戴麦之和、电平对齐远场混合；mf 各划分不变。"
                "每条记录加 labels.target_sim / impostor_sim / sim_margin / opener_sim：ECAPA（WeSpeaker ECAPA-TDNN512-LM）"
                f"计算注册前 {real.ENROLL_CROP:g} 秒与该条混合里各说话人独自说话部分（标注无他人、每段 ≥{SOLO_PIECE_MIN} 秒、"
                f"合计 ≥{SOLO_MIN} 秒）的余弦；impostor 取非目标中的最大值，sim_margin = target − impostor，目标缺席时 target 与 margin 为空。"
                f"目标在场且 sim_margin ≤ {HARD_MARGIN} 的另列入 <划分>-hard（子集，badcase 的 margin 为 0.25）。"
                "统计见 source/<版本>/report.json。生成脚本 scripts/ts_real/first_speaker_near.py。只用于评测，不进训练。"),
            "sources": [*old.get("sources", []), f"{DATASET_ID}@{SOURCE}"],
        },
    }
    if args.no_register:
        return
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    rows_yaml = list(yaml.safe_load(path.read_text()))
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows_yaml, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", VERSION, sum(map(len, splits.values())), "records", flush=True)


if __name__ == "__main__":
    main()
