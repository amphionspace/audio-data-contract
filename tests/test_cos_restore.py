import gzip
import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import zstandard

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
for name in ('cos_backup', 'cos_sync_catalog', 'cos_restore', 'cos_relocate'):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
restore = sys.modules['cos_restore']
relocate = sys.modules['cos_relocate']
backup = sys.modules['cos_backup']


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Cloud:
    def __init__(self):
        self.objects, self.facts, self.reads = {}, {}, []

    def put(self, key, data, plan='plan'):
        self.objects[key] = data
        crc = backup.crc64()
        crc.update(data)
        facts = {'size': len(data), 'sha256': sha(data), 'crc64': str(crc.crcValue)}
        self.facts[key] = {**facts, 'plan_sha256': plan}
        return facts

    def get_object(self, Bucket, Key, **kwargs):
        self.reads.append((Key, kwargs))
        data = self.objects[Key]
        if 'Range' in kwargs:
            start, end = map(int, kwargs['Range'].removeprefix('bytes=').split('-'))
            data = data[start:end + 1]
        return {'Body': type('Body', (), {'get_raw_stream': lambda _: io.BytesIO(data)})()}

    def head_object(self, Bucket, Key):
        facts = self.facts[Key]
        return {'Content-Length': str(facts['size']), 'x-cos-hash-crc64ecma': facts['crc64'],
                'x-cos-meta-plan-sha256': facts['plan_sha256']}

    def list_objects(self, Bucket, Prefix, Marker):
        # Paginate to exercise discovery instead of assuming one page.
        keys = sorted(key for key in self.objects if key.startswith(Prefix) and key > Marker)
        return {'Contents': [{'Key': key} for key in keys[:2]],
                'IsTruncated': str(len(keys) > 2).lower(),
                'NextMarker': keys[1] if len(keys) > 2 else ''}


@pytest.fixture
def setup(tmp_path):
    binding = {'bucket': 'bucket', 'region': 'region', 'roots': {'data': '/old/data'},
               'allowed': ['/old/data'], 'datasets': [], 'reused_receipts': [],
               'batches_prefix': 'run/batches/', 'index_prefix': 'run/index/',
               'dataset_bindings': {}}
    return Cloud(), binding, tmp_path / 'work', tmp_path / 'destination'


def publish(cloud, files, fmt='tar.zst', key='run/batches/one/shard.tar.zst'):
    if fmt == 'raw':
        content = files[0][1]
    else:
        archive = io.BytesIO()
        if fmt == 'zip':
            with zipfile.ZipFile(archive, 'w') as output:
                for name, data, _ in files:
                    output.writestr(name, data)
        else:
            with tarfile.open(fileobj=archive, mode='w:gz' if fmt == 'tar.gz' else 'w') as output:
                for name, data, _ in files:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    output.addfile(info, io.BytesIO(data))
        content = archive.getvalue()
        if fmt == 'tar.zst':
            content = zstandard.ZstdCompressor().compress(content)
    facts = cloud.put(key, content)
    shard = {'key': key, **facts, 'format': fmt, 'files': [
        {'sha256': sha(data), 'size': len(data), 'sources': [{'path': p} for p in paths]}
        for _, data, paths in files]}
    receipt = {'status': 'verified', 'plan_sha256': 'plan', 'shards': [shard]}
    cloud.put(restore.receipt_key(receipt), backup.encoded(receipt))
    return receipt


def test_cloud_only_restore_preserves_bytes_aliases_and_subset(setup):
    cloud, binding, work, destination = setup
    data = b'waveform' * 100
    publish(cloud, [('files/' + sha(data), data, ['/old/data/a.wav', '/old/data/alias.wav'])])
    db = restore.prepare(cloud, binding, work)
    with pytest.raises(ValueError, match='backup incomplete'):
        restore.restore(cloud, binding, db, destination)
    result = restore.restore(cloud, binding, db, destination, ['/old/data', '/old/data/a.wav'], True)
    assert result['files'] == 2
    first = destination / 'files/old/data/a.wav'
    alias = first.with_name('alias.wav')
    assert first.read_bytes() == data
    assert first.stat().st_ino == alias.stat().st_ino
    assert json.loads((destination / 'roots.restored.json').read_text())['data'] == str(first.parent)
    reads = list(cloud.reads)

    def no_inventory_copy(action, table, *_):
        if action == sqlite3.SQLITE_INSERT and table == 'selected':
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    db.set_authorizer(no_inventory_copy)
    restore.restore(cloud, binding, db, destination, allow_incomplete=True)
    # Python 3.10 requires a callable when replacing an authorizer.
    db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
    assert cloud.reads == reads
    # Switching back to a subset must work after a full restore in the same DB.
    restore.restore(cloud, binding, db, destination, ['/old/data/a.wav'], True)
    db.close()


@pytest.mark.parametrize('fmt', ['tar.gz', 'zip'])
def test_final_index_restores_members_reused_from_raw_source_archive(setup, fmt):
    cloud, binding, work, destination = setup
    data = b'archive member' * 1000
    receipt = publish(cloud, [('nested/audio.wav', data, ['/old/data/unused'])], fmt,
                      'run/batches/source/shard.bin')
    raw = cloud.objects[receipt['shards'][0]['key']]
    receipt['shards'][0]['format'] = 'raw'
    receipt['shards'][0]['files'] = [{'size': len(raw), 'sha256': sha(raw),
                                     'sources': [{'path': '/old/data/source.' + fmt}]}]
    cloud.put(restore.receipt_key(receipt), backup.encoded(receipt))
    row = {'type': 'files', 'status': 'verified', 'path': '/old/data/extracted.wav',
           'size': len(data), 'sha256': sha(data), 'object_key': receipt['shards'][0]['key'],
           'member': 'nested/audio.wav', 'container_format': fmt}
    index = gzip.compress(backup.encoded(row) + b'\n')
    publish(cloud, [('', index, ['/old/data/index.gz'])], 'raw', 'run/index/final/shard.bin')
    db = restore.prepare(cloud, binding, work)
    result = restore.restore(cloud, binding, db, destination)
    assert result['full_index_available']
    assert (destination / 'files/old/data/extracted.wav').read_bytes() == data
    assert not (destination / ('files/old/data/source.' + fmt)).exists()
    if fmt == 'zip':
        assert any(kwargs.get('Range') for _, kwargs in cloud.reads)
    db.close()


def test_corrupt_member_and_existing_file_never_overwrite(setup):
    cloud, binding, work, destination = setup
    receipt = publish(cloud, [('', b'good', ['/old/data/a.bin'])], 'raw', 'run/batches/raw/shard.bin')
    db = restore.prepare(cloud, binding, work)
    cloud.objects[receipt['shards'][0]['key']] = b'evil'
    with pytest.raises(ValueError, match='SHA-256/size mismatch'):
        restore.restore(cloud, binding, db, destination, allow_incomplete=True)
    target = destination / 'files/old/data/a.bin'
    assert not target.exists()
    assert not list(target.parent.glob('.cos-restore-*'))
    target.write_bytes(b'user work')
    with pytest.raises(ValueError, match='refusing overwrite'):
        restore.restore(cloud, binding, db, destination, allow_incomplete=True)
    assert target.read_bytes() == b'user work'
    db.close()


def test_recovery_paths_cannot_escape_or_follow_symlinks(setup, tmp_path):
    _, binding, _, destination = setup
    for path in ('/old/data/../../etc/passwd', '/etc/passwd', 'relative.wav'):
        with pytest.raises(ValueError):
            restore.target_path(destination, path, binding)
    (destination / 'files/old').mkdir(parents=True)
    (destination / 'files/old/data').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='symlink'):
        restore.target_path(destination, '/old/data/a.wav', binding)


def test_bad_final_index_does_not_replace_available_index(setup):
    cloud, binding, work, _ = setup
    publish(cloud, [('', b'available', ['/old/data/a.bin'])], 'raw', 'run/batches/raw/shard.bin')
    db = restore.prepare(cloud, binding, work)
    db.close()
    receipt = publish(cloud, [('', gzip.compress(b'{}\n'), ['/old/data/index.gz'])],
                      'raw', 'run/index/final/shard.bin')
    row = {'type': 'issues', 'reason': 'missing'}
    cloud.objects[receipt['shards'][0]['key']] = gzip.compress(backup.encoded(row) + b'\n')
    with pytest.raises(ValueError, match='index SHA-256 mismatch'):
        restore.prepare(cloud, binding, work)
    db = restore.database(work / 'restore.sqlite')
    assert db.execute('SELECT path FROM files').fetchone()[0] == '/old/data/a.bin'
    assert 'final_index' not in dict(db.execute('SELECT key,value FROM meta'))
    db.close()


def test_final_index_publication_during_discovery_keeps_receipts_complete(setup, monkeypatch):
    cloud, binding, work, destination = setup
    publish(cloud, [('', b'first', ['/old/data/first.bin'])], 'raw', 'run/batches/first/shard.bin')
    original_listing = cloud.list_objects
    published = False

    def listing(**kwargs):
        nonlocal published
        page = original_listing(**kwargs)
        if kwargs['Prefix'] == binding['batches_prefix'] and not published:
            published = True
            last = publish(cloud, [('', b'last', ['/old/data/last.bin'])], 'raw', 'run/batches/last/shard.bin')
            row = {'type': 'files', 'status': 'verified', 'path': '/old/data/last.bin',
                   'size': 4, 'sha256': sha(b'last'), 'object_key': last['shards'][0]['key'],
                   'member': '', 'container_format': 'raw'}
            index = gzip.compress(backup.encoded(row) + b'\n')
            publish(cloud, [('', index, ['/old/data/index.gz'])], 'raw', 'run/index/final/shard.bin')
        return page

    monkeypatch.setattr(cloud, 'list_objects', listing)
    db = restore.prepare(cloud, binding, work)
    assert db.execute('SELECT count(*) FROM files f LEFT JOIN objects o ON f.object_key=o.key WHERE o.key IS NULL').fetchone()[0] == 0
    db.close()
    db = restore.prepare(cloud, binding, work)
    restore.restore(cloud, binding, db, destination)
    assert (destination / 'files/old/data/last.bin').read_bytes() == b'last'
    db.close()


def test_relocate_nested_audio_features_commands_and_preserve_text(setup):
    cloud, binding, work, destination = setup
    original = '/old/data/train.jsonl.gz'
    binding['datasets'] = [{'dataset_id': 'sample', 'version': 'v1', 'artifacts': [
        {'name': 'train', 'root_alias': 'data', 'relative_path': 'train.jsonl.gz', 'kind': 'lhotse-cuts'}]}]
    binding['dataset_bindings'] = {'sample@v1': {'artifacts': {'train': 'data:train.jsonl.gz'}}}
    item = {'text': '/old/data/audio.wav', 'tracks': [{'cut': {'recording': {
        'sources': [{'type': 'file', 'source': 'audio.wav'}],
        'transforms': [{'kwargs': {'rir': {'sources': [{'type': 'command',
         'source': "tar -xOf /old/data/source.tar 'member with spaces.wav'"}]}}}]},
        'features': {'storage_type': 'lilcom_chunky', 'storage_path': '/old/data/features.lca'}}}]}
    data = gzip.compress(backup.encoded(item) + b'\n')
    files = [('files/' + sha(data), data, [original])]
    for name in ('audio.wav', 'source.tar', 'features.lca'):
        payload = name.encode()
        files.append(('files/' + sha(payload), payload, ['/old/data/' + name]))
    publish(cloud, files)
    db = restore.prepare(cloud, binding, work)
    assert restore.locate(binding, db, 'sample@v1', 'train')['status'] == 'verified'
    restore.restore(cloud, binding, db, destination, allow_incomplete=True)
    result = relocate.relocate(db, binding, destination)
    assert result == {'relocated': 1, 'not_restored': 0, 'failures': []}
    with gzip.open(destination / 'files/old/data/train.jsonl.gz', 'rt') as stream:
        changed = json.load(stream)
    assert changed['text'] == item['text']
    cut = changed['tracks'][0]['cut']
    assert cut['recording']['sources'][0]['source'] == str(destination / 'files/old/data/audio.wav')
    assert 'member with spaces.wav' in cut['recording']['transforms'][0]['kwargs']['rir']['sources'][0]['source']
    assert (destination / 'original-manifests/old/data/train.jsonl.gz').read_bytes() == data
    assert relocate.relocate(db, binding, destination)['relocated'] == 0
    db.close()


def test_relocation_missing_audio_leaves_original_manifest(setup):
    cloud, binding, work, destination = setup
    binding['datasets'] = [{'artifacts': [{'name': 'train', 'root_alias': 'data',
                                          'relative_path': 'train.jsonl', 'kind': 'sharegpt-jsonl'}]}]
    data = backup.encoded({'audios': ['/old/data/missing.wav']}) + b'\n'
    publish(cloud, [('files/' + sha(data), data, ['/old/data/train.jsonl'])])
    db = restore.prepare(cloud, binding, work)
    restore.restore(cloud, binding, db, destination, allow_incomplete=True)
    result = relocate.relocate(db, binding, destination)
    assert len(result['failures']) == 1
    assert (destination / 'files/old/data/train.jsonl').read_bytes() == data
    db.close()


def test_relocation_relative_parent_path_recovers_after_replace_interruption(setup, monkeypatch):
    cloud, binding, work, destination = setup
    binding['datasets'] = [{'artifacts': [{'name': 'train', 'root_alias': 'data',
                                          'relative_path': 'manifests/train.jsonl', 'kind': 'sharegpt-jsonl'}]}]
    data = backup.encoded({'audios': ['../audio.wav']}) + b'\n'
    publish(cloud, [('files/' + sha(data), data, ['/old/data/manifests/train.jsonl']),
                    ('files/' + sha(b'audio'), b'audio', ['/old/data/audio.wav'])])
    db = restore.prepare(cloud, binding, work)
    restore.restore(cloud, binding, db, destination, allow_incomplete=True)
    target = destination / 'files/old/data/manifests/train.jsonl'
    replace = Path.replace

    def interrupted_replace(path, other):
        result = replace(path, other)
        if other == target:
            raise OSError('interrupted after manifest replacement')
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', interrupted_replace)
        result = relocate.relocate(db, binding, destination)
    assert len(result['failures']) == 1
    assert json.loads(target.read_text())['audios'] == [str(destination / 'files/old/data/audio.wav')]
    result = relocate.relocate(db, binding, destination)
    assert result == {'relocated': 0, 'not_restored': 0, 'failures': []}
    assert (destination / 'original-manifests/old/data/manifests/train.jsonl').read_bytes() == data
    db.close()
