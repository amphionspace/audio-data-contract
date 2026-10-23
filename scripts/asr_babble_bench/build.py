#!/usr/bin/env python3
"""Build and register the plain-ASR babble benchmark (asr_babble_bench).

The 10.21 AmphionASR release outputs unrelated text on segments that hold only
background babble. Every sample is an ``audio-record/1.0`` ``asr`` record with a
single ``primary`` slot, following ``recipe.yaml``:

* ``noise`` splits hold only babble (synthetic or recorded crowds); the
  reference is empty, so the evaluator reports the false-output rate;
* ``speech`` splits hold one test-split utterance with 1-5 s of babble before
  and after it, babble also under it at a fixed SNR; a ``-tight`` split is the
  same audio without the padding, so the difference is what the babble-only
  seconds cost.

Synthetic babble is mixed from test/dev speakers that are in no training set and
not among the target speakers, each reverberated at its own position in one
simulated room (``source/<version>/babble``, with a manifest of every talker's
utterances, times and room response). Splits that share a ``pair`` draw the same
utterance, padding and babble window, so their results compare record by record.

    python scripts/asr_babble_bench/build.py --roots /workspace/data/registry/roots.json --workers 16
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing
import random
import re
import shutil
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

# The target-speaker benchmark's helpers (audio I/O, FSD50K selection, registration I/O), loaded under
# another name so this script's own module name does not shadow it.
_spec = importlib.util.spec_from_file_location("ts_build", REPO / "scripts" / "ts_benchmark" / "build.py")
ts_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts_build)

from audio_data_contract import AudioRecord, load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

SR = mixer.SAMPLE_RATE
GENERATOR_VERSION = "2"
TEXT = {"zh": re.compile(r"^[一-鿿]+$"), "en": re.compile(r"^[a-z']+( [a-z']+)*$")}
G = {}  # worker-global state, set before the pool forks
FORK = multiprocessing.get_context("fork")  # Python 3.14 defaults to forkserver, which would not see G


# --- sources -------------------------------------------------------------------


def load_utterances(source, language, catalog, roots):
    """{speaker: [Utt]} of a registered split; text keeps English word spaces and must be plain words."""
    paths = {role: resolve_split(catalog, source["dataset"], source["version"], source["split"], role, roots)
             for role in ("recordings", "supervisions")}
    audio = {r["id"]: r["sources"][0]["source"] for path in paths["recordings"] for r in ts_build._rows(path)}
    by_speaker = defaultdict(list)
    for row in (row for path in paths["supervisions"] for row in ts_build._rows(path)):
        text = " ".join((row.get("text") or "").split())
        text = text.replace(" ", "") if language == "zh" else text.lower()
        if not TEXT[language].match(text) or row.get("start", 0) != 0 or row["recording_id"] not in audio:
            continue
        speaker = f"{source['dataset']}:{row['speaker']}"
        by_speaker[speaker].append(mixer.Utt(
            id=f"{source['dataset']}:{row['id']}", speaker=speaker, text=text, duration=float(row["duration"]),
            path=audio[row["recording_id"]], corpus=source["dataset"]))
    return dict(by_speaker)


def build_sources(recipe, catalog, roots):
    targets, talkers = {}, {}
    for language, spec in recipe["targets"].items():
        lo, hi = spec["seconds"]
        utts = [u for source in spec["sources"]
                for us in load_utterances(source, language, catalog, roots).values() for u in us]
        targets[language] = sorted((u for u in utts if lo <= u.duration <= hi), key=lambda u: u.id)
    for language, spec in recipe["babble"].items():
        speakers = {}
        for source in spec["sources"]:
            speakers.update(load_utterances(source, language, catalog, roots))
        talkers[language] = {s: u for s, u in sorted(speakers.items()) if len(u) >= recipe["babble_min_utterances"]}
        overlap = {u.speaker for u in targets.get(language, [])} & set(talkers[language])
        if overlap:
            raise ValueError(f"babble talkers are also target speakers: {sorted(overlap)[:5]}")
    return targets, talkers


def babble_rooms(recipe, catalog, roots):
    """{room: [room response path]}; each simulated room has one receiver and a response per talker position."""
    spec = recipe["babble_rir"]
    rooms = defaultdict(list)
    for path in resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "recordings", roots):
        for row in ts_build._rows(path):
            source = Path(row["sources"][0]["source"])
            if source.parts[-3] in spec["rooms"]:
                rooms[f"{source.parts[-3]}/{source.parts[-2]}"].append(str(source))
    return {room: sorted(paths) for room, paths in sorted(rooms.items())}


def real_noise_files(recipe, roots):
    out = {}
    for name, spec in recipe["real_noise"].items():
        files = ts_build.fsd_files(spec, roots) if "fsd" in spec else sorted(
            str(p) for p in Path(roots[spec["alias"]]).glob(spec["glob"]))
        out[name] = [(f, sf.info(f).duration) for f in files]
    return out


# --- babble bank ------------------------------------------------------------------


def render_babble(job):
    """One babble clip: ``n`` talkers in one room, each a continuous stream of their utterances, cropped at random."""
    language, index, out = job
    recipe, pool = G["recipe"], G["talkers"][language]
    rng = random.Random(f"{recipe['seed']}:babble:{language}:{index}")
    length = int(recipe["babble_clip_seconds"] * SR)
    speakers = rng.sample(sorted(pool), rng.randint(*recipe["babble_talkers"]))
    room = rng.choice(sorted(G["rooms"]))
    rirs = rng.sample(G["rooms"][room], len(speakers))  # one receiver, every talker at another position
    mix = np.zeros(length, dtype=np.float64)
    talkers = []
    for speaker, rir in zip(speakers, rirs):
        chunks, placed, total = [], [], 0
        while total < length + SR:
            utt = rng.choice(pool[speaker])
            gap = int(rng.uniform(*recipe["babble_gap_seconds"]) * SR)
            w = ts_build.read_audio(utt.path)
            placed.append((utt, total + gap, len(w)))
            chunks += [np.zeros(gap, dtype=np.float32), w]
            total += gap + len(w)
        track = np.concatenate(chunks)
        track = mixer.apply_rir(track, ts_build.read_audio(rir))[:len(track)]
        start = rng.randint(0, len(track) - length)
        track = track[start:start + length]
        gain_db = rng.uniform(*recipe["babble_gain_db"])
        mix += track / mixer.rms(track) * 10.0 ** (gain_db / 20.0)
        talkers.append({"speaker": speaker, "gain_db": round(gain_db, 2), "rir": Path(rir).stem, "utts": [
            {"id": u.id, "start": round((begin - start) / SR, 3), "duration": round(n / SR, 3), "text": u.text}
            for u, begin, n in placed if begin + n > start and begin < start + length]})
    mix = mixer.normalize_rms(mix.astype(np.float32), recipe["speech_dbfs"])
    clip_id = f"babble-{language}-{index:04d}"
    relative = f"babble/{language}/{clip_id}.flac"
    (out / relative).parent.mkdir(parents=True, exist_ok=True)
    sf.write(out / relative, np.clip(mix, -1.0, 1.0), SR, format="FLAC", subtype="PCM_16")
    return {"id": clip_id, "path": relative, "language": language, "duration": recipe["babble_clip_seconds"],
            "num_talkers": len(talkers), "rms_dbfs": recipe["speech_dbfs"], "room": room, "talkers": talkers}


# --- planning ----------------------------------------------------------------------


def plan_split(recipe, split, targets, bank, real):
    """Per-sample plans; draws that splits of one pair share come from the pair's stream, in a fixed order."""
    seed, pair, n = recipe["seed"], split.get("pair", split["name"]), split["n"]
    kind = split["noise"].split("_")[0] if "noise" in split else None
    plans = []
    if split["kind"] == "speech":
        chosen = random.Random(f"{seed}:{pair}:targets").sample(targets[split["language"]], n)
    for index in range(n):
        rng = random.Random(f"{seed}:{pair}:{index}")
        floor = {"kind": rng.choice(recipe["noise_floor"]["kinds"]),
                 "dbfs": round(rng.uniform(*recipe["noise_floor"]["dbfs"]), 2), "seed": rng.getrandbits(32)}
        plan = {"floor": floor}
        if split["kind"] == "speech":
            lead, trail = (rng.uniform(*recipe["padding_seconds"]) for _ in range(2))
            clip = rng.randrange(len(bank[split["language"]]))
            # 0.5 s margin: the audio can run slightly past the supervision duration
            slack = recipe["babble_clip_seconds"] - (lead + chosen[index].duration + trail) - 0.5
            offset = rng.uniform(0.0, max(slack, 0.0))
            if split.get("tight"):  # same audio without the padding: the babble under the speech is unchanged
                offset, lead, trail = offset + lead, 0.0, 0.0
            plan.update(utt=chosen[index], lead=round(lead, 3), trail=round(trail, 3))
            if kind == "babble":
                plan["noise"] = {"kind": split["noise"], "clip": bank[split["language"]][clip]["id"],
                                 "offset_s": round(offset, 3), "snr_db": split["snr_db"]}
        else:
            duration = rng.uniform(*split["duration"])
            if kind == "babble":
                language = split["noise"].split("_")[1]
                clip, length = bank[language][rng.randrange(len(bank[language]))]["id"], recipe["babble_clip_seconds"]
            else:
                clip, length = rng.choice(real[split["noise"]])
            duration = min(duration, length)
            plan.update(duration=round(duration, 3), noise={
                "kind": split["noise"], "clip": clip, "offset_s": round(rng.uniform(0.0, length - duration), 3),
                "level_dbfs": round(random.Random(f"{seed}:{split['name']}:{index}:level").uniform(
                    *split["level_dbfs"]), 2)})
        plans.append(plan)
    return plans


# --- rendering ---------------------------------------------------------------------


def noise_path(spec):
    if spec["kind"].startswith("babble_"):
        return str(G["bank_dir"] / G["bank_paths"][spec["clip"]])
    return spec["clip"]


def render_job(job):
    split, index, plan, out = job
    recipe = G["recipe"]
    level = recipe["speech_dbfs"]
    spec = plan.get("noise")
    noise = ts_build.read_audio(noise_path(spec)) if spec else None
    if "utt" in plan:
        speech = mixer.normalize_rms(ts_build.read_audio(plan["utt"].path), level)
        begin = int(plan["lead"] * SR)
        w = np.zeros(begin + len(speech) + int(plan["trail"] * SR), dtype=np.float32)
        w[begin:begin + len(speech)] = speech
        if spec:
            segment = noise[int(spec["offset_s"] * SR):][:len(w)]
            if len(segment) < len(w):
                raise ValueError(f"{split['name']}[{index}]: babble window runs past the clip")
            under = segment[begin:begin + len(speech)]  # SNR is measured where the speech is
            w = w + segment * (10.0 ** ((level - spec["snr_db"]) / 20.0) / mixer.rms(under))
    else:
        start = int(spec["offset_s"] * SR)
        segment = noise[start:start + int(plan["duration"] * SR)]
        w = mixer.normalize_rms(segment.astype(np.float32), spec["level_dbfs"])
    w = (w + mixer.floor_noise(len(w), plan["floor"])).astype(np.float32)
    peak = float(np.abs(w).max())
    scale_db = 0.0
    if peak > 0.99:  # keep the relative levels, avoid clipping
        scale_db = 20.0 * np.log10(0.99 / peak)
        w = w * (0.99 / peak)
    name = split["name"]
    relative = f"audio/{name}/{name}-{index:04d}.wav"
    ts_build.write_wav(out / relative, w)
    entry = {"cut_id": f"{name}-{index:04d}", "relative_path": relative, "num_frames": len(w),
             "duration": round(len(w) / SR, 4), "sha256": ts_build.sha256_file(out / relative)}
    labels = {"scenario": name, "kind": split["kind"], "pair": split.get("pair", name),
              "duration_s": entry["duration"], "noise_floor_dbfs": plan["floor"]["dbfs"],
              "noise_floor_kind": plan["floor"]["kind"]}
    metadata = {"generator": GENERATOR_VERSION, "seed": recipe["seed"], "split": name, "index": index}
    if spec:
        labels["noise"] = spec["kind"]
        metadata["noise"] = {"kind": spec["kind"], "clip": spec["clip"], "offset_s": spec["offset_s"]}
        if spec["kind"].startswith("babble_"):
            labels["num_talkers"] = G["bank_talkers"][spec["clip"]]
        else:
            metadata["noise"]["clip"] = str(Path(spec["clip"]).relative_to(G["roots"]["open_noise"]))
    if "utt" in plan:
        utt = plan["utt"]
        labels.update(speech_start_s=plan["lead"], speech_end_s=round(plan["lead"] + len(speech) / SR, 3),
                      lead_s=plan["lead"], trail_s=plan["trail"])
        if spec:
            labels["snr_db"] = spec["snr_db"]
        metadata["utterance"] = {"id": utt.id, "speaker": utt.speaker, "duration": round(utt.duration, 3),
                                 "text": utt.text}
    else:
        labels["level_dbfs"] = spec["level_dbfs"]
    if scale_db:
        labels["peak_scale_db"] = round(scale_db, 2)
    return {"split": name, "index": index, "target": plan["utt"].text if "utt" in plan else "",
            "language": split.get("language") or (spec["kind"].split("_")[1] if spec["kind"].startswith("babble_")
                                                   else "en"),
            "labels": labels, "metadata": metadata, "entry": entry}


# --- registration ------------------------------------------------------------------


def register(recipe, splits, results, data_root, alias):
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    by_split = defaultdict(list)
    for r in results:
        by_split[r["split"]].append(r)
    index_rows, records_by_split = [], {}
    for split in splits:
        records = []
        for r in sorted(by_split[split["name"]], key=lambda r: r["index"]):
            entry = r["entry"]
            index_rows.append({**entry, "root_alias": alias, "sample_rate": SR, "channels": 1,
                               "relative_path": f"source/{version}/{entry['relative_path']}"})
            records.append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{split['name']}:{r['index']:04d}", "task": "asr",
                "audio_slots": [{"name": "primary", "purpose": "primary", "ref": {
                    "dataset_id": dataset_id, "version": version, "split": split["name"],
                    "cut_id": entry["cut_id"], "duration": entry["duration"]}}],
                "target": r["target"], "language": r["language"], "labels": r["labels"], "metadata": r["metadata"],
            }).to_dict())
        records_by_split[split["name"]] = records
        ts_build.write_jsonl_gz(data_root / "versions" / version / "records" / f"{split['name']}.jsonl.gz", records)
    if len({e["cut_id"] for e in index_rows}) != len(index_rows):
        raise ValueError("duplicate cut ids: two samples would share one audio index entry")
    ts_build.write_jsonl_gz(data_root / "versions" / version / "audio-index.jsonl.gz",
                            sorted(index_rows, key=lambda e: e["cut_id"]))

    def artifact(name, kind, path, count):
        return {"name": name, "kind": kind, "root_alias": alias, "relative_path": path,
                "sha256": ts_build.sha256_file(data_root / path), "metadata": {"record_count": count}}

    bank = f"source/{version}/babble/manifest.jsonl"
    artifacts = [artifact("audio-index", "audio-index", f"versions/{version}/audio-index.jsonl.gz", len(index_rows)),
                 artifact("babble-manifest", "jsonl-metadata", bank, sum(1 for _ in (data_root / bank).open()))]
    split_decl = {}
    for split in splits:
        name, records = split["name"], records_by_split[split["name"]]
        artifacts.append(artifact(f"{name}-records", "audio-records", f"versions/{version}/records/{name}.jsonl.gz",
                                  len(records)))
        params = {k: v for k, v in split.items() if k not in ("name", "n", "display", "description")}
        split_decl[name] = {
            "artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
            "task": "asr",
            "statistics": {"records": len(records),
                           "duration_hours": round(sum(r["audio_slots"][0]["ref"]["duration"] for r in records) / 3600, 4),
                           "duration_basis": "clip duration"},
            "provenance": {"description": f"{split['display']}：{split['description']}。参数 "
                                          f"{json.dumps(params, ensure_ascii=False)}"},
        }
    sources = [f"{s['dataset']}@{s['version']}:{s['split']}" for part in ("targets", "babble")
               for spec in recipe[part].values() for s in spec["sources"]]
    rir = recipe["babble_rir"]
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": sorted(recipe["targets"]), "tasks": ["asr"], "artifacts": artifacts, "splits": split_decl,
        "provenance": {
            "status": "complete", "synthetic": "full",
            "description": "普通 ASR 背景人声评测集：只有背景人声的片段（合成的中文、英文背景人声和真实录音的人群声，期望输出为空），"
                           "以及一句话前后和说话时都有背景人声的片段（与无背景人声的对照逐条配对）。合成背景人声由不进训练、"
                           "也不与目标语音重叠的 test/dev 说话人在模拟房间里混成。只用于评测，不进训练。配方 scripts/asr_babble_bench/recipe.yaml。",
            "sources": [*sources, f"{rir['dataset']}@{rir['version']}:{rir['split']}",
                        "wham_noise@official-20261013:tt", "fsd50k@zenodo-4060432-20261013:eval"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=HERE / "recipe.yaml")
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, help="samples per split (smoke runs)")
    parser.add_argument("--no-register", action="store_true", help="write audio and records but not the catalog")
    args = parser.parse_args()

    recipe = yaml.safe_load(args.recipe.read_text())
    roots = json.loads(args.roots.read_text())
    alias, version = recipe["dataset_id"], recipe["version"]
    data_root = Path(roots[alias])
    final = data_root / "source" / version
    if (data_root / "versions" / version).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {version}")
    splits = [{"n": recipe["default_n"], **s} for s in recipe["splits"]]
    if len({s["name"] for s in splits}) != len(splits):
        raise ValueError("duplicate split names in the recipe")
    if args.limit:
        for s in splits:
            s["n"] = min(s["n"], args.limit)

    catalog = load_catalog(args.catalog)
    targets, talkers = build_sources(recipe, catalog, roots)
    rooms = babble_rooms(recipe, catalog, roots)
    real = real_noise_files(recipe, roots)
    print({k: len(v) for k, v in targets.items()}, {k: len(v) for k, v in talkers.items()},
          {k: len(v) for k, v in real.items()}, f"{len(rooms)} rooms", flush=True)
    partial = data_root / "source" / (version + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    G.update(recipe=recipe, talkers=talkers, rooms=rooms, roots=roots, bank_dir=partial)
    jobs = [(language, i, partial) for language, spec in recipe["babble"].items() for i in range(spec["clips"])]
    with ProcessPoolExecutor(args.workers, mp_context=FORK) as pool:
        manifest = list(pool.map(render_babble, jobs, chunksize=4))
    with (partial / "babble" / "manifest.jsonl").open("w", encoding="utf-8") as stream:
        stream.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest)
    bank = defaultdict(list)
    for row in manifest:
        bank[row["language"]].append(row)
    G.update(bank_paths={r["id"]: r["path"] for r in manifest}, bank_talkers={r["id"]: r["num_talkers"] for r in manifest})

    jobs = [(split, i, plan, partial) for split in splits
            for i, plan in enumerate(plan_split(recipe, split, targets, bank, real))]
    print(f"{len(splits)} splits, {len(jobs)} samples", flush=True)
    with ProcessPoolExecutor(args.workers, mp_context=FORK) as pool:
        results = list(pool.map(render_job, jobs, chunksize=8))
    partial.rename(final)
    declaration = register(recipe, splits, results, data_root, alias)
    if args.no_register:
        return
    path = REPO / "catalog" / f"{recipe['dataset_id']}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    if any(r["version"] == version for r in rows):
        raise FileExistsError(f"version already registered: {version}")
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512),
                    encoding="utf-8")
    print(json.dumps(Counter(s["kind"] for s in splits)), "registered", version)


if __name__ == "__main__":
    main()
