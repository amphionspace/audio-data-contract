#!/usr/bin/env python3
"""Relocate known manifest references after byte-verified COS restoration."""

import argparse
import fcntl
import gzip
import json
import os
import shlex
import tempfile
from pathlib import Path

from cos_backup import digest_file, save
from cos_restore import DEFAULT_BINDING, database, matching, target_path

from audio_data_contract.audio_prepare import _parse

KINDS = {'lhotse-recordings', 'lhotse-cuts', 'auto-lhotse', 'sharegpt-jsonl', 'target-asr-jsonl'}


def relocate_item(item, resolve):
    """Change path fields only; text, IDs and command member names stay intact."""
    if not isinstance(item, dict):
        return item
    if 'sources' in item:
        for source in item['sources']:
            if source['type'] == 'file':
                source['source'] = resolve(source['source'])
            elif source['type'] == 'command':
                _parse(source, Path('/'), extract=True)  # validate, never execute
                tokens = shlex.split(source['source'])
                start = 4 if tokens[0] == 'timeout' else 0
                if tokens[start] == 'tar':
                    tokens[start + 2] = resolve(tokens[start + 2])
                else:
                    tokens[start + 1] = 'if=' + resolve(tokens[start + 1][3:])
                source['source'] = shlex.join(tokens)
            else:
                raise ValueError('unsupported audio source type')
    if item.get('storage_path') and 'storage_type' in item:
        item['storage_path'] = resolve(item['storage_path'])
    if 'audios' in item:
        item['audios'] = [resolve(value) for value in item['audios']]
    for field in ('mix_wav', 'enroll_wav'):
        if field in item:
            item[field] = resolve(item[field])
    for value in item.values():
        if isinstance(value, dict):
            relocate_item(value, resolve)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    relocate_item(child, resolve)
    return item


def resolve_reference(db, binding, destination, task, value):
    if not isinstance(value, str) or not value or '://' in value:
        raise ValueError('unsupported manifest reference')
    path, manifest = Path(value), Path(task['path'])
    if path.is_absolute():
        candidates = {path}
    else:
        resolutions = db.execute('SELECT path FROM resolutions WHERE manifest=? AND reference=?',
                                 (str(manifest), value)).fetchall()
        candidates = {Path(row[0]) for row in resolutions}
        if not candidates:
            candidates = {manifest.parent / path}
            root = binding['roots'].get(task['root_alias'])
            if root:
                root = Path(root)
                candidates.add(root / path)
                candidates.update(p / path for p in manifest.parents if p.is_relative_to(root))
    targets = set()
    for candidate in candidates:
        # Resolve lexical '..' in references before enforcing the configured roots.
        original = os.path.normpath(str(candidate))
        if not any(Path(original).is_relative_to(root) for root in binding['allowed']):
            continue
        target = target_path(destination, original, binding)
        if target.exists():
            targets.add(target)
    if len(targets) != 1:
        raise ValueError('manifest reference missing or ambiguous: ' + value)
    return str(targets.pop())


def relocate(db, binding, destination):
    journal_path = destination / 'relocated-manifests.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    changed, skipped, failures = 0, 0, []
    for task in db.execute('SELECT * FROM tasks'):
        if task['kind'] not in KINDS:
            continue
        original = task['path']
        row = db.execute('SELECT * FROM files WHERE path=?', (original,)).fetchone()
        if row is None:
            skipped += 1
            continue
        target = target_path(destination, original, binding)
        if not target.exists():
            skipped += 1
            continue
        try:
            previous = journal.get(original)
            if previous and digest_file(target) == previous['localized_sha256']:
                continue
            matching(target, row)
            # Keep original bytes via a hard link before replacing the manifest.
            saved = destination / 'original-manifests' / original.lstrip('/')
            if saved.resolve() != saved or saved.is_symlink():
                raise ValueError('symlink in original manifest destination')
            saved.parent.mkdir(parents=True, exist_ok=True)
            if not matching(saved, row):
                os.link(target, saved)
            fd, name = tempfile.mkstemp(prefix='.cos-relocate-', dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            opener = gzip.open if original.endswith('.gz') else open
            try:
                with opener(saved, 'rt', encoding='utf-8') as source, opener(temporary, 'wt', encoding='utf-8') as output:
                    for line in source:
                        if line.strip():
                            item = relocate_item(json.loads(line),
                                                 lambda value, task=task: resolve_reference(db, binding, destination, task, value))
                            output.write(json.dumps(item, ensure_ascii=False) + '\n')
                # Do not replace a manifest edited while it was being relocated.
                matching(target, row)
                # Persist the new digest before replacing the file so a restart
                # recognizes either the original or the completed relocation.
                journal[original] = {'original_sha256': row['sha256'],
                                     'localized_sha256': digest_file(temporary),
                                     'original_copy': str(saved)}
                save(journal_path, journal)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            changed += 1
        except (OSError, ValueError, KeyError) as exc:
            failures.append({'path': original, 'error': str(exc)})
    result = {'relocated': changed, 'not_restored': skipped, 'failures': failures}
    save(destination / 'relocate-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, default=DEFAULT_BINDING)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if not (args.work / 'restore.sqlite').is_file():
        parser.error('run cos_restore.py restore first')
    with (args.work / 'restore.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = database(args.work / 'restore.sqlite')
        try:
            result = relocate(db, json.loads(args.binding.read_text()), args.destination.resolve())
        finally:
            db.close()
    print(json.dumps(result, ensure_ascii=False))
    if result['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
