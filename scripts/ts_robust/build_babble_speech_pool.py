#!/usr/bin/env python3
"""Build asr_babble_speech_pool: plain-ASR utterances with room babble before, under and after them.

ts_nonspeech_pool@babble-20261024 teaches plain ASR that room babble alone transcribes as nothing. With it, the
TS-ASR line drops whole utterances on asr_babble_bench@v2-20261023's speech splits: speech with 1-5 s of babble
before and after it comes back empty (045@5000: zh 11 of 600, en 50 of 600), while the same audio without the
padding (``*-babble10-tight``) never does. The English splits already lost 9-14 utterances that way before (033 /
037 / 044). Training has no sample that pairs babble-only seconds with a sentence to transcribe; this pool is one.

Each sample is one training utterance (zh: AISHELL-2 and KeSpeech train, en: LibriSpeech train; 1-15 s, texts of
the benchmark's targets excluded) with 0-5 s of babble before and after it and babble also under it at 0-20 dB SNR,
cut from babble_noise_train@v2-20261024 (mostly the same language; never a clip in which the speaker is a talker),
on a low white or pink floor like the benchmark's. The target is the utterance's text.

    python scripts/ts_robust/build_babble_speech_pool.py --version v1-20261024 [--per-language 12000 --workers 24]

Writes source/<version>/audio/<language>/*.flac and versions/<version>/records_<language>.jsonl.gz +
audio_index_<language>.jsonl.gz + report.json under /workspace/data/datasets/asr_babble_speech_pool, ready for
register_records_pool.py.
"""

import argparse
import gzip
import importlib.util
import json
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
_spec = importlib.util.spec_from_file_location("babble_bench", REPO / "scripts" / "asr_babble_bench" / "build.py")
bench = importlib.util.module_from_spec(_spec)
sys.modules["babble_bench"] = bench
_spec.loader.exec_module(bench)

from audio_data_contract import load_catalog
from audio_data_contract.roots import load_roots

DATA = Path("/workspace/data")
ROOT_ALIAS = "aidc_data"
DATASET_ID = "asr_babble_speech_pool"
BABBLE = DATA / "datasets/babble_noise_train/source/v2-20261024"
BENCH_RECIPE = REPO / "scripts" / "asr_babble_bench" / "recipe.yaml"
SEED = 20261025
SR = bench.SR
TARGETS = {
    "zh": [{"dataset": "aishell2", "version": "legacy-20260804", "split": "train"},
           {"dataset": "kespeech", "version": "legacy-20260804", "split": "train"}],
    "en": [{"dataset": "librispeech", "version": "legacy-20260804", "split": "train"}],
}
SECONDS = (1.0, 15.0)
PAD_SECONDS = (0.0, 5.0)  # the benchmark pads 1-5 s; 0 keeps the plain "babble under the speech" case too
SNR_DB = (0.0, 20.0)  # the benchmark tests 20 / 10 / 5 dB
SPEECH_DBFS = (-35.0, -18.0)
SAME_LANGUAGE_PROB = 0.8
G = {}


def plan(language, index, targets, clips):
    rng = random.Random(f"{SEED}:{language}:{index}")
    utt = targets[index]
    lead, trail = (round(rng.uniform(*PAD_SECONDS), 3) for _ in range(2))
    babble_language = language if rng.random() < SAME_LANGUAGE_PROB else ("en" if language == "zh" else "zh")
    while True:
        clip = rng.choice(clips[babble_language])
        if utt.speaker not in clip["speakers"]:
            break
    slack = clip["duration"] - (lead + utt.duration + trail) - 0.5
    floor = G["recipe"]["noise_floor"]
    return {"id": f"{DATASET_ID}:{language}:{index:06d}", "language": language, "utt": utt, "lead": lead,
            "trail": trail, "clip": clip["id"], "clip_path": str(BABBLE / clip["path"]),
            "offset": round(rng.uniform(0.0, max(slack, 0.0)), 3), "snr_db": round(rng.uniform(*SNR_DB), 2),
            "speech_dbfs": round(rng.uniform(*SPEECH_DBFS), 2),
            "floor": {"kind": rng.choice(floor["kinds"]), "dbfs": round(rng.uniform(*floor["dbfs"]), 2),
                      "seed": rng.getrandbits(32)}}


def render(job):
    p, out = job
    speech = bench.mixer.normalize_rms(bench.ts_build.read_audio(p["utt"].path), p["speech_dbfs"])
    begin = int(p["lead"] * SR)
    w = np.zeros(begin + len(speech) + int(p["trail"] * SR), dtype=np.float32)
    w[begin:begin + len(speech)] = speech
    noise = bench.ts_build.read_audio(p["clip_path"])
    segment = noise[int(p["offset"] * SR):][:len(w)]
    if len(segment) < len(w):
        raise ValueError(f"{p['id']}: babble window runs past the clip")
    under = segment[begin:begin + len(speech)]  # SNR is measured where the speech is, as in the benchmark
    w = w + segment * (10.0 ** ((p["speech_dbfs"] - p["snr_db"]) / 20.0) / bench.mixer.rms(under))
    w = (w + bench.mixer.floor_noise(len(w), p["floor"])).astype(np.float32)
    peak = float(np.abs(w).max())
    if peak > 0.99:
        w = w * (0.99 / peak)
    name = p["id"].split(":", 1)[1].replace(":", "-")
    relative = f"datasets/{DATASET_ID}/source/{G['version']}/audio/{p['language']}/{name}.flac"
    (out / relative).parent.mkdir(parents=True, exist_ok=True)
    sf.write(out / relative, w, SR, format="FLAC", subtype="PCM_16")
    return p["id"], relative, len(w), len(speech), round(20 * np.log10(peak + 1e-12), 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--per-language", type=int, default=12000)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    import yaml
    recipe = yaml.safe_load(BENCH_RECIPE.read_text())
    catalog, roots = load_catalog(str(DATA / "registry/catalog")), load_roots(str(DATA / "registry/roots.json"))
    held = {u.text for language, spec in recipe["targets"].items() for source in spec["sources"]
            for us in bench.load_utterances(source, language, catalog, roots).values() for u in us}
    clips = {"zh": [], "en": []}
    for line in (BABBLE / "manifest.jsonl").read_text().splitlines():
        c = json.loads(line)
        clips[c["language"]].append({"id": c["id"], "path": c["path"], "duration": c["duration"],
                                     "speakers": {t["speaker"] for t in c["talkers"]}})
    G.update(recipe=recipe, version=args.version)
    jobs, report = [], {}
    for language, sources in TARGETS.items():
        pool = sorted((u for source in sources for us in bench.load_utterances(source, language, catalog, roots).values()
                       for u in us if SECONDS[0] <= u.duration <= SECONDS[1] and u.text not in held), key=lambda u: u.id)
        targets = random.Random(f"{SEED}:{language}:targets").sample(pool, args.per_language)
        jobs += [(plan(language, i, targets, clips), DATA) for i in range(args.per_language)]
        report[language] = {"pool_utterances": len(pool), "corpora": dict(Counter(u.corpus for u in targets))}
        print(language, report[language], flush=True)
    with ProcessPoolExecutor(args.workers, mp_context=bench.FORK) as pool:
        rendered = {i: rest for i, *rest in pool.map(render, jobs, chunksize=16)}
    out = DATA / "datasets" / DATASET_ID / "versions" / args.version
    out.mkdir(parents=True, exist_ok=True)
    for language in TARGETS:
        records, index = [], []
        for p, _ in (j for j in jobs if j[0]["language"] == language):
            relative, frames, speech_frames, peak = rendered[p["id"]]
            cut = p["id"]
            duration = round(frames / SR, 4)
            records.append({
                "schema_version": "audio-record/1.0", "id": cut, "task": "asr", "target": p["utt"].text,
                "language": language, "labels": {"target_present": True}, "hotwords": [],
                "audio_slots": [{"name": "primary", "ref": {"dataset_id": DATASET_ID, "version": args.version,
                                                            "split": language, "cut_id": cut, "start": 0.0,
                                                            "duration": duration}}],
                "metadata": {"source_dataset": p["utt"].corpus, "source_group": p["utt"].id, "speaker": p["utt"].speaker,
                             "speech_start_s": p["lead"], "speech_end_s": round(p["lead"] + speech_frames / SR, 3),
                             "snr_db": p["snr_db"], "speech_dbfs": p["speech_dbfs"], "peak_dbfs": peak,
                             "babble": {"clip": p["clip"], "offset_s": p["offset"]}, "floor": p["floor"]}})
            index.append({"cut_id": cut, "root_alias": ROOT_ALIAS, "relative_path": relative, "sample_rate": SR,
                          "channels": 1, "num_frames": frames, "duration": duration})
        for stem, rows in (("records", records), ("audio_index", index)):
            with gzip.open(out / f"{stem}_{language}.jsonl.gz", "wt", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        seconds = [r["duration"] for r in index]
        report[language].update(records=len(records), hours=round(sum(seconds) / 3600, 2),
                                seconds_median=round(float(np.median(seconds)), 2),
                                other_language_babble=sum(1 for p, _ in jobs if p["language"] == language
                                                          and not p["clip"].startswith(f"babble-train-{language}-")))
        print(language, report[language], flush=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
