"""Per-utterance CER between a WenetSpeech dialect label and the Qwen3-ASR hypothesis from qwen_infer.py.

Tokens follow the icefall scoring_norm used for the dialect test sets: one token per CJK character, SpeechIO TextNorm
(`zh`: Sichuanese / Wu; `yue`: fillers kept, traditional -> simplified, needs opencc), punctuation dropped, upper case.
`--norm-dir` is the directory holding scoring_norm.py (icefall egs/amphion/shared_amphion/zipformer).

    python scripts/wenetspeech_qwen/score.py --format cuts --lang zh --norm-dir DIR CUTS.jsonl.gz qwen.jsonl OUT.jsonl
    python scripts/wenetspeech_qwen/score.py --format supervisions --lang yue --norm-dir DIR SUPS.jsonl.gz qwen.jsonl OUT.jsonl

OUT rows: {id, duration, [confidence,] ref, hyp, ref_tokens, hyp_tokens, errors}, in source order. Rows without a
hypothesis in qwen.jsonl (errors, audio over the service limit) are not scored.
"""

import argparse
import gzip
import json
import re
import sys
from collections import Counter

from rapidfuzz.distance import Levenshtein

CJK = re.compile(r"([㐀-䶿一-鿿豈-﫿])")
PUNCTUATION = re.compile(r"[^\w\s']|_", re.UNICODE)
BUCKET_EDGES = [0, 0.0001, 5, 10, 20, 30, 50, 100, 1e9]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("results")
    parser.add_argument("out")
    parser.add_argument("--format", choices=["cuts", "supervisions"], required=True)
    parser.add_argument("--lang", choices=["zh", "yue"], required=True)
    parser.add_argument("--norm-dir", required=True)
    args = parser.parse_args()

    sys.path.insert(0, args.norm_dir)
    import scoring_norm

    normalize = scoring_norm._speechio_zh if args.lang == "zh" else scoring_norm._speechio_yue

    def tokens(text):
        words = normalize([t for t in CJK.sub(r" \1 ", text or "").split() if t])
        return [t for t in (PUNCTUATION.sub("", w).upper() for w in words) if t]

    with open(args.results, encoding="utf-8") as stream:
        hypotheses = {r["id"]: r for r in map(json.loads, stream) if "hypothesis" in r}
    rows = []
    with gzip.open(args.source, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not hypotheses:
                break
            item = json.loads(line)
            if args.format == "cuts":
                row_id, supervision = item["id"], item["supervisions"][0]
            else:
                row_id, supervision = item["recording_id"], item
            found = hypotheses.pop(row_id, None)
            if found is None:
                continue
            reference, hypothesis = supervision["text"], found["hypothesis"]
            ref, hyp = tokens(reference), tokens(hypothesis)
            row = {"id": row_id, "duration": item["duration"]}
            if args.format == "supervisions":
                row["confidence"] = supervision["custom"].get("confidence")
            row.update(ref=reference, hyp=hypothesis, ref_tokens=len(ref), hyp_tokens=len(hyp),
                       errors=Levenshtein.distance(ref, hyp))
            rows.append(row)
    with open(args.out, "w", encoding="utf-8") as sink:
        sink.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    ref_total = sum(r["ref_tokens"] for r in rows)
    print(f"{len(rows)} utts {sum(r['duration'] for r in rows) / 3600:.2f} h, corpus CER "
          f"{100 * sum(r['errors'] for r in rows) / ref_total:.2f}")
    buckets = Counter()
    for r in rows:
        cer = 100 * r["errors"] / max(r["ref_tokens"], 1)
        buckets[next(i for i in range(len(BUCKET_EDGES) - 1) if cer < BUCKET_EDGES[i + 1])] += 1
    for i in range(len(BUCKET_EDGES) - 1):
        print(f"CER [{BUCKET_EDGES[i]:g}, {BUCKET_EDGES[i + 1]:g}): {buckets[i]} ({100 * buckets[i] / len(rows):.1f}%)")


if __name__ == "__main__":
    main()
