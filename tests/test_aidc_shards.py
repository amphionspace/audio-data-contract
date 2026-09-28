import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from aidc_migrate import build_batches, database
from aidc_shards import export_plans, import_results, validate_receipt
from aidc_supervise import pending_work
from aidc_transfer import encoded, receive, save, signature, write_stream


def fixture(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    remote = tmp_path / 'remote'
    remote.mkdir()
    config = {'run': 'test', 'destination': str(remote),
              'sharding': {'directory': str(work / 'shards')}}
    db = database(work)
    for number in range(1, 13):
        source = tmp_path / (f'{number}.jsonl' if number == 5 else f'{number}.wav')
        source.write_bytes(b'x' * (30 if number == 6 else 5))
        sig = signature(source)
        db.execute('''INSERT INTO objects(id,source,target,size,mtime,device,inode,kind,status)
            VALUES(?,?,?,?,?,?,?,?,?)''', (number, str(source), f'datasets/test/{source.name}', *sig,
                                         'audio-index' if number == 9 else None,
                                         'complete' if number == 3 else 'pending'))
    db.commit()
    return work, remote, config, db


def test_shards_disjoint_and_legacy_batches_retained(tmp_path):
    work, _, config, db = fixture(tmp_path)
    legacy = {'run': 'test', 'batch': 'b00000001', 'files': [{'id': 1}]}
    db.execute("INSERT INTO batches(id,plan,status,bytes) VALUES(1,?,'pending',5)", (json.dumps(legacy),))
    db.execute("UPDATE objects SET status='queued' WHERE id=1")
    db.commit()
    build_batches(db, config, 20, 10)
    owners = {}
    for batch in db.execute('SELECT b.*,a.agent FROM batches b LEFT JOIN batch_agents a ON a.batch=b.id'):
        plan = json.loads(batch['plan'])
        for row in plan['files']:
            owner = batch['agent'] or 'a'
            assert row['id'] not in owners or row['id'] == 6
            owners[row['id']] = owner
            assert plan['run'] == ('test' if owner == 'a' else 'test-' + owner)
    assert owners == {1: 'a', 2: 'c', 4: 'a', 5: 'a', 6: 'a', 7: 'd',
                      8: 'a', 9: 'a', 10: 'c', 11: 'd', 12: 'a'}
    assert json.loads(db.execute('SELECT plan FROM batches WHERE id=1').fetchone()[0]) == legacy
    plans = list((work / 'shards').glob('agent-*/plans/*.json'))
    assert plans
    before = {p: p.read_bytes() for p in plans}
    # Simulate crash after file publication but before exported flag committed.
    db.execute('UPDATE batch_agents SET exported=0')
    db.commit()
    export_plans(db, config)
    assert all(p.read_bytes() == data for p, data in before.items())
    db.execute("INSERT INTO meta VALUES('scan_complete','true')")
    db.execute("UPDATE objects SET status='complete'")
    db.execute("UPDATE batches SET status='complete' WHERE status='pending'")
    db.commit()
    assert pending_work(work)['transfer']
    assert not pending_work(work)['ready']


def test_import_only_after_remote_receipt_matches(tmp_path, monkeypatch):
    import aidc_shards

    work, remote, config, db = fixture(tmp_path)
    build_batches(db, config, 20, 10)
    batch = db.execute("SELECT b.* FROM batches b JOIN batch_agents a ON a.batch=b.id WHERE a.agent='b'").fetchone()
    plan = json.loads(batch['plan'])
    stream = io.BytesIO()
    write_stream(stream, plan)
    stream.seek(0)
    receipt = receive(remote, plan['run'], plan['batch'], stream)
    path = work / 'shards/agent-b/results' / (plan['batch'] + '.json')
    save(path, receipt)
    monkeypatch.setattr(aidc_shards, 'remote_command', lambda *args: ['unused'])
    monkeypatch.setattr(aidc_shards.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, b'null'))
    with pytest.raises(ValueError, match='differs from destination'):
        import_results(db, config, work)
    assert db.execute('SELECT status FROM batches WHERE id=?', (batch['id'],)).fetchone()[0] == 'external'
    monkeypatch.setattr(aidc_shards.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, encoded(receipt)))
    import_results(db, config, work)
    assert db.execute('SELECT status FROM batches WHERE id=?', (batch['id'],)).fetchone()[0] == 'complete'
    assert not path.exists()
    for row in plan['files']:
        assert db.execute('SELECT status FROM objects WHERE id=?', (row['id'],)).fetchone()[0] == 'complete'
    bad = {**receipt, 'files': []}
    with pytest.raises(ValueError, match='file count'):
        validate_receipt(plan, bad)


def test_portable_mount_keeps_original_plan_hash_and_checks_changes(tmp_path):
    source = tmp_path / 'audio.wav'
    source.write_bytes(b'hello')
    sig = signature(source)
    plan = {'run': 'test-b', 'batch': 'b1', 'files': [{'source': str(source),
            'signature': [*sig[:2], sig[2] + 1, sig[3] + 1], 'length': 5,
            'target': 'datasets/test/audio.wav'}]}
    with pytest.raises(ValueError, match='source changed'):
        write_stream(io.BytesIO(), plan)
    stream = io.BytesIO()
    write_stream(stream, plan, portable=True)
    stream.seek(0)
    remote = tmp_path / 'remote'
    remote.mkdir()
    receipt = receive(remote, plan['run'], plan['batch'], stream)
    assert receipt['plan_sha256'] == hashlib.sha256(encoded(plan)).hexdigest()
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='source changed'):
        write_stream(io.BytesIO(), plan, portable=True)


def test_remote_guard_rejects_duplicate_agent(tmp_path):
    receiver = Path(__file__).resolve().parents[1] / 'scripts/aidc_transfer.py'
    command = [sys.executable, str(receiver), 'guard', '--root', str(tmp_path), '--run', 'test-b']
    first = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert first.stdout.readline() == b'ready\n'
        second = subprocess.run(command, input=b'', capture_output=True, timeout=5, check=False)
        assert second.returncode != 0
        assert b'BlockingIOError' in second.stderr
    finally:
        first.stdin.close()
        first.wait(timeout=5)
    third = subprocess.run(command, input=b'', capture_output=True, timeout=5, check=False)
    assert third.returncode == 0 and third.stdout == b'ready\n'
