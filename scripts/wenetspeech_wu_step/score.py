# ruff: noqa: SIM115  # archived copy of the script that ran; one-shot reads, kept as run
"""Per-utterance CER between the WenetSpeech-Wu label and an ASR hypothesis (Qwen or Step-Audio2-Wu) (SpeechIO TextNorm zh tokens, same
rules as ming-asr-tiny-eval-20261019/scripts/score_dialect.py).

usage: score.py CUTS RESULTS.jsonl OUT.jsonl   -> rows {id, duration, ref, hyp, ref_tokens, errors}; prints a summary
"""
import gzip
import json
import re
import sys
from collections import Counter

sys.path.insert(0, '/workspace/workspace/mingdong/repo/icefall/egs/amphion/shared_amphion/zipformer')
from rapidfuzz.distance import Levenshtein
from scoring_norm import _speechio_zh

CJK = re.compile(r'([㐀-䶿一-鿿豈-﫿])')
PUNC = re.compile(r"[^\w\s']|_", re.UNICODE)


def tokens(text):
    toks = _speechio_zh([t for t in CJK.sub(r' \1 ', text or '').split() if t])
    return [t for t in (PUNC.sub('', t).upper() for t in toks) if t]


cuts, res_path, out_path = sys.argv[1:4]
res = {r['id']: r for r in map(json.loads, open(res_path)) if 'hypothesis' in r}
rows = []
for line in gzip.open(cuts, 'rt'):
    if not res:
        break
    c = json.loads(line)
    r = res.pop(c['id'], None)
    if r is None:
        continue
    ref, hyp = c['supervisions'][0]['text'], r['hypothesis']
    a, b = tokens(ref), tokens(hyp)
    rows.append({'id': c['id'], 'duration': c['duration'], 'ref': ref, 'hyp': hyp, 'ref_tokens': len(a),
                 'hyp_tokens': len(b), 'errors': Levenshtein.distance(a, b)})
with open(out_path, 'w') as f:
    f.write(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
n_ref = sum(r['ref_tokens'] for r in rows)
print(f"{len(rows)} utts {sum(r['duration'] for r in rows) / 3600:.2f} h, corpus CER "
      f"{100 * sum(r['errors'] for r in rows) / n_ref:.2f}")
edges = [0, 0.0001, 5, 10, 20, 30, 50, 100, 1e9]
b = Counter()
for r in rows:
    cer = 100 * r['errors'] / max(r['ref_tokens'], 1)
    b[next(i for i in range(len(edges) - 1) if cer < edges[i + 1])] += 1
for i in range(len(edges) - 1):
    print(f"CER [{edges[i]:g}, {edges[i + 1]:g}): {b[i]} ({100 * b[i] / len(rows):.1f}%)")
