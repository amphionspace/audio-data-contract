#!/usr/bin/env python3
"""Build and register the blank / non-speech splits of the plain-ASR babble benchmark (asr_babble_bench v3).

Every sample is an ``audio-record/1.0`` ``asr`` record with an empty reference, so the native evaluator reports
the false-output rate. ``recipe-blank.yaml`` lists the splits: real blank stretches of TD-Tech device recordings,
synthetic noise floors and mains hum, and FSD50K eval-split environment sounds without voices or music.

Three steps, because the VAD check runs in an environment with FunASR:

    python scripts/asr_babble_bench/build_blank.py candidates --roots /workspace/data/registry/roots.json
    /workspace/workspace/mingdong/miniconda3/envs/dolphin/bin/python scripts/asr_babble_bench/vad_blank.py \\
        /workspace/data/datasets/asr_babble_bench/source/v3-20261104.partial/tdtech-candidates
    python scripts/asr_babble_bench/build_blank.py render --roots /workspace/data/registry/roots.json --workers 16

``candidates`` cuts every stretch on which none of the three diarization teachers has speech (each segment widened
by ``margin_seconds``). ``vad_blank.py`` writes FSMN-VAD speech spans next to the cuts. ``render`` quarantines cuts
with VAD speech, draws each TD-Tech split from its length bin, renders the synthetic and FSD50K splits, and
registers the version. No ASR output is used to choose samples: that would drop exactly the clips a model
hallucinates on.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import multiprocessing
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts" / "ts_benchmark"))
import mixer

_spec = importlib.util.spec_from_file_location("ts_build", REPO / "scripts" / "ts_benchmark" / "build.py")
ts_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts_build)

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

SR = mixer.SAMPLE_RATE
GENERATOR_VERSION = "blank-1"
MAINS_HZ = 50.0  # China mains frequency
HUM_HARMONICS = range(2, 11)
SILENT_WINDOW_RATIO = 10.0 ** (-30.0 / 20.0)  # a window 30 dB below its clip's RMS holds no sound worth testing
G = {}
FORK = multiprocessing.get_context("fork")


def paths(recipe, roots):
    data_root = Path(roots[recipe["dataset_id"]])
    partial = data_root / "source" / f"{recipe['version']}.partial"
    return data_root, partial, partial / "tdtech-candidates"


# --- TD-Tech blank stretches ----------------------------------------------------------


def teacher_labels(spec):
    """{recording_id: {teacher: label row}} for recordings every teacher labelled successfully."""
    by_recording = defaultdict(dict)
    for teacher, path in spec["teachers"].items():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["status"] == "ok":
                by_recording[row["recording_id"]][teacher] = row
    return {rid: rows for rid, rows in sorted(by_recording.items()) if len(rows) == len(spec["teachers"])}


def blank_stretches(rows, margin, min_seconds):
    """[(start, end)] free of every teacher's speech, segments widened by ``margin``."""
    duration = min(row["duration"] for row in rows.values())
    busy = sorted((max(0.0, s["start"] - margin), s["end"] + margin) for row in rows.values() for s in row["segments"])
    out, cursor = [], 0.0
    for start, end in [*busy, (duration, duration)]:
        if start - cursor >= min_seconds:
            out.append((round(cursor, 3), round(min(start, duration), 3)))
        cursor = max(cursor, end)
    return out


def cmd_candidates(recipe, roots):
    spec = recipe["tdtech"]
    _, _, cuts = paths(recipe, roots)
    if cuts.exists():
        raise FileExistsError(f"candidates already cut: {cuts}")
    cuts.mkdir(parents=True)
    rows = []
    for rid, labels in teacher_labels(spec).items():
        audio = next(iter(labels.values()))["audio"]
        if len({row["audio"] for row in labels.values()}) != 1:
            raise ValueError(f"{rid}: teachers labelled different audio files")
        w = ts_build.read_audio(audio)
        for start, end in blank_stretches(labels, spec["margin_seconds"], spec["min_seconds"]):
            end = min(end, start + spec["max_seconds"])
            cut_id = f"{rid}-{round(start * 1000):07d}"
            segment = w[int(start * SR):int(end * SR)]
            ts_build.write_wav(cuts / f"{cut_id}.wav", segment)
            rows.append({"cut_id": cut_id, "recording_id": rid, "audio": audio, "start": start, "end": end,
                         "duration": round(len(segment) / SR, 4), "rms_dbfs": round(mixer.db(mixer.rms(segment)), 2)})
    with (cuts / "candidates.jsonl").open("w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(f"{len(rows)} candidates from {len({r['recording_id'] for r in rows})} recordings", flush=True)


def tdtech_pool(recipe, cuts):
    """Candidates that passed the VAD check, and the quarantined ones with their reason."""
    vad = {}
    for line in (cuts / "vad.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        vad[row["cut_id"]] = row
    keep, quarantine = [], []
    for line in (cuts / "candidates.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        check = vad.get(row["cut_id"])
        if check is None:
            raise ValueError(f"{row['cut_id']}: no VAD result; run vad_blank.py first")
        speech = sum(end - start for start, end in check["speech"]) / 1000.0
        row["vad_speech_s"] = round(speech, 3)
        if speech >= recipe["tdtech"]["vad_max_speech_seconds"]:
            quarantine.append({**row, "reason": "fsmn_vad_speech", "vad_speech_ms": check["speech"]})
        else:
            keep.append(row)
    return keep, quarantine


# --- FSD50K pools ----------------------------------------------------------------------


def fsd_pools(recipe, roots):
    spec = recipe["fsd"]
    base = Path(roots["open_noise"]) / "fsd50k" / "extracted"
    with (base / "FSD50K.ground_truth" / f"{spec['split']}.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    exclude, used, pools = set(spec["exclude"]), set(), {}
    for name, include in spec["pools"].items():
        files = []
        for row in rows:
            labels = set(row["labels"].split(","))
            if row["fname"] in used or not labels & set(include) or labels & exclude:
                continue
            path = base / f"FSD50K.{spec['split']}_audio" / f"{row['fname']}.wav"
            duration = sf.info(path).duration
            if duration >= spec["min_seconds"]:
                files.append({"path": str(path), "duration": duration, "fname": row["fname"],
                              "labels": sorted(labels & set(include))})
                used.add(row["fname"])  # a clip belongs to the first pool that takes it
        pools[name] = sorted(files, key=lambda f: f["fname"])
    return pools


# --- planning and rendering ------------------------------------------------------------


def log_uniform(rng, lo, hi):
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def plan_split(recipe, split, by_name, tdtech, fsd):
    seed, n, plans = recipe["seed"], split["n"], []
    if split["source"] == "tdtech":
        lo, hi = split["bin"]
        pool = [c for c in tdtech if lo <= c["duration"] < hi or (hi == recipe["tdtech"]["max_seconds"] and c["duration"] >= lo)]
        chosen = sorted(random.Random(f"{seed}:{split['name']}").sample(pool, min(n, len(pool))), key=lambda c: c["cut_id"])
        return [{"source": "tdtech", "cut": c} for c in chosen]
    for index in range(n):
        rng = random.Random(f"{seed}:{split['name']}:{index}")
        donor = by_name[rng.choice(split["donors"])] if split["source"] == "mixed" else split
        duration = log_uniform(rng, *split["duration"])
        level = round(rng.uniform(*donor["level_dbfs"]), 2)
        plan = {"source": donor["source"], "donor": donor["name"], "level_dbfs": level}
        if donor["source"] in ("floor", "hum"):
            plan.update(duration=round(duration, 3), kind=rng.choice(recipe["floor_kinds"]), noise_seed=rng.getrandbits(32))
            if donor["source"] == "hum":
                plan.update(hum_gains_db=[round(rng.uniform(-30.0, 0.0), 2) for _ in HUM_HARMONICS],
                            hum_phase=[round(rng.uniform(0, 2 * math.pi), 4) for _ in range(len(HUM_HARMONICS) + 1)],
                            floor_dbfs=round(rng.uniform(-65.0, -55.0), 2))
        else:
            clip = rng.choice(fsd[donor["source"].split(":", 1)[1]])
            duration = min(duration, clip["duration"])
            plan.update(duration=round(duration, 3), clip=clip,
                        offset_s=round(rng.uniform(0.0, clip["duration"] - duration), 3))
        plans.append(plan)
    return plans


def floor_noise(n, kind, dbfs, seed):
    if kind != "brown":
        return mixer.floor_noise(n, {"kind": kind, "dbfs": dbfs, "seed": seed})
    spectrum = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    spectrum[1:] /= np.arange(1, len(spectrum))
    spectrum[0] = 0.0
    return mixer.normalize_rms(np.fft.irfft(spectrum, n).astype(np.float32), dbfs)


def render_job(job):
    split, index, plan, out = job
    name = split["name"]
    labels = {"scenario": name, "kind": "noise", "source": plan["source"]}
    metadata = {"generator": GENERATOR_VERSION, "seed": G["recipe"]["seed"], "split": name, "index": index}
    if plan["source"] == "tdtech":
        cut = plan["cut"]
        w = ts_build.read_audio(G["cuts"] / f"{cut['cut_id']}.wav")
        labels.update(level_dbfs=cut["rms_dbfs"], vad_speech_s=cut["vad_speech_s"])
        metadata["tdtech"] = {k: cut[k] for k in ("recording_id", "audio", "start", "end")}
    else:
        n = round(plan["duration"] * SR)
        if plan["source"] == "floor":
            w = floor_noise(n, plan["kind"], plan["level_dbfs"], plan["noise_seed"])
        elif plan["source"] == "hum":
            t = np.arange(n) / SR
            gains = [0.0, *plan["hum_gains_db"]]
            hum = sum(10.0 ** (g / 20.0) * np.sin(2 * np.pi * MAINS_HZ * k * t + p)
                      for k, g, p in zip([1, *HUM_HARMONICS], gains, plan["hum_phase"]))
            w = mixer.normalize_rms(hum.astype(np.float32), plan["level_dbfs"])
            w = w + floor_noise(n, plan["kind"], plan["floor_dbfs"], plan["noise_seed"])
        else:
            clip = ts_build.read_audio(plan["clip"]["path"])
            start = int(plan["offset_s"] * SR)
            moved = mixer.rms(clip[start:start + n]) < mixer.rms(clip) * SILENT_WINDOW_RATIO
            if moved:  # a sparse event clip can be silent where the window fell: take its most energetic window
                energy = np.concatenate([[0.0], np.cumsum(np.square(clip, dtype=np.float64))])
                start = int(np.argmax(energy[n:] - energy[:-n])) if len(clip) > n else 0
            segment = clip[start:start + n]
            w = mixer.normalize_rms(segment.astype(np.float32), plan["level_dbfs"])
            metadata["fsd"] = {"fname": plan["clip"]["fname"], "labels": plan["clip"]["labels"],
                               "offset_s": round(start / SR, 3), **({"drawn_offset_s": plan["offset_s"]} if moved else {})}
        labels["level_dbfs"] = plan["level_dbfs"]
        if plan["source"] in ("floor", "hum"):
            labels["noise_kind"] = plan["kind"]
        if plan.get("donor") != name:
            labels["donor"] = plan["donor"]
    w = np.asarray(w, dtype=np.float32)
    peak = float(np.abs(w).max()) if len(w) else 0.0
    if peak > 0.99:
        labels["peak_scale_db"] = round(20.0 * math.log10(0.99 / peak), 2)
        w = w * (0.99 / peak)
    relative = f"audio/{name}/{name}-{index:04d}.wav"
    ts_build.write_wav(out / relative, w)
    entry = {"cut_id": f"{name}-{index:04d}", "relative_path": relative, "num_frames": len(w),
             "duration": round(len(w) / SR, 4), "sha256": ts_build.sha256_file(out / relative)}
    labels["duration_s"] = entry["duration"]
    return {"split": name, "index": index, "labels": labels, "metadata": metadata, "entry": entry}


# --- registration ----------------------------------------------------------------------


def register(recipe, splits, results, data_root, alias, report):
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    by_split = defaultdict(list)
    for r in results:
        by_split[r["split"]].append(r)
    index_rows, artifacts, split_decl = [], [], {}

    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": alias, "relative_path": path,
                "sha256": ts_build.sha256_file(data_root / path), "metadata": {"record_count": count}}

    for split in splits:
        name, records = split["name"], []
        for r in sorted(by_split[name], key=lambda r: r["index"]):
            entry = r["entry"]
            index_rows.append({**entry, "root_alias": alias, "sample_rate": SR, "channels": 1,
                               "relative_path": f"source/{version}/{entry['relative_path']}"})
            records.append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{name}:{r['index']:04d}", "task": "asr",
                "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                    "dataset_id": dataset_id, "version": version, "split": name,
                    "cut_id": entry["cut_id"], "duration": entry["duration"]}}],
                "target": "", "language": recipe["language"], "labels": r["labels"], "metadata": r["metadata"],
            }).to_dict())
        path = f"versions/{version}/records/{name}.jsonl.gz"
        ts_build.write_jsonl_gz(data_root / path, records)
        artifacts.append(artifact(f"{name}-records", "audio-records", path, len(records)))
        params = {k: v for k, v in split.items() if k not in ("name", "n", "display", "description")}
        split_decl[name] = {
            "artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
            "task": "asr",
            "statistics": {"records": len(records),
                           "duration_hours": round(sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600, 4),
                           "duration_basis": "clip duration"},
            "provenance": {"description": f"{split['display']}：{split['description']}。参数 {json.dumps(params, ensure_ascii=False)}"},
        }
    if len({e["cut_id"] for e in index_rows}) != len(index_rows):
        raise ValueError("duplicate cut ids")
    ts_build.write_jsonl_gz(data_root / "versions" / version / "audio-index.jsonl.gz", sorted(index_rows, key=lambda e: e["cut_id"]))
    artifacts.insert(0, artifact("audio-index", "audio-index", f"versions/{version}/audio-index.jsonl.gz", len(index_rows)))
    for name in ("candidates", "quarantine"):
        rel = f"source/{version}/tdtech-candidates/{name}.jsonl"
        artifacts.append(artifact(f"tdtech-{name}", "jsonl-metadata", rel, sum(1 for _ in (data_root / rel).open())))
    teachers = ", ".join(recipe["tdtech"]["teachers"])
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": [recipe["language"]], "tasks": ["asr"], "artifacts": artifacts, "splits": split_decl,
        "provenance": {
            "status": "complete", "synthetic": "partial",
            "description": "普通 ASR 空白 / 非人声评测切分（参考全部为空，看误输出率）：鼎桥设备真实录音里三个说话人老师"
                           f"（{teachers}）都判为无人说话、FSMN-VAD 也未检出语音的区间（按时长分四档，原电平）；合成的近静音、底噪、"
                           "50 Hz 电流嗡声；FSD50K 评测划分的稳态噪声、突发声、咳嗽呼吸（不含人声和音乐）；0.3–1.5 秒混合短片段。"
                           f"自动质检隔离 {report['quarantined']} 条（tdtech-quarantine），未发起人工听审。只用于评测，不进训练。"
                           "配方 scripts/asr_babble_bench/recipe-blank.yaml；原 16 个背景人声切分仍在 v2-20261023。",
            "sources": ["diarization/dingqiao-diarization-quality@20261016-machine01", "diarization/dingqiao-online-issues@20261015-v1",
                        "/workspace/data/runs/tdtech-customer-v4/diar (三个老师时间线)", "fsd50k@zenodo-4060432-20261013:eval"],
            "known_risks": ["DNS5 noise 的 freesound 部分已按内容哈希改名，无法按 freesound ID 与 FSD50K 去重；DNS5 只作训练时有字语音的背景噪声",
                            "鼎桥空白只由三个说话人老师与 FSMN-VAD 自动判定，极轻的远处人声可能漏判"],
        },
    }


def cmd_render(recipe, roots, catalog_dir, workers, limit, no_register):
    data_root, partial, cuts = paths(recipe, roots)
    final = data_root / "source" / recipe["version"]
    if (data_root / "versions" / recipe["version"]).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {recipe['version']}")
    splits = [{"n": recipe["default_n"], **s} for s in recipe["splits"]]
    if limit:
        for s in splits:
            s["n"] = min(s["n"], limit)
    by_name = {s["name"]: s for s in splits}
    keep, quarantine = tdtech_pool(recipe, cuts)
    with (cuts / "quarantine.jsonl").open("w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in quarantine)
    fsd = fsd_pools(recipe, roots)
    print(f"tdtech kept {len(keep)} quarantined {len(quarantine)}", {k: len(v) for k, v in fsd.items()}, flush=True)
    G.update(recipe=recipe, cuts=cuts)
    jobs = [(split, i, plan, partial) for split in splits for i, plan in enumerate(plan_split(recipe, split, by_name, keep, fsd))]
    with ProcessPoolExecutor(workers, mp_context=FORK) as pool:
        results = list(pool.map(render_job, jobs, chunksize=8))
    counts = Counter(r["split"] for r in results)
    print(json.dumps(counts), flush=True)
    partial.rename(final)
    report = {"quarantined": len(quarantine), "kept": len(keep), "records": dict(counts)}
    declaration = register(recipe, splits, results, data_root, recipe["dataset_id"], report)
    (final / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if no_register:
        return
    path = REPO / "catalog" / f"{recipe['dataset_id']}.yaml"
    rows = list(yaml.safe_load(path.read_text()))
    if any(r["version"] == recipe["version"] for r in rows):
        raise FileExistsError(f"version already registered: {recipe['version']}")
    validate_catalog([*load_catalog(catalog_dir), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", recipe["version"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["candidates", "render"])
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe-blank.yaml")
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=REPO / "catalog")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, help="samples per split (smoke runs)")
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    roots = json.loads(args.roots.read_text())
    if args.step == "candidates":
        cmd_candidates(recipe, roots)
    else:
        cmd_render(recipe, roots, args.catalog, args.workers, args.limit, args.no_register)


if __name__ == "__main__":
    main()
