#!/usr/bin/env python3
"""Publish relocated manifests and a verified registry from an aidc inventory.

Runs on the destination with a snapshot of the migration database, config,
original declarations, and the same Python modules used by the scanner.
"""

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path

from aidc_migrate import JSON, JSONL, paths_in_item
from aidc_transfer import digest, publish, safe_path, save

from audio_data_contract import load_catalog
from audio_data_contract.audio_prepare import _parse
from audio_data_contract.declarations import read_declarations, write_declarations
from audio_data_contract.views import load_view_catalog


def closure_issues(db, path):
    return db.execute('''WITH RECURSIVE dependencies(path) AS (
        SELECT ? UNION SELECT e.child FROM edges e JOIN dependencies d ON e.parent=d.path)
        SELECT i.* FROM issues i JOIN dependencies d ON i.path=d.path''', (path,)).fetchall()


def mapped(db, config, manifest, value):
    resolution = db.execute('SELECT path FROM resolutions WHERE manifest=? AND reference=?',
                            (manifest, value)).fetchone()
    original = resolution['path'] if resolution else value
    row = db.execute('SELECT o.* FROM paths p JOIN objects o ON o.id=p.object_id WHERE p.path=?',
                     (original,)).fetchone()
    if row:
        if row['status'] != 'complete':
            raise ValueError('dependency not transferred: ' + original)
        return str(Path(config['destination']) / row['target'])
    directory = db.execute('SELECT target FROM directories WHERE path=?', (original,)).fetchone()
    if directory:
        return str(Path(config['destination']) / directory['target'])
    raise ValueError('unmapped runtime reference: ' + value)


def read_sample(path, samples):
    extension = path.suffix.lower()
    if extension not in {'.wav', '.flac', '.mp3', '.ogg', '.opus', '.sph', '.m4a'} or extension in samples:
        return
    import soundfile as sf
    data, rate = sf.read(path, frames=16, always_2d=True)
    if not len(data) or rate <= 0:
        raise ValueError('empty audio sample: ' + str(path))
    samples[extension] = {'path': str(path), 'sample_rate': rate, 'frames_read': len(data)}


def sample_command(item, samples, db):
    if isinstance(item, list):
        for child in item:
            sample_command(child, samples, db)
    if not isinstance(item, dict):
        return
    for source in item.get('sources', []):
        if source['type'] != 'command':
            continue
        kind, archive, selector = _parse(source, Path('/'), extract=True)
        db.execute('INSERT OR IGNORE INTO command_refs VALUES(?,?,?)',
                   (str(archive), kind, json.dumps(selector)))
        if kind in samples:
            continue
        import soundfile as sf
        if kind == 'tar':
            with tarfile.open(archive, 'r:*') as stream:
                member = stream.getmember(selector)
                with stream.extractfile(member) as audio:
                    data = audio.read()
        else:
            with archive.open('rb') as stream:
                stream.seek(selector[0])
                data = stream.read(selector[1])
        audio, rate = sf.read(io.BytesIO(data), frames=16, always_2d=True)
        if not len(audio):
            raise ValueError('empty archived audio')
        samples[kind] = {'archive': str(archive), 'selector': selector,
                         'sample_rate': rate, 'frames_read': len(audio)}
    for value in item.values():
        if isinstance(value, (dict, list)):
            sample_command(value, samples, db)


def verify_command_references(db):
    for row in db.execute('SELECT DISTINCT archive,kind FROM command_refs').fetchall():
        selectors = [json.loads(r[0]) for r in db.execute(
            'SELECT selector FROM command_refs WHERE archive=? AND kind=?', tuple(row))]
        archive = Path(row['archive'])
        if row['kind'] == 'dd':
            size = archive.stat().st_size
            if any(offset < 0 or length <= 0 or offset + length > size for offset, length in selectors):
                raise ValueError('audio byte range exceeds archive: ' + str(archive))
        else:
            wanted, seen = set(selectors), set()
            with tarfile.open(archive, 'r:*') as stream:
                for member in stream:
                    if member.name not in wanted:
                        continue
                    if member.name in seen or not member.isfile():
                        raise ValueError('ambiguous or non-file audio member: ' + member.name)
                    seen.add(member.name)
            if wanted != seen:
                raise ValueError('missing referenced archive members: ' + str(archive))


def relocate(db, config, root, samples):
    rewritten = {}
    for row in db.execute('SELECT * FROM objects WHERE kind IS NOT NULL').fetchall():
        if row['kind'] not in JSONL | JSON or row['status'] != 'complete':
            continue
        if closure_issues(db, row['source']):
            continue
        original = safe_path(root, f'migration/{config["run"]}/original-manifests/{row["id"]}/{Path(row["source"]).name}')
        if original.stat().st_size != row['size'] or digest(original) != row['sha256']:
            raise ValueError('original manifest checksum mismatch: ' + str(original))
        target = safe_path(root, row['target'])
        temporary = safe_path(root, f'.incoming/{config["run"]}/rewritten/{row["id"]}')
        temporary.parent.mkdir(parents=True, exist_ok=True)
        source_opener = gzip.open if original.name.endswith('.gz') else open
        count = 0
        # Deterministic gzip bytes allow an interrupted finalization to compare
        # an already-published manifest without changing its checksum.
        with source_opener(original, 'rt', encoding='utf-8') as source, temporary.open('wb') as raw:
            compressed = gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) if target.suffix == '.gz' else raw
            out = io.TextIOWrapper(compressed, encoding='utf-8')
            try:
                rows = (json.loads(line) for line in source if line.strip()) if row['kind'] in JSONL else [json.load(source)]
                for item in rows:
                    item = paths_in_item(item, lambda value, original=row['source']: mapped(db, config, original, value),
                                         config['roots'], row['kind'], row['source'], config['destination'])
                    sample_command(item, samples, db)
                    out.write(json.dumps(item, ensure_ascii=False, separators=(',', ':')) + '\n')
                    count += 1
                out.flush()
            finally:
                out.detach()
                if compressed is not raw:
                    compressed.close()
        localized = {'sha256': digest(temporary), 'bytes': temporary.stat().st_size,
                     'records': count, 'original_sha256': row['sha256'], 'path': row['target']}
        publish(temporary, target, localized['sha256'])
        rewritten[str(row['id'])] = localized
        db.commit()
    save(root / 'migration' / config['run'] / 'relocated-manifests.json', rewritten)
    return rewritten


def materialize_directories(db, config, root):
    for directory in db.execute('SELECT * FROM directories'):
        target = safe_path(root, directory['target'])
        target.mkdir(parents=True, exist_ok=True)
        prefix = directory['path'].rstrip('/') + '/'
        for row in db.execute('''SELECT p.path,o.target,o.status FROM paths p
                                JOIN objects o ON o.id=p.object_id WHERE p.path>=? AND p.path<?''',
                              (prefix, prefix + '\U0010ffff')):
            if row['status'] != 'complete':
                continue
            source = safe_path(root, row['target'])
            if not source.is_file():
                continue
            child = safe_path(root, str(Path(directory['target']) / Path(row['path']).relative_to(directory['path'])))
            if child == source:
                continue
            child.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, child)
            except FileExistsError:
                if not os.path.samefile(source, child) and digest(source) != digest(child):
                    raise ValueError('directory alias conflict: ' + str(child))


def directory_integrity(path, cache):
    sha = hashlib.sha256()
    total, count = 0, 0
    for child in sorted(p for p in path.rglob('*') if p.is_file()):
        info = child.stat()
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in cache:
            cache[identity] = digest(child)
        sha.update(f'{child.relative_to(path).as_posix()}\0{info.st_size}\0{cache[identity]}\n'.encode())
        total += info.st_size
        count += 1
    return {'file_count': count, 'expected_bytes': total, 'tree_sha256': sha.hexdigest()}


def original_directory_integrity(db, path):
    prefix = path.rstrip('/') + '/'
    sha = hashlib.sha256()
    count, total = 0, 0
    for row in db.execute('''SELECT p.path,o.size,o.sha256 FROM paths p JOIN objects o
                            ON o.id=p.object_id WHERE p.path>=? AND p.path<? ORDER BY p.path''',
                          (prefix, prefix + '\U0010ffff')):
        if row['sha256'] is None:
            raise ValueError('source directory includes an unverified file: ' + row['path'])
        relative = row['path'][len(prefix):]
        sha.update(f'{relative}\0{row["size"]}\0{row["sha256"]}\n'.encode())
        count += 1
        total += row['size']
    return {'file_count': count, 'expected_bytes': total, 'tree_sha256': sha.hexdigest()}


def finalize(work):
    config = json.loads((work / 'config.json').read_text())
    root = Path(config['destination'])
    db = sqlite3.connect(work / 'migration.sqlite')
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS command_refs(archive TEXT,kind TEXT,selector TEXT,
                  PRIMARY KEY(archive,kind,selector))''')
    db.commit()
    if not db.execute("SELECT 1 FROM meta WHERE key='scan_complete'").fetchone():
        raise ValueError('inventory is incomplete')
    if db.execute("SELECT 1 FROM objects WHERE status NOT IN ('complete','excluded') LIMIT 1").fetchone():
        raise ValueError('transfer is incomplete; do not publish a success registry')
    problems = [dict(r) for r in db.execute('SELECT * FROM issues')]
    save(work / 'exceptions.json', problems)
    excluded_specs = list(config['exclusions'])
    eligible = []
    original_trees = {}
    for spec in config['datasets']:
        key = spec['dataset_id'] + '@' + spec['version']
        problems = []
        for artifact in db.execute('SELECT path FROM artifacts WHERE spec=?', (key,)):
            problems.extend(dict(r) for r in closure_issues(db, artifact['path']))
        for artifact in spec['artifacts']:
            metadata = artifact.get('metadata', {})
            if not any(k in metadata for k in ('file_count', 'tree_sha256', 'expected_bytes')):
                continue
            path = str(Path(config['roots'][artifact['root_alias']]) / artifact['relative_path'])
            if db.execute('SELECT 1 FROM directories WHERE path=?', (path,)).fetchone():
                if path not in original_trees:
                    original_trees[path] = original_directory_integrity(db, path)
                for field, actual in original_trees[path].items():
                    if metadata.get(field) is not None and metadata[field] != actual:
                        problems.append({'path': path, 'reason': 'source_directory_integrity_mismatch',
                                         'field': field, 'expected': metadata[field], 'actual': actual})
        if problems:
            excluded_specs.append({'key': key, 'reason': 'deferred_dependencies', 'issues': problems})
        else:
            eligible.append(spec)
    save(work / 'excluded-versions.json', excluded_specs)
    samples = {}
    rewritten = relocate(db, config, root, samples)
    verify_command_references(db)
    materialize_directories(db, config, root)
    registry = work / 'registry-candidate'
    (registry / 'catalog').mkdir(parents=True, exist_ok=True)
    (registry / 'views').mkdir(parents=True, exist_ok=True)
    output = []
    cache = {}
    for original in eligible:
        spec = copy.deepcopy(original)
        for artifact in spec['artifacts']:
            path = str(Path(config['roots'][artifact['root_alias']]) / artifact['relative_path'])
            target = Path(mapped(db, config, '', path))
            artifact['root_alias'] = 'aidc_data'
            artifact['relative_path'] = str(target.relative_to(root))
            if target.is_dir():
                artifact.pop('expected_bytes', None)
                artifact.pop('sha256', None)
                artifact.setdefault('metadata', {}).update(directory_integrity(target, cache))
            else:
                obj = db.execute('SELECT o.* FROM objects o JOIN paths p ON p.object_id=o.id WHERE p.path=?', (path,)).fetchone()
                changed = rewritten.get(str(obj['id']))
                artifact['expected_bytes'] = target.stat().st_size
                artifact['sha256'] = changed['sha256'] if changed else obj['sha256']
                if changed and 'record_count' in artifact.get('metadata', {}):
                    artifact['metadata']['record_count'] = changed['records']
        output.append(spec)
    write_declarations(registry / 'catalog/datasets.yaml', output)
    migrated = {s['dataset_id'] + '@' + s['version'] for s in output}
    views, excluded_views = [], []
    for path in sorted((work / 'original-registry/views').glob('*')):
        for _, row in read_declarations(path):
            refs = [row[field] for field in ('source', 'result')]
            if all(r['dataset_id'] + '@' + r['version'] in migrated for r in refs):
                views.append(row)
            else:
                excluded_views.append(row['view_id'] + '@' + row['version'])
    write_declarations(registry / 'views/views.yaml', views)
    save(registry / 'roots.json', {'aidc_data': str(root)})
    catalog = load_catalog(registry / 'catalog')
    load_view_catalog(registry / 'views', catalog)
    # Verify file coverage and format samples. Content checksums were checked
    # during reception; rewritten bytes are hashed above, originals retained.
    total = 0
    with (work / 'path-map.jsonl').open('w') as out:
        for row in db.execute("SELECT p.path,o.* FROM paths p JOIN objects o ON p.object_id=o.id WHERE o.status='complete'"):
            target = safe_path(root, row['target'])
            changed = rewritten.get(str(row['id']))
            expected_size = changed['bytes'] if changed else row['size']
            if target.exists():
                if target.stat().st_size != expected_size:
                    raise ValueError('target size mismatch: ' + str(target))
                read_sample(target, samples)
            elif not closure_issues(db, row['source']):
                raise ValueError('missing destination file: ' + str(target))
            out.write(json.dumps({'source': row['path'], 'target': str(target),
                                  'sha256': changed['sha256'] if changed else row['sha256'],
                                  'size': expected_size}, ensure_ascii=False) + '\n')
            total += 1
    # Register only after the entire candidate has been checked. Existing,
    # different registry content is rejected in the same way as data files.
    for path in sorted(p for p in registry.rglob('*') if p.is_file()):
        destination = safe_path(root, 'registry/' + str(path.relative_to(registry)))
        staged = work / ('publish-' + hashlib.sha256(str(path).encode()).hexdigest())
        staged.write_bytes(path.read_bytes())
        publish(staged, destination, digest(staged))
    result = {'status': 'complete_with_exclusions' if excluded_specs else 'complete',
              'versions': len(output), 'views': len(views), 'mapped_paths': total,
              'excluded_versions': len(excluded_specs), 'excluded_views': excluded_views,
              'format_samples': samples, 'verification': 'SHA-256 checked in transfer; runtime references resolved; sizes and registry checked'}
    save(work / 'verification.json', result)
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    finalize(parser.parse_args().work)


if __name__ == '__main__':
    main()
