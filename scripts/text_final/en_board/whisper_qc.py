#!/usr/bin/env python3
"""Reject list for the English board versions: records whose whisper-large-v3 transcript is far from the target.

Both sides go through the Whisper English normalizer (case, punctuation, fillers, number words); a record is rejected
when its word error rate is above --max-wer. Input rows {id: "<dataset_id>:<record id>", target, whisper} come from
the run directory's verify_asr.py. Writes {record id: wer} and prints counts.

    python -I scripts/text_final/en_board/whisper_qc.py IN.jsonl OUT.json [--max-wer 0.5]
"""

import argparse
import json

from transformers.models.whisper.english_normalizer import EnglishTextNormalizer


def errors(ref: list[str], hyp: list[str]) -> int:
    d = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(hyp) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ref[i - 1] != hyp[j - 1]))
    return d[len(hyp)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--max-wer", type=float, default=0.5)
    args = ap.parse_args()
    norm = EnglishTextNormalizer({})
    out, n, failed = {}, 0, []
    with open(args.inp) as f:
        rows = [json.loads(line) for line in f]
    for r in rows:
        if "error" in r:
            failed.append(r["id"])
            continue
        n += 1
        ref, hyp = norm(r["target"]).split(), norm(r["whisper"]).split()
        wer = errors(ref, hyp) / max(len(ref), 1)
        if wer > args.max_wer:
            out[r["id"].split(":", 1)[1]] = round(wer, 3)
    assert not failed, f"{len(failed)} rows without a transcript, e.g. {failed[:3]}"
    with open(args.out, "w") as w:
        json.dump(out, w, indent=0, sort_keys=True)
    print(f"scored {n} rejected {len(out)} ({len(out) / max(n, 1):.1%}) at WER > {args.max_wer}")


if __name__ == "__main__":
    main()
