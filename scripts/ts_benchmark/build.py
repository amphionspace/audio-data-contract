#!/usr/bin/env python3
"""Build and register the target-speaker ASR benchmark (ts_asr_benchmark).

Scenes are synthesized from the test splits of registered single-speaker corpora
(speakers unseen in training) following ``recipe.yaml``. Every sample is an
``audio-record/1.0`` ``ts_asr`` record with an ``enrollment`` and a ``mixture``
slot; the reference is the concatenated text of the target utterances, or empty
when the target is absent. Each recipe version is a new immutable dataset version.

    python scripts/ts_benchmark/build.py --roots /workspace/data/registry/roots.json \
        --embeddings <speaker-embeddings.npz> --workers 16

``speaker_embeddings.py`` writes the embedding file used to pick hard negatives.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import itertools
import json
import math
import random
import re
import shutil
import sys
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mixer

from audio_data_contract import AudioRecord, load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

REPO = Path(__file__).resolve().parents[2]
SR = mixer.SAMPLE_RATE
GENERATOR_VERSION = "1"
ATTEMPTS = 40
G = {}  # worker-global state, set before the pool forks


# --- recipe ----------------------------------------------------------------


def expand_splits(recipe):
    """Flat list of {name, group, n, params} from the recipe's split entries."""
    out = []
    for entry in recipe["splits"]:
        entry = dict(entry)
        group = entry.pop("group")
        n = entry.pop("n", recipe.get("default_n", 100))
        if "expand" in entry:
            spec, base = entry["expand"], entry["base"]
            names = list(spec["over"])
            for values in itertools.product(*(spec["over"][k] for k in names)):
                bound = dict(zip(names, values))
                if "cond_params" in spec:  # the condition sets arbitrary parameters, not only the enrollment
                    params = {**base[bound["kind"]], **spec["cond_params"][bound["cond"]],
                              "pair": f"{group}-{bound['kind']}"}
                else:
                    params = {**base[bound["kind"]], "enroll": bound["cond"], "pair": f"{group}-{bound['kind']}"}
                out.append({"name": spec["template"].format(**bound), "group": group, "n": n,
                            "params": params})
        else:
            name = entry.pop("name")
            out.append({"name": name, "group": group, "n": entry.pop("n", n), "params": entry})
    if len({s["name"] for s in out}) != len(out):
        raise ValueError("duplicate split names in the recipe")
    if recipe.get("noise_floor"):
        for split in out:
            split["params"].setdefault("noise_floor", recipe["noise_floor"])
    return out


# --- audio -------------------------------------------------------------------


def read_audio(path):
    w, sr = sf.read(path, dtype="float32", always_2d=False)
    if w.ndim > 1:
        w = w.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly

        g = math.gcd(sr, SR)
        w = resample_poly(w, SR // g, sr // g).astype(np.float32)
    return w


def write_wav(path, w):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.clip(w, -1.0, 1.0), SR, subtype="PCM_16")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- pools -------------------------------------------------------------------


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def load_source(source, catalog, roots, rng):
    """{speaker: [Utt]} of one registered single-speaker split."""
    paths = {}
    for role in ("recordings", "supervisions"):
        found = resolve_split(catalog, source["dataset"], source["version"], source["split"], role, roots)
        if len(found) != 1:
            raise ValueError(f"{source['dataset']}: expected one {role} file")
        paths[role] = found[0]
    audio = {r["id"]: r["sources"][0]["source"] for r in _rows(paths["recordings"])}
    by_speaker = defaultdict(list)
    for row in _rows(paths["supervisions"]):
        text = re.sub(r"\s+", "", row.get("text") or "")
        if not text or row.get("start", 0) != 0 or row["recording_id"] not in audio:
            continue
        speaker = f"{source['dataset']}:{row['speaker']}"
        by_speaker[speaker].append(mixer.Utt(
            id=f"{source['dataset']}:{row['id']}", speaker=speaker, text=text,
            duration=float(row["duration"]), path=audio[row["recording_id"]],
            corpus=source["dataset"], gender=row.get("gender")))
    keep = sorted(by_speaker)
    if source.get("max_speakers"):
        keep = sorted(rng.sample(keep, min(source["max_speakers"], len(keep))))
    return {s: by_speaker[s] for s in keep}


def build_pools(recipe, catalog, roots):
    rng = random.Random(f"{recipe['seed']}:pools")
    lo, hi = recipe["utterance_seconds"]
    short_lo, short_hi = recipe["short_utterance_seconds"]
    pools, raw = {}, {}
    for name, spec in recipe["pools"].items():
        if "union" in spec:
            continue
        speakers = {}
        for source in spec["sources"]:
            speakers.update(load_source(source, catalog, roots, rng))
        raw[name] = speakers
    for name, spec in recipe["pools"].items():
        if "union" in spec:
            raw[name] = {s: u for member in spec["union"] for s, u in raw[member].items()}
    for name, speakers in raw.items():
        normal, short = {}, {}
        for speaker, utts in speakers.items():
            fits = [u for u in utts if lo <= u.duration <= hi]
            if len(fits) >= recipe["min_utterances_per_speaker"] and any(
                    u.duration >= mixer.ENROLL_SECONDS + 0.5 for u in fits):
                normal[speaker] = fits
                quick = [u for u in utts if short_lo <= u.duration <= short_hi]
                if len(quick) >= 2:
                    short[speaker] = quick
        pools[name] = {"speakers": normal, "short": short}
    return pools


def noise_files(spec, catalog, roots):
    (path,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "recordings", roots)
    return [r["sources"][0]["source"] for r in _rows(path) if r.get("duration", 0) >= 3.0]


def enrollment_files(recipe, roots):
    """Recorded registrations (business feedback) usable as the enrollment of an absent target."""
    out = {}
    for name, spec in (recipe.get("enrollment_files") or {}).items():
        path = Path(roots[spec["alias"]]) / spec["path"]
        if not path.is_file():
            raise FileNotFoundError(f"enrollment file {name}: {path}")
        out[name] = str(path)
    return out


def prepared_noise(directory):
    """Pools of the clips ``prepare_noise.py`` wrote: all clips and the steady ones, plus RIR pools."""
    manifest = json.loads((directory / "manifest.json").read_text())
    noise, rirs = defaultdict(list), defaultdict(list)
    for entry in manifest:
        path = str(directory / entry["path"])
        if entry["path"].startswith("rir/"):
            rirs[entry["pool"]].append(path)
        else:
            noise[entry["pool"]].append(path)
            if entry["stationary"]:
                noise[entry["pool"] + "_stationary"].append(path)
    return {k: sorted(v) for k, v in noise.items()}, {k: sorted(v) for k, v in rirs.items()}


def prepare_rirs(recipe, directory):
    """Stream a deterministic sample of room impulse responses out of the DNS5 archive."""
    directory.mkdir(parents=True, exist_ok=True)
    wanted = recipe["rir"]["count"]
    seen = []
    with tarfile.open(recipe["rir"]["archive"], "r|bz2") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith(".wav"):
                continue
            key = int(hashlib.sha256(member.name.encode()).hexdigest(), 16)
            seen.append((key, member.name, archive.extractfile(member).read()))
    seen.sort()
    paths = []
    for _, name, data in seen[:wanted]:
        w, sr = sf.read(io.BytesIO(data), dtype="float32")
        if w.ndim > 1:
            w = w[:, 0]
        if sr != SR:
            from scipy.signal import resample_poly

            g = math.gcd(sr, SR)
            w = resample_poly(w, SR // g, sr // g).astype(np.float32)
        target = directory / (hashlib.sha256(name.encode()).hexdigest()[:16] + ".wav")
        sf.write(target, w, SR, subtype="FLOAT")
        paths.append(str(target))
    return sorted(paths)


# --- sample construction ------------------------------------------------------


def _label_text(items):
    return "".join(u.text for u, _ in sorted(items, key=lambda x: x[1]))


def _utt_json(utt, start):
    return {"id": utt.id, "start": round(start, 3), "duration": round(utt.duration, 3), "text": utt.text}


def describe(plan, split, index):
    params = plan["params"]
    target = next((t for t in plan["tracks"] if t.role == "target"), None)
    interferers = [t for t in plan["tracks"] if t.role == "interferer"]
    kind = plan["kind"]
    labels = {
        "scenario": split["name"], "group": split["group"], "kind": kind,
        "target_present": kind == "pos", "enroll_condition": params.get("enroll", "clean"),
        "duration_s": plan["total"], "n_interferers": len(interferers),
    }
    for key in ("schedule", "hard", "pair"):
        if key in params:
            labels[key] = params[key]
    if plan.get("noise"):
        labels["noise"] = plan["noise"]["kind"]
        if "snr_db" in plan["noise"]:
            labels["snr_db"] = plan["noise"]["snr_db"]
    if params.get("rir"):
        labels["reverb"] = True
    if "target_overlap_ratio" in plan:
        labels["target_overlap_ratio"] = plan["target_overlap_ratio"]
    if plan.get("floor"):
        floor = plan["floor"]["mix"]
        labels["noise_floor_dbfs"] = floor["dbfs"]
        labels["noise_floor_kind"] = floor.get("pool", floor["kind"])
        if "file" in floor:
            labels["noise_floor_clip"] = Path(floor["file"]).stem
    if "rir_pool" in plan:
        labels["rir_pool"] = plan["rir_pool"]
    if "mix_gain_db" in plan:
        labels["mix_gain_db"] = plan["mix_gain_db"]
    if params.get("mix_effect"):
        labels["mix_effect"] = params["mix_effect"]
    if "enroll_file" in plan:
        labels["enroll_file"] = plan["enroll_file"]["id"]
    if "target_gap" in plan:
        labels["target_gap_s"] = plan["target_gap"]
    if "interferer_gap" in plan:
        labels["interferer_gap_s"] = plan["interferer_gap"]
    if interferers:
        labels["interferer_gain_db"] = round(float(np.mean([t.gain_db for t in interferers])), 2)
    if "hard_cosine" in plan:
        labels["hard_cosine"] = plan["hard_cosine"]
    metadata = {
        "generator": GENERATOR_VERSION, "seed": G["recipe"]["seed"], "split": split["name"], "index": index,
        "enrollment_utt": _utt_json(plan["enroll_utt"], 0.0),
        "target_speaker": plan.get("target_speaker") or plan.get("enroll_speaker"),
        "target_utts": [_utt_json(u, s) for u, s in sorted(target.items, key=lambda x: x[1])] if target else [],
        "interferers": [{"speaker": t.speaker, "gain_db": round(t.gain_db, 2),
                         "utts": [_utt_json(u, s) for u, s in t.items]} for t in interferers],
    }
    if plan.get("hard_anchor"):
        metadata["hard_anchor"] = plan["hard_anchor"]
    return labels, metadata


def plan_split(recipe, split, pools, similarity):
    plans = []
    for index in range(split["n"]):
        for attempt in range(ATTEMPTS):
            # Splits that share a pair key draw the same scene, so their differences are paired.
            rng = random.Random(f"{recipe['seed']}:{split['params'].get('pair', split['name'])}:{index}:{attempt}")
            try:
                plans.append(mixer.plan_scene(rng, split["params"], pools, similarity))
                break
            except mixer.PlanError:
                continue
        else:
            raise RuntimeError(f"could not plan {split['name']}[{index}]")
    return plans


def _cached(loader, size=64):
    cache = {}

    def get(key):
        if key not in cache:
            if len(cache) >= size:
                cache.pop(next(iter(cache)))
            cache[key] = loader(key)
        return cache[key]

    return get


def render_job(job):
    split, index, plan, out = job
    name = split["name"]
    load = _cached(lambda utt: read_audio(utt.path))
    load_rir = _cached(lambda path: sf.read(path, dtype="float32")[0])

    def noise_loader(kind, path):
        if kind == "quiet":
            return np.random.default_rng(0).standard_normal(SR * 30).astype(np.float32)
        return _cached_noise(path)

    mix = mixer.render_mixture(plan, load, load_rir, noise_loader)
    enroll = mixer.render_enrollment(plan, load, load_rir, noise_loader)
    base = f"{name}-{index:04d}"
    entries = []
    for suffix, w in (("mix", mix), ("enroll", enroll)):
        relative = f"audio/{name}/{base}-{suffix}.wav"
        path = out / relative
        write_wav(path, w)
        entries.append({"cut_id": f"{base}-{suffix}", "relative_path": relative,
                        "num_frames": len(w), "duration": round(len(w) / SR, 4),
                        "sha256": sha256_file(path)})
    labels, metadata = describe(plan, split, index)
    target = next((t for t in plan["tracks"] if t.role == "target"), None)
    text = _label_text(target.items) if target else ""
    return {"split": name, "index": index, "target": text, "labels": labels,
            "metadata": metadata, "entries": entries}


_NOISE = {}


def _cached_noise(path):
    if path not in _NOISE:
        if len(_NOISE) >= 16:
            _NOISE.pop(next(iter(_NOISE)))
        _NOISE[path] = read_audio(path)
    return _NOISE[path]


# --- registration --------------------------------------------------------------


def write_jsonl_gz(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def register(recipe, splits, results, data_root, alias):
    version, dataset_id = recipe["version"], recipe["dataset_id"]
    by_split = defaultdict(list)
    for r in results:
        by_split[r["split"]].append(r)
    index_rows, records_by_split = [], {}
    for split in splits:
        rows = sorted(by_split[split["name"]], key=lambda r: r["index"])
        records = []
        for r in rows:
            mix, enroll = r["entries"]
            for entry in r["entries"]:
                index_rows.append({**entry, "root_alias": alias, "sample_rate": SR, "channels": 1,
                                   "relative_path": f"source/{version}/{entry['relative_path']}"})
            def ref(e, split_name=split["name"]):
                return {"dataset_id": dataset_id, "version": version, "split": split_name,
                        "cut_id": e["cut_id"], "duration": e["duration"]}

            records.append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{split['name']}:{r['index']:04d}",
                "task": "ts_asr",
                "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": ref(enroll)},
                                {"name": "mixture", "purpose": "mixture", "ref": ref(mix)}],
                "target": r["target"], "language": "zh", "labels": r["labels"], "metadata": r["metadata"],
            }).to_dict())
        records_by_split[split["name"]] = records
        write_jsonl_gz(data_root / "versions" / version / "records" / f"{split['name']}.jsonl.gz", records)
    if len({e["cut_id"] for e in index_rows}) != len(index_rows):
        raise ValueError("duplicate cut ids: two samples would share one audio index entry")
    write_jsonl_gz(data_root / "versions" / version / "audio-index.jsonl.gz",
                   sorted(index_rows, key=lambda e: e["cut_id"]))

    def relative(*parts):
        return "/".join(("versions", version, *parts))

    artifacts = [{"name": "audio-index", "kind": "audio-index", "root_alias": alias,
                  "relative_path": relative("audio-index.jsonl.gz"),
                  "sha256": sha256_file(data_root / relative("audio-index.jsonl.gz")),
                  "metadata": {"record_count": len(index_rows)}}]
    split_decl = {}
    for split in splits:
        name = split["name"]
        path = relative("records", f"{name}.jsonl.gz")
        artifacts.append({"name": f"{name}-records", "kind": "audio-records", "root_alias": alias,
                          "relative_path": path, "sha256": sha256_file(data_root / path),
                          "metadata": {"record_count": len(records_by_split[name])}})
        seconds = sum(r["audio_slots"][1]["ref"]["duration"] for r in records_by_split[name])
        split_decl[name] = {"artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]},
                            "task": "ts_asr",
                            "statistics": {"records": len(records_by_split[name]),
                                           "duration_hours": round(seconds / 3600, 4),
                                           "duration_basis": "Mixture duration"},
                            "provenance": {"description": f"{split['group']}: {json.dumps(split['params'], ensure_ascii=False)}"}}
    return {
        "schema_version": "dataset-catalog/2.0", "dataset_id": dataset_id, "version": version,
        "languages": ["zh"], "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl,
        "provenance": {
            "status": "complete", "synthetic": "full",
            "description": "目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test "
                           "划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。"
                           "场景见 scripts/ts_benchmark/recipe.yaml。",
            "sources": [f"{s['dataset']}@{s['version']}:{s['split']}" for p in recipe["pools"].values()
                        for s in p.get("sources", [])],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", type=Path, default=Path(__file__).with_name("recipe.yaml"))
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--embeddings", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, help="samples per split (smoke runs)")
    parser.add_argument("--only", help="regex on split names")
    parser.add_argument("--noise-cache", type=Path, help="output of prepare_noise.py (real noise and RIR pools)")
    parser.add_argument("--rir-cache", type=Path, help="reuse (or fill) extracted room impulse responses")
    parser.add_argument("--no-register", action="store_true", help="write audio and records but not the catalog")
    args = parser.parse_args()

    recipe = yaml.safe_load(args.recipe.read_text())
    roots = json.loads(args.roots.read_text())
    alias = recipe["dataset_id"]
    data_root = Path(roots[alias])
    version = recipe["version"]
    final = data_root / "source" / version
    if (data_root / "versions" / version).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {version}")
    splits = expand_splits(recipe)
    if args.only:
        splits = [s for s in splits if re.search(args.only, s["name"])]
    if args.limit:
        for s in splits:
            s["n"] = min(s["n"], args.limit)

    catalog = load_catalog(args.catalog)
    pools = build_pools(recipe, catalog, roots)
    pools["__enroll_files__"] = enrollment_files(recipe, roots)
    pools["__noise__"] = {kind: noise_files(spec, catalog, roots) for kind, spec in recipe["noise"].items()}
    partial = data_root / "source" / (version + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    noise_dir = partial / "noise"
    if not (args.noise_cache and (args.noise_cache / "manifest.json").is_file()):
        parser.error("--noise-cache must hold the output of prepare_noise.py")
    shutil.copytree(args.noise_cache, noise_dir)
    extra_noise, rir_pools = prepared_noise(noise_dir)
    pools["__noise__"].update(extra_noise)
    pools["__rir_pools__"] = rir_pools
    if args.rir_cache and any(args.rir_cache.glob("*.wav")):
        shutil.copytree(args.rir_cache, partial / "rir")
        pools["__rirs__"] = sorted(str(p) for p in (partial / "rir").glob("*.wav"))
    else:
        pools["__rirs__"] = prepare_rirs(recipe, partial / "rir")
        if args.rir_cache:
            shutil.copytree(partial / "rir", args.rir_cache, dirs_exist_ok=True)
    similarity = None
    if args.embeddings:
        data = np.load(args.embeddings, allow_pickle=False)
        vectors = dict(zip(data["keys"].tolist(), data["vectors"]))
        similarity = lambda a, b: float(vectors[a] @ vectors[b])
    elif any(s["params"].get("hard") for s in splits):
        parser.error("the recipe has hard-negative splits; pass --embeddings")

    pools["__rir_pools__"]["dns5_sim"] = list(pools["__rirs__"])
    pools["__rirs__"] = sorted(p for v in pools["__rir_pools__"].values() for p in v)
    if args.embeddings:
        shutil.copy(args.embeddings, partial / "speaker-embeddings.npz")
    G.update(recipe=recipe, pools=pools)
    jobs = []
    for split in splits:
        plans = plan_split(recipe, split, pools, similarity)
        jobs.extend((split, i, p, partial) for i, p in enumerate(plans))
    print(f"{len(splits)} splits, {len(jobs)} samples", flush=True)
    with ProcessPoolExecutor(args.workers) as pool:
        results = []
        for done, result in enumerate(pool.map(render_job, jobs, chunksize=8), 1):
            results.append(result)
            if done % 500 == 0:
                print(f"rendered {done}/{len(jobs)}", flush=True)
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
    print(json.dumps(Counter(s["group"] for s in splits)), "registered", version)


if __name__ == "__main__":
    main()
