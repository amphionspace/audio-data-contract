"""Transcribe Wu audio with Step-Audio2-Wu-ASR (ASLP-lab LoRA on Step-Audio-2-mini), HF transformers, one GPU.

The released HF modeling code returns no KV cache, so generate() re-encodes the audio and the whole prefix at
every step. Here the audio encoder + adapter build the prompt embeddings once (same mel / chunking / token count
as ms-swift's step_audio2_mini template, the one the LoRA was trained with), then the Qwen2 LLM decodes greedily
with a KV cache over a left-padded batch. Prompt: <|BOT|>human\n<audio>语音说了什么<|EOT|><|BOT|>assistant\n.

Inputs: a lhotse cuts .jsonl.gz whose recording sources are `dd` byte ranges into tars (WenetSpeech-Wu train), or a
.jsonl manifest with {id, audio, duration[, label]} (the Wu-Bench sample). Appends {id, duration, hypothesis} rows to
OUT; rerunning skips ids already done.

usage: step_infer.py INPUT OUT [--label wu] [--sample N] [--shard I/N] [--batch-seconds 400] [--max-batch 64]
"""
import argparse, gzip, io, json, os, random, re, sys, time

import librosa
import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/workspace/model/Step-Audio-2-mini'
LORA = '/workspace/model/WSWu-ASR/stepaudio2-ASR'
DD = re.compile(r'dd if=(\S+) iflag=skip_bytes,count_bytes skip=(\d+) count=(\d+)')
AUDIO_START = 151688
CHUNK = 16000 * 25

p = argparse.ArgumentParser()
p.add_argument('input')
p.add_argument('out')
p.add_argument('--label')
p.add_argument('--sample', type=int)
p.add_argument('--shard', default='0/1')
p.add_argument('--batch-seconds', type=float, default=400)
p.add_argument('--max-batch', type=int, default=64)
args = p.parse_args()

tasks = []
if args.input.endswith('.gz'):
    for line in gzip.open(args.input, 'rt'):
        c = json.loads(line)
        path, skip, count = DD.match(c['recording']['sources'][0]['source']).groups()
        tasks.append((c['id'], (path, int(skip), int(count)), c['duration']))
else:
    for r in map(json.loads, open(args.input)):
        if args.label is None or r.get('label') == args.label:
            tasks.append((r['id'], r['audio'], r['duration']))
if args.sample:
    tasks = random.Random(42).sample(tasks, args.sample)
i, n = map(int, args.shard.split('/'))
tasks = tasks[i::n]
done = set()
if os.path.exists(args.out):
    done = {r['id'] for r in map(json.loads, open(args.out)) if 'hypothesis' in r}
tasks = sorted((t for t in tasks if t[0] not in done), key=lambda t: t[2])
print(f'{len(done)} done, {len(tasks)} to transcribe ({sum(t[2] for t in tasks) / 3600:.2f} h)', flush=True)

tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(BASE, trust_remote_code=True, torch_dtype=torch.bfloat16)
model = PeftModel.from_pretrained(model, LORA).merge_and_unload().cuda().eval()
EOT = tok.convert_tokens_to_ids('<|EOT|>')
STOP = torch.tensor([EOT, tok.eos_token_id], device='cuda')
FILTERS = torch.from_numpy(librosa.filters.mel(sr=16000, n_fft=400, n_mels=128)).cuda()
WINDOW = torch.hann_window(400).cuda()
HEAD = tok('<|BOT|>human\n')['input_ids']
TAIL = tok('语音说了什么<|EOT|><|BOT|>assistant\n')['input_ids']
fds = {}


def load(src):
    if isinstance(src, tuple):
        path, skip, count = src
        fd = fds.get(path) or fds.setdefault(path, os.open(path, os.O_RDONLY))
        data = os.pread(fd, count, skip)
        if len(data) != count or data[:4] != b'RIFF':
            raise ValueError(f'bad audio bytes at {path}:{skip}+{count}')
        audio, sr = sf.read(io.BytesIO(data), dtype='float32', always_2d=True)
    else:
        audio, sr = sf.read(src, dtype='float32', always_2d=True)
    audio = audio[:, 0]
    if sr != 16000:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
    return torch.from_numpy(np.ascontiguousarray(audio))


def mel(audio):
    stft = torch.stft(F.pad(audio, (0, 479)), 400, 160, window=WINDOW, return_complex=True)
    spec = (FILTERS @ (stft[..., :-1].abs() ** 2)).clamp(min=1e-10).log10()
    return (torch.maximum(spec, spec.max() - 8.0) + 4.0) / 4.0


def n_tokens(frames):
    enc = (frames - 2 + 1) // 2 // 2
    return (enc + 2 - 3) // 2 + 1


@torch.inference_mode()
def transcribe(batch):
    mels, ids = [], []
    for _, src, _ in batch:
        audio = load(src).cuda()
        row = list(HEAD)
        for s in range(0, max(len(audio), 1), CHUNK):
            m = mel(audio[s:s + CHUNK])
            mels.append(m)
            row += tok('<audio_start>' + '<audio_patch>' * n_tokens(m.shape[1]) + '<audio_end>')['input_ids']
        ids.append(row + TAIL)
    lens = torch.tensor([m.shape[1] - 2 for m in mels], dtype=torch.int32, device='cuda')
    wavs = torch.nn.utils.rnn.pad_sequence([m.t() for m in mels], batch_first=True).transpose(1, 2).bfloat16()
    feats, feat_lens = model.encoder(wavs, lens)
    feats = model.adapter(feats)
    feat_lens = (feat_lens - 1) // 2 + 1
    embed = model.model.embed_tokens
    width = max(map(len, ids))
    emb = torch.zeros(len(ids), width, embed.embedding_dim, dtype=torch.bfloat16, device='cuda')
    mask = torch.zeros(len(ids), width, dtype=torch.long, device='cuda')
    k = 0
    for b, row in enumerate(ids):
        t = torch.tensor(row, device='cuda')
        e = embed(t)
        for s in torch.nonzero(t == AUDIO_START)[:, 0].tolist():
            e[s + 1:s + 1 + feat_lens[k]] = feats[k, :feat_lens[k]]
            k += 1
        emb[b, width - len(row):] = e
        mask[b, width - len(row):] = 1
    pos = (mask.cumsum(1) - 1).clamp(min=0)
    max_new = int(max(d for _, _, d in batch) * 10) + 32
    out = model.model(inputs_embeds=emb, attention_mask=mask, position_ids=pos, use_cache=True)
    past, last_pos = out.past_key_values, pos[:, -1:]
    nxt = model.lm_head(out.last_hidden_state[:, -1]).argmax(-1)
    gen, finished = [], torch.zeros(len(ids), dtype=torch.bool, device='cuda')
    for _ in range(max_new):
        gen.append(nxt)
        finished |= torch.isin(nxt, STOP)
        if finished.all():
            break
        mask = torch.cat([mask, torch.ones(len(ids), 1, dtype=mask.dtype, device='cuda')], 1)
        last_pos = last_pos + 1
        out = model.model(inputs_embeds=embed(nxt)[:, None], attention_mask=mask, position_ids=last_pos,
                          past_key_values=past, use_cache=True)
        past = out.past_key_values
        nxt = model.lm_head(out.last_hidden_state[:, -1]).argmax(-1)
    gen = torch.stack(gen, 1).tolist()
    rows = []
    for (cut_id, _, duration), g in zip(batch, gen):
        cut = next((j for j, x in enumerate(g) if x in (EOT, tok.eos_token_id)), None)
        text = tok.decode([x for x in g[:cut] if x < AUDIO_START]).strip()
        rows.append({'id': cut_id, 'duration': duration, 'hypothesis': text, 'truncated': cut is None})
    return rows


def batches():
    cur, secs = [], 0.0
    for t in tasks:
        if cur and (secs + t[2] > args.batch_seconds or len(cur) >= args.max_batch):
            yield cur
            cur, secs = [], 0.0
        cur.append(t)
        secs += t[2]
    if cur:
        yield cur


n = errors = 0
hours, t0, last = 0.0, time.time(), 0
with open(args.out, 'a') as sink:
    for batch in batches():
        try:
            rows = transcribe(batch)
        except Exception as e:  # noqa: BLE001  one bad file should not stop the run; retried on rerun
            torch.cuda.empty_cache()
            rows = []
            for t in batch:
                try:
                    rows += transcribe([t])
                except Exception as e1:  # noqa: BLE001
                    rows.append({'id': t[0], 'duration': t[2], 'error': repr(e1)[:300]})
        sink.write(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        n += len(rows)
        errors += sum('error' in r for r in rows)
        hours += sum(r['duration'] for r in rows) / 3600
        if n - last >= 2000 or n == len(tasks):
            last = n
            sink.flush()
            el = time.time() - t0
            print(f'{n}/{len(tasks)} {errors} errors {hours:.2f} h {el:.0f} s {hours * 3600 / el:.0f}x realtime',
                  flush=True)
