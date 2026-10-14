#!/usr/bin/env python3
"""AliMeeting windows with near-field (headset) and far-field enrollment and mixture (ts_asr_nearfar).

Re-uses the AliMeeting windows of ``ts_asr_real`` (same far-field mixture, same enrollment utterance) and
adds the near-field counterparts, so one window is seen under four conditions:

* enrollment: ``ef`` far-field (the registered sample), ``en`` the same utterance from the speaker's headset
* mixture: ``mf`` far-field channel 0 (the registered sample), ``mn`` the sum of all headsets of the recording
  over the window, scaled to the RMS of the far-field mixture so that only the acoustics differ, not the level

``ef-mf`` is the registered sample itself (copied so that the dataset is self-contained); ``en-mf`` is a
registration made on the phone next to the mouth and used in a meeting room. Near and far recordings of
AliMeeting are aligned to within 0.12 s, which is far below what the 3 s enrollment or the transcript can see.

    python scripts/ts_real/near_far.py --roots /workspace/data/registry/roots.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ts_benchmark"))
import build as synth

from audio_data_contract import load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

REPO = Path(__file__).resolve().parents[2]
SR = 16000
DATASET_ID = "ts_asr_nearfar"
VERSION = "v1-20261014"
SOURCE = ("ts_asr_real", "v2-20261013")
NEAR_DIR = Path("/workspace/data/datasets/alimeeting/source/openslr-119-local-20260826/Test_Ali/Test_Ali_near/audio_dir")
BUCKETS = ("1spk", "2spk", "3plus")
CELLS = {"ef-mf": ("far", "far"), "en-mf": ("near", "far"), "ef-mn": ("far", "near"), "en-mn": ("near", "near")}
PEAK_LIMIT = 0.99


def read(path):
    w, rate = sf.read(path, dtype="float32")
    assert rate == SR, (path, rate)
    return w


def cut_near(path, start, end):
    """Seconds [start, end) of a headset recording; zeros past its end (the near files end a little earlier)."""
    first, count = round(start * SR), round((end - start) * SR)
    with sf.SoundFile(path) as stream:
        stream.seek(min(first, len(stream)))
        w = stream.read(count, dtype="float32")
    return np.pad(w, (0, count - len(w)))


def rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)) + 1e-12))


def near_mixture(recording, start, end, far_rms):
    files = sorted(NEAR_DIR.glob(f"{recording}_N_SPK*.wav"))
    if not files:
        return None
    total = sum(cut_near(path, start, end) for path in files)
    total = total * (far_rms / rms(total))
    peak = float(np.abs(total).max())
    return total * (PEAK_LIMIT / peak) if peak > PEAK_LIMIT else total


def load_windows(data_root):
    base = data_root / "versions" / SOURCE[1]
    index = {}
    with gzip.open(base / "audio-index.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            index[row["cut_id"]] = data_root / row["relative_path"]
    windows = defaultdict(dict)
    for bucket in BUCKETS:
        for kind in ("pos", "neg"):
            with gzip.open(base / "records" / f"real-alimeeting-{bucket}-{kind}.jsonl.gz", "rt", encoding="utf-8") as stream:
                for line in stream:
                    record = json.loads(line)
                    enroll, mix = (index[s["ref"]["cut_id"]] for s in record["audio_slots"])
                    windows[(bucket, record["id"].rsplit(":", 1)[1])][kind] = {"record": record, "enroll": enroll, "mix": mix}
    return windows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    data_root = Path(roots[DATASET_ID])
    final = data_root / "source" / VERSION
    if (data_root / "versions" / VERSION).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    partial = data_root / "source" / (VERSION + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    windows = load_windows(Path(roots[SOURCE[0]]))
    results, counts, skipped = [], defaultdict(int), []
    for (bucket, number), pair in sorted(windows.items()):
        recording = pair["pos"]["record"]["labels"]["recording"]
        labels = pair["pos"]["record"]["labels"]
        start = labels["window_start_s"]
        far_mix = read(pair["pos"]["mix"])
        mixes = {"far": far_mix, "near": near_mixture(recording, start, start + len(far_mix) / SR, rms(far_mix))}
        enrolls = {}
        for kind, sample in pair.items():
            meta = sample["record"]["metadata"]
            speaker = meta["target_speaker"].split(":", 1)[1]
            near_path = NEAR_DIR / f"{meta['enrollment']['recording']}_N_SPK{speaker}.wav"
            if near_path.exists():
                enrolls[kind] = {"far": read(sample["enroll"]),
                                 "near": cut_near(near_path, meta["enrollment"]["start"],
                                                  meta["enrollment"]["start"] + len(read(sample["enroll"])) / SR)}
        if mixes["near"] is None or set(enrolls) != {"pos", "neg"}:
            skipped.append(f"{bucket}:{number}")
            continue
        for cell, (enroll_domain, mix_domain) in CELLS.items():
            for kind, sample in pair.items():
                source = sample["record"]
                split = f"nearfar-{bucket}-{cell}-{kind}"
                index = counts[split]
                counts[split] += 1
                entries = []
                for suffix, w in (("mix", mixes[mix_domain]), ("enroll", enrolls[kind][enroll_domain])):
                    relative = f"audio/{split}/{split}-{index:04d}-{suffix}.wav"
                    synth.write_wav(partial / relative, w)
                    entries.append({"cut_id": f"{split}-{index:04d}-{suffix}", "relative_path": relative,
                                    "num_frames": len(w), "duration": round(len(w) / SR, 4),
                                    "sha256": synth.sha256_file(partial / relative)})
                results.append({
                    "split": split, "index": index, "target": source["target"], "entries": entries,
                    "labels": {**source["labels"], "scenario": split, "group": "nearfar", "bucket": bucket,
                               "enroll_domain": enroll_domain, "mix_domain": mix_domain,
                               "window_id": f"{bucket}:{number}", "source_scene": source["labels"]["scenario"]},
                    "metadata": {**source["metadata"], "split": split, "index": index,
                                 "source_record": source["id"]},
                })
    if skipped:
        print("skipped windows without headset audio:", skipped)
    splits = [{"name": name, "group": "nearfar", "params": {"corpus": "alimeeting"}, "n": n}
              for name, n in sorted(counts.items())]
    partial.rename(final)
    declaration = synth.register({"version": VERSION, "dataset_id": DATASET_ID, "pools": {}}, splits, results,
                                 data_root, DATASET_ID)
    declaration["provenance"] = {
        "status": "complete", "synthetic": "none",
        "description": "AliMeeting 测试集窗口的近场与远场对照：同一窗口、同一条注册语句，注册取远场或说话人的头戴麦，"
                       "混合取远场通道 0 或各头戴麦之和（电平对齐远场混合）。基于 ts_asr_real@v2-20261013 的 AliMeeting 窗口。"
                       "只用于评测，不进训练。",
        "sources": [f"{SOURCE[0]}@{SOURCE[1]}", "alimeeting:Test_Ali_near"],
    }
    if args.no_register:
        return
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text())) if path.exists() else []
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", VERSION, len(results), "samples", {k: v for k, v in sorted(counts.items())})


if __name__ == "__main__":
    main()
