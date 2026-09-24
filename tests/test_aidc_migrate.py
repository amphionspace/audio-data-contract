import gzip
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from aidc_migrate import (
    MigrationInventory,
    build_batches,
    database,
    init,
    paths_in_item,
    scan,
)
from aidc_transfer import assemble, digest, receive, signature, write_stream


def plan_for(tmp_path, data=b'payload', batch='pilot'):
    source = tmp_path / 'source.bin'
    source.write_bytes(data)
    return {'run': 'test', 'batch': batch, 'files': [
        {'source': str(source), 'target': 'datasets/sample/source/audio.bin',
         'signature': signature(source), 'length': len(data)}]}


def stream_for(plan):
    stream = io.BytesIO()
    write_stream(stream, plan)
    stream.seek(0)
    return stream


def test_stream_hashes_no_clobber_and_resume(tmp_path):
    root = tmp_path / 'remote'
    root.mkdir()
    plan = plan_for(tmp_path)
    receipt = receive(root, 'test', 'pilot', stream_for(plan))
    target = root / plan['files'][0]['target']
    assert target.read_bytes() == b'payload'
    assert receipt['files'][0]['sha256'] == digest(target)
    assert receive(root, 'test', 'pilot', stream_for(plan)) == receipt
    target.write_bytes(b'changed')
    with pytest.raises(ValueError, match='destination conflict'):
        receive(root, 'test', 'pilot', stream_for(plan))
    assert target.read_bytes() == b'changed'


def test_interrupted_batch_publishes_nothing_and_can_resume(tmp_path):
    root = tmp_path / 'remote'
    root.mkdir()
    plan = plan_for(tmp_path, os.urandom(1024 * 1024))
    data = stream_for(plan).getvalue()
    with pytest.raises((tarfile.ReadError, ValueError)):
        receive(root, 'test', 'pilot', io.BytesIO(data[:20000]))
    assert not (root / plan['files'][0]['target']).exists()
    assert not (root / 'migration/test/receipts/pilot.json').exists()
    receive(root, 'test', 'pilot', io.BytesIO(data))
    assert digest(root / plan['files'][0]['target']) == digest(plan['files'][0]['source'])


def test_changed_source_and_corrupt_stream_are_rejected(tmp_path):
    plan = plan_for(tmp_path)
    stream = stream_for(plan).getvalue()
    root = tmp_path / 'remote'
    root.mkdir()
    with pytest.raises(ValueError, match='checksum'):
        receive(root, 'test', 'pilot', io.BytesIO(stream.replace(b'payload', b'corrupt')))
    Path(plan['files'][0]['source']).write_bytes(b'changed source')
    with pytest.raises(ValueError, match='source changed'):
        write_stream(io.BytesIO(), plan)


def test_chunk_assembly(tmp_path):
    root = tmp_path / 'remote'
    root.mkdir()
    plan = plan_for(tmp_path, b'abcdefghij')
    parts = []
    for offset in (0, 5):
        chunk = {**plan, 'batch': f'part{offset}', 'files': [
            {**plan['files'][0], 'offset': offset, 'length': 5,
             'target': f'.incoming/test/chunks/1/{offset}'}]}
        parts.extend(receive(root, 'test', chunk['batch'], stream_for(chunk))['files'])
    result = assemble(root, 'test', {'id': 1, 'target': plan['files'][0]['target'],
                                   'size': 10, 'expected': digest(plan['files'][0]['source']), 'parts': parts})
    assert (root / result['target']).read_bytes() == b'abcdefghij'
    assert all(not (root / p['target']).exists() for p in parts)


def test_inventory_shared_files_exclusion_and_rewrite(tmp_path):
    work = tmp_path / 'state'
    work.mkdir()
    source = tmp_path / 'audio'
    source.mkdir()
    audio = source / 'sample.wav'
    audio.write_bytes(b'audio')
    alias = source / 'same.wav'
    os.link(audio, alias)
    config = {'roots': {'local': str(source)}, 'datasets': [], 'explicit': {}, 'anchors': []}
    db = database(work)
    inv = MigrationInventory(db, config)
    inv.owner = 'example@v1'
    assert inv.add(audio)
    assert inv.add(alias)
    assert db.execute('SELECT count(*) FROM objects').fetchone()[0] == 1
    blocked = source / 'WenetSpeech.wav'
    blocked.write_bytes(b'excluded')
    assert inv.add(blocked) is None
    assert db.execute('SELECT reason FROM issues').fetchone()[0] == 'excluded_wenetspeech_dependency'
    manifest = source / 'recordings.jsonl.gz'
    row = {'id': 'keep-id', 'text': str(audio), 'sources': [{'type': 'file', 'source': str(audio)}]}
    with gzip.open(manifest, 'wt') as out:
        out.write(json.dumps(row) + '\n')
    inv.add(manifest, 'lhotse-recordings', 'local')
    task = db.execute('SELECT * FROM tasks').fetchone()
    assert inv.expand(task) == 1
    paths_in_item(row, lambda _: '/workspace/data/datasets/example/source/sample.wav', config['roots'], 'lhotse-recordings', manifest)
    assert row['id'] == 'keep-id' and row['text'] == str(audio)
    assert row['sources'][0]['source'].startswith('/workspace/data/')
    db.close()


def test_archive_commands_are_parsed_without_execution(tmp_path):
    row = {'sources': [{'type': 'command', 'source': 'tar -xOf /old/audio.tar member.wav'}]}
    paths_in_item(row, lambda p: '/workspace/data/datasets/test/source/audio.tar', {}, '', '')
    assert row['sources'][0]['source'] == 'tar -xOf /workspace/data/datasets/test/source/audio.tar member.wav'
    malicious = {'sources': [{'type': 'command', 'source': 'touch /tmp/should-not-run'}]}
    with pytest.raises(ValueError, match='unsupported command'):
        paths_in_item(malicious, str, {}, '', '')


def test_scan_releases_writer_lock_and_resumes_committed_rows(tmp_path, monkeypatch):
    import aidc_migrate

    work = tmp_path / 'state'
    work.mkdir()
    source = tmp_path / 'source'
    source.mkdir()
    audio = source / 'audio.wav'
    audio.write_bytes(b'audio')
    manifest = source / 'recordings.jsonl'
    rows = [{'id': str(i), 'sources': [{'type': 'file', 'source': str(audio)}]} for i in range(2)]
    manifest.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    config = {'roots': {'local': str(source)}, 'datasets': [], 'explicit': {}, 'anchors': []}
    db = database(work)
    inventory = MigrationInventory(db, config)
    inventory.owner = 'example@v1'
    inventory.add(manifest, 'lhotse-recordings', 'local')
    inventory.add(audio)
    # Make the first row reuse a known dependency, bypassing add()'s commit.
    inventory.reference(str(audio), manifest, 'local')
    db.commit()

    def interrupted(item, *args):
        if item['id'] == '1':
            with sqlite_connection(work / 'migration.sqlite') as writer:
                writer.execute('PRAGMA busy_timeout=50')
                writer.execute("INSERT INTO meta VALUES('other_writer','ok')")
            raise RuntimeError('interrupted scan')
        result = paths_in_item(item, *args)
        inventory.last_commit -= 2
        return result

    monkeypatch.setattr(aidc_migrate, 'paths_in_item', interrupted)
    with pytest.raises(RuntimeError, match='interrupted scan'):
        inventory.expand(db.execute('SELECT * FROM tasks').fetchone())
    db.close()
    db = database(work)
    task = db.execute('SELECT * FROM tasks').fetchone()
    assert task['records'] == 1
    assert db.execute("SELECT value FROM meta WHERE key='other_writer'").fetchone()[0] == 'ok'
    parsed = []

    def resumed(item, *args):
        parsed.append(item['id'])
        return paths_in_item(item, *args)

    monkeypatch.setattr(aidc_migrate, 'paths_in_item', resumed)
    inventory = MigrationInventory(db, config)
    assert inventory.expand(task) == 2
    assert parsed == ['1']
    manifest.write_text(manifest.read_text() + json.dumps(rows[0]) + '\n')
    with pytest.raises(ValueError, match='manifest_changed_since_checkpoint'):
        inventory.expand(task)
    db.close()


def test_end_to_end_registry_uses_only_destination_audio(tmp_path):
    import shutil
    import wave

    from aidc_finalize import finalize

    from audio_data_contract import load_catalog, resolve_artifact, verify_artifact_file
    from audio_data_contract.declarations import write_declarations

    source = tmp_path / 'source'
    source.mkdir()
    audio = source / 'tone.wav'
    with wave.open(str(audio), 'wb') as out:
        out.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        out.writeframes(b'\x00\x00' * 160)
    row = {'id': 'sample', 'sources': [{'type': 'file', 'source': str(audio), 'channels': [0]}],
           'sampling_rate': 16000, 'num_samples': 160, 'duration': 0.01, 'channel_ids': [0]}
    recordings = source / 'recordings.jsonl.gz'
    with gzip.open(recordings, 'wt') as out:
        out.write(json.dumps(row) + '\n')
    audio_index = source / 'index.jsonl'
    audio_index.write_text(json.dumps({'cut_id': 'keep-original-id', 'root_alias': 'local', 'relative_path': 'tone.wav'}) + '\n')
    declarations = tmp_path / 'catalog'
    declarations.mkdir()
    views = tmp_path / 'views'
    views.mkdir()
    write_declarations(views / 'empty.yaml', [])
    spec = {'schema_version': 'dataset-catalog/1.0', 'dataset_id': 'example', 'version': 'v1',
            'languages': ['en'], 'tasks': ['asr'], 'artifacts': [
                {'name': 'recordings', 'kind': 'lhotse-recordings', 'root_alias': 'local', 'relative_path': recordings.name,
                 'sha256': digest(recordings), 'expected_bytes': recordings.stat().st_size},
                {'name': 'audio_index', 'kind': 'audio-index', 'root_alias': 'local', 'relative_path': audio_index.name}],
            'splits': {'test': {'recordings_artifact': 'recordings', 'audio_index_artifact': 'audio_index'}}}
    write_declarations(declarations / 'example.yaml', [spec])
    roots_file = tmp_path / 'roots.json'
    roots_file.write_text(json.dumps({'local': str(source)}))
    remote = tmp_path / 'remote'
    remote.mkdir()
    work = tmp_path / 'local-state'
    args = SimpleNamespace(work=work, catalog=declarations, views=views, roots=roots_file,
                           host='unused', destination=str(remote), run='test', dataset=None)
    init(args)
    scan(args)
    config = json.loads((work / 'config.json').read_text())
    db = database(work)
    assert db.execute('SELECT count(*) FROM issues').fetchone()[0] == 0
    build_batches(db, config, 8 * 1024**3, 1024**3)
    for batch in db.execute('SELECT * FROM batches').fetchall():
        plan = json.loads(batch['plan'])
        receipt = receive(remote, 'test', plan['batch'], stream_for(plan))
        for before, after in zip(plan['files'], receipt['files']):
            db.execute("UPDATE objects SET status='complete',sha256=? WHERE id=?", (after['sha256'], before['id']))
    db.commit()
    db.close()
    remote_work = remote / 'migration/test'
    with sqlite_connection(work / 'migration.sqlite') as local, sqlite_connection(remote_work / 'migration.sqlite') as copy:
        local.backup(copy)
    shutil.copyfile(work / 'config.json', remote_work / 'config.json')
    shutil.copytree(work / 'original-registry', remote_work / 'original-registry')
    original_hash = digest(recordings)
    finalize(remote_work)
    migrated = load_catalog(remote / 'registry/catalog')
    target_roots = {'aidc_data': remote}
    for artifact in migrated.get('example', 'v1').artifacts:
        target = resolve_artifact(migrated, 'example', 'v1', artifact.name, target_roots)
        verify_artifact_file(artifact, target)
        if artifact.name == 'recordings':
            with gzip.open(target, 'rt') as stream:
                localized = json.load(stream)
            assert localized['id'] == 'sample'
            assert Path(localized['sources'][0]['source']).is_relative_to(remote)
            assert Path(localized['sources'][0]['source']).read_bytes() == audio.read_bytes()
        else:
            localized = json.loads(target.read_text())
            assert localized['root_alias'] == 'aidc_data'
            assert localized['cut_id'] == 'keep-original-id'
            assert (remote / localized['relative_path']).is_file()
    assert digest(recordings) == original_hash
    finalize(remote_work)  # Deterministic rewrites and publication are resumable.


def sqlite_connection(path):
    import sqlite3
    return sqlite3.connect(path)


@pytest.mark.parametrize('invalid', ['missing_tar_member', 'duplicate_tar_member', 'dd_overrun'])
def test_archive_dependencies_must_resolve_completely(tmp_path, invalid):
    import sqlite3

    from aidc_finalize import verify_command_references

    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE command_refs(archive TEXT,kind TEXT,selector TEXT)')
    archive = tmp_path / 'audio.tar'
    with tarfile.open(archive, 'w') as out:
        for _ in range(2 if invalid == 'duplicate_tar_member' else 1):
            info = tarfile.TarInfo('audio.wav')
            info.size = 3
            out.addfile(info, io.BytesIO(b'abc'))
    if invalid == 'dd_overrun':
        kind, selector = 'dd', [archive.stat().st_size - 1, 2]
    else:
        kind = 'tar'
        selector = 'absent.wav' if invalid == 'missing_tar_member' else 'audio.wav'
    db.execute('INSERT INTO command_refs VALUES(?,?,?)', (str(archive), kind, json.dumps(selector)))
    with pytest.raises(ValueError):
        verify_command_references(db)
    db.close()


@pytest.mark.parametrize('returncode,retry', [(255, True), (1, False)])
def test_broken_stream_preserves_ssh_failure_class(tmp_path, monkeypatch, returncode, retry):
    import subprocess

    import aidc_transfer
    from aidc_migrate import retryable

    plan = plan_for(tmp_path, b'x' * (8 * 1024 * 1024))

    def command(config, action, *extra):
        code = ('print("null")' if action == 'receipt' else
                f'import sys; print("receiver error", file=sys.stderr); sys.exit({returncode})')
        return [sys.executable, '-c', code]

    monkeypatch.setattr(aidc_transfer, 'remote_command', command)
    with pytest.raises(subprocess.CalledProcessError) as error:
        aidc_transfer.send({}, plan)
    assert error.value.returncode == returncode
    assert b'receiver error' in error.value.stderr
    assert retryable(error.value) is retry


def test_transient_batch_retries_survive_restart_without_requeuing_corruption(tmp_path):
    import sqlite3
    import subprocess

    from aidc_migrate import record_batch_failure, retryable

    db = database(tmp_path)
    db.execute("INSERT INTO batches(id,status) VALUES(1,'running'),(2,'running')")
    record_batch_failure(db, 1, subprocess.CalledProcessError(255, 'ssh', stderr=b'connection reset'))
    record_batch_failure(db, 2, ValueError('checksum mismatch'))
    db.commit()
    db.close()
    db = database(tmp_path)
    assert list(map(tuple, db.execute('SELECT id,status FROM batches ORDER BY id'))) == [(1, 'retry'), (2, 'failed')]
    first = db.execute('SELECT * FROM batch_retries').fetchone()
    record_batch_failure(db, 1, BrokenPipeError(32, 'broken pipe'))
    second = db.execute('SELECT * FROM batch_retries').fetchone()
    assert second['attempts'] == 2 and second['not_before'] > first['not_before']
    assert retryable(sqlite3.OperationalError('database is locked'))
    assert not retryable(sqlite3.OperationalError('database disk image is malformed'))
    assert not retryable(subprocess.CalledProcessError(255, 'ssh', stderr=b'Permission denied'))
    db.close()


def test_supervisor_restarts_killed_worker_and_preserves_checkpoint(tmp_path, monkeypatch):
    import signal
    import subprocess
    import threading
    import time

    import aidc_supervise

    work = tmp_path / 'work'
    work.mkdir()
    db = database(work)
    db.execute("INSERT INTO meta VALUES('scan_complete','true')")
    db.execute("INSERT INTO objects(id,source,target,size,status) VALUES(1,'source','target',1,'pending')")
    db.commit()
    db.close()
    checkpoint = work / 'checkpoint'
    checkpoint.write_text('completed data stays intact')
    worker = tmp_path / 'aidc_migrate.py'
    worker.write_text('import time\nwhile True: time.sleep(1)\n')
    original_popen = subprocess.Popen
    children = []

    def launch(command, **kwargs):
        command[2] = str(worker)
        child = original_popen(command, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(aidc_supervise.subprocess, 'Popen', launch)
    args = SimpleNamespace(work=work, workers=4, tune=False, poll_seconds=.03,
                           restart_delay=.03, stall_seconds=60)
    thread = threading.Thread(target=aidc_supervise.supervise, args=(args,), daemon=True)
    thread.start()

    def wait_for(predicate):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if predicate():
                return
            if not thread.is_alive():
                raise AssertionError('supervisor exited early')
            time.sleep(.02)
        raise AssertionError('supervisor did not progress')

    try:
        wait_for(lambda: len(children) == 1 and aidc_supervise.process_info(work, 'transfer'))
        first = children[0]
        os.kill(first.pid, signal.SIGKILL)
        wait_for(lambda: len(children) == 2 and aidc_supervise.process_info(work, 'transfer'))
        assert children[1].pid != first.pid
        assert checkpoint.read_text() == 'completed data stays intact'
    finally:
        with sqlite_connection(work / 'migration.sqlite') as db:
            db.execute("UPDATE objects SET status='complete'")
        (work / 'verification.json').write_text('{"status":"complete"}')
        for child in children:
            if child.poll() is None:
                child.terminate()
        thread.join(timeout=5)
        for child in children:
            child.wait(timeout=5)
    assert not thread.is_alive()
    assert json.loads((work / 'controller.json').read_text())['status'] == 'complete'


def test_supervisor_stops_on_permanent_worker_error(tmp_path):
    from aidc_supervise import supervise

    db = database(tmp_path)
    db.execute("INSERT INTO meta VALUES('scan_complete','true')")
    db.execute("INSERT INTO objects(id,source,target,status) VALUES(1,'source','target','queued')")
    db.commit()
    db.close()
    (tmp_path / 'supervision.json').write_text(json.dumps({'workers': {
        'transfer': {'pid': 999999999, 'restarts': 1, 'failures': 0}}}))
    (tmp_path / 'transfer-exit.json').write_text(json.dumps({
        'pid': 999999999, 'retryable': False, 'error': 'destination conflict'}))
    args = SimpleNamespace(work=tmp_path, workers=4, tune=False, poll_seconds=.01,
                           restart_delay=.01, stall_seconds=60)
    supervise(args)
    status = json.loads((tmp_path / 'controller.json').read_text())
    assert status['status'] == 'needs_attention'
    assert status['blocked']['transfer'] == 'destination conflict'
    assert status['workers']['transfer']['restarts'] == 1
