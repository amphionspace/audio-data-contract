"""Merge all police releases into one train/dev/test dataset without copying audio."""
import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_split, verify_artifact_file
from audio_data_contract.declarations import write_declarations

DATASET_ID = 'police_asr_unified'
VERSION = 'v1-20261009'
V5_MANIFESTS = 'migration/aidc-v5-20261009/manifests'
TERMS_V5 = 'v5-20260830-qwen75-cosy25-split80-10-10'
# (target split, source dataset, source version, source split, registry version or None for V5 files)
SOURCES = [
    ('train', 'police_terms_v5', TERMS_V5, 'train', None),
    ('train', 'police_synthetic_zh_accent', 'legacy-rebalance-100k-20260916', 'train', 'legacy-rebalance-100k-20260916'),
    ('train', 'police_v6_expanded', 'v6-expanded-20260915', 'train', 'v6-expanded-20260915'),
    ('train', 'police_v6_8h', 'v6-8h-20260915', 'train', 'v6-8h-20260915'),
    ('train', 'police_synthetic_zh_accent', 'v1-20260817', 'train', 'v1-20260817'),
    ('train', 'police_synthetic_zh_accent', 'v3-20260820', 'train', 'icefall-20260908'),
    ('train', 'police_synthetic_zh_accent', 'v5-20260830-qc', 'train', None),
    ('dev', 'police_terms_v5', TERMS_V5, 'dev', None),
    ('dev', 'police_synthetic_zh_accent', 'legacy-rebalance-100k-20260916', 'dev', 'legacy-rebalance-100k-20260916'),
    ('dev', 'police_v6_expanded', 'v6-expanded-20260915', 'dev', 'v6-expanded-20260915'),
    ('dev', 'police_v6_8h', 'v6-8h-20260915', 'dev', 'v6-8h-20260915'),
    ('test', 'police_terms_v5', TERMS_V5, 'test', None),
    ('test', 'police_synthetic_zh_accent', 'legacy-rebalance-100k-20260916', 'test', 'legacy-rebalance-100k-20260916'),
    ('test', 'police_v6_expanded', 'v6-expanded-20260915', 'test', 'v6-expanded-20260915'),
    ('test', 'police_v6_8h', 'v6-8h-20260915', 'test', 'v6-8h-20260915'),
    ('test', 'police_synthetic_zh_accent', 'v2-20260818', 'test', 'icefall-20260908'),
    ('test', 'police_v6_acceptance_205', 'v6-acceptance-20260921', 'test', 'v6-acceptance-20260921'),
]
V5_FILES = {
    (TERMS_V5, s): (f'{TERMS_V5}/police_terms_v5_recordings_{s}.jsonl.gz', f'{TERMS_V5}/police_terms_v5_supervisions_{s}.jsonl.gz')
    for s in ('train', 'dev', 'test')
}
V5_FILES['v5-20260830-qc', 'train'] = ('v5-20260830-qc/police_synthetic_recordings_train.jsonl.gz', 'v5-20260830-qc/police_synthetic_supervisions_train.jsonl.gz')


def norm(text):
    return re.sub(r'[\W_]+', '', text)


def read(path):
    with gzip.open(path, 'rt') as f:
        return [json.loads(line) for line in f]


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as f:
        for row in rows:
            f.write((json.dumps(row, ensure_ascii=False) + '\n').encode())


def load_source(data, registry, roots, dataset_id, version, split, registry_version):
    if registry_version is None:
        rec, sup = (data/V5_MANIFESTS/p for p in V5_FILES[version, split])
    else:
        rec, = resolve_split(registry, dataset_id, registry_version, split, 'recordings', roots)
        sup, = resolve_split(registry, dataset_id, registry_version, split, 'supervisions', roots)
    recs, sups = read(rec), read(sup)
    assert len(recs) == len(sups) and {r['id'] for r in recs} == {s['recording_id'] for s in sups}, (dataset_id, version, split)
    by_id = {r['id']: r for r in recs}
    return [(by_id[s['recording_id']], s) for s in sups], {'recordings': str(rec), 'supervisions': str(sup)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=Path('/workspace/data'), help='aidc_data root')
    args = p.parse_args()
    data = args.data.resolve()
    repo = Path(__file__).resolve().parents[1]
    target = repo/'catalog/police_asr_unified.yaml'
    if target.exists():
        raise FileExistsError(target)
    registry = load_catalog(data/'registry/catalog')
    roots = {'aidc_data': data}
    loaded = [(src, *load_source(data, registry, roots, *src[1:5])) for src in SOURCES]

    # Every train source is filtered against all held-out sets; this mostly affects the unsplit v1/v3/v5-qc batches.
    held_ids, held_speakers, held_texts = set(), set(), set()
    for (split, *_), rows, _ in loaded:
        for rec, sup in rows:
            if split != 'train':
                held_ids.add(rec['id']); held_speakers.add(sup['speaker']); held_texts.add(norm(sup['text']))

    out = {s: {} for s in ('train', 'dev', 'test')}
    report = []
    for (split, dataset_id, version, source_split, _), rows, paths in loaded:
        drops = Counter()
        for rec, sup in rows:
            if split == 'train':
                if rec['id'] in held_ids:
                    drops['held_out_id'] += 1; continue
                if sup['speaker'] in held_speakers:
                    drops['held_out_speaker'] += 1; continue
                if norm(sup['text']) in held_texts:
                    drops['held_out_text'] += 1; continue
            if any(rec['id'] in out[s] for s in out):
                drops['duplicate_id'] += 1; continue
            sup = dict(sup, custom={**(sup.get('custom') or {}), 'source_dataset': dataset_id, 'source_version': version, 'source_split': source_split})
            out[split][rec['id']] = (rec, sup)
        report.append({'split': split, 'source_dataset': dataset_id, 'source_version': version, 'source_split': source_split,
                       'manifests': {k: str(Path(v).relative_to(data)) for k, v in paths.items()},
                       'input': len(rows), 'kept': len(rows) - sum(drops.values()), 'dropped': dict(drops)})

    facts = {s: {'ids': set(rows), 'speakers': {sup['speaker'] for _, sup in rows.values()},
                 'texts': {norm(sup['text']) for _, sup in rows.values()}} for s, rows in out.items()}
    for a, b in (('train', 'dev'), ('train', 'test'), ('dev', 'test')):
        for key in ('ids', 'speakers', 'texts'):
            assert not facts[a][key] & facts[b][key], (a, b, key, len(facts[a][key] & facts[b][key]))
    for rows in out.values():
        for rec, _ in rows.values():
            assert rec['sampling_rate'] == 16000 and Path(rec['sources'][0]['source']).is_file(), rec['id']

    version_dir = data/'datasets'/DATASET_ID/'versions'/VERSION
    artifacts, splits = [], {}
    def add(name, kind, path, record_count=None):
        item = {'name': name, 'kind': kind, 'root_alias': 'aidc_data', 'relative_path': str(path.relative_to(data)),
                'expected_bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        if record_count is not None:
            item['metadata'] = {'record_count': record_count}
        artifacts.append(item)
    for split, rows in out.items():
        ordered = [rows[k] for k in sorted(rows)]
        for role, index in (('recordings', 0), ('supervisions', 1)):
            path = version_dir/f'manifests/police_asr_unified_{role}_{split}.jsonl.gz'
            write(path, [pair[index] for pair in ordered])
            add(f'{split}_{role}', f'lhotse-{role}', path, len(ordered))
        sources = Counter(f"{sup['custom']['source_dataset']}@{sup['custom']['source_version']}" for _, sup in ordered)
        splits[split] = {'artifacts': {'recordings': [f'{split}_recordings'], 'supervisions': [f'{split}_supervisions']},
                         'statistics': {'recordings': len(ordered), 'supervisions': len(ordered),
                                        'duration_hours': round(sum(rec['duration'] for rec, _ in ordered)/3600, 6),
                                        'duration_basis': 'sum_of_recording_durations',
                                        'unique_texts': len(facts[split]['texts']), 'speakers': len(facts[split]['speakers']),
                                        'sources': dict(sorted(sources.items()))}}
    report_path = version_dir/'build_report.json'
    report_path.write_text(json.dumps({'sources': report, 'splits': {s: v['statistics'] for s, v in splits.items()}}, ensure_ascii=False, indent=2) + '\n')
    add('build_report', 'json-metadata', report_path)

    spec = {'schema_version': 'dataset-catalog/2.0', 'dataset_id': DATASET_ID, 'version': VERSION, 'languages': ['zh'], 'tasks': ['asr'],
            'artifacts': artifacts, 'splits': splits,
            'recipe_parameters': {'sample_rate': 16000, 'channels': 1, 'text_normalization_for_overlap': 'remove punctuation, symbols and whitespace'},
            'provenance': {
                'source': 'Merged from registered police synthetic releases on aidc-dev',
                'status': 'ready',
                'description': '警务合成语音统合版：V1-V6 全部批次合并为 train/dev/test 三个集合，不复制音频。',
                'sources': [{k: r[k] for k in ('split', 'source_dataset', 'source_version', 'source_split', 'manifests')} for r in report],
                'split_policy': 'Released splits are kept: dev/test use the shared nationwide_v2_480 384/48/48 speaker assignment plus the separate nationwide_test_v1_110 pool for v2 test and V6 acceptance. Every train source, chiefly the early unsplit batches (v1, v3, v5-qc), drops held-out recording IDs, speakers and normalized texts, and IDs already taken by an earlier source (v5-qc repeats police_terms_v5). Recording IDs, speakers and normalized texts are disjoint across train/dev/test.',
                'excluded': {
                    'police_robust_monitor': 'augmented copies of 60 v2 test utterances, monitoring only',
                    'per_tts_provider_splits': 'duplicates of the combined splits',
                    'v5-20260830-qwen75-cosy25': 'subset of v5-20260830-qc',
                    'icefall-20260908 views': 'same files as their source versions'},
                'source_tagging': 'supervision custom.source_dataset, source_version and source_split identify the original release for per-subset scoring',
                'evaluation_limitations': 'All audio is synthetic with automatic QC and no human listening review. V6 acceptance texts are original commands and reading variants; this is not an unseen-semantics test.',
                'audio_location_policy': 'Manifests reference existing audio under aidc_data; no audio was copied or moved.',
                'verification': {'cross_split_ids_speakers_texts': 'disjoint', 'audio_paths_exist': True, 'sample_rate_16k': True},
            }}
    write_declarations(target, [spec])
    catalog = load_catalog(repo/'catalog')
    for a in catalog.get(DATASET_ID, VERSION).artifacts:
        verify_artifact_file(a, data/a.relative_path)
    print(json.dumps({s: {k: v['statistics'][k] for k in ('recordings', 'duration_hours', 'speakers', 'unique_texts')} for s, v in splits.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
