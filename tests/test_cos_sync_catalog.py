import gzip
import importlib.util
import io
import json
import os
import select
import sqlite3
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('cos_backup', SCRIPTS / 'cos_backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
sys.modules['cos_backup'] = backup
spec = importlib.util.spec_from_file_location('cos_sync_catalog', SCRIPTS / 'cos_sync_catalog.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
sys.modules['cos_sync_catalog'] = sync
spec = importlib.util.spec_from_file_location('cos_index_archives', SCRIPTS / 'cos_index_archives.py')
archives = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archives)


@pytest.fixture
def inventory(tmp_path):
    db = sync.connect(tmp_path)
    inv = sync.Inventory(db, {'data': tmp_path}, [tmp_path])
    yield db, inv
    db.close()


def test_nested_cuts_expand_audio_commands_rir_and_features(tmp_path, inventory):
    db, inv = inventory
    for name in ('audio.wav', 'rir.wav', 'archive.tar', 'feature.lca'):
        (tmp_path / name).write_bytes(name.encode())

    def recording(name):
        return {'sources': [{'type': 'file', 'source': str(tmp_path / name)}]}

    item = {'type': 'MixedCut', 'tracks': [{'cut': {
        'type': 'MonoCut', 'recording': {
            **recording('audio.wav'), 'transforms': [{'kwargs': {'rir': recording('rir.wav')}}]},
        'features': {'storage_type': 'lilcom_chunky', 'storage_path': str(tmp_path / 'feature.lca')},
    }}, {'cut': {'recording': {'sources': [
        {'type': 'command', 'source': 'tar -xOf archive.tar member.wav'}]}}}]}
    inv.lhotse(item, tmp_path / 'cuts.jsonl', 'data')
    assert {Path(r[0]).name for r in db.execute('SELECT path FROM files')} == {
        'audio.wav', 'rir.wav', 'archive.tar', 'feature.lca'}
    assert db.execute('SELECT count(*) FROM issues').fetchone()[0] == 0


def test_scan_directory_excludes_partial_and_escaping_symlink(tmp_path, inventory):
    db, inv = inventory
    (tmp_path / 'ready.wav').write_bytes(b'ready')
    (tmp_path / 'busy.tar').write_bytes(b'partial')
    (tmp_path / 'busy.tar.aria2').write_bytes(b'checkpoint')
    (tmp_path / '.env').write_bytes(b'secret')
    (tmp_path / 'escape.wav').symlink_to('/etc/passwd')
    inv.expand({'path': str(tmp_path), 'kind': 'source-directory', 'root_alias': 'data'})
    names = {Path(r[0]).name for r in db.execute('SELECT path FROM files')}
    assert 'ready.wav' in names
    assert not names & {'busy.tar', 'busy.tar.aria2', '.env', 'escape.wav'}
    reasons = {r[0] for r in db.execute('SELECT reason FROM issues')}
    assert {'outside_data_roots', 'private_path', 'unfinished_download'} <= reasons


def test_dedup_reuses_contents_across_batches_and_keeps_aliases(tmp_path, inventory, monkeypatch):
    db, inv = inventory
    a, b = tmp_path / 'a.wav', tmp_path / 'b.wav'
    a.write_bytes(b'identical')
    b.write_bytes(b'identical')
    inv.add(a)
    db.commit()
    config = {'roots': {'data': str(tmp_path)}, 'bucket': 'test', 'region': 'test', 'prefix': 'backup'}
    args = SimpleNamespace(shard_bytes=1024, hash_workers=2, part_mib=1, workers=1)
    first = sync.plan_batch(db, tmp_path, config, args)
    calls = []

    def fake_upload(args):
        plan = json.loads(args.plan.read_text())
        calls.append(args.plan)
        backup.save(args.plan.parent / 'upload/complete.json', {
            'shards': [{**job, 'key': 'verified-object'} for job in plan['jobs']]})

    monkeypatch.setattr(sync, 'upload', fake_upload)
    sync.transfer_batch(db, first, config, args)
    inv.add(b)
    db.commit()
    assert sync.plan_batch(db, tmp_path, config, args) is False
    assert len(calls) == 1
    rows = db.execute('SELECT path,status,object_key,member FROM files ORDER BY path').fetchall()
    assert len(rows) == 2
    assert all(r['status'] == 'verified' and r['object_key'] == 'verified-object' for r in rows)
    assert rows[0]['member'] == rows[1]['member']


def test_changed_source_is_recorded_without_blocking_other_files(tmp_path, inventory):
    db, inv = inventory
    changed, good = tmp_path / 'changed.wav', tmp_path / 'good.wav'
    changed.write_bytes(b'first')
    good.write_bytes(b'valid')
    inv.add(changed)
    inv.add(good)
    db.commit()
    changed.write_bytes(b'changed')
    batch = sync.plan_batch(db, tmp_path, {'roots': {}}, SimpleNamespace(shard_bytes=1024, hash_workers=1))
    plan = json.loads(Path(batch['plan']).read_text())
    assert len(plan['jobs'][0]['files']) == 1
    assert plan['jobs'][0]['files'][0]['sources'][0]['path'] == str(good)
    assert db.execute('SELECT status FROM files WHERE path=?', (str(changed),)).fetchone()[0] == 'failed'


def test_audio_index_sharegpt_target_and_extraction_references(tmp_path, inventory):
    db, inv = inventory
    audio = tmp_path / 'audio.wav'
    audio.write_bytes(b'audio')
    cases = {
        'audio-index': {'root_alias': 'data', 'relative_path': 'audio.wav'},
        'sharegpt-jsonl': {'audios': [str(audio)]},
        'target-asr-jsonl': {'mix_wav': str(audio), 'enroll_wav': str(audio)},
        'extraction-inventory': {'path': 'audio.wav'},
    }
    for kind, row in cases.items():
        path = tmp_path / 'inventories' / (kind + '.jsonl')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(row) + '\n')
        inv.expand({'path': str(path), 'kind': kind, 'root_alias': 'data'})
    assert [r[0] for r in db.execute('SELECT path FROM files')] == [str(audio)]
    assert db.execute('SELECT count(*) FROM issues').fetchone()[0] == 0


def test_final_index_reports_gaps_and_reuses_frozen_plan(tmp_path, inventory, monkeypatch):
    db, _ = inventory
    sync.issue(db, 'missing.wav', 'FileNotFoundError')
    db.execute("INSERT INTO meta VALUES('scan','done')")
    db.commit()
    plans = []
    monkeypatch.setattr(sync, 'upload', lambda args: plans.append(args.plan.read_bytes()))
    config = {'roots': {}, 'datasets': [], 'bucket': 'test', 'region': 'test', 'prefix': 'test'}
    sync.publish_index(db, tmp_path, config)
    sync.publish_index(db, tmp_path, config)
    assert plans[0] == plans[1]
    result = json.loads((tmp_path / 'result.json').read_text())
    assert result['status'] == 'completed_available_files_with_gaps'
    with gzip.open(tmp_path / 'recovery-index.jsonl.gz', 'rt') as stream:
        rows = [json.loads(line) for line in stream]
    assert any(row.get('reason') == 'FileNotFoundError' for row in rows)


def test_unpacked_copy_reuses_verified_source_archive(tmp_path, inventory):
    db, inv = inventory
    data = b'original waveform' * 1000
    path = tmp_path / 'source.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        info = tarfile.TarInfo('dataset/audio.wav')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    inv.add(path, 'source-archive')
    db.commit()
    archives.index_archive(db, db.execute('SELECT * FROM files').fetchone())
    assert db.execute('SELECT count(*) FROM contents').fetchone()[0] == 0
    archive_sha = backup.digest_file(path)
    assert db.execute('SELECT sha256 FROM archive_index').fetchone()[0] == archive_sha
    db.execute("UPDATE files SET status='verified',sha256=?,object_key='source-object',member='',container_format='raw'",
               (archive_sha,))
    db.commit()
    archives.publish_members(db)
    copy = tmp_path / 'extracted.wav'
    copy.write_bytes(data)
    inv.add(copy)
    db.commit()
    assert sync.plan_batch(db, tmp_path, {'roots': {}}, SimpleNamespace(shard_bytes=1024**2, hash_workers=1)) is False
    row = db.execute('SELECT * FROM files WHERE path=?', (str(copy),)).fetchone()
    assert row['object_key'] == 'source-object'
    assert row['container_format'] == 'tar.gz'
    with tarfile.open(path) as archive:
        assert archive.extractfile(row['member']).read() == data
    assert db.execute('SELECT count(*) FROM archive_members').fetchone()[0] == 0


def test_competing_process_waits_for_writer_beyond_sqlite_timeout(tmp_path, inventory):
    db, _ = inventory
    db.execute("INSERT INTO meta VALUES('first','committed')")
    program = """
import sqlite3,sys
from cos_sync_catalog import BackupConnection
db=sqlite3.connect(sys.argv[1],timeout=0.001,factory=BackupConnection)
print('ready',flush=True)
db.execute("INSERT INTO meta VALUES('second','committed')")
db.commit()
db.close()
"""
    env = {**os.environ, 'PYTHONPATH': str(SCRIPTS) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    child = subprocess.Popen([sys.executable, '-u', '-c', program, str(tmp_path / 'inventory.sqlite')],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([child.stdout], [], [], 5)[0]
        assert child.stdout.readline().strip() == 'ready'
        time.sleep(0.05)
        assert child.poll() is None
        db.commit()
        _, error = child.communicate(timeout=5)
        assert child.returncode == 0, error
        assert dict(db.execute('SELECT key,value FROM meta')) == {'first': 'committed', 'second': 'committed'}
    finally:
        db.rollback()
        if child.poll() is None:
            child.kill()
            child.wait()


def test_lightweight_status_does_not_scan_file_sizes(tmp_path, inventory):
    db, inv = inventory
    path = tmp_path / 'audio.wav'
    path.write_bytes(b'audio')
    inv.add(path)
    db.commit()

    def authorize(action, table, column, *_):
        if action == sqlite3.SQLITE_READ and table == 'files' and column == 'size':
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    db.set_authorizer(authorize)
    result = sync.status(db, count_files=False)
    assert result['discovered_paths'] == 1
    assert 'files' not in result
