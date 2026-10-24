#!/usr/bin/env python3
"""Build training babble like asr_babble_bench@v2-20261023's, from training speakers, as babble_noise_train v2.

On asr_babble_bench@v2-20261023 the TS-ASR models answer babble alone with invented text far more often than the
base Qwen3-ASR (zh-babble-mid 13-55% across checkpoints against 9.5%). Their plain-ASR training has no babble-only
clip with an empty transcript: ts_nonspeech_pool@v1-20261016 is MUSAN noise and music, and the registered training
babble (babble_noise_train@v1-20261017, 5-20 talkers, no room) can hold intelligible words, so it cannot be taught as
"nothing". This renders the benchmark's kind of babble instead, with the benchmark's own renderer
(scripts/asr_babble_bench/build.py ``render_babble``): 30 s clips, 16-24 talkers at once, each at its own position
in one SLR28 medium or large room, so no single talker can be followed. The talkers come from training splits (zh:
AISHELL-2 and KeSpeech train; en: LibriSpeech train), none of them a benchmark babble or target speaker.

    python scripts/ts_robust/build_babble_noise_room.py --output-dir /workspace/data/datasets/babble_noise_train/source/v2-20261024 \\
        --catalog CATALOG --version v2-20261024 [--clips 3000 --workers 24]

Writes babble/<language>/*.flac, manifest.jsonl (room, talkers, utterances and their times in each clip),
recordings/babble_<language>_recordings.jsonl.gz and appends the catalog entry to CATALOG/babble_noise_train.yaml.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from lhotse import AudioSource, Recording, RecordingSet
from ruamel.yaml import YAML

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
_spec = importlib.util.spec_from_file_location("babble_bench", REPO / "scripts" / "asr_babble_bench" / "build.py")
bench = importlib.util.module_from_spec(_spec)
sys.modules["babble_bench"] = bench  # the worker pool pickles render_babble by its module name
_spec.loader.exec_module(bench)

from audio_data_contract import load_catalog  # noqa: E402
from audio_data_contract.roots import load_roots  # noqa: E402

DATA = Path("/workspace/data")
ROOT_ALIAS = "aidc_data"
BENCH_RECIPE = REPO / "scripts" / "asr_babble_bench" / "recipe.yaml"
BENCH_MANIFEST = DATA / "datasets/asr_babble_bench/source/v2-20261023/babble/manifest.jsonl"
SEED = 20261024
TALKERS = {
    "zh": [{"dataset": "aishell2", "version": "legacy-20260804", "split": "train"},
           {"dataset": "kespeech", "version": "legacy-20260804", "split": "train"}],
    "en": [{"dataset": "librispeech", "version": "legacy-20260804", "split": "train"}],
}
DESCRIPTION = (
    "训练用房间背景人声（babble）：按 asr_babble_bench@v2-20261023 的合成方法（同一个渲染函数）用训练划分的说话人生成，"
    "每段 30 秒、16–24 人同时连续说话、每人站在 SLR28 中/大模拟房间的不同位置，听不出某一个人说的内容；"
    "中文说话人取自 AISHELL-2、KeSpeech train，英文取自 LibriSpeech train，与评测的背景人声和目标说话人互不重叠。"
    "按 Lhotse 录音清单登记，可作为 noise_sources、nonspeech_sources 或普通 ASR 空目标片段的来源。"
    "v1-20261017 是 5–20 人、无混响，可能听得清某句话。脚本 scripts/ts_robust/build_babble_noise_room.py。")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--clips", type=int, default=3000, help="clips per language")
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    import yaml
    recipe = {**yaml.safe_load(BENCH_RECIPE.read_text()), "seed": SEED}
    catalog, roots = load_catalog(str(DATA / "registry/catalog")), load_roots(str(DATA / "registry/roots.json"))
    held = {t["speaker"] for line in BENCH_MANIFEST.read_text().splitlines() if line.strip()
            for t in json.loads(line)["talkers"]}
    talkers = {}
    for language, sources in TALKERS.items():
        speakers = {}
        for source in sources:
            speakers.update(bench.load_utterances(source, language, catalog, roots))
        talkers[language] = {s: u for s, u in sorted(speakers.items()) if len(u) >= recipe["babble_min_utterances"]}
        overlap = held & set(talkers[language])
        if overlap:
            raise SystemExit(f"{language}: benchmark babble talkers in the training pool: {sorted(overlap)[:5]}")
        print(language, "talkers", len(talkers[language]), flush=True)
    bench.G.update(recipe=recipe, talkers=talkers, rooms=bench.babble_rooms(recipe, catalog, roots))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(language, index, args.output_dir) for language in TALKERS for index in range(args.clips)]
    with ProcessPoolExecutor(args.workers, mp_context=bench.FORK) as pool:
        clips = list(pool.map(bench.render_babble, jobs, chunksize=8))
    for clip in clips:  # the renderer names clips like the benchmark's; keep the training ones apart
        clip["id"] = clip["id"].replace("babble-", "babble-train-", 1)
    with open(args.output_dir / "manifest.jsonl", "w", encoding="utf-8") as stream:
        for clip in clips:
            stream.write(json.dumps(clip, ensure_ascii=False) + "\n")
    (args.output_dir / "recordings").mkdir(exist_ok=True)
    rate = bench.SR
    artifacts, splits = [], {}
    for language in TALKERS:
        rows = [c for c in clips if c["language"] == language]
        recordings = [Recording(id=c["id"], sources=[AudioSource("file", [0], str(args.output_dir / c["path"]))],
                                sampling_rate=rate, num_samples=round(c["duration"] * rate), duration=c["duration"])
                      for c in rows]
        target = args.output_dir / "recordings" / f"babble_{language}_recordings.jsonl.gz"
        RecordingSet.from_recordings(recordings).to_file(target)
        hours = sum(r.duration for r in recordings) / 3600
        artifacts.append({"name": f"{language}-recordings", "kind": "lhotse-recordings", "root_alias": ROOT_ALIAS,
                          "relative_path": target.relative_to(DATA).as_posix(), "expected_bytes": target.stat().st_size,
                          "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                          "metadata": {"record_count": len(recordings)}})
        splits[language] = {"artifacts": {"recordings": [f"{language}-recordings"]}, "task": "noise",
                            "statistics": {"records": len(recordings), "duration_hours": round(hours, 2),
                                           "talkers_in_pool": len(talkers[language])}}
        print(language, len(recordings), round(hours, 2), flush=True)
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": "babble_noise_train", "version": args.version,
             "languages": ["zh", "en"], "tasks": ["noise"], "aliases": [], "artifacts": artifacts, "splits": splits,
             "provenance": {"status": "complete", "synthetic": "full", "snapshot_date": args.version.split("-")[-1],
                            "sources": [f"{s['dataset']}@{s['version']}:{s['split']}" for ss in TALKERS.values() for s in ss]
                            + ["sim_rir_slr28@legacy-20260804:all"], "description": DESCRIPTION}}
    yaml_rt = YAML()
    yaml_rt.allow_unicode = True
    yaml_rt.width = 4096
    yaml_rt.indent(mapping=2, sequence=2, offset=0)
    path = args.catalog / "babble_noise_train.yaml"
    entries = yaml_rt.load(path.read_text(encoding="utf-8")) if path.exists() else []
    if any(e["version"] == args.version for e in entries):
        raise SystemExit(f"babble_noise_train {args.version} is already in {path}")
    entries.append(entry)
    with open(path, "w", encoding="utf-8") as stream:
        yaml_rt.dump(entries, stream)


if __name__ == "__main__":
    main()
