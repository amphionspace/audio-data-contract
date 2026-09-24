#!/usr/bin/env python3
"""Prepare speaker-disjoint source pools and render reproducible SOT mixtures."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import multiprocessing
import os
import random
import re
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_data_contract import load_catalog, load_roots, resolve_artifact

# These energy intervals describe synthesis difficulty, not reference diarization.
FRAME_SECONDS = 0.02
ACTIVITY_RELATIVE_DB = -35
MAX_CANDIDATE_ATTEMPTS = 100
MP3_FRAME_SAMPLES = 1152
_POOLS = {}
_RECIPE = {}
_ROOTS = {}
_OUTPUT = None


def rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(encoded(value) + '\n', encoding='utf-8')
    temporary.replace(path)


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def speaker_split(key, recipe):
    total = sum(recipe['split_buckets'].values())
    bucket = int(hashlib.sha256(f"{recipe['seed']}:{key}".encode()).hexdigest(), 16) % total
    for split in ('train', 'dev', 'test'):
        count = recipe['split_buckets'][split]
        if bucket < count:
            return split
        bucket -= count
    raise AssertionError('Invalid split buckets')


def portable(path, roots):
    path = Path(path)
    for alias, root in sorted(roots.items(), key=lambda item: -len(str(item[1]))):
        if path.is_relative_to(root):
            return {'root_alias': alias, 'relative_path': str(path.relative_to(root))}
    raise ValueError(f'Audio path is outside configured roots: {path}')


def prepare_source(source, recipe, catalog_path, roots_path, destination):
    catalog, roots = load_catalog(catalog_path), load_roots(roots_path)
    spec = catalog.get(source['dataset_id'], source['version'])
    split = spec.splits[source['split']]

    def artifacts(kind):
        names = source.get(kind[:-1] + '_artifacts')
        if names is None:
            names = split.get(kind + '_artifacts') or [split[kind + '_artifact']]
        return [resolve_artifact(catalog, spec.dataset_id, spec.version, name, roots)
                for name in names]

    recordings_paths, supervision_paths = artifacts('recordings'), artifacts('supervisions')
    recording_index = {row['id']: row for path in recordings_paths for row in rows(path)}
    destination = Path(destination)
    temporary = destination.with_name(destination.name + '.tmp')
    counts, speakers, hours = Counter(), defaultdict(set), Counter()
    seen = set()
    lower, upper = recipe['source_seconds']
    with gzip.open(temporary, 'wt', encoding='utf-8') as stream:
        for path in supervision_paths:
            for supervision in rows(path):
                counts['input'] += 1
                clean = (supervision.get('custom') or {}).get('clean') or {}
                if source['require_clean_pass'] and clean.get('pass') is not True:
                    counts['clean_rejected'] += 1
                    continue
                speaker, text = supervision.get('speaker'), supervision.get('text', '').strip()
                if not speaker or str(speaker).lower() in {'none', 'unknown', 'null'}:
                    counts['missing_speaker'] += 1
                    continue
                if not text or re.search(r'\[S\d+\]|<\||<asr_text>', text):
                    counts['invalid_text'] += 1
                    continue
                recording = recording_index.get(supervision['recording_id'])
                start, duration = supervision['start'], supervision['duration']
                if not lower <= duration <= upper:
                    counts['duration_filtered'] += 1
                    continue
                if (recording is None or start < 0 or
                        start + duration > recording['duration'] + 1 / recording['sampling_rate']):
                    counts['invalid_bounds'] += 1
                    continue
                channels = supervision['channel']
                if isinstance(channels, list):
                    if len(channels) != 1:
                        counts['unsupported_channels'] += 1
                        continue
                    channels = channels[0]
                audio_sources = [item for item in recording['sources'] if channels in item['channels']]
                if len(audio_sources) != 1 or audio_sources[0]['type'] != 'file':
                    counts['unsupported_audio_source'] += 1
                    continue
                audio_source = audio_sources[0]
                if supervision['id'] in seen:
                    raise ValueError(f"Duplicate supervision: {spec.key}:{supervision['id']}")
                seen.add(supervision['id'])
                speaker_key = source['dataset_id'] + ':' + str(speaker)
                assigned = speaker_split(speaker_key, recipe)
                row = {
                    'source_id': supervision['id'], 'speaker': speaker_key, 'split': assigned,
                    'dataset_id': spec.dataset_id, 'version': spec.version,
                    'source_split': source['split'], 'recording_id': recording['id'],
                    'audio': portable(audio_source['source'], roots),
                    'channel': audio_source['channels'].index(channels),
                    'start': start, 'duration': duration, 'sample_rate': recording['sampling_rate'],
                    'text': ' '.join(text.split()), 'language': source['language'],
                    'upstream_clean_pass': clean.get('pass') is True,
                }
                stream.write(encoded(row) + '\n')
                counts[assigned] += 1
                hours[assigned] += duration / 3600
                speakers[assigned].add(speaker_key)
    temporary.replace(destination)
    summary = {
        'source': source, 'counts': dict(counts), 'hours': dict(hours),
        'speakers': {key: len(value) for key, value in speakers.items()},
        'pool_sha256': digest_file(destination),
        'artifacts': [{'path': portable(path, roots), 'sha256': digest_file(path)}
                      for path in recordings_paths + supervision_paths],
    }
    write_json(destination.with_suffix('.summary.json'), summary)
    print(encoded({'prepared': source['dataset_id'], **summary['counts']}), flush=True)
    return summary


def prepare(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    recipe = json.loads(args.recipe.read_text())
    recipe_path = output / 'recipe.json'
    if recipe_path.exists() and json.loads(recipe_path.read_text()) != recipe:
        raise ValueError('Output already contains a different recipe')
    write_json(recipe_path, recipe)
    pools = output / 'pools'
    pools.mkdir(exist_ok=True)
    if getattr(args, 'reuse_pools', None):
        previous = json.loads((args.reuse_pools / 'recipe.json').read_text())
        for key in ('seed', 'split_buckets', 'source_seconds', 'sources'):
            if previous[key] != recipe[key]:
                raise ValueError(f'Source-pool reuse would change {key}')
        for source in recipe['sources']:
            for suffix in ('.jsonl.gz', '.jsonl.summary.json'):
                name = source['dataset_id'] + suffix
                if not (pools / name).exists():
                    shutil.copy2(args.reuse_pools / 'pools' / name, pools / name)
    summaries = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for source in recipe['sources']:
            path = pools / (source['dataset_id'] + '.jsonl.gz')
            summary = path.with_suffix('.summary.json')
            if summary.exists():
                existing = json.loads(summary.read_text())
                if existing['source'] != source or existing['pool_sha256'] != digest_file(path):
                    raise ValueError(f'Existing pool does not match recipe: {path}')
                summaries.append(existing)
            else:
                futures.append(executor.submit(prepare_source, source, recipe,
                                               args.catalog, args.roots, path))
        summaries.extend(future.result() for future in as_completed(futures))
    roots = {key: str(value) for key, value in load_roots(args.roots).items()}
    roots['multispeaker_synthetic'] = str(output)
    write_json(output / 'roots.json', roots)
    write_json(output / 'sources.json', sorted(summaries, key=lambda item: item['source']['dataset_id']))
    print(encoded({'status': 'sources_ready', 'output': str(output)}), flush=True)


def activity(audio, rate):
    width = round(rate * FRAME_SECONDS)
    padded = np.pad(audio, (0, (-len(audio)) % width))
    rms = np.sqrt(np.mean(padded.reshape(-1, width).astype(np.float64) ** 2, axis=1))
    threshold = max(float(rms.max()) * 10 ** (ACTIVITY_RELATIVE_DB / 20), 1e-5)
    return rms > threshold


def load_audio(row, roots, rate):
    path = Path(roots[row['audio']['root_alias']]) / row['audio']['relative_path']
    with sf.SoundFile(path) as stream:
        if stream.samplerate != row['sample_rate']:
            raise ValueError(f"Source rate changed: {row['source_id']}")
        stream.seek(round(row['start'] * stream.samplerate))
        count = round(row['duration'] * stream.samplerate)
        waveform = stream.read(count, dtype='float32', always_2d=True)
        # Some MP3 headers overstate the complete decoded length by < one frame.
        # Accept the actual EOF only for a whole-file read, never a truncated segment.
        whole_mp3 = stream.format == 'MP3' and row['start'] == 0 and abs(count - stream.frames) <= 1
        allowance = MP3_FRAME_SAMPLES if whole_mp3 else 1
        if len(waveform) < count - allowance:
            raise ValueError(f"Short audio: {row['source_id']}")
        waveform = waveform[:, row['channel']]
    if row['sample_rate'] != rate:
        from scipy.signal import resample_poly

        divisor = math.gcd(row['sample_rate'], rate)
        waveform = resample_poly(waveform, rate // divisor, row['sample_rate'] // divisor)
    if not np.isfinite(waveform).all() or not activity(waveform, rate).any():
        raise ValueError(f"Invalid or silent audio: {row['source_id']}")
    return waveform


def synthesis_cells(recipe):
    """Return language/count/overlap cells with explicit sampling probabilities."""
    if 'overlap_profiles' not in recipe:
        values = list(itertools.product(['zh', 'en'], recipe['speakers'], recipe['profiles']))
        return [(*cell, 1 / len(values)) for cell in values]
    profiles = recipe['overlap_profiles']
    if (not profiles or not recipe['speakers'] or len(set(recipe['speakers'])) != len(recipe['speakers'])
            or len(recipe['overlap_beta']) != 2 or min(recipe['overlap_beta']) <= 0
            or not 0 <= recipe['overlap_tolerance'] <= 1
            or type(recipe['overlap_search_steps']) is not int or recipe['overlap_search_steps'] < 2):
        raise ValueError('Invalid speaker coverage or overlap distribution/search settings')
    for name, spec in profiles.items():
        lower, upper = spec['range']
        if not 0 <= lower <= upper <= 1 or spec['weight'] <= 0:
            raise ValueError(f'Invalid overlap profile: {name}')
        if 'turn_duration_tolerance' in spec and not 0 <= spec['turn_duration_tolerance'] < 1:
            raise ValueError(f'Invalid turn duration tolerance: {name}')
    result = []
    for count in recipe['speakers']:
        if type(count) is not int or not 1 <= count <= 5:
            raise ValueError('Speaker counts must be integers from 1 to 5')
        languages = {key: value for key, value in recipe['language_modes'].items()
                     if count > 1 or key != 'zh-en'}
        eligible = {key: value for key, value in profiles.items()
                    if count > 1 or value['range'] == [0, 0]}
        if not eligible:
            raise ValueError('Single-speaker synthesis requires a zero-overlap profile')
        for language, weight in languages.items():
            if language not in ('zh', 'en', 'zh-en') or weight <= 0:
                raise ValueError('Language modes must be zh/en/zh-en with positive weights')
            for profile, spec in eligible.items():
                probability = (weight / sum(languages.values()) / len(recipe['speakers'])
                               * spec['weight'] / sum(item['weight'] for item in eligible.values()))
                result.append((language, count, profile, probability))
    return result


def cell_quotas(cells, amount):
    expected = [amount * cell[3] for cell in cells]
    quotas = [math.floor(value + 1e-8) for value in expected]
    remainder = amount - sum(quotas)
    for index in sorted(range(len(cells)), key=lambda i: expected[i] - quotas[i], reverse=True)[:remainder]:
        quotas[index] += 1
    return quotas


def choose_conversation_tracks(split, language, count, profile, rng):
    spec = _RECIPE['overlap_profiles'][profile]
    lower, upper = spec['range']
    middle = (lower + upper) / 2
    gap_max = _RECIPE['turn_gap_seconds'][1]
    budget = (_RECIPE['max_mix_seconds'] - gap_max * (2 * count - 1)) / (count * (1 - middle) + middle)
    languages = [language] * count
    if language == 'zh-en':
        if count < 2:
            raise ValueError('Mixed-speaker bilingual audio needs at least two speakers')
        chinese = rng.randrange(1, count)
        languages = ['zh'] * chinese + ['en'] * (count - chinese)
        rng.shuffle(languages)
    selected, used = [], set()
    for wanted in languages:
        sources = [source for source in _RECIPE['sources'] if source['language'] == wanted]
        # Dense mixtures need comparable full turns: offsets cannot overlap a short
        # reply with an arbitrarily longer monologue at a high global ratio.
        reference = selected[0]['turns'] if selected and 'turn_duration_tolerance' in spec else None
        for _ in range(200):
            source = rng.choices(sources, weights=[item['weight'] for item in sources])[0]
            available = _POOLS[(split, source['dataset_id'])]
            speaker = rng.choice(available['speakers'])
            choices = [row for row in available['utterances'][speaker] if row['duration'] <= budget]
            if speaker in used or not choices:
                continue
            requested = len(reference) if reference else rng.choices([1, 2, 3], weights=_RECIPE['speaker_turn_weights'])[0]
            chosen, duration, used_ids = [], 0.0, set()
            for number in range(requested):
                remaining = [row for row in choices if row['source_id'] not in used_ids
                             and duration + row['duration'] <= budget]
                if reference:
                    target = reference[number]['duration']
                    tolerance = spec['turn_duration_tolerance']
                    remaining = [row for row in remaining if abs(row['duration'] / target - 1) <= tolerance]
                if not remaining:
                    break
                row = rng.choice(remaining)
                chosen.append(row)
                duration += row['duration'] + gap_max
                used_ids.add(row['source_id'])
            if chosen and (not reference or len(chosen) == len(reference)):
                break
        else:
            raise ValueError('Insufficient distinct speakers within the complete-utterance budget')
        used.add(speaker)
        turns = []
        for row in chosen:
            waveform = load_audio(row, _ROOTS, _RECIPE['sampling_rate'])
            turns.append({'source': row, 'audio': waveform,
                          'duration': len(waveform) / _RECIPE['sampling_rate']})
        selected.append({'speaker': speaker, 'turns': turns})
    return selected


def mix_conversation(tracks, profile, rng, recipe):
    """Tune turn offsets against measured activity; never crop source utterances."""
    rate = recipe['sampling_rate']
    frame = round(rate * FRAME_SECONDS)
    lower, upper = recipe['overlap_profiles'][profile]['range']
    target = lower + (upper - lower) * rng.betavariate(*recipe['overlap_beta'])
    tolerance = recipe['overlap_tolerance']
    turns = []
    positions = [0] * len(tracks)
    previous, cursor = None, 0
    while any(positions[i] < len(track['turns']) for i, track in enumerate(tracks)):
        available = [i for i, track in enumerate(tracks) if positions[i] < len(track['turns'])]
        alternative = [i for i in available if i != previous]
        speaker = rng.choice(alternative or available)
        turn = tracks[speaker]['turns'][positions[speaker]]
        active = activity(turn['audio'], rate)
        turns.append({**turn, 'speaker_index': speaker, 'active': active, 'sequential_start': cursor})
        gap = round(rng.uniform(*recipe['turn_gap_seconds']) / FRAME_SECONDS)
        cursor += len(active) + gap
        positions[speaker] += 1
        previous = speaker

    def schedule(compression):
        ends, offsets = [0] * len(tracks), []
        for turn in turns:
            speaker = turn['speaker_index']
            start = max(round(turn['sequential_start'] * (1 - compression)), ends[speaker])
            offsets.append(start)
            ends[speaker] = start + len(turn['active'])
        concurrency = np.zeros(max(ends), dtype=np.int16)
        for turn, start in zip(turns, offsets):
            concurrency[start:start + len(turn['active'])] += turn['active']
        active_count = np.count_nonzero(concurrency)
        overlap = float(np.count_nonzero(concurrency >= 2) / active_count)
        return offsets, concurrency, overlap

    best = None
    # A bounded grid also handles non-monotonic changes caused by internal pauses.
    for compression in ([0.0] if upper == 0 else np.linspace(0, 1, recipe['overlap_search_steps'])):
        offsets, concurrency, overlap = schedule(compression)
        samples = max(start * frame + len(turn['audio']) for turn, start in zip(turns, offsets))
        if (samples <= round(recipe['max_mix_seconds'] * rate) and lower <= overlap <= upper
                and abs(overlap - target) <= tolerance
                and (not recipe['overlap_profiles'][profile].get('all_speakers_overlap')
                     or int(concurrency.max()) == len(tracks))):
            distance = abs(overlap - target)
            if best is None or distance < best[0]:
                best = distance, offsets, concurrency, overlap, samples
    if best is None:
        return None
    _, offsets, concurrency, overlap, samples = best
    mixture = np.zeros(samples, dtype=np.float32)
    scheduled = []
    for number, track in enumerate(tracks):
        selected = [(turn, start) for turn, start in zip(turns, offsets) if turn['speaker_index'] == number]
        energy, active_samples = 0.0, 0
        for turn, _ in selected:
            mask = np.repeat(turn['active'], frame)[:len(turn['audio'])]
            values = turn['audio'][mask].astype(np.float64)
            energy += float(np.dot(values, values))
            active_samples += len(values)
        rms = math.sqrt(energy / active_samples)
        gain_db = rng.uniform(*recipe['speaker_gain_db'])
        gain = 10 ** ((-26 + gain_db) / 20) / max(rms, 1e-8)
        new_turns = []
        for turn, start in selected:
            position = start * frame
            mixture[position:position + len(turn['audio'])] += turn['audio'] * gain
            new_turns.append({'source': turn['source'], 'duration': turn['duration'],
                              'track_start': position / rate})
        first = min((start + int(np.flatnonzero(turn['active'])[0])) * FRAME_SECONDS
                    for turn, start in selected)
        scheduled.append({'speaker': track['speaker'], 'turns': new_turns, 'offset': 0.0,
                          'first_active': first, 'gain': gain, 'relative_gain_db': gain_db})
    scale = rng.uniform(0.75, 0.95) / float(np.abs(mixture).max())
    mixture *= scale
    scheduled.sort(key=lambda track: track['first_active'])
    for track in scheduled:
        track['gain'] *= scale
    return mixture, scheduled, {
        'target_energy_overlap_ratio': target, 'energy_overlap_ratio': overlap,
        'overlap_range': [lower, upper], 'overlap_absolute_error': abs(overlap - target),
        'max_energy_concurrency': int(concurrency.max()),
        'energy_silence_ratio': float(np.count_nonzero(concurrency == 0) / len(concurrency)),
        'energy_activity_seconds_by_concurrency': {
            str(number): int(np.count_nonzero(concurrency == number)) * FRAME_SECONDS
            for number in range(len(tracks) + 1)},
        'output_peak': float(np.abs(mixture).max()),
    }


def mix_tracks(tracks, profile, rng, recipe):
    if 'overlap_profiles' in recipe:
        return mix_conversation(tracks, profile, rng, recipe)
    rate = recipe['sampling_rate']
    frame = round(rate * FRAME_SECONDS)
    starts = [0]
    for previous in tracks[:-1]:
        delay = (rng.uniform(0.2, 0.6) if profile == 'dense'
                 else len(previous['audio']) / rate * rng.uniform(0.45, 0.8))
        starts.append(starts[-1] + round(delay / FRAME_SECONDS) * frame)
    length = max(start + len(track['audio']) for start, track in zip(starts, tracks))
    if length > round(recipe['max_mix_seconds'] * rate):
        return None
    mixture = np.zeros(length, dtype=np.float32)
    concurrency = np.zeros(math.ceil(length / frame), dtype=np.int16)
    scheduled = []
    for start, track in zip(starts, tracks):
        audio = track['audio']
        active = activity(audio, rate)
        sample_mask = np.repeat(active, frame)[:len(audio)]
        rms = float(np.sqrt(np.mean(audio[sample_mask].astype(np.float64) ** 2)))
        gain_db = rng.uniform(*recipe['speaker_gain_db'])
        gain = 10 ** ((-26 + gain_db) / 20) / max(rms, 1e-8)
        mixture[start:start + len(audio)] += audio * gain
        concurrency[start // frame:start // frame + len(active)] += active
        scheduled.append({**track, 'offset': start / rate, 'gain': gain, 'relative_gain_db': gain_db,
                          'first_active': start / rate + int(np.flatnonzero(active)[0]) * FRAME_SECONDS})
    active_frames = int(np.count_nonzero(concurrency))
    overlap = float(np.count_nonzero(concurrency >= 2) / active_frames)
    maximum = int(concurrency.max())
    if profile == 'dense' and (overlap < 0.65 or maximum != len(tracks)):
        return None
    if profile == 'staggered' and not 0.15 <= overlap <= 0.65:
        return None
    scale = rng.uniform(0.75, 0.95) / float(np.abs(mixture).max())
    mixture *= scale
    scheduled.sort(key=lambda track: track['first_active'])
    for track in scheduled:
        track['gain'] *= scale
    return mixture, scheduled, {
        'energy_overlap_ratio': overlap, 'max_energy_concurrency': maximum,
        'energy_activity_seconds_by_concurrency': {
            str(number): int(np.count_nonzero(concurrency == number)) * FRAME_SECONDS
            for number in range(len(tracks) + 1)
        },
        'output_peak': float(np.abs(mixture).max()),
    }


def choose_tracks(split, language, count, profile, rng):
    if 'overlap_profiles' in _RECIPE:
        return choose_conversation_tracks(split, language, count, profile, rng)
    sources = [source for source in _RECIPE['sources'] if source['language'] == language]
    selected, used = [], set()
    # Bound each complete speaker track using the maximum delay in mix_tracks.
    # Dense mixtures can retain long source utterances without truncating labels.
    budget = (_RECIPE['max_mix_seconds'] - 0.6 * (count - 1) if profile == 'dense'
              else _RECIPE['max_mix_seconds'] / (1 + 0.8 * (count - 1)))
    for _ in range(200):
        if len(selected) == count:
            return selected
        source = rng.choices(sources, weights=[item['weight'] for item in sources])[0]
        available = _POOLS[(split, source['dataset_id'])]
        speaker = rng.choice(available['speakers'])
        if speaker in used:
            continue
        choices = [row for row in available['utterances'][speaker] if row['duration'] <= budget]
        if not choices:
            continue
        used.add(speaker)
        utterances = [rng.choice(choices)]
        remaining = [row for row in choices if row['source_id'] != utterances[0]['source_id']
                     and row['duration'] + utterances[0]['duration'] + 0.9 <= budget]
        if remaining and rng.random() < _RECIPE['second_turn_probability']:
            utterances.append(rng.choice(remaining))
        waveform, turns, cursor = [], [], 0
        for index, row in enumerate(utterances):
            if index:
                gap = np.zeros(round(rng.uniform(0.3, 0.9) * _RECIPE['sampling_rate']), dtype=np.float32)
                waveform.append(gap)
                cursor += len(gap)
            audio = load_audio(row, _ROOTS, _RECIPE['sampling_rate'])
            turns.append({'source': row, 'track_start': cursor / _RECIPE['sampling_rate'],
                          'duration': len(audio) / _RECIPE['sampling_rate']})
            waveform.append(audio)
            cursor += len(audio)
        selected.append({'speaker': speaker, 'audio': np.concatenate(waveform), 'turns': turns})
    raise ValueError('Insufficient distinct speakers with utterances inside the duration budget')


def generate_shard(job):
    split, language, count, profile, shard, size = job
    key = f'{split}/{language}/{count}spk/{profile}/{shard:05d}'
    directory = _OUTPUT / key
    directory.mkdir(parents=True, exist_ok=True)
    summary_path = directory / 'summary.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        if summary['records'] != size:
            raise ValueError('Shard size changed; use a new output directory')
        return summary
    rng = random.Random(int(hashlib.sha256(f"{_RECIPE['seed']}:{key}".encode()).hexdigest(), 16))
    summary = {'key': key, 'split': split, 'language': language, 'speakers': count, 'profile': profile,
               'records': size, 'duration_hours': 0.0, 'attempts': 0, 'decode_rejections': 0,
               'max_sample_attempts': 0,
               'overlap_sum': 0.0, 'sources': Counter(), 'speaker_turns': Counter()}
    max_attempts = _RECIPE.get('max_candidate_attempts', MAX_CANDIDATE_ATTEMPTS)
    record_path, index_path = directory / 'records.jsonl.gz', directory / 'audio-index.jsonl.gz'
    with (gzip.open(str(record_path) + '.tmp', 'wt', encoding='utf-8') as records,
          gzip.open(str(index_path) + '.tmp', 'wt', encoding='utf-8') as index,
          (directory / 'rejections.jsonl').open('w') as rejected):
        for item in range(size):
            for attempt in range(max_attempts):
                summary['attempts'] += 1
                try:
                    tracks = choose_tracks(split, language, count, profile, rng)
                    result = mix_tracks(tracks, profile, rng, _RECIPE)
                except (OSError, ValueError, RuntimeError) as exc:
                    summary['decode_rejections'] += 1
                    rejected.write(encoded({'sample': item, 'attempt': attempt, 'error': str(exc)}) + '\n')
                    continue
                if result is not None:
                    break
            else:
                raise RuntimeError(f'Unable to generate {key}:{item} after {max_attempts} attempts')
            summary['max_sample_attempts'] = max(summary['max_sample_attempts'], attempt + 1)
            waveform, scheduled, quality = result
            record_id = key.replace('/', '-') + f'-{item:04d}'
            audio_path = directory / f'{item:04d}.flac'
            sf.write(str(audio_path) + '.tmp', waveform, _RECIPE['sampling_rate'], format='FLAC', subtype='PCM_16')
            Path(str(audio_path) + '.tmp').replace(audio_path)
            duration = len(waveform) / _RECIPE['sampling_rate']
            speakers, segments, targets = [], [], []
            for number, track in enumerate(scheduled, 1):
                label = f'S{number}'
                text = ' '.join(turn['source']['text'] for turn in track['turns'])
                targets.append(f'[{label}] {text}')
                speakers.append({'label': label, 'source_speaker': track['speaker'], 'text': text,
                                 'language': track['turns'][0]['source']['language'],
                                 'first_active': track['first_active'], 'gain': track['gain'],
                                 'relative_gain_db': track['relative_gain_db']})
                summary['speaker_turns'][str(len(track['turns']))] += 1
                for turn in track['turns']:
                    segments.append({'speaker': label, 'start': track['offset'] + turn['track_start'],
                                     'duration': turn['duration'], 'text': turn['source']['text'],
                                     'decode_duration_delta_seconds': turn['duration'] - turn['source']['duration'],
                                     'source': turn['source']})
                    summary['sources'][turn['source']['dataset_id']] += 1
            quality['all_sources_clean_pass'] = all(segment['source']['upstream_clean_pass'] for segment in segments)
            language_seconds = Counter()
            for segment in segments:
                language_seconds[segment['source']['language']] += segment['duration']
            record = {
                'schema_version': 'audio-record/1.0', 'id': record_id, 'task': 'speaker_attributed_asr',
                'audio_slots': [{'name': 'mixture', 'ref': {'dataset_id': _RECIPE['dataset_id'],
                    'version': _RECIPE['version'], 'split': split, 'cut_id': record_id, 'duration': duration}}],
                'target': '\n'.join(targets), 'language': language,
                'labels': {'speaker_count': count, 'profile': profile},
                'metadata': {'speakers': speakers, 'segments': segments, 'quality': quality,
                             'primary_language': max(language_seconds, key=language_seconds.get),
                             'recipe_seed': _RECIPE['seed'], 'shard': key},
            }
            records.write(encoded(record) + '\n')
            index.write(encoded({'cut_id': record_id, 'root_alias': 'multispeaker_synthetic',
                'relative_path': str(audio_path.relative_to(_OUTPUT)), 'sample_rate': _RECIPE['sampling_rate'],
                'channels': 1, 'num_frames': len(waveform), 'duration': duration}) + '\n')
            summary['duration_hours'] += duration / 3600
            summary['overlap_sum'] += quality['energy_overlap_ratio']
    Path(str(record_path) + '.tmp').replace(record_path)
    Path(str(index_path) + '.tmp').replace(index_path)
    summary['manifest_sha256'] = {'records': digest_file(record_path), 'audio_index': digest_file(index_path)}
    write_json(summary_path, summary)
    return summary


def publish(output, recipe, completed, requested, status, started):
    artifacts, splits, total = [], {}, 0
    for split in requested:
        selected = sorted((item for item in completed if item['split'] == split), key=lambda item: item['key'])
        names = []
        for item in selected:
            name = item['key'].replace('/', '-') + '-records'
            names.append(name)
            artifacts.append({'name': name, 'kind': 'audio-records',
                'root_alias': 'multispeaker_synthetic', 'relative_path': item['key'] + '/records.jsonl.gz',
                'sha256': item['manifest_sha256']['records'], 'metadata': {'record_count': item['records']}})
        records = sum(item['records'] for item in selected)
        total += records
        if selected:
            index_name = split + '-audio-index'
            index_path = output / 'indexes' / (split + '.jsonl.gz')
            artifacts.append({'name': index_name, 'kind': 'audio-index',
                'root_alias': 'multispeaker_synthetic', 'relative_path': str(index_path.relative_to(output)),
                'metadata': {'record_count': records},
                **({'sha256': digest_file(index_path)} if status == 'complete' else {})})
            splits[split] = {'records_artifacts': names, 'audio_index_artifact': index_name,
                'statistics': {'records': records, 'duration_hours': sum(item['duration_hours'] for item in selected),
                               'duration_basis': 'Rendered mixture duration; source speech counted once per output timeline'}}
    spec = {'schema_version': 'dataset-catalog/1.0', 'dataset_id': recipe['dataset_id'],
        'version': recipe['version'], 'languages': list(recipe.get('language_modes', ['zh', 'en'])), 'tasks': ['speaker_attributed_asr'],
        'artifacts': artifacts, 'splits': splits, 'recipe_parameters': recipe,
        'provenance': {'synthetic': True, 'status': status, 'source_manifest_audit': 'sources.json',
            'speaker_partition': 'SHA256(seed:dataset_id:speaker_id); no cross-corpus identity verification',
            'ordering': 'First 20ms source-energy-active frame; IDs are local to the mixture',
            'activity_estimator': {'frame_seconds': FRAME_SECONDS, 'relative_db': ACTIVITY_RELATIVE_DB},
            'clean_policy': 'Prefer applicable clean training sources; quality of original labels is retained otherwise',
            'label_scope': 'Complete utterance transcripts with source intervals; no word-level timestamps'}}
    if splits:
        write_json(output / 'catalog.jsonl', spec)
    write_json(output / 'progress.json', {'status': status, 'pid': os.getpid(), 'started': started,
        'updated': time.time(), 'requested': requested, 'completed_records': total,
        'completed_by_split': {key: value['statistics'] for key, value in splits.items()},
        'completed_shards': len(completed), 'decode_rejections': sum(item['decode_rejections'] for item in completed)})


def append_index(output, summary):
    # gzip permits concatenated members. Only complete, closed shard indexes are appended.
    source = output / summary['key'] / 'audio-index.jsonl.gz'
    destination = output / 'indexes' / (summary['split'] + '.jsonl.gz')
    with source.open('rb') as incoming, destination.open('ab') as outgoing:
        for block in iter(lambda: incoming.read(1024 * 1024), b''):
            outgoing.write(block)


def generate(args):
    global _RECIPE, _ROOTS, _OUTPUT
    _OUTPUT = args.output.resolve()
    _RECIPE = json.loads((_OUTPUT / 'recipe.json').read_text())
    _ROOTS = json.loads((_OUTPUT / 'roots.json').read_text())
    audit = {item['source']['dataset_id']: item for item in json.loads((_OUTPUT / 'sources.json').read_text())}
    heldout = {}
    for source in _RECIPE['sources']:
        path = _OUTPUT / 'pools' / (source['dataset_id'] + '.jsonl.gz')
        if digest_file(path) != audit[source['dataset_id']]['pool_sha256']:
            raise ValueError(f'Source pool changed: {path}')
        groups = defaultdict(lambda: defaultdict(list))
        for row in rows(path):
            groups[row['split']][row['speaker']].append(row)
        for split, speakers in groups.items():
            _POOLS[(split, source['dataset_id'])] = {'speakers': sorted(speakers), 'utterances': dict(speakers)}
        heldout[source['dataset_id']] = {split: sorted(groups[split]) for split in ('dev', 'test')}
        print(encoded({'loaded': source['dataset_id'], 'speakers': {key: len(value) for key, value in groups.items()}}), flush=True)
    # Ordinary-ASR replay must exclude these identities too when evaluating this holdout.
    write_json(_OUTPUT / 'heldout-speakers.json', heldout)
    requested = {'dev': args.dev, 'test': args.test, 'train': args.train}
    cells = synthesis_cells(_RECIPE)
    jobs = []
    for split, amount in requested.items():
        counts = cell_quotas(cells, amount)
        for offset in range(0, max(counts, default=0), args.shard_size):
            for (language, count, profile, _), per_cell in zip(cells, counts):
                if offset < per_cell:
                    jobs.append((split, language, count, profile, offset // args.shard_size, min(args.shard_size, per_cell - offset)))
    # Persist the job plan: changing counts/shard boundaries cannot silently reuse samples.
    plan = {'counts': requested, 'shard_size': args.shard_size}
    plan_path = _OUTPUT / 'generation-plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError('Generation plan changed; use a new output directory')
    write_json(plan_path, plan)
    completed, started = [], time.time()
    (args.output / 'indexes').mkdir(exist_ok=True)
    for split in requested:
        # Resume reconstructs these derived indexes from committed shard manifests.
        (args.output / 'indexes' / (split + '.jsonl.gz')).write_bytes(b'')
    publish(_OUTPUT, _RECIPE, completed, requested, 'generating', started)
    executor = ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('fork'))
    futures = []
    try:
        # Linux fork shares immutable source metadata across workers; audio stays local.
        futures = [executor.submit(generate_shard, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            append_index(_OUTPUT, result)
            completed.append(result)
            publish(_OUTPUT, _RECIPE, completed, requested, 'generating', started)
            print(encoded({'shard_complete': result['key'], 'records': result['records'],
                           'completed': sum(item['records'] for item in completed)}), flush=True)
    except BaseException:
        for future in futures:
            future.cancel()
        publish(_OUTPUT, _RECIPE, completed, requested, 'failed', started)
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    publish(_OUTPUT, _RECIPE, completed, requested, 'complete', started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    preparing = commands.add_parser('prepare')
    preparing.add_argument('--recipe', type=Path, default=Path(__file__).with_name('recipe.json'))
    preparing.add_argument('--catalog', type=Path, required=True)
    preparing.add_argument('--roots', type=Path, required=True)
    preparing.add_argument('--workers', type=int, default=4)
    preparing.add_argument('--output', type=Path, required=True)
    preparing.add_argument('--reuse-pools', type=Path,
                           help='Reuse pools with identical sources and speaker partition')
    generating = commands.add_parser('generate')
    generating.add_argument('--output', type=Path, required=True)
    generating.add_argument('--workers', type=int, default=16)
    generating.add_argument('--train', type=int, default=1200000)
    generating.add_argument('--dev', type=int, default=6000)
    generating.add_argument('--test', type=int, default=6000)
    generating.add_argument('--shard-size', type=int, default=500)
    args = parser.parse_args()
    if args.workers <= 0 or (args.command == 'generate' and
                            (args.shard_size <= 0 or min(args.train, args.dev, args.test) < 0)):
        parser.error('Workers/shard size must be positive, counts nonnegative')
    (prepare if args.command == 'prepare' else generate)(args)


if __name__ == '__main__':
    main()
