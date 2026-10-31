#!/usr/bin/env python3
"""Export utterances of a TTS Lance release as 16 kHz FLAC files plus an utterance list for a recipe pool.

The benchmark builder reads utterance audio by path, while TTS releases (``DATA-TTS-UNIFIED``) keep the encoded
audio inside a Lance table. This writes ``utterances.jsonl.gz`` (``id``, ``speaker``, ``text``, ``duration``,
``path`` relative to the list, ``gender``, ``accent``) next to ``audio/<speaker>/<id>.flac``; a recipe pool source
``{manifest: {alias, path}, dataset, version, split}`` reads it. ``--per-speaker`` keeps a fixed sample of each
speaker's utterances (lowest sha256 of the sample id), enough for scenes and 10 s enrollments.

    python scripts/ts_benchmark/export_tts_pool.py --dataset vctk --version tts-unified-v0.1 \
        --filter "source_key LIKE '%_mic1'" --per-speaker 80 \
        --output /workspace/data/datasets/ts_asr_benchmark/source/pools/vctk-tts-unified-v0.1-mic1
"""

import argparse
import gzip
import hashlib
import io
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_data_contract import load_catalog, tts_lance

SR = 16000


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifact", default="samples")
    parser.add_argument("--filter", help="Lance SQL predicate on the base columns")
    parser.add_argument("--per-speaker", type=int, required=True)
    parser.add_argument("--seconds", type=float, nargs=2, default=(1.0, 12.0), help="utterance length range kept")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roots", type=Path, default=Path("/workspace/data/registry/roots.json"))
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    args = parser.parse_args()
    if (args.output / "utterances.jsonl.gz").exists():
        raise FileExistsError(f"refusing to replace {args.output}")

    from scipy.signal import resample_poly

    release = tts_lance.open_release(load_catalog(args.catalog), args.dataset, args.version, args.artifact,
                                     json.loads(args.roots.read_text()))
    conditions = ["text IS NOT NULL", f"duration_seconds BETWEEN {args.seconds[0]} AND {args.seconds[1]}"]
    if args.filter:
        conditions.append(f"({args.filter})")
    rows = release.dataset.to_table(columns=["sample_id", "speaker_id", "text", "duration_seconds", "metadata_json"],
                                    filter=" AND ".join(conditions)).to_pylist()
    by_speaker = defaultdict(list)
    for row in rows:
        if row["text"].strip():
            by_speaker[row["speaker_id"]].append(row)
    chosen = []
    for speaker in sorted(by_speaker):
        ranked = sorted(by_speaker[speaker], key=lambda r: hashlib.sha256(r["sample_id"].encode()).hexdigest())
        chosen.extend(ranked[:args.per_speaker])

    out = []
    for start in range(0, len(chosen), 256):
        batch = chosen[start:start + 256]
        audio = tts_lance.read_audio(release, [r["sample_id"] for r in batch])
        for row in batch:
            w, sr = sf.read(io.BytesIO(audio[row["sample_id"]]), dtype="float32", always_2d=False)
            if w.ndim > 1:
                w = w.mean(axis=1)
            if sr != SR:
                g = math.gcd(sr, SR)
                w = resample_poly(w, SR // g, sr // g).astype(np.float32)
            meta = json.loads(row["metadata_json"])
            info = meta.get("upstream_speaker_info") or []
            speaker = row["speaker_id"].split(":", 1)[-1]
            utt = meta.get("upstream_utterance_id") or row["sample_id"][:16]
            relative = f"audio/{speaker}/{utt}.flac"
            (args.output / relative).parent.mkdir(parents=True, exist_ok=True)
            sf.write(args.output / relative, np.clip(w, -1.0, 1.0), SR, subtype="PCM_16")
            out.append({"id": utt, "speaker": speaker, "text": row["text"].strip(), "duration": round(len(w) / SR, 4),
                        "path": relative, "gender": info[1] if len(info) > 1 else None,
                        "accent": info[2] if len(info) > 2 else None, "sample_id": row["sample_id"]})
        print(f"exported {len(out)}/{len(chosen)}", flush=True)
    with gzip.open(args.output / "utterances.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in out:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"{len(out)} utterances of {len(by_speaker)} speakers -> {args.output}")


if __name__ == "__main__":
    main()
