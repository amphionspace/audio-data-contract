#!/usr/bin/env python3
"""Keep only the utterances of a bilingual Common Voice target that are the same voice (ts_asr_crosslingual).

A Common Voice account (``client_id``) is not always one person: some accounts hold sessions of several voices,
e.g. all Spanish clips one voice and all English clips another. For such a target the cross-lingual enrollment
would be someone else. Per target, with ECAPA embeddings (``speaker_embeddings.make_embedder``):

1. an utterance of the anchor language (the first of ``--languages``, the mixture language) is kept when its cosine
   to the mean of the target's other anchor utterances is at least ``MIN_COSINE``;
2. an utterance of the other language is kept when its cosine to the mean of the kept anchor utterances is at
   least ``MIN_COSINE``;
3. the target is kept when both languages keep at least ``--min-utterances``.

``MIN_COSINE`` is 0.5: on es-v1-20261111 an utterance against another target's centroid exceeds it once in a
thousand (99.9th percentile 0.497). The input lists are those of ``export_bilingual_pool.py``; the kept ones go to
``cv-bilingual-<lang>-verified/utterances.jsonl.gz``, the per-utterance scores to ``cv-bilingual-identity.json``.
The run fails (non-zero, nothing written) when fewer than half of the exported targets are kept, which means the
embeddings or the lists are wrong rather than a few shared accounts. Needs ``onnxruntime`` and ``torchaudio``:

    PYTHONPATH=src python scripts/ts_benchmark/qc_bilingual_identity.py --languages es en \\
        --pools /workspace/data/datasets/ts_asr_crosslingual/source/pools/es-v1-20261111
"""

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
from speaker_embeddings import make_embedder

MIN_COSINE = 0.5
MIN_KEPT_SHARE = 0.5


def _unit(x):
    return x / np.linalg.norm(x)


def _read(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pools", type=Path, required=True, help="output directory of export_bilingual_pool.py")
    parser.add_argument("--languages", nargs=2, required=True, help="anchor (mixture) language first")
    parser.add_argument("--min-utterances", type=int, default=5, help="per language, as in the export")
    args = parser.parse_args()
    anchor, other = args.languages
    embed = make_embedder()
    rows = {lang: _read(args.pools / f"cv-bilingual-{lang}/utterances.jsonl.gz") for lang in (anchor, other)}
    by_speaker = defaultdict(lambda: defaultdict(list))
    for lang, items in rows.items():
        for row in items:
            by_speaker[row["speaker"]][lang].append((row, embed(build.read_audio(row["path"]))))
    report, kept = {}, {}
    for speaker, langs in sorted(by_speaker.items()):
        vectors = [v for _, v in langs[anchor]]
        loo = [float(v @ _unit(sum(vectors) - v)) if len(vectors) > 1 else 0.0 for v in vectors]
        keep_anchor = [(r, v) for (r, v), c in zip(langs[anchor], loo) if c >= MIN_COSINE]
        centroid = _unit(sum(v for _, v in keep_anchor)) if keep_anchor else None
        cross = [float(v @ centroid) if centroid is not None else 0.0 for _, v in langs[other]]
        keep_other = [r for (r, _), c in zip(langs[other], cross) if c >= MIN_COSINE]
        ok = len(keep_anchor) >= args.min_utterances and len(keep_other) >= args.min_utterances
        report[speaker] = {
            "kept": ok, f"{anchor}_kept": len(keep_anchor), f"{anchor}_total": len(vectors),
            f"{other}_kept": len(keep_other), f"{other}_total": len(cross),
            "cosine": {**{r["id"]: round(c, 3) for (r, _), c in zip(langs[anchor], loo)},
                       **{r["id"]: round(c, 3) for (r, _), c in zip(langs[other], cross)}}}
        if ok:
            kept[speaker] = {anchor: [r for r, _ in keep_anchor], other: keep_other}
    summary = {"languages": [anchor, other], "min_cosine": MIN_COSINE, "min_utterances": args.min_utterances,
               "targets": len(report), "kept_targets": len(kept),
               "dropped_targets": sorted(s for s, r in report.items() if not r["kept"]),
               **{f"kept_{lang}_utterances": sum(len(k[lang]) for k in kept.values()) for lang in (anchor, other)}}
    print(json.dumps({k: v for k, v in summary.items() if k != "dropped_targets"}))
    if len(kept) < MIN_KEPT_SHARE * len(report):
        raise SystemExit(f"only {len(kept)}/{len(report)} targets kept; check the embeddings and the lists")
    for lang in (anchor, other):
        path = args.pools / f"cv-bilingual-{lang}-verified/utterances.jsonl.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for speaker in sorted(kept):
                for row in kept[speaker][lang]:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.pools / "cv-bilingual-identity.json").write_text(
        json.dumps({"summary": summary, "speakers": report}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
