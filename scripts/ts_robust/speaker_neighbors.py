#!/usr/bin/env python3
"""Find, for every target-capable speaker, the other speakers who sound most like them.

A speaker's vector is the mean of the L2-normalized ERes2NetV2 embeddings of up to
``--utterances`` utterances of 2-8 s. Utterance spans come from the Lance record index
(speaker, audio location), the same source `build_ts_scene_pool.py` draws scenes from.
For each speaker of a target corpus the ``--top`` closest speakers of the same language
(any corpus, never the speaker itself) are kept with their cosine similarity.

Neighbours are chosen by rank, not by a threshold: the best threshold differs between
corpora (0.33-0.60 in our check), so a fixed cosine would select different things in each.

Output: neighbors.json  {language: {speaker: [[neighbor, cosine], ...]}}
        embeddings.npz  speaker names and vectors
        report.json     distribution of the closest-neighbor cosines

    python speaker_neighbors.py --output-dir DIR [--device cuda:2]
"""

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import lance
import numpy as np
import soundfile as sf
import yaml

DATA = Path("/workspace/data")
REGISTRY = DATA / "registry/catalog/datasets.yaml"
MODEL = "/workspace/model/modelscope/models/iic--speech_eres2netv2_sv_zh-cn_16k-common/snapshots/master"
SR = 16000
SEED = 20261016
UTTERANCE_SECONDS = (2.0, 8.0)
# (dataset, version, split, can be a target, speakers drawn at random or None for all)
CORPORA = {
    "zh": [("aishell2", "legacy-20260804", "train", True, None), ("kespeech", "legacy-20260804", "train", False, 6000)],
    "en": [("librispeech", "legacy-20260804", "train", True, None), ("common_voice_en", "legacy-20260804", "train", False, 6000)],
}
COLUMNS = ["speaker", "duration", "root_alias", "relative_path", "start_frame", "num_frames", "sample_rate"]


def load_rows(dataset, version, split):
    entry = next(e for e in yaml.safe_load(REGISTRY.read_text()) if e["dataset_id"] == dataset and e["version"] == version)
    artifact = next(a for a in entry["artifacts"] if a["name"] == entry["splits"][split]["artifacts"]["records_lance"][0])
    directory = DATA / artifact["relative_path"].rsplit("/", 1)[0]
    manifest = json.loads((directory / "index.json").read_text())
    return lance.dataset(str(directory / manifest["table_path"])).to_table(
        columns=COLUMNS, filter=f"array_has(splits, '{split}')").to_pydict()


def pick_utterances(rows, count, wanted, rng):
    """{speaker: [row index, ...]} for ``wanted`` speakers (None = all) with enough utterances."""
    by_speaker = {}
    for i, (speaker, duration) in enumerate(zip(rows["speaker"], rows["duration"])):
        if speaker and UTTERANCE_SECONDS[0] <= duration <= UTTERANCE_SECONDS[1]:
            by_speaker.setdefault(speaker, []).append(i)
    names = sorted(s for s, ids in by_speaker.items() if len(ids) >= min(count, 3))
    if wanted is not None and len(names) > wanted:
        names = rng.sample(names, wanted)
    return {s: rng.sample(by_speaker[s], min(count, len(by_speaker[s]))) for s in names}


def read_clip(rows, i):
    path = DATA / rows["relative_path"][i] if rows["root_alias"][i] == "aidc_data" else None
    if path is None:
        raise ValueError(f"unexpected root alias {rows['root_alias'][i]}")
    start, frames = rows["start_frame"][i], rows["num_frames"][i]
    audio, file_rate = sf.read(path, start=start, frames=frames, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if file_rate != SR:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(file_rate, SR)
        audio = resample_poly(audio, SR // g, file_rate // g).astype(np.float32)
    return audio


def embed_corpus(model, rows, chosen, workers):
    names = list(chosen)
    vectors = np.zeros((len(names), 192), dtype=np.float32)
    kept = np.zeros(len(names), dtype=bool)

    def clips(speaker):
        out = []
        for i in chosen[speaker]:
            try:
                out.append(read_clip(rows, i))
            except Exception:  # noqa: BLE001, S112  an unreadable clip is skipped; the speaker keeps the others
                continue
        return out

    with ThreadPoolExecutor(workers) as pool:
        for number, audio in enumerate(pool.map(clips, names)):
            if not audio:
                continue
            embeddings = np.stack([np.asarray(model([a], output_emb=True)["embs"])[0] for a in audio])
            embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
            vectors[number], kept[number] = embeddings.mean(axis=0), True
            if number % 1000 == 0:
                print(f"  {number}/{len(names)}", flush=True)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
    return [n for n, k in zip(names, kept) if k], vectors[kept]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:2")
    parser.add_argument("--utterances", type=int, default=4)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--smoke", action="store_true", help="50 speakers per corpus, to check the setup")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    from modelscope.pipelines import pipeline

    model = pipeline(task="speaker-verification", model=MODEL, device=args.device)
    neighbors, report, store = {}, {}, {}
    for language, corpora in CORPORA.items():
        names, vectors, targets = [], [], []
        for dataset, version, split, can_target, wanted in corpora:
            print(language, dataset, flush=True)
            rows = load_rows(dataset, version, split)
            chosen = pick_utterances(rows, args.utterances, 50 if args.smoke else wanted, random.Random(f"{SEED}:{dataset}"))
            speakers, embeddings = embed_corpus(model, rows, chosen, args.workers)
            names += [f"{dataset}:{s}" for s in speakers]
            vectors.append(embeddings)
            targets += [can_target] * len(speakers)
        vectors, targets = np.concatenate(vectors), np.array(targets)
        store[language] = (names, vectors)
        result, best = {}, []
        for i in np.nonzero(targets)[0]:
            scores = vectors @ vectors[i]
            scores[i] = -1
            order = np.argsort(-scores)[: args.top]
            result[names[i]] = [[names[j], round(float(scores[j]), 4)] for j in order]
            best.append(scores[order[0]])
        neighbors[language] = result
        best = np.array(best)
        report[language] = {"speakers": len(names), "targets": int(targets.sum()),
                            "top1_cosine_percentiles_10_50_90": [round(float(x), 3) for x in np.percentile(best, [10, 50, 90])]}
        print(language, report[language], flush=True)
    (args.output_dir / "neighbors.json").write_text(json.dumps(neighbors, ensure_ascii=False))
    np.savez(args.output_dir / "embeddings.npz", **{f"{lang}_names": np.array(n) for lang, (n, _) in store.items()},
             **{f"{lang}_vectors": v for lang, (_, v) in store.items()})
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
