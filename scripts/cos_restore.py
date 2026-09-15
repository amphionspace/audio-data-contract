#!/usr/bin/env python3
"""Bind catalog versions to COS and restore verified files without staging archives."""

import argparse
import fcntl
import gzip
import hashlib
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from cos_backup import HashingReader, digest_file, encoded, save, verify_head
from cos_sync_catalog import cos_client

DEFAULT_BINDING = Path('catalog/backups/cos-20260914.json')


def receipt_key(receipt):
    parents = {str(PurePosixPath(s['key']).parent) for s in receipt['shards']}
    if len(parents) != 1 or receipt['status'] != 'verified':
        raise ValueError('invalid completed receipt')
    return parents.pop() + '/complete.json'


def get_stream(client, binding, key, **kwargs):
    return client.get_object(Bucket=binding['bucket'], Key=key, **kwargs)['Body'].get_raw_stream()


def get_json(client, binding, key, sha256=None):
    with closing(get_stream(client, binding, key)) as stream:
        data = stream.read()
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError('metadata SHA-256 mismatch: ' + key)
    return json.loads(data)


def bind(args):
    config = json.loads((args.work / 'config.json').read_text())
    prefix = config['prefix'].rstrip('/')
    receipts = []
    for path in args.reuse:
        receipt = json.loads(path.read_text())
        receipts.append({'key': receipt_key(receipt),
                         'sha256': hashlib.sha256(encoded(receipt)).hexdigest()})
    binding = {
        'schema_version': 'cos-catalog-binding/1',
        'bucket': config['bucket'], 'region': config['region'],
        'catalog_key': prefix + '/catalog-binding.json',
        'batches_prefix': prefix + '/batches/', 'index_prefix': prefix + '/index/',
        'reused_receipts': receipts, 'roots': config['roots'],
        'allowed': config['allowed'], 'datasets': config['datasets'],
        'dataset_bindings': {
            s['dataset_id'] + '@' + s['version']: {
                'cos_uri': 'cos://' + config['bucket'] + '/' + prefix + '/',
                'artifacts': {a['name']: a['root_alias'] + ':' + a['relative_path']
                              for a in s['artifacts']},
            } for s in config['datasets']
        },
    }
    content = encoded(binding)
    client = cos_client(binding)
    try:
        for receipt in receipts:
            get_json(client, binding, receipt['key'], receipt['sha256'])
        client.put_object(Bucket=binding['bucket'], Key=binding['catalog_key'],
                          Body=content, ACL='private', EnableMD5=True,
                          ContentType='application/json')
        get_json(client, binding, binding['catalog_key'], hashlib.sha256(content).hexdigest())
    finally:
        client._session.close()
    save(args.binding, binding)
    print(json.dumps({'binding': str(args.binding), 'datasets': len(binding['datasets']),
                      'cos_uri': 'cos://' + binding['bucket'] + '/' + binding['catalog_key']}))


def completed_keys(client, binding, prefix):
    marker = ''
    while True:
        page = client.list_objects(Bucket=binding['bucket'], Prefix=prefix, Marker=marker)
        for item in page.get('Contents', []):
            if item['Key'].endswith('/complete.json'):
                yield item['Key']
        if str(page.get('IsTruncated', 'false')).lower() != 'true':
            break
        following = page['NextMarker']
        if following <= marker:
            raise ValueError('COS listing did not advance')
        marker = following


def database(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,size INTEGER,sha256 TEXT,
        object_key TEXT,member TEXT,container_format TEXT);
      CREATE INDEX IF NOT EXISTS files_object ON files(object_key,member);
      CREATE TABLE IF NOT EXISTS objects(key TEXT PRIMARY KEY,receipt TEXT);
      CREATE TABLE IF NOT EXISTS imported(key TEXT PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS tasks(path TEXT PRIMARY KEY,kind TEXT,root_alias TEXT);
      CREATE TABLE IF NOT EXISTS resolutions(manifest TEXT,reference TEXT,path TEXT,
        PRIMARY KEY(manifest,reference,path));
      CREATE TABLE IF NOT EXISTS issues(payload TEXT);
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
    ''')
    return db


def insert_file(db, row):
    db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)',
               tuple(row[k] for k in ('path', 'size', 'sha256', 'object_key', 'member', 'container_format')))


def import_receipt(db, receipt):
    receipt_key(receipt)
    for shard in receipt['shards']:
        facts = {k: shard[k] for k in ('size', 'sha256', 'crc64')}
        facts['plan_sha256'] = receipt['plan_sha256']
        db.execute('INSERT OR REPLACE INTO objects VALUES(?,?)', (shard['key'], json.dumps(facts)))
        for item in shard['files']:
            for source in item['sources']:
                insert_file(db, {'path': source['path'], 'size': item['size'], 'sha256': item['sha256'],
                                 'object_key': shard['key'], 'container_format': shard['format'],
                                 'member': '' if shard['format'] == 'raw' else 'files/' + item['sha256']})


def prepare(client, binding, work):
    """Incrementally discover cloud receipts; the final index is authoritative."""
    work.mkdir(parents=True, exist_ok=True)
    db = database(work / 'restore.sqlite')
    identity = hashlib.sha256(encoded(binding)).hexdigest()
    meta = dict(db.execute('SELECT key,value FROM meta'))
    if meta.get('binding', identity) != identity:
        db.close()
        raise ValueError('restore work directory belongs to another binding')
    db.execute("INSERT OR REPLACE INTO meta VALUES('binding',?)", (identity,))
    if meta.get('final_index'):
        return db
    # Discover the final index first: once published, every referenced batch
    # receipt already exists. Listing batches first races the last upload.
    finals = list(completed_keys(client, binding, binding['index_prefix']))
    if len(finals) > 1:
        raise ValueError('multiple final indexes; select an unambiguous snapshot')
    refs = list(binding['reused_receipts'])
    refs += [{'key': key} for key in completed_keys(client, binding, binding['batches_prefix'])]
    for ref in refs:
        if db.execute('SELECT 1 FROM imported WHERE key=?', (ref['key'],)).fetchone():
            continue
        receipt = get_json(client, binding, ref['key'], ref.get('sha256'))
        if receipt_key(receipt) != ref['key']:
            raise ValueError('receipt object identity mismatch')
        import_receipt(db, receipt)
        db.execute('INSERT INTO imported VALUES(?)', (ref['key'],))
        db.commit()
    from cos_sync_catalog import MANIFESTS
    for spec in binding['datasets']:
        for artifact in spec['artifacts']:
            if artifact['kind'] in MANIFESTS and artifact['root_alias'] in binding['roots']:
                path = str(Path(binding['roots'][artifact['root_alias']]) / artifact['relative_path'])
                db.execute('INSERT OR IGNORE INTO tasks VALUES(?,?,?)',
                           (path, artifact['kind'], artifact['root_alias']))
            elif artifact['kind'] == 'lhotse-manifest-dir' and artifact['root_alias'] in binding['roots']:
                path = str(Path(binding['roots'][artifact['root_alias']]) / artifact['relative_path']).rstrip('/')
                for row in db.execute('SELECT path FROM files WHERE path>=? AND path<?', (path + '/', path + '0')):
                    if row[0].endswith(('.jsonl', '.jsonl.gz')):
                        db.execute('INSERT OR IGNORE INTO tasks VALUES(?,?,?)',
                                   (row[0], 'auto-lhotse', artifact['root_alias']))
    db.commit()
    if finals:
        receipt = get_json(client, binding, finals[0])
        if receipt_key(receipt) != finals[0] or len(receipt['shards']) != 1:
            raise ValueError('invalid final index receipt')
        shard = receipt['shards'][0]
        if shard['format'] != 'raw':
            raise ValueError('final index must be a raw gzip object')
        # Stream into a fresh DB. A failed import never replaces a usable index.
        pending = work / 'final-index.sqlite'
        pending.unlink(missing_ok=True)
        final = database(pending)
        for row in db.execute('SELECT * FROM objects'):
            final.execute('INSERT INTO objects VALUES(?,?)', tuple(row))
        try:
            with closing(get_stream(client, binding, shard['key'])) as source:
                reader = HashingReader(source)
                with gzip.GzipFile(fileobj=reader) as stream:
                    for number, line in enumerate(stream, 1):
                        row = json.loads(line)
                        if row['type'] == 'files' and row['status'] == 'verified':
                            insert_file(final, row)
                        elif row['type'] == 'tasks':
                            final.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?)',
                                          (row['path'], row['kind'], row['root_alias']))
                        elif row['type'] == 'resolutions':
                            final.execute('INSERT OR IGNORE INTO resolutions VALUES(?,?,?)',
                                          (row['manifest'], row['reference'], row['path']))
                        elif row['type'] == 'issues':
                            final.execute('INSERT INTO issues VALUES(?)', (json.dumps(row),))
                        if number % 10000 == 0:
                            final.commit()
                if reader.sha.hexdigest() != shard['sha256']:
                    raise ValueError('final index SHA-256 mismatch')
            final.execute("INSERT INTO meta VALUES('binding',?)", (identity,))
            final.execute("INSERT INTO meta VALUES('final_index',?)", (finals[0],))
            final.commit()
        finally:
            final.close()
        db.close()
        pending.replace(work / 'restore.sqlite')
        db = database(work / 'restore.sqlite')
    return db


def target_path(destination, original, binding):
    path = PurePosixPath(original)
    if not path.is_absolute() or '..' in path.parts or path == PurePosixPath('/'):
        raise ValueError('unsafe recovery path: ' + original)
    if not any(path.is_relative_to(PurePosixPath(root)) for root in binding['allowed']):
        raise ValueError('recovery path outside data roots: ' + original)
    target = destination / 'files' / str(path).lstrip('/')
    # Reject existing symlinks, including links to another location in the tree.
    if target.resolve() != target or target.is_symlink():
        raise ValueError('symlink in recovery destination: ' + str(target))
    return target


def matching(path, row):
    if not path.exists():
        return False
    if not path.is_file() or path.stat().st_size != row['size'] or digest_file(path) != row['sha256']:
        raise ValueError('existing file differs; refusing overwrite: ' + str(path))
    return True


def write_member(stream, rows, destination, binding):
    """Verify one content and hard-link its aliases; never extract archive paths."""
    targets = [(target_path(destination, row['path'], binding), row) for row in rows]
    if len({(row['size'], row['sha256']) for _, row in targets}) != 1:
        raise ValueError('conflicting archive member identities')
    existing = None
    missing = []
    for target, row in targets:
        if matching(target, row):
            existing = target
        else:
            missing.append(target)
    if not missing:
        return
    if existing is None:
        target, row = targets[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.cos-restore-', dir=target.parent)
        temporary = Path(name)
        try:
            digest, size = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as output:
                for block in iter(lambda: stream.read(8 * 1024**2), b''):
                    size += len(block)
                    if size > row['size']:
                        raise ValueError('restored member exceeds expected size')
                    digest.update(block)
                    output.write(block)
            if size != row['size'] or digest.hexdigest() != row['sha256']:
                raise ValueError('restored member SHA-256/size mismatch')
            os.link(temporary, target)
            existing = target
            missing.remove(target)
        finally:
            temporary.unlink(missing_ok=True)
    for target in missing:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(existing, target)


class RangeReader(io.RawIOBase):
    """ZIP needs seeking; fetch bounded COS ranges instead of staging the ZIP."""

    def __init__(self, client, binding, key, size):
        self.client, self.binding, self.key, self.size = client, binding, key, size
        self.position, self.start, self.block = 0, 0, b''

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = (0, self.position, self.size)[whence] + offset
        if position < 0:
            raise ValueError('negative seek')
        self.position = position
        return position

    def read(self, size=-1):
        remaining = max(0, self.size - self.position)
        size = remaining if size < 0 else min(size, remaining)
        output = bytearray()
        while len(output) < size:
            if not self.start <= self.position < self.start + len(self.block):
                self.start = self.position
                end = min(self.size, self.start + 8 * 1024**2) - 1
                with closing(get_stream(self.client, self.binding, self.key,
                                        Range=f'bytes={self.start}-{end}')) as stream:
                    self.block = stream.read()
                if len(self.block) != end - self.start + 1:
                    raise ValueError('short COS range read')
            offset = self.position - self.start
            chunk = self.block[offset:offset + size - len(output)]
            output.extend(chunk)
            self.position += len(chunk)
        return bytes(output)


def selection(db, prefixes):
    previous = db.execute("SELECT type FROM sqlite_temp_master WHERE name='selected'").fetchone()
    if previous:
        db.execute('DROP ' + previous[0].upper() + ' temp.selected')
    if not prefixes:
        # The complete inventory can contain tens of millions of paths. Reuse
        # its indexes without duplicating it in SQLite's temporary storage.
        db.execute('CREATE TEMP VIEW selected AS SELECT * FROM files')
        return
    db.execute('CREATE TEMP TABLE selected AS SELECT * FROM files WHERE 0')
    db.execute('CREATE UNIQUE INDEX temp.selected_path ON selected(path)')
    for prefix in prefixes:
        db.execute('INSERT OR IGNORE INTO selected SELECT * FROM files WHERE path=? OR (path>=? AND path<?)',
                   (prefix, prefix.rstrip('/') + '/', prefix.rstrip('/') + '0'))
    db.execute('CREATE INDEX temp.selected_object ON selected(object_key,member)')


def restore(client, binding, db, destination, prefixes=(), allow_incomplete=False):
    meta = dict(db.execute('SELECT key,value FROM meta'))
    gaps = db.execute('SELECT count(*) FROM issues').fetchone()[0]
    if (not meta.get('final_index') or gaps) and not allow_incomplete:
        raise ValueError('backup incomplete or has gaps; use --allow-incomplete for available files')
    selection(db, prefixes)
    count = db.execute('SELECT count(*) FROM selected').fetchone()[0]
    if not count:
        raise ValueError('no verified files match selection')
    for item in db.execute('SELECT DISTINCT object_key FROM selected'):
        key = item[0]
        facts = db.execute('SELECT receipt FROM objects WHERE key=?', (key,)).fetchone()
        if facts is None:
            raise ValueError('no verified object receipt: ' + key)
        facts = json.loads(facts[0])
        verify_head(client.head_object(Bucket=binding['bucket'], Key=key), facts, facts['plan_sha256'])
        if all(matching(target_path(destination, r['path'], binding), r)
               for r in db.execute('SELECT * FROM selected WHERE object_key=?', (key,))):
            print(json.dumps({'reused_object': key}), flush=True)
            continue
        raw = db.execute("SELECT * FROM selected WHERE object_key=? AND member=''", (key,)).fetchall()
        local_archive = None
        if raw:
            if all(matching(target_path(destination, r['path'], binding), r) for r in raw):
                local_archive = target_path(destination, raw[0]['path'], binding)
            else:
                with closing(get_stream(client, binding, key)) as stream:
                    write_member(stream, raw, destination, binding)
                local_archive = target_path(destination, raw[0]['path'], binding)
        members = db.execute("SELECT DISTINCT member,container_format FROM selected WHERE object_key=? AND member!=''",
                             (key,)).fetchall()
        if members:
            formats = {r['container_format'] for r in members}
            if len(formats) != 1:
                raise ValueError('ambiguous container format')
            fmt = formats.pop()
            wanted = {r['member'] for r in members}

            def consume(name, stream, key=key, wanted=wanted):
                rows = db.execute('SELECT * FROM selected WHERE object_key=? AND member=?', (key, name)).fetchall()
                write_member(stream, rows, destination, binding)
                wanted.remove(name)

            if fmt == 'zip':
                source = (local_archive.open('rb') if local_archive else
                          RangeReader(client, binding, key, facts['size']))
                with source, zipfile.ZipFile(source) as archive:
                    for name in list(wanted):
                        with archive.open(name) as stream:
                            consume(name, stream)
            elif fmt in {'tar', 'tar.gz', 'tgz', 'tar.xz', 'tar.bz2', 'tar.zst'}:
                source = local_archive.open('rb') if local_archive else get_stream(client, binding, key)
                with closing(source):
                    if fmt == 'tar.zst':
                        import zstandard
                        reader = zstandard.ZstdDecompressor().stream_reader(source, closefd=False)
                    else:
                        reader = source
                    with closing(reader), tarfile.open(fileobj=reader, mode='r|*') as archive:
                        for info in archive:
                            if info.name in wanted:
                                if not info.isfile():
                                    raise ValueError('indexed member is not a regular file')
                                with archive.extractfile(info) as stream:
                                    consume(info.name, stream)
                            if not wanted:
                                break
            else:
                raise ValueError('unsupported recovery container: ' + fmt)
            if wanted:
                raise ValueError('archive is missing indexed members')
        print(json.dumps({'restored_object': key}), flush=True)
    roots = {alias: str(target_path(destination, root, binding)) for alias, root in binding['roots'].items()}
    save(destination / 'roots.restored.json', roots)
    result = {'status': 'verified_selected_files' if prefixes else 'verified_available_files',
              'files': count, 'full_index_available': bool(meta.get('final_index')),
              'known_issues': gaps if meta.get('final_index') else None,
              'destination': str(destination), 'archive_staging_bytes': 0}
    save(destination / 'restore-result.json', result)
    return result


def locate(binding, db, dataset, artifact):
    entry = binding['dataset_bindings'].get(dataset)
    if not entry or artifact not in entry['artifacts']:
        raise ValueError('dataset version or artifact is not bound')
    alias, relative = entry['artifacts'][artifact].split(':', 1)
    if alias not in binding['roots']:
        return {'dataset': dataset, 'artifact': artifact, 'status': 'unconfigured_root'}
    path = str(Path(binding['roots'][alias]) / relative)
    row = db.execute('SELECT * FROM files WHERE path=?', (path,)).fetchone()
    if row:
        return {'dataset': dataset, 'artifact': artifact, 'status': 'verified', **dict(row),
                'cos_uri': 'cos://' + binding['bucket'] + '/' + row['object_key']}
    children = db.execute('SELECT count(*) FROM files WHERE path>=? AND path<?',
                          (path.rstrip('/') + '/', path.rstrip('/') + '0')).fetchone()[0]
    return {'dataset': dataset, 'artifact': artifact, 'path': path,
            'status': 'directory_has_verified_files' if children else 'not_yet_verified',
            'verified_paths': children}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['bind', 'prepare', 'locate', 'restore'])
    parser.add_argument('--binding', type=Path, default=DEFAULT_BINDING)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--reuse', type=Path, action='append', default=[])
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--path-prefix', action='append', default=[])
    parser.add_argument('--allow-incomplete', action='store_true')
    parser.add_argument('--dataset')
    parser.add_argument('--artifact')
    args = parser.parse_args()
    if args.command == 'restore' and not args.destination:
        parser.error('restore requires --destination')
    if args.command == 'locate' and not (args.dataset and args.artifact):
        parser.error('locate requires --dataset and --artifact')
    from qcloud_cos.cos_exception import CosClientError, CosServiceError
    try:
        if args.command == 'bind':
            bind(args)
            return
        binding = json.loads(args.binding.read_text())
        args.work.mkdir(parents=True, exist_ok=True)
        with (args.work / 'restore.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            client = cos_client(binding)
            try:
                db = prepare(client, binding, args.work)
                try:
                    if args.command == 'restore':
                        destination = args.destination.resolve()
                        destination.mkdir(parents=True, exist_ok=True)
                        result = restore(client, binding, db, destination,
                                         args.path_prefix, args.allow_incomplete)
                    elif args.command == 'locate':
                        result = locate(binding, db, args.dataset, args.artifact)
                    else:
                        result = {'files': db.execute('SELECT count(*) FROM files').fetchone()[0],
                                  'full_index_available': bool(dict(db.execute('SELECT key,value FROM meta')).get('final_index'))}
                    print(json.dumps(result, ensure_ascii=False))
                finally:
                    db.close()
            finally:
                client._session.close()
    except (CosClientError, CosServiceError) as exc:
        print(json.dumps({'error': type(exc).__name__,
                          'code': exc.get_error_code() if isinstance(exc, CosServiceError) else None}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
