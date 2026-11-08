"""Keep rule v2 for LegCo (chosen by the user 2026-11-08 after the rejected-sample review in README).

Re-scores out/qwen-scored.jsonl: both sides unify the particle variants 噉->咁 and 呢->咧 before TextNorm, and insertions
at the very start or end of the hypothesis are not counted (Qwen hears words of the neighbouring segment because each file
runs past its supervision). Keep = label non-empty after TextNorm and (duration < 2 s, which single-speaker ASR cannot judge,
or adjusted CER < 30). Writes {id, duration, ref_tokens, errors_v2, keep, reason} per row.

usage: rule_v2.py SCORED.jsonl OUT.jsonl
"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, '/workspace/workspace/mingdong/repo/icefall/egs/amphion/shared_amphion/zipformer')
from rapidfuzz.distance import Levenshtein
from scoring_norm import _speechio_yue

CJK = re.compile(r'([㐀-䶿一-鿿豈-﫿])')
PUNC = re.compile(r"[^\w\s']|_", re.UNICODE)
VARIANTS = str.maketrans({'噉': '咁', '呢': '咧'})
SHORT_S, KEEP_CER_BELOW = 2.0, 30


def tokens(text):
    toks = _speechio_yue([t for t in CJK.sub(r' \1 ', (text or '').translate(VARIANTS)).split() if t])
    return [t for t in (PUNC.sub('', t).upper() for t in toks) if t]


def errors_without_edge_insertions(a, b):
    ops = Levenshtein.opcodes(a, b)
    return sum(max(o.src_end - o.src_start, o.dest_end - o.dest_start) for k, o in enumerate(ops)
               if o.tag != 'equal' and not (o.tag == 'insert' and k in (0, len(ops) - 1)))


src, out = sys.argv[1:3]
n, h = Counter(), Counter()
with open(src) as f, open(out, 'w') as w:
    for line in f:
        r = json.loads(line)
        a, b = tokens(r['ref']), tokens(r['hyp'])
        e = errors_without_edge_insertions(a, b) if a else None
        if not a:
            keep, reason = False, 'label empty after TextNorm'
        elif r['duration'] < SHORT_S:
            keep, reason = True, 'short, not judged'
        elif 100 * e < KEEP_CER_BELOW * len(a):
            keep, reason = True, 'cer_v2 < 30'
        else:
            keep, reason = False, 'cer_v2 >= 30'
        w.write(json.dumps({'id': r['id'], 'duration': r['duration'], 'ref_tokens': len(a), 'errors_v2': e,
                            'keep': keep, 'reason': reason}, ensure_ascii=False) + '\n')
        n[reason] += 1
        h[reason] += r['duration'] / 3600
for k in n:
    print(f'{k}: {n[k]} rows {h[k]:.1f} h')
