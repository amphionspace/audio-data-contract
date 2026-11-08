"""Transcribe LegCo-Speech (Cantonese) train segments with Qwen3-ASR-1.7B on the shared service (127.0.0.1:8003).

Same request as wenetspeech-yue-rest-qwen-20261025/scripts/qwen_infer.py (language auto, no to_language), which put
Qwen at 6.2 CER on WSYue-ASR-eval. Each recording is one 48 kHz Ogg Opus segment file (mostly stereo) that runs 0-1 s
(median 0.5 s) past its supervision duration. The file bytes are sent as-is: the service decodes Opus, and the file is
about 60% of the 16 kHz FLAC bytes (the tunnel to :8003 carries about 18 MB/s).
--span sends only [start, start + duration] on channel 0 instead (decoded, resampled to 16 kHz, lossless FLAC). On the
2,000-row pilot that raised CER from 8.62 to 11.75: every supervision has start 0, but the speech sits later in the
file, so the span picks up the previous words and cuts the last ones.
Rows are appended to OUT as {id, duration, hypothesis, raw} or {id, duration, error}, keyed by recording id, with the
supervision duration; rerunning skips ids that already have a hypothesis, so errors get retried.

usage: qwen_infer.py RECORDINGS SUPERVISIONS OUT [--workers 64] [--sample N] [--span] [--base-url URL]
  (--sample: seed-42 random subset of recordings for the pilot)
"""
import argparse
import base64
import gzip
import io
import json
import os
import random
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import numpy as np
import soundfile as sf
import soxr
from openai import OpenAI

p = argparse.ArgumentParser()
p.add_argument('recordings')
p.add_argument('supervisions')
p.add_argument('out')
p.add_argument('--workers', type=int, default=64)
p.add_argument('--sample', type=int)
p.add_argument('--span', action='store_true')
p.add_argument('--base-url', default='http://127.0.0.1:8003/v1')
args = p.parse_args()

client = OpenAI(base_url=args.base_url, api_key='x', timeout=600, max_retries=0)
with gzip.open(args.recordings, 'rt') as stream:
    tasks = [(c['id'], c['sources'][0]['source'], c['duration']) for c in map(json.loads, stream)]
if args.sample:
    tasks = random.Random(42).sample(tasks, args.sample)
spans = {t[0]: None for t in tasks}
with gzip.open(args.supervisions, 'rt') as stream:
    for s in map(json.loads, stream):
        if s['recording_id'] in spans:
            if spans[s['recording_id']] is not None:
                raise ValueError(f"recording {s['recording_id']} has more than one supervision")
            if s['channel'] != 0:
                raise ValueError(f"supervision {s['id']} is on channel {s['channel']}")
            spans[s['recording_id']] = (s['start'], s['duration'])
tasks = [(i, path, d, spans[i]) for i, path, d in tasks if spans[i] is not None]
done = set()
if os.path.exists(args.out):
    with open(args.out) as stream:
        done = {r['id'] for r in map(json.loads, stream) if 'hypothesis' in r}
tasks = sorted((t for t in tasks if t[0] not in done), key=lambda t: t[1])
print(f'{len(done)} done, {len(tasks)} to transcribe ({sum(t[3][1] for t in tasks) / 3600:.1f} h)', flush=True)


def audio_url(path, start, duration):
    if not args.span:
        with open(path, 'rb') as f:
            return 'data:audio/ogg;base64,' + base64.b64encode(f.read()).decode()
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    x = x[round(start * sr):round((start + duration) * sr), 0]
    x = soxr.resample(x, sr, 16000)
    buf = io.BytesIO()
    sf.write(buf, np.clip(x, -1, 1), 16000, format='FLAC', subtype='PCM_16')
    return 'data:audio/flac;base64,' + base64.b64encode(buf.getvalue()).decode()


def ffmpeg_url(path):
    """Whole file decoded by ffmpeg to 16 kHz mono FLAC: for the ~0.5% of Opus files the local server's libsndfile rejects."""
    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    if not pcm:
        raise ValueError('ffmpeg decoded no audio (corrupt Ogg)')
    buf = io.BytesIO()  # piped FLAC has no sample count in its header; write it from PCM on a seekable buffer
    sf.write(buf, np.frombuffer(pcm, dtype='<i2'), 16000, format='FLAC', subtype='PCM_16')
    return 'data:audio/flac;base64,' + base64.b64encode(buf.getvalue()).decode()


def transcribe(url, c=None):
    return (c or client).chat.completions.create(model='Qwen/Qwen3-ASR-1.7B', messages=[{'role': 'user', 'content': [
        {'type': 'audio_url', 'audio_url': {'url': url}}]}],
        temperature=0, max_tokens=2048, extra_body={'repetition_penalty': 1.1})


def run(task):
    cut_id, path, _, (start, duration) = task
    try:
        try:
            x = transcribe(audio_url(path, start, duration))
        except Exception:
            if args.span:
                raise
            # a fresh client: the failed request can leave a dropped keep-alive connection in the shared pool
            with OpenAI(base_url=args.base_url, api_key='x', timeout=600, max_retries=0) as fresh:
                x = transcribe(ffmpeg_url(path), fresh)
        raw = (x.choices[0].message.content or '').strip()
        hyp = raw.split('<asr_text>', 1)[1].strip() if '<asr_text>' in raw else raw
        return {'id': cut_id, 'duration': duration, 'hypothesis': hyp, 'raw': raw}
    except Exception as e:  # noqa: BLE001 - any failure is recorded and retried on the next run
        return {'id': cut_id, 'duration': duration, 'error': repr(e)[:300]}


n = errors = 0
hours = 0.0
t0 = time.time()
with open(args.out, 'a') as sink, ThreadPoolExecutor(args.workers) as ex:
    pending, it = set(), iter(tasks)
    while True:
        while len(pending) < args.workers * 4:
            task = next(it, None)
            if task is None:
                break
            pending.add(ex.submit(run, task))
        if not pending:
            break
        finished, pending = wait(pending, return_when=FIRST_COMPLETED)
        for f in finished:
            r = f.result()
            sink.write(json.dumps(r, ensure_ascii=False) + '\n')
            n += 1
            errors += 'error' in r
            hours += r['duration'] / 3600
            if n % 5000 == 0 or n == len(tasks):
                sink.flush()
                el = time.time() - t0
                print(f'{time.strftime("%m-%d %H:%M:%S")} {n}/{len(tasks)} errors {errors} {hours:.1f} h '
                      f'{n / el:.1f} utt/s {hours * 3600 / el:.0f}x realtime', flush=True)
print('finished', n, 'errors', errors, flush=True)
