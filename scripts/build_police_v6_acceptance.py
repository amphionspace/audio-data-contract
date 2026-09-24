"""Reuse an OBS handoff and registered test splits; report conservative V6 coverage.

Requirements JSONL retains source lines and explicit spoken variants. No ASR
predictions, train/dev rows, or generated audio are used by this script.
"""

import argparse
import csv
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from audio_data_contract.declarations import declaration_files, read_declarations


def key(text):
    return re.sub(
        r"[\s，。！？、：；,.!?;:'\"“”‘’（）()]+", "",
        unicodedata.normalize("NFKC", text).casefold(),
    )


def read_rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_rows(path, rows):
    with path.open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def audio_sha256(row):
    hasher = hashlib.sha256()
    with Path(row['audio_path']).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--requirements', type=Path, required=True)
    parser.add_argument('--roots', type=Path, default=Path('roots.json'))
    parser.add_argument('--catalog', type=Path, default=Path('catalog'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.report.mkdir(parents=True, exist_ok=True)
    requirements = read_rows(args.requirements)
    exact = defaultdict(set)
    source_keys = defaultdict(set)
    terms = []
    for index, req in enumerate(requirements):
        for variant in req['variants']:
            exact[key(variant)].add(index)
        source_keys[key(req['text'])].add(index)
        if req['section'] in ('行业词汇', '北京应用名称', '特殊代码',
                              '20260713新增', '20260714新增', '20260731新增'):
            terms.extend((index, term) for term in
                         dict.fromkeys(key(v) for v in req['variants']))

    def matches(row):
        text_key = key(row['text'])
        result = {i: '原句或明确读法' for i in exact.get(text_key, [])}
        for i, term in terms:
            # Special codes must occur in explicitly labelled code test material.
            if (requirements[i]['section'] == '特殊代码'
                    and 'special_codes' not in row['dataset_id']):
                continue
            if term in text_key:
                result.setdefault(i, '术语在句中出现')
        metadata = row.get('custom', {}).get('source_metadata', {})
        if row.get('custom', {}).get('clean', {}).get('pass'):
            for i in source_keys.get(key(metadata.get('text', '')), []):
                if requirements[i]['section'] != '特殊代码':
                    result.setdefault(i, '来源标注的改写')
        return result

    rows = []
    for raw in read_rows(args.handoff / 'manifest.jsonl'):
        rows.append({**raw, 'id': 'obs-' + raw['audio_sha256'],
                     'audio_path': str((args.handoff / raw['audio_path']).resolve()),
                     'source_split': raw['scope'], 'origin': 'obs_handoff'})
    base_count = len(rows)
    roots = json.loads(args.roots.read_text())
    inventories = []
    seen_manifests = set()
    for catalog_file in declaration_files(args.catalog):
        for _, dataset in read_declarations(catalog_file):
            if 'police' not in dataset['dataset_id']:
                continue
            split = dataset.get('splits', {}).get('test')
            if not split:
                continue
            artifacts = {a['name']: a for a in dataset['artifacts']}
            sup_names = split.get('supervisions_artifacts') or [
                split.get('supervisions_artifact')]
            rec_names = split.get('recordings_artifacts') or [
                split.get('recordings_artifact')]
            for sup_name, rec_name in zip(sup_names, rec_names, strict=True):
                if not sup_name or not rec_name:
                    continue
                sup_art, rec_art = artifacts[sup_name], artifacts[rec_name]
                sup_path = Path(roots[sup_art['root_alias']]) / sup_art['relative_path']
                rec_path = Path(roots[rec_art['root_alias']]) / rec_art['relative_path']
                # Some consumer entries expose dev audio under a "test" key.
                if '_dev' in dataset['dataset_id'] or '_dev.' in sup_path.name:
                    continue
                if sup_path in seen_manifests:
                    continue
                seen_manifests.add(sup_path)
                recs = {r['id']: r for r in read_rows(rec_path)}
                sups = read_rows(sup_path)
                inventories.append({'dataset_id': dataset['dataset_id'],
                                    'version': dataset['version'],
                                    'supervisions': str(sup_path), 'rows': len(sups)})
                for sup in sups:
                    rec = recs[sup['recording_id']]
                    assert len(rec['sources']) == 1
                    assert rec['sources'][0]['type'] == 'file'
                    assert sup['start'] == 0
                    assert abs(sup['duration'] - rec['duration']) < 0.001
                    audio_path = Path(rec['sources'][0]['source'])
                    if not audio_path.is_absolute():
                        audio_path = rec_path.parent / audio_path
                    rows.append({**sup, 'id': dataset['dataset_id'] + '-' + sup['id'],
                                 'source_item_id': sup['id'],
                                 'dataset_id': dataset['dataset_id'],
                                 'version': dataset['version'],
                                 'source_split': 'test', 'origin': 'catalog_test',
                                 'audio_path': str(audio_path),
                                 'duration_sec': sup['duration'],
                                 'sample_rate_hz': rec['sampling_rate'],
                                 'channels': len(rec['sources'][0]['channels']),
                                 'audio_origin': 'synthetic_tts'})

    index_matches = [matches(r) for r in rows]
    available = defaultdict(list)
    base = defaultdict(list)
    for ri, mapping in enumerate(index_matches):
        for qi, method in mapping.items():
            available[qi].append((ri, method))
            if ri < base_count:
                base[qi].append((ri, method))
    selected = set(range(base_count))
    # Fill missing content with at most ten existing voices; this is not a
    # minimum acceptance requirement. Prefer literal evidence over paraphrases.
    for qi in range(len(requirements)):
        if base[qi]:
            continue
        candidates = sorted(available[qi], key=lambda pair: (
            pair[1] == '来源标注的改写', pair[1] != '原句或明确读法', pair[0]))
        speakers = set()
        for ri, _ in candidates:
            row = rows[ri]
            speaker = row.get('speaker') or row['id']
            if speaker in speakers:
                continue
            if not Path(row['audio_path']).is_file():
                raise FileNotFoundError(row['audio_path'])
            selected.add(ri)
            speakers.add(speaker)
            if len(speakers) == 10:
                break

    output = []
    hashes = {}
    deduplicated = 0
    # Bound parallel reads: serial hashing of this many small files is dominated
    # by shared-filesystem latency. Preserve selection order in the output.
    ordered = sorted(selected)
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = list(pool.map(audio_sha256, (rows[i] for i in ordered)))
    for ri, digest in zip(ordered, digests, strict=True):
        row = rows[ri]
        path = Path(row['audio_path'])
        if row.get('audio_sha256'):
            assert digest == row['audio_sha256'], path
        if digest in hashes:
            assert key(hashes[digest]['text']) == key(row['text']), path
            hashes[digest]['coverage'].update(
                {requirements[i]['id']: m for i, m in index_matches[ri].items()})
            deduplicated += 1
            continue
        result = {**row, 'audio_sha256': digest,
                  'coverage': {requirements[i]['id']: m
                               for i, m in index_matches[ri].items()}}
        hashes[digest] = result
        output.append(result)
    assert len({r['id'] for r in output}) == len(output)
    write_rows(args.output / 'manifest.jsonl', output)
    write_rows(args.output / 'supplement.jsonl',
               [r for r in output if r['origin'] == 'catalog_test'])
    with (args.output / 'pairs.tsv').open('w') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['item_id', 'audio_path', 'text'])
        writer.writerows((r['id'], r['audio_path'], r['text']) for r in output)
    coverage = defaultdict(list)
    for row in output:
        for requirement, method in row['coverage'].items():
            coverage[requirement].append((row, method))
    report_rows = []
    for qi, req in enumerate(requirements):
        evidence = coverage[req['id']]
        counts = Counter(method for _, method in evidence)
        report_rows.append({
            'id': req['id'], 'section': req['section'],
            'source_line': req['source_line'], 'text': req['text'],
            'base_audio': len(base[qi]), 'selected_audio': len(evidence),
            'literal_audio': counts['原句或明确读法'],
            'term_context_audio': counts['术语在句中出现'],
            'paraphrase_audio': counts['来源标注的改写'],
            'status': ('缺音频' if not evidence else
                       '仅改写覆盖' if not (counts['原句或明确读法']
                                         + counts['术语在句中出现']) else '已覆盖'),
            'datasets': ';'.join(sorted({r['dataset_id'] for r, _ in evidence})),
        })
    for name, subset in (
        ('coverage.tsv', report_rows),
        ('missing.tsv', [r for r in report_rows if r['status'] == '缺音频']),
        ('paraphrase_only.tsv', [r for r in report_rows if r['status'] == '仅改写覆盖']),
        ('v6_new_commands.tsv', [r for r in report_rows
                                if r['section'] == '20260915新增']),
    ):
        with (args.report / name).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(report_rows[0]),
                                    delimiter='\t')
            writer.writeheader()
            writer.writerows(subset)
    sections = {}
    for section in dict.fromkeys(r['section'] for r in report_rows):
        group = [r for r in report_rows if r['section'] == section]
        sections[section] = {
            'requirements': len(group),
            'base_covered': sum(bool(r['base_audio']) for r in group),
            **dict(Counter(r['status'] for r in group)),
        }
    summary = {
        'requirements': len(requirements), 'base_audio': base_count,
        'selected_audio': len(output),
        'supplement_audio': sum(r['origin'] == 'catalog_test' for r in output),
        'duration_hours': sum(r['duration_sec'] for r in output) / 3600,
        'supplement_duration_hours': sum(r['duration_sec'] for r in output
                                         if r['origin'] == 'catalog_test') / 3600,
        'deduplicated_audio': deduplicated, 'sections': sections,
        'candidate_test_sources': inventories,
        'candidate_test_audio': len(rows) - base_count,
        'selected_audio_sha256_verified': len(output),
        'human_listening_review': False,
        'global_training_overlap_verified': False,
    }
    (args.report / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
