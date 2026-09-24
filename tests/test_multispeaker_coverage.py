import json
from collections import Counter

import numpy as np
import pytest
import soundfile as sf
from test_multispeaker_synthesis import SCRIPT, synthesis

from audio_data_contract import AudioRecord


def recipe_v2():
    return json.loads(SCRIPT.with_name('recipe-v2.json').read_text())


def test_coverage_has_every_speaker_count_language_mode_and_overlap_band():
    cells = synthesis.synthesis_cells(recipe_v2())
    assert len(cells) == 62
    quotas = synthesis.cell_quotas(cells, 2000000)
    assert sum(quotas) == 2000000 and min(quotas) > 0
    speakers, languages = Counter(), Counter()
    for (language, count, profile, _), amount in zip(cells, quotas):
        speakers[count] += amount
        languages[language] += amount
        if count == 1:
            assert language != 'zh-en' and profile == 'none'
    assert speakers == {number: 400000 for number in range(1, 6)}
    assert languages == {'zh': 840000, 'en': 840000, 'zh-en': 320000}
    assert all(synthesis.cell_quotas(cells, 10000))


@pytest.fixture
def conversation_pool(tmp_path, monkeypatch):
    recipe = recipe_v2()
    recipe['speaker_turn_weights'] = [0, 1, 0]
    recipe['turn_gap_seconds'] = [.1, .3]
    recipe['sources'] = [{'dataset_id': language, 'language': language, 'weight': 1}
                         for language in ['zh', 'en']]
    pools = {}
    for language in ['zh', 'en']:
        utterances = {}
        for number in range(6):
            speaker = f'{language}:{number}'
            utterances[speaker] = []
            for turn in range(2):
                path = tmp_path / f'{language}-{number}-{turn}.wav'
                waveform = (.1 * np.sin(np.arange(32000) / 16000 * 2 * np.pi * (180 + 30 * number))).astype('float32')
                waveform[:number * 320] = 0
                sf.write(path, waveform, 16000, subtype='FLOAT')
                utterances[speaker].append({
                    'source_id': path.stem, 'speaker': speaker, 'split': 'dev',
                    'dataset_id': language, 'version': '1', 'source_split': 'train',
                    'recording_id': path.stem, 'audio': {'root_alias': 'test', 'relative_path': path.name},
                    'channel': 0, 'start': 0, 'duration': 2., 'sample_rate': 16000,
                    'text': f'原文{number}句{turn}' if language == 'zh' else f'Original speaker {number} turn {turn}',
                    'language': language, 'upstream_clean_pass': True})
        pools[('dev', language)] = {'speakers': sorted(utterances), 'utterances': utterances}
    monkeypatch.setattr(synthesis, '_OUTPUT', tmp_path)
    monkeypatch.setattr(synthesis, '_RECIPE', recipe)
    monkeypatch.setattr(synthesis, '_ROOTS', {'test': str(tmp_path)})
    monkeypatch.setattr(synthesis, '_POOLS', pools)
    return tmp_path, recipe


@pytest.mark.parametrize('count,profile', [(1, 'none')] + [
    (count, profile) for count in range(2, 6) for profile in ['none', 'low', 'medium', 'high', 'dense']])
def test_full_utterances_and_speaker_revisits_reconstruct_at_controlled_overlap(conversation_pool, count, profile):
    output, recipe = conversation_pool
    language = 'zh' if count == 1 else 'zh-en'
    summary = synthesis.generate_shard(('dev', language, count, profile, 0, 2))
    directory = output / summary['key']
    records = list(synthesis.rows(directory / 'records.jsonl.gz'))
    indexes = list(synthesis.rows(directory / 'audio-index.jsonl.gz'))
    for record, index in zip(records, indexes):
        AudioRecord.from_dict(record)
        metadata = record['metadata']
        speakers, segments, quality = metadata['speakers'], metadata['segments'], metadata['quality']
        assert len({s['source_speaker'] for s in speakers}) == count
        assert len(segments) == 2 * count
        assert len(record['target'].splitlines()) == count
        assert {s['language'] for s in speakers} == ({'zh'} if count == 1 else {'zh', 'en'})
        lower, upper = recipe['overlap_profiles'][profile]['range']
        assert lower <= quality['energy_overlap_ratio'] <= upper
        assert abs(quality['energy_overlap_ratio'] - quality['target_energy_overlap_ratio']) <= recipe['overlap_tolerance']
        if profile == 'dense':
            assert quality['max_energy_concurrency'] == count
        waveform, rate = sf.read(output / index['relative_path'], dtype='float32')
        expected = np.zeros_like(waveform)
        gains = {s['label']: s['gain'] for s in speakers}
        for speaker in speakers:
            turns = sorted((s for s in segments if s['speaker'] == speaker['label']), key=lambda s: s['start'])
            assert round((turns[0]['start'] + turns[0]['duration']) * rate) <= round(turns[1]['start'] * rate)
        for segment in segments:
            assert segment['text'] in record['target']
            audio = synthesis.load_audio(segment['source'], {'test': str(output)}, rate)
            start = round(segment['start'] * rate)
            assert start + len(audio) <= len(waveform)
            expected[start:start + len(audio)] += audio * gains[segment['speaker']]
        np.testing.assert_allclose(waveform, expected, atol=1/32768 + 1e-6, rtol=0)
        assert index['duration'] <= 28 and quality['all_sources_clean_pass']
        assert metadata['primary_language'] in ('zh', 'en')


def test_invalid_overlap_configuration_is_rejected():
    recipe = recipe_v2()
    recipe['overlap_profiles']['dense']['range'] = [.9, .5]
    with pytest.raises(ValueError, match='overlap profile'):
        synthesis.synthesis_cells(recipe)
