#!/usr/bin/env python3
"""Which MagicData-RAMC speaker IDs sound like one person: input to ``build_ts_scene_pool.py --ramc --same-voice``.

RAMC gives every speaker of a new conversation a new ID, so one person can sit under several IDs: 2026-10-28, with the
ERes2NetV2 embedding of ``speaker_neighbors.py`` averaged per (speaker, recording) over up to 6 clean-pass utterances of
2-8 s, the 24 pairs of one ID in two recordings (one person) scored 0.72-0.93 (median 0.87), while half of the
(speaker, recording) units had a different ID in another recording at 0.80 or more, often both partners of one
conversation matching both partners of another. A scene pool that takes such a pair for target and "other speaker"
(or near-voice twin enrollment, which picks exactly these pairs) labels the target's own speech as someone else's.
The same holds across splits: train IDs whose voice matches a dev / test speaker are the people of the benchmark's
real-ramc windows.

Output identities.json:
  same_voice  [[speaker, speaker, cosine], ...]   different IDs, different recordings, cosine >= THRESHOLD
  drop        {speaker: [held-out unit, cosine]}  train IDs with a unit >= THRESHOLD to a dev / test unit
  units       per-unit embeddings in units.npz; report.json has the distributions behind THRESHOLD

THRESHOLD sits below the lowest same-ID cross-recording cosine (0.72) with margin: a pair kept apart that is really two
people only costs the pool a near-voice choice, a pair missed mislabels scenes.

    CUDA_VISIBLE_DEVICES=6 python ramc_voice_identities.py --output-dir DIR
"""

import argparse
import gzip
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from build_ts_scene_pool import DATA, catalog_entry
from speaker_neighbors import MODEL, embed_corpus, load_rows

TRAIN = ("magicdata_ramc", "clean-dual-pass-20261027", "train")
HELD_OUT = ("magicdata_ramc", "icefall-20260908", ("dev", "test"))
THRESHOLD = 0.6
UNIT_UTTERANCES = 6
SEED = 20261028


def lhotse(entry, roots, split, kind):
    name = entry["splits"][split]["artifacts"][kind][0]
    artifact = next(a for a in entry["artifacts"] if a["name"] == name)
    with gzip.open(Path(roots[artifact["root_alias"]]) / artifact["relative_path"], "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def unit_embedding(model, clips):
    embeddings = np.stack([np.asarray(model([a], output_emb=True)["embs"])[0] for a in clips])
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    vector = embeddings.mean(axis=0)
    return vector / np.linalg.norm(vector)


def percentiles(values):
    return np.round(np.percentile(values, [0, 10, 50, 90, 100]), 3).tolist() if len(values) else []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    from modelscope.pipelines import pipeline

    model = pipeline(task="speaker-verification", model=MODEL, device=args.device)
    rng = random.Random(SEED)

    rows = load_rows(*TRAIN)
    by_unit = defaultdict(list)
    for i, (speaker, path, duration) in enumerate(zip(rows["speaker"], rows["relative_path"], rows["duration"])):
        if speaker and 2.0 <= duration <= 8.0:
            by_unit[f"{speaker}|{path.rsplit('/', 1)[-1].removesuffix('.wav')}"].append(i)
    chosen = {u: rng.sample(ids, min(UNIT_UTTERANCES, len(ids))) for u, ids in sorted(by_unit.items()) if len(ids) >= 3}
    names, vectors = embed_corpus(model, rows, chosen, 8)

    roots = json.loads((DATA / "registry/roots.json").read_text())
    entry = catalog_entry(HELD_OUT[0], HELD_OUT[1])
    held_names, held_vectors = [], []
    for split in HELD_OUT[2]:
        recordings = {r["id"]: r for r in lhotse(entry, roots, split, "recordings")}
        units = defaultdict(list)
        for s in lhotse(entry, roots, split, "supervisions"):
            if 2.0 <= s["duration"] <= 8.0:
                units[(s["speaker"], s["recording_id"])].append(s)
        for (speaker, recording_id), supervisions in sorted(units.items()):
            if len(supervisions) < 3:
                continue
            recording = recordings[recording_id]
            source = recording["sources"][0]["source"]
            path = Path(source) if source.startswith("/") else Path(roots["aidc_data"]) / source
            rate = recording["sampling_rate"]
            clips = [sf.read(path, start=int(s["start"] * rate), frames=int(s["duration"] * rate), dtype="float32",
                             always_2d=True)[0].mean(axis=1) for s in rng.sample(supervisions, min(UNIT_UTTERANCES, len(supervisions)))]
            if rate != 16000:
                raise ValueError(f"{path}: {rate} Hz")
            held_names.append(f"{speaker}|{split}|{recording_id.removeprefix('magicdata_ramc_')}")
            held_vectors.append(unit_embedding(model, clips))
    held_vectors = np.stack(held_vectors)
    np.savez(args.output_dir / "units.npz", names=np.array(names), vectors=vectors,
             held_names=np.array(held_names), held_vectors=held_vectors)

    speaker = np.array([n.split("|")[0] for n in names])
    recording = np.array([n.split("|")[1] for n in names])
    cosine = vectors @ vectors.T
    upper = np.triu(np.ones_like(cosine, dtype=bool), 1)
    one_id = upper & (speaker[:, None] == speaker[None, :]) & (recording[:, None] != recording[None, :])
    partners = upper & (speaker[:, None] != speaker[None, :]) & (recording[:, None] == recording[None, :])
    others = upper & (speaker[:, None] != speaker[None, :]) & (recording[:, None] != recording[None, :])
    best = {}
    for i, j in zip(*np.where(others & (cosine >= THRESHOLD))):
        pair = tuple(sorted((f"magicdata_ramc:{speaker[i]}", f"magicdata_ramc:{speaker[j]}")))
        best[pair] = max(best.get(pair, -1.0), round(float(cosine[i, j]), 4))
    cross = vectors @ held_vectors.T
    held_ids = {n.split("|")[0] for n in held_names}
    drop = {}
    for i in np.where(cross.max(axis=1) >= THRESHOLD)[0]:
        if speaker[i] in held_ids:  # dropped by ID already (HELD_OUT_SPEAKERS)
            continue
        j = int(np.argmax(cross[i]))
        name = f"magicdata_ramc:{speaker[i]}"
        if name not in drop or cross[i, j] > drop[name][1]:
            drop[name] = [held_names[j], round(float(cross[i, j]), 4)]
    out = {"threshold": THRESHOLD, "train": "@".join(TRAIN[:2]), "held_out": f"{HELD_OUT[0]}@{HELD_OUT[1]} {'/'.join(HELD_OUT[2])}",
           "same_voice": [[a, b, c] for (a, b), c in sorted(best.items(), key=lambda x: -x[1])], "drop": dict(sorted(drop.items()))}
    (args.output_dir / "identities.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    top = np.where(others | others.T, cosine, -1).max(axis=1)
    report = {
        "units": len(names), "held_out_units": len(held_names),
        "cosine_percentiles_0_10_50_90_100": {
            "one_id_two_recordings": percentiles(cosine[one_id]),
            "partners_one_recording": percentiles(cosine[partners]),
            "different_id_two_recordings": percentiles(cosine[others]),
            "different_id_two_recordings_top1_per_unit": percentiles(top),
            "train_unit_best_held_out": percentiles(cross.max(axis=1)),
        },
        "same_voice_pairs": len(best), "speakers_in_same_voice_pairs": len({s for p in best for s in p}),
        "dropped_train_speakers": len(drop),
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
