"""Static file ownership: A owns SQLite; B/C/D consume immutable shared plans."""

import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from aidc_transfer import encoded, remote_command, save, send, signature


def export_plans(db, config):
    root = Path(config['sharding']['directory'])
    for batch in db.execute('''SELECT b.*,a.agent FROM batches b JOIN batch_agents a
            ON a.batch=b.id WHERE a.agent!='a' AND a.exported=0''').fetchall():
        folder = root / ('agent-' + batch['agent'])
        plan = json.loads(batch['plan'])
        path = folder / 'plans' / (plan['batch'] + '.json')
        if path.exists():
            if json.loads(path.read_text()) != plan:
                raise ValueError('exported plan changed: ' + str(path))
        else:
            save(path, plan)
        db.execute('UPDATE batch_agents SET exported=1 WHERE batch=?', (batch['id'],))
        db.commit()


def validate_receipt(plan, receipt):
    if receipt.get('plan_sha256') != hashlib.sha256(encoded(plan)).hexdigest():
        raise ValueError('receipt plan mismatch')
    files = receipt.get('files', [])
    if len(files) != len(plan['files']):
        raise ValueError('receipt file count mismatch')
    for source, received in zip(plan['files'], files):
        sha = received.get('sha256', '')
        if (received.get('target') != source['target'] or received.get('size') != source['length']
                or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha)
                or (source.get('expected') and source['expected'] != sha)):
            raise ValueError('receipt file mismatch')


def import_results(db, config, work):
    """Only A writes SQLite; independently fetch remote receipts before accepting."""
    from aidc_migrate import retryable

    root = Path(config['sharding']['directory'])
    for agent in 'bcd':
        folder = root / ('agent-' + agent)
        for path in sorted((folder / 'results').glob('b*.json')):
            number = int(path.stem[1:])
            batch = db.execute('''SELECT b.*,a.agent FROM batches b JOIN batch_agents a
                ON a.batch=b.id WHERE b.id=?''', (number,)).fetchone()
            if batch is None or batch['agent'] != agent:
                raise ValueError('result outside assigned scope: ' + str(path))
            plan = json.loads(batch['plan'])
            reported = json.loads(path.read_text())
            validate_receipt(plan, reported)
            if batch['status'] != 'complete':
                remote = {**config, 'run': plan['run']}
                try:
                    result = subprocess.run(remote_command(remote, 'receipt', '--batch', plan['batch']),
                                            capture_output=True, check=True, timeout=60)
                except (OSError, subprocess.SubprocessError) as error:
                    if retryable(error):
                        return
                    raise
                receipt = json.loads(result.stdout)
                if receipt != reported:
                    raise ValueError('reported receipt differs from destination: ' + str(path))
                for row in plan['files']:
                    if signature(row['source']) != row['signature']:
                        raise ValueError('source changed before receipt import: ' + row['source'])
                save(work / 'receipts' / (str(number) + '.json'), receipt)
                for row, received in zip(plan['files'], receipt['files']):
                    db.execute("UPDATE objects SET status='complete',sha256=? WHERE id=?",
                               (received['sha256'], row['id']))
                db.execute("UPDATE batches SET status='complete',error=NULL WHERE id=?", (number,))
                db.commit()
            archive = folder / 'imported' / path.name
            archive.parent.mkdir(parents=True, exist_ok=True)
            path.replace(archive)


def worker(args):
    from aidc_migrate import error_details, retryable

    folder = args.handoff.resolve()
    config = json.loads((folder / 'worker.json').read_text())
    if config['agent'] not in 'bcd' or folder.name != 'agent-' + config['agent']:
        raise ValueError('invalid agent handoff')
    local = args.local_state.resolve()
    local.mkdir(parents=True, exist_ok=True)
    guard = subprocess.Popen(remote_command(config, 'guard'), stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if guard.stdout.readline() != b'ready\n':
        _, err = guard.communicate()
        raise RuntimeError('agent already active or remote lock unavailable: ' + err.decode())
    completed = {p.stem for name in ('results', 'imported') for p in (folder / name).glob('b*.json')}
    errors = {p.stem: json.loads(p.read_text()) for p in (local / 'errors').glob('b*.json')}
    started = time.monotonic()
    last_report = 0
    streamed = 0
    meter_lock = threading.Lock()

    def progress(size):
        nonlocal streamed
        with meter_lock:
            streamed += size

    futures = {}
    try:
        with ThreadPoolExecutor(args.workers) as pool:
            while True:
                if guard.poll() is not None:
                    raise RuntimeError('lost exclusive agent lock; stop and inspect before restart')
                guard.stdin.write(b'.')
                guard.stdin.flush()
                active = {plan['batch'] for plan in futures.values()}
                for path in sorted((folder / 'plans').glob('b*.json')):
                    if len(futures) >= args.workers:
                        break
                    if path.stem in completed or path.stem in active:
                        continue
                    error = errors.get(path.stem)
                    if error and (not error['retryable'] or error['retry_at'] > time.time()):
                        continue
                    plan = json.loads(path.read_text())
                    if plan['run'] != config['run'] or plan['batch'] != path.stem:
                        raise ValueError('plan outside assigned run')
                    futures[pool.submit(send, config, plan, progress, True)] = plan
                done, _ = wait(futures, timeout=10, return_when=FIRST_COMPLETED) if futures else ([], [])
                for future in done:
                    plan = futures.pop(future)
                    try:
                        receipt = future.result()
                        validate_receipt(plan, receipt)
                        save(folder / 'results' / (plan['batch'] + '.json'), receipt)
                        completed.add(plan['batch'])
                        errors.pop(plan['batch'], None)
                        (local / 'errors' / (plan['batch'] + '.json')).unlink(missing_ok=True)
                        (folder / 'errors' / (plan['batch'] + '.json')).unlink(missing_ok=True)
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                        attempts = errors.get(plan['batch'], {}).get('attempts', 0) + 1
                        record = {'error': error_details(error), 'retryable': retryable(error),
                                  'attempts': attempts, 'retry_at': time.time() + min(300, 10 * 2 ** min(attempts, 5))}
                        errors[plan['batch']] = record
                        save(local / 'errors' / (plan['batch'] + '.json'), record)
                        save(folder / 'errors' / (plan['batch'] + '.json'), record)
                        print(json.dumps({'batch': plan['batch'], **record}), flush=True)
                now = time.monotonic()
                if now - last_report >= 30:
                    state = {'agent': config['agent'], 'pid': os.getpid(), 'at': time.time(),
                             'workers': args.workers, 'active_batches': len(futures), 'complete_batches': len(completed),
                             'streamed_bytes': streamed, 'bytes_per_second': streamed / max(now - started, 1),
                             'errors': len(errors)}
                    save(local / 'progress.json', state)
                    save(folder / 'progress.json', state)
                    print(json.dumps(state), flush=True)
                    last_report = now
                if not futures:
                    time.sleep(10)
    finally:
        if guard.stdin:
            guard.stdin.close()
        try:
            guard.wait(timeout=10)
        except subprocess.TimeoutExpired:
            guard.kill()
            guard.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--local-state', type=Path, required=True)
    parser.add_argument('--workers', type=int, required=True, help='Independent per-container concurrency; no global quota')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')
    worker(args)


if __name__ == '__main__':
    main()
