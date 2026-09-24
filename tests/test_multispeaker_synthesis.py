import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio_data_contract import AudioRecord, load_catalog

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'multispeaker' / 'synthesize.py'
SPEC = importlib.util.spec_from_file_location('multispeaker_synthesize', SCRIPT)
synthesis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(synthesis)


def test_speaker_partition_is_stable_across_json_order_and_utterances():
    recipe = {'seed': 42, 'split_buckets': {'train': 960, 'dev': 20, 'test': 20}}
    reordered = json.loads(json.dumps(recipe, sort_keys=True))
    groups = {key: set() for key in recipe['split_buckets']}
    for index in range(1000):
        speaker = f'corpus:{index}'
        assigned = synthesis.speaker_split(speaker, recipe)
        assert assigned == synthesis.speaker_split(speaker, reordered)
        groups[assigned].add(speaker)
    assert all(groups.values())
    assert not groups['train'] & groups['dev']
    assert not groups['train'] & groups['test']
    assert not groups['dev'] & groups['test']


def test_prepare_filters_clean_flags_missing_speakers_and_invalid_bounds(tmp_path):
    audio = tmp_path / 'source.wav'
    sf.write(audio, np.ones(40000) * .1, 16000)
    recording = {'id': 'recording', 'sampling_rate': 16000, 'duration': 2.5,
                 'sources': [{'type': 'file', 'channels': [0], 'source': str(audio)}]}
    (tmp_path / 'recordings.jsonl').write_text(json.dumps(recording) + '\n')
    base = {'recording_id': 'recording', 'start': 0, 'duration': 2.5, 'channel': 0,
            'text': '原始完整文字', 'speaker': 'person'}
    examples = [{**base, 'id': str(index), 'custom': {'clean': {'pass': flag}}}
                for index, flag in enumerate([True, False, 'true', 1, None])]
    examples += [{**examples[0], 'id': 'missing-speaker', 'speaker': None},
                 {**examples[0], 'id': 'outside', 'start': 1}]
    (tmp_path / 'supervisions.jsonl').write_text('\n'.join(map(json.dumps, examples)))
    spec = {'schema_version': 'dataset-catalog/1.0', 'dataset_id': 'test', 'version': '1',
            'languages': ['zh'], 'tasks': ['asr'],
            'artifacts': [{'name': kind, 'kind': 'lhotse-' + kind, 'root_alias': 'test',
                           'relative_path': kind + '.jsonl'} for kind in ('recordings', 'supervisions')],
            'splits': {'train': {'recordings_artifact': 'recordings', 'supervisions_artifact': 'supervisions'}}}
    catalog, roots = tmp_path / 'catalog.jsonl', tmp_path / 'roots.json'
    catalog.write_text(json.dumps(spec) + '\n')
    roots.write_text(json.dumps({'test': str(tmp_path)}))
    source = {'dataset_id': 'test', 'version': '1', 'split': 'train', 'language': 'zh',
              'require_clean_pass': True}
    recipe = {'seed': 42, 'source_seconds': [2, 8], 'split_buckets': {'train': 960, 'dev': 20, 'test': 20}}
    pool = tmp_path / 'pool.jsonl.gz'
    result = synthesis.prepare_source(source, recipe, catalog, roots, pool)
    assert result['counts']['clean_rejected'] == 4
    assert result['counts']['missing_speaker'] == result['counts']['invalid_bounds'] == 1
    records = list(synthesis.rows(pool))
    assert len(records) == 1 and records[0]['text'] == base['text']
    assert records[0]['audio'] == {'root_alias': 'test', 'relative_path': 'source.wav'}
    source['require_clean_pass'] = False
    synthesis.prepare_source(source, recipe, catalog, roots, tmp_path / 'raw.jsonl.gz')
    assert len(list(synthesis.rows(tmp_path / 'raw.jsonl.gz'))) == 5


@pytest.mark.parametrize('count', [3, 4, 5])
@pytest.mark.parametrize('profile', ['staggered', 'dense'])
def test_render_preserves_every_speaker_turn_and_reconstructs_waveform(tmp_path, monkeypatch, count, profile):
    recipe = json.loads(SCRIPT.with_name('recipe.json').read_text())
    recipe['second_turn_probability'] = 1.0
    recipe['sources'] = [{'dataset_id': 'test', 'language': 'zh', 'weight': 1}]
    utterances = {}
    for number in range(6):
        speaker = f'test:{number}'
        utterances[speaker] = []
        for turn in range(2):
            path = tmp_path / f'source-{number}-{turn}.wav'
            waveform = (.1 * np.sin(np.arange(32000) / 16000 * 2 * np.pi * (180 + number * 30))).astype('float32')
            # Include leading silence to exercise ordering by detected source activity.
            waveform[:number * 320] = 0
            sf.write(path, waveform, 16000, subtype='FLOAT')
            utterances[speaker].append({'source_id': f'{number}-{turn}', 'speaker': speaker,
                'split': 'dev', 'dataset_id': 'test', 'version': '1', 'source_split': 'train',
                'recording_id': f'{number}-{turn}', 'audio': {'root_alias': 'test', 'relative_path': path.name},
                'channel': 0, 'start': 0, 'duration': 2.0, 'sample_rate': 16000,
                'text': f'完整文字{number}句{turn}', 'language': 'zh', 'upstream_clean_pass': True})
    monkeypatch.setattr(synthesis, '_OUTPUT', tmp_path)
    monkeypatch.setattr(synthesis, '_RECIPE', recipe)
    monkeypatch.setattr(synthesis, '_ROOTS', {'test': str(tmp_path)})
    monkeypatch.setattr(synthesis, '_POOLS', {('dev', 'test'): {
        'speakers': sorted(utterances), 'utterances': utterances}})
    job = ('dev', 'zh', count, profile, 0, 3)
    summary = synthesis.generate_shard(job)
    directory = tmp_path / summary['key']
    records = list(synthesis.rows(directory / 'records.jsonl.gz'))
    indexes = list(synthesis.rows(directory / 'audio-index.jsonl.gz'))
    for record, index in zip(records, indexes):
        AudioRecord.from_dict(record)
        metadata = record['metadata']
        speakers, segments = metadata['speakers'], metadata['segments']
        assert len(speakers) == len({item['source_speaker'] for item in speakers}) == count
        assert len(segments) == count * 2
        assert [item['first_active'] for item in speakers] == sorted(item['first_active'] for item in speakers)
        assert len(record['target'].splitlines()) == count
        assert all(segment['text'] in record['target'] for segment in segments)
        assert all(len([segment for segment in segments if segment['speaker'] == item['label']]) == 2 for item in speakers)
        waveform, rate = sf.read(tmp_path / index['relative_path'], dtype='float32')
        assert rate == 16000 and len(waveform) == index['num_frames']
        assert index['duration'] <= 28 and np.isfinite(waveform).all() and np.abs(waveform).max() < 1
        expected = np.zeros_like(waveform)
        gains = {item['label']: item['gain'] for item in speakers}
        for segment in segments:
            source = synthesis.load_audio(segment['source'], {'test': str(tmp_path)}, rate)
            start = round(segment['start'] * rate)
            assert start + len(source) <= len(expected)
            expected[start:start + len(source)] += source * gains[segment['speaker']]
        np.testing.assert_allclose(waveform, expected, atol=1 / 32768 + 1e-6, rtol=0)
        quality = metadata['quality']
        if profile == 'dense':
            assert quality['energy_overlap_ratio'] >= .65
            assert quality['max_energy_concurrency'] == count
        else:
            assert .15 <= quality['energy_overlap_ratio'] <= .65
        assert quality['all_sources_clean_pass'] is True
        assert 'clean' not in metadata  # Mixing does not fabricate upstream cleaning approval.
    assert synthesis.generate_shard(job) == summary
    (tmp_path / 'indexes').mkdir()
    synthesis.append_index(tmp_path, summary)
    synthesis.publish(tmp_path, recipe, [summary], {'dev': 3}, 'complete', 0)
    catalog = load_catalog(tmp_path / 'catalog.jsonl')
    split = catalog.get(recipe['dataset_id'], recipe['version']).splits['dev']
    assert 'audio_index_artifact' in split
    assert len(list(synthesis.rows(tmp_path / 'indexes' / 'dev.jsonl.gz'))) == 3


def test_resampling_keeps_the_complete_source_interval(tmp_path):
    pytest.importorskip('scipy')
    path = tmp_path / '48khz.wav'
    waveform = np.sin(np.arange(48000) * 2 * np.pi * 300 / 48000).astype('float32') * .1
    sf.write(path, waveform, 48000, subtype='FLOAT')
    row = {'audio': {'root_alias': 'test', 'relative_path': path.name},
           'sample_rate': 48000, 'start': .25, 'duration': .5, 'channel': 0, 'source_id': 'example'}
    result = synthesis.load_audio(row, {'test': str(tmp_path)}, 16000)
    assert len(result) == 8000 and np.isfinite(result).all()


@pytest.mark.parametrize('format,missing,start,accepted', [
    ('MP3', 966, 0, True), ('MP3', 1153, 0, False),
    ('WAV', 966, 0, False), ('MP3', 966, .25, False),
])
def test_mp3_header_rounding_does_not_reject_complete_audio(monkeypatch, format, missing, start, accepted):
    class Decoder:
        samplerate = 16000
        frames = 32000

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def seek(self, position):
            pass

        def read(self, count, **kwargs):
            return np.full((count - missing, 1), .1, dtype='float32')

    Decoder.format = format
    monkeypatch.setattr(sf, 'SoundFile', lambda path: Decoder())
    row = {'audio': {'root_alias': 'test', 'relative_path': 'example.mp3'},
           'sample_rate': 16000, 'start': start, 'duration': 2.0, 'channel': 0, 'source_id': 'example'}
    if accepted:
        result = synthesis.load_audio(row, {'test': '/unused'}, 16000)
        assert len(result) == 32000 - missing
    else:
        with pytest.raises(ValueError, match='Short audio'):
            synthesis.load_audio(row, {'test': '/unused'}, 16000)
