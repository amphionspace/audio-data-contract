"""Per-utterance CER between the LegCo-Speech label and the Qwen hypothesis (Cantonese SpeechIO TextNorm tokens:
fillers kept, traditional -> simplified; same rules as ming-asr-tiny-eval-20261019/scripts/score_dialect.py).

usage: score.py SUPERVISIONS RESULTS.jsonl OUT.jsonl
  -> rows {id, duration, confidence, ref, hyp, ref_tokens, hyp_tokens, errors}; prints a summary
"""
import gzip
import json
import re
import sys
from collections import Counter

sys.path.insert(0, '/workspace/workspace/mingdong/repo/icefall/egs/amphion/shared_amphion/zipformer')
from rapidfuzz.distance import Levenshtein
from scoring_norm import _speechio_yue

CJK = re.compile(r'([㐀-䶿一-鿿豈-﫿])')
PUNC = re.compile(r"[^\w\s']|_", re.UNICODE)


def tokens(text):
    toks = _speechio_yue([t for t in CJK.sub(r' \1 ', text or '').split() if t])
    return [t for t in (PUNC.sub('', t).upper() for t in toks) if t]


sups, res_path, out_path = sys.argv[1:4]
with open(res_path) as stream:
    res = {r['id']: r for r in map(json.loads, stream) if 'hypothesis' in r}
rows = []
with gzip.open(sups, 'rt') as stream:
    for line in stream:
        if not res:
            break
        c = json.loads(line)
        r = res.pop(c['recording_id'], None)
        if r is None:
            continue
        ref, hyp = c['text'], r['hypothesis']
        a, b = tokens(ref), tokens(hyp)
        rows.append({'id': c['recording_id'], 'duration': c['duration'], 'confidence': c['custom'].get('confidence'),
                     'ref': ref, 'hyp': hyp, 'ref_tokens': len(a),
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
