"""Supervise one migration, retaining checkpoints and classifying failures."""

import fcntl
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from aidc_transfer import save


def process_info(work, name):
    try:
        pid = int((work / (name + '.pid')).read_text())
        proc = Path('/proc') / str(pid)
        command = (proc / 'cmdline').read_bytes().split(b'\0')
        args = [part.decode() for part in command if part]
        if not any(Path(part).name == 'aidc_migrate.py' for part in args) or name not in args:
            return None
        source_work = Path(args[args.index('--work') + 1])
        if not source_work.is_absolute():
            source_work = (proc / 'cwd').resolve() / source_work
        if source_work.resolve() != work.resolve():
            return None
        stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        io = (proc / 'io').read_text()
        return {'pid': pid, 'start_ticks': stat[19], 'group': int(stat[2]),
                'activity': [stat[11], stat[12], io]}
    except (OSError, ValueError, IndexError):
        return None


def pending_work(work):
    with sqlite3.connect(f'file:{work / "migration.sqlite"}?mode=ro', uri=True, timeout=2) as db:
        done = bool(db.execute("SELECT 1 FROM meta WHERE key='scan_complete'").fetchone())
        objects = bool(db.execute("SELECT 1 FROM objects WHERE status IN ('pending','queued','chunked') LIMIT 1").fetchone())
        batches = bool(db.execute("SELECT 1 FROM batches WHERE status IN ('pending','running','retry') LIMIT 1").fetchone())
        failed = bool(db.execute("SELECT 1 FROM batches WHERE status='failed' LIMIT 1").fetchone()
                      or db.execute("SELECT 1 FROM objects WHERE status='failed' LIMIT 1").fetchone())
    return {'scan': not done, 'transfer': not done or objects or batches,
            'failed': failed, 'ready': done and not objects and not batches and not failed}


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def event(name, **details):
    print(json.dumps({'at': time.time(), 'event': name, **details}), flush=True)


def signal_worker(info, sig):
    """Signal only a verified worker, or its surviving original process group."""
    pid = info.get('pid')
    if not pid:
        return
    try:
        stat = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[19] != info.get('start_ticks'):
            return  # PID was reused.
    except FileNotFoundError:
        pass
    try:
        if info.get('group') == pid:
            os.killpg(pid, sig)
        elif Path('/proc', str(pid)).exists():
            os.kill(pid, sig)
    except ProcessLookupError:
        pass


def supervise(args):
    work = args.work.resolve()
    children = {}
    with (work / 'watch.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (work / 'controller.pid').write_text(str(os.getpid()) + '\n')
        saved = read_json(work / 'supervision.json', {})
        workers = saved.get('workers', {})
        last_report = 0
        event('supervisor_started', pid=os.getpid())
        while True:
            now = time.time()
            for name, child in list(children.items()):
                if child.poll() is not None:
                    children.pop(name)
            live = {name: process_info(work, name) for name in ('scan', 'transfer', 'finalize')}
            try:
                pending = pending_work(work)
            except sqlite3.OperationalError as error:
                state = {'pid': os.getpid(), 'updated_at': now, 'status': 'waiting_for_database',
                         'error': str(error), 'running': [name for name, info in live.items() if info]}
                save(work / 'controller.json', state)
                event('database_wait', error=str(error))
                time.sleep(args.poll_seconds)
                continue
            blocked, restarting = {}, {}
            for name in ('scan', 'transfer', 'finalize'):
                info = workers.setdefault(name, {'restarts': 0, 'failures': 0})
                active = live[name]
                needed = (pending[name] if name != 'finalize'
                          else pending['ready'] and not live['scan'] and not live['transfer'])
                if active:
                    if active['pid'] != info.get('pid') or active['start_ticks'] != info.get('start_ticks'):
                        info.update(active, started_at=now, last_activity=now)
                        info.pop('next_restart', None)
                        info.pop('blocked', None)
                        info.pop('stopping_at', None)
                        info.pop('noticed_exit', None)
                        event('worker_running', worker=name, pid=active['pid'])
                    if active['activity'] != info.get('activity'):
                        info.update(activity=active['activity'], last_activity=now)
                    if name != 'finalize' and now - info['last_activity'] > args.stall_seconds:
                        if 'stopping_at' not in info:
                            event('worker_stalled', worker=name, pid=active['pid'])
                            signal_worker(info, signal.SIGTERM)
                            info['stopping_at'] = now
                        elif now - info['stopping_at'] > 30:
                            signal_worker(info, signal.SIGKILL)
                        restarting[name] = 'stalled worker is stopping'
                    continue
                if not needed:
                    continue
                exit_record = read_json(work / (name + '-exit.json'), {})
                if exit_record.get('pid') == info.get('pid') and not exit_record.get('retryable', True):
                    info['blocked'] = exit_record.get('error', 'worker failed')
                if (name == 'transfer' and pending['failed'] and exit_record.get('success')
                        and exit_record.get('pid') == info.get('pid')):
                    info['blocked'] = 'permanent batch or source error; see transfer.log'
                if name == 'finalize' and (work / 'verification.json').exists():
                    result = read_json(work / 'verification.json', {})
                    if result.get('status', '').startswith('complete'):
                        state = {'pid': os.getpid(), 'updated_at': now, 'status': 'complete', 'verification': result}
                        save(work / 'controller.json', state)
                        event('migration_complete')
                        return
                if info.get('blocked'):
                    blocked[name] = info['blocked']
                    continue
                if 'next_restart' not in info:
                    if info.get('pid') and info.get('noticed_exit') != info['pid']:
                        signal_worker(info, signal.SIGTERM)
                        info['noticed_exit'] = info['pid']
                        info['failures'] = (0 if now - info.get('started_at', now) >= 300 else info['failures']) + 1
                        event('worker_exited', worker=name, pid=info['pid'], error=exit_record.get('error', 'process disappeared'))
                    delay = min(300, args.restart_delay * 2 ** min(max(info['failures'] - 1, 0), 5)) if info.get('pid') else 0
                    info['next_restart'] = now + delay
                restarting[name] = info['next_restart']
                if now < info['next_restart']:
                    continue
                command = [sys.executable, '-u', str(Path(__file__).with_name('aidc_migrate.py')),
                           name, '--work', str(work)]
                if name == 'transfer':
                    tuning = read_json(work / 'throughput-tuning.json', {})
                    command += ['--workers', str(tuning.get('selected_workers', args.workers))]
                    if args.tune and not tuning:
                        command.append('--tune')
                with (work / (name + '.log')).open('ab') as log:
                    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True)
                children[name] = child
                (work / (name + '.pid')).write_text(str(child.pid) + '\n')
                info['restarts'] += 1
                info.pop('next_restart', None)
                # Save identity before the next poll, including for a quick crash.
                active = process_info(work, name)
                if active:
                    info.update(active, started_at=now, last_activity=now)
                else:
                    info.update(pid=child.pid, started_at=now)
                event('worker_started', worker=name, pid=child.pid, starts=info['restarts'])
            terminal = bool(blocked) and not any(live.values()) and not children and not restarting
            state = {'pid': os.getpid(), 'updated_at': now,
                     'status': 'needs_attention' if terminal else 'recovering' if restarting else 'running',
                     'running': [name for name, info in live.items() if info],
                     'restarting': restarting, 'blocked': blocked,
                     'workers': {name: {key: value for key, value in info.items() if key != 'activity'}
                                 for name, info in workers.items()}}
            if pending['failed'] and not pending['transfer'] and not pending['scan'] and not any(live.values()):
                state.update(status='needs_attention', error='permanent batch or source errors remain')
                terminal = True
            save(work / 'supervision.json', {'workers': workers})
            save(work / 'controller.json', state)
            if restarting or blocked or now - last_report >= 60:
                event('supervisor_status', **state)
                last_report = now
            if terminal:
                return
            time.sleep(args.poll_seconds)
