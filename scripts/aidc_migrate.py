#!/usr/bin/env python3
"""Inventory current declarations and migrate local data to aidc-dev over SSH.

The inventory and transfer commands may run concurrently. State is independent
of the COS inventory. Run finalize only after both commands have completed.
"""

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from aidc_transfer import encoded, remote_command, save, send, signature, ssh
from cos_sync_catalog import DIRECTORIES, PRIVATE, Inventory

from audio_data_contract import load_catalog
from audio_data_contract.audio_prepare import _parse
from audio_data_contract.declarations import declaration_files
from audio_data_contract.roots import load_roots

GIB = 1024 ** 3
JSONL = {'lhotse-recordings', 'lhotse-cuts', 'lhotse-supervisions', 'auto-lhotse',
         'audio-index', 'audio-records', 'sharegpt-jsonl', 'target-asr-jsonl',
         'extraction-inventory', 'jsonl-metadata'}
JSON = {'json-metadata', 'quality-report', 'dataset-state',
        'dataset-preparation-status', 'alignment-plan'}
PLAIN = {'metadata', 'license', 'archive', 'source-archive', 'source-archive-part',
         'repaired-source-archive', 'markdown-report', 'verification-trials'}


def database(work):
    db = sqlite3.connect(Path(work) / 'migration.sqlite', timeout=60)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA busy_timeout=60000')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
      CREATE TABLE IF NOT EXISTS objects(
        id INTEGER PRIMARY KEY,source TEXT UNIQUE,target TEXT UNIQUE,
        size INTEGER,mtime INTEGER,device INTEGER,inode INTEGER,
        kind TEXT,expected TEXT,status TEXT DEFAULT 'pending',sha256 TEXT,
        UNIQUE(device,inode,size,mtime));
      CREATE INDEX IF NOT EXISTS object_status ON objects(status,id);
      CREATE TABLE IF NOT EXISTS paths(path TEXT PRIMARY KEY,object_id INTEGER);
      CREATE TABLE IF NOT EXISTS directories(path TEXT PRIMARY KEY,target TEXT UNIQUE);
      CREATE TABLE IF NOT EXISTS tasks(path TEXT PRIMARY KEY,kind TEXT,root_alias TEXT,
        owner TEXT,status TEXT DEFAULT 'pending',records INTEGER DEFAULT 0);
      CREATE INDEX IF NOT EXISTS task_status ON tasks(status);
      CREATE TABLE IF NOT EXISTS edges(parent TEXT,child TEXT,PRIMARY KEY(parent,child));
      CREATE TABLE IF NOT EXISTS issues(path TEXT,reason TEXT,context TEXT,
        PRIMARY KEY(path,reason,context));
      CREATE TABLE IF NOT EXISTS resolutions(manifest TEXT,reference TEXT,path TEXT,
        PRIMARY KEY(manifest,reference));
      CREATE TABLE IF NOT EXISTS artifacts(spec TEXT,name TEXT,path TEXT,kind TEXT,
        PRIMARY KEY(spec,name));
      CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY,plan TEXT,status TEXT,
        error TEXT,bytes INTEGER,elapsed REAL);
      CREATE TABLE IF NOT EXISTS memberships(manifest TEXT,cut_id TEXT,
        PRIMARY KEY(manifest,cut_id));
      CREATE TABLE IF NOT EXISTS record_refs(manifest TEXT,spec TEXT,split TEXT,cut_id TEXT,
        PRIMARY KEY(manifest,spec,split,cut_id));
    ''')
    db.commit()
    return db


def excluded(value):
    return 'wenet' in str(value).lower()


def object_signature(row):
    return [row['size'], row['mtime'], row['device'], row['inode']]


def config_at(work):
    return json.loads((Path(work) / 'config.json').read_text())


def issue(db, path, reason, context=''):
    db.execute('INSERT OR IGNORE INTO issues VALUES(?,?,?)',
               (str(path), str(reason), str(context)))


def paths_in_item(item, resolve, roots, kind, manifest, destination='/workspace/data'):
    """Walk runtime fields only, retaining IDs, text and historical provenance.

    resolve returns the destination spelling, or the source spelling during
    inventory. Command parsing is shared with the existing audio preparation.
    """
    if isinstance(item, list):
        for child in item:
            paths_in_item(child, resolve, roots, kind, manifest, destination)
        return item
    if not isinstance(item, dict):
        return item
    if 'root_alias' in item and 'relative_path' in item:
        alias = item['root_alias']
        if alias not in roots:
            raise ValueError('unconfigured root: ' + alias)
        target = resolve(str(Path(roots[alias]) / item['relative_path']))
        if target.startswith(destination.rstrip('/') + '/'):
            item['root_alias'] = 'aidc_data'
            item['relative_path'] = str(Path(target).relative_to(destination))
    for source in item.get('sources', []):
        if source['type'] == 'file':
            source['source'] = resolve(source['source'])
        else:
            sentinel = Path('/__aidc_relative__')
            _, path, _ = _parse(source, sentinel, extract=True)
            original = str(path.relative_to(sentinel)) if path.is_relative_to(sentinel) else str(path)
            target = resolve(original)
            tokens = shlex.split(source['source'])
            start = 4 if tokens[0] == 'timeout' else 0
            if tokens[start] == 'tar':
                tokens[start + 2] = target
            else:
                tokens[start + 1] = 'if=' + target
            source['source'] = shlex.join(tokens)
    if item.get('storage_path') and 'storage_type' in item:
        if item['storage_type'] in {'numpy_files', 'lilcom_files'}:
            target = Path(resolve(str(Path(item['storage_path']) / item['storage_key'])))
            item['storage_path'], item['storage_key'] = str(target.parent), target.name
        else:
            item['storage_path'] = resolve(item['storage_path'])
    if 'audios' in item:
        item['audios'] = [resolve(value) for value in item['audios']]
    for key in ('mix_wav', 'enroll_wav', 'audio_path', 'audio_filepath', 'wav_path'):
        if isinstance(item.get(key), str):
            item[key] = resolve(item[key])
    if kind == 'extraction-inventory' and 'path' in item:
        item['path'] = resolve(str(Path(manifest).parent.parent / item['path']))
    for key, value in item.items():
        if key not in {'sources', 'provenance'} and isinstance(value, (dict, list)):
            paths_in_item(value, resolve, roots, kind, manifest, destination)
    return item


class MigrationInventory(Inventory):
    def __init__(self, db, config):
        roots = {k: Path(v) for k, v in config['roots'].items()}
        super().__init__(db, roots, list(roots.values()), config['datasets'])
        self.config = config
        self.owner = self.parent = ''
        self.anchors = sorted(config['anchors'], key=lambda a: -len(a['path']))
        self.explicit = config['explicit']
        self.last_commit = time.monotonic()

    def destination(self, path):
        value = str(path)
        if value in self.explicit:
            return self.explicit[value]
        for anchor in self.anchors:
            if path.is_relative_to(anchor['path']):
                return str(Path(anchor['target']) / path.relative_to(anchor['path']))
        # Dependencies outside registered directory artifacts still belong to
        # the referring dataset; preserve their internal tree below a data root.
        root = next((r for r in sorted(self.roots.values(), key=lambda p: -len(str(p)))
                     if path.is_relative_to(r)), None)
        if root is None:
            raise ValueError('outside_data_roots')
        relative = path.relative_to(root)
        base = root / relative.parts[0] if len(relative.parts) > 1 else root
        if relative.parts[:1] == ('LHOTSE',) and len(relative.parts) > 2:
            base = root / 'LHOTSE' / relative.parts[1]
        owner = self.owner.rsplit('@', 1)[0]
        label = base.name + '-' + hashlib.sha256(str(base).encode()).hexdigest()[:8]
        return str(Path('datasets') / owner / 'source' / label / path.relative_to(base))

    def add(self, path, kind=None, root_alias='', expected=None, expected_bytes=None):
        path = Path(os.path.abspath(path))
        spelling = str(path)
        if self.parent and spelling != self.parent:
            self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?)', (self.parent, spelling))
        cache_key = (spelling, kind)
        if cache_key in self.seen:
            return self.seen[cache_key]
        result = None
        try:
            if excluded(spelling):
                raise ValueError('excluded_wenetspeech_dependency')
            self.safe(path)
            if excluded(path.resolve()):
                raise ValueError('excluded_wenetspeech_dependency')
            if path.name.endswith(('.aria2', '.incomplete', '.partial', '.lock')):
                raise ValueError('unfinished_download')
            target = self.destination(path)
            if path.is_dir():
                self.db.execute('INSERT OR IGNORE INTO directories VALUES(?,?)', (spelling, target))
                kind = kind or 'source-directory'
            else:
                sig = signature(path)
                if Path(spelling + '.aria2').exists():
                    raise ValueError('unfinished_download')
                if expected_bytes is not None and sig[0] != expected_bytes:
                    raise ValueError('catalog_size_mismatch')
                row = self.db.execute('SELECT * FROM objects WHERE device=? AND inode=? AND size=? AND mtime=?',
                                      (sig[2], sig[3], sig[0], sig[1])).fetchone()
                if row:
                    number = row['id']
                    if expected and row['expected'] and expected != row['expected']:
                        raise ValueError('conflicting_catalog_hashes')
                    if expected:
                        self.db.execute('UPDATE objects SET expected=? WHERE id=?', (expected, number))
                    if kind in JSONL | JSON:
                        self.db.execute('UPDATE objects SET kind=? WHERE id=?', (kind, number))
                else:
                    number = self.db.execute('''INSERT INTO objects
                      (source,target,size,mtime,device,inode,kind,expected)
                      VALUES(?,?,?,?,?,?,?,?)''', (spelling, target, *sig, kind, expected)).lastrowid
                for alias in {spelling, str(path.resolve())}:
                    self.db.execute('INSERT OR IGNORE INTO paths VALUES(?,?)', (alias, number))
            if kind in DIRECTORIES | JSONL | JSON:
                self.db.execute('''INSERT OR IGNORE INTO tasks(path,kind,root_alias,owner)
                                  VALUES(?,?,?,?)''', (spelling, kind, root_alias, self.owner))
            result = spelling
        except (OSError, ValueError, sqlite3.IntegrityError) as error:
            issue(self.db, spelling, str(error), self.parent or self.owner)
        self.seen[cache_key] = result
        if len(self.seen) > 100000:
            self.seen.popitem(last=False)
        if time.monotonic() - self.last_commit > 1:
            self.db.commit()
            self.last_commit = time.monotonic()
        return result

    def reference(self, value, manifest, root_alias, kind=None):
        if not isinstance(value, str) or not value or '://' in value:
            raise ValueError('unsupported reference: ' + str(value))
        prior = self.db.execute('SELECT path FROM resolutions WHERE manifest=? AND reference=?',
                                (str(manifest), value)).fetchone()
        if prior:
            return prior['path']
        path = Path(value)
        if not path.is_absolute():
            candidates = {manifest.parent / path}
            if root_alias in self.roots:
                root = self.roots[root_alias]
                candidates.add(root / path)
                candidates.update(parent / path for parent in manifest.parents if parent.is_relative_to(root))
            # A source inventory may live in the repository, while its source
            # directories are declared under a different root alias.
            if not any(p.exists() for p in candidates):
                candidates.update(root / path for root in self.roots.values())
                for artifact in self.db.execute('SELECT path FROM artifacts WHERE spec=?', (self.owner,)):
                    candidate = Path(artifact['path'])
                    if candidate.is_dir():
                        candidates.add(candidate.parent / path)
            matches = {p.resolve() for p in candidates if p.exists()}
            if len(matches) != 1:
                raise ValueError('relative_path_missing_or_ambiguous: ' + value)
            path = matches.pop()
        path = Path(os.path.abspath(path))
        if not self.add(path, kind, root_alias):
            raise ValueError('unavailable dependency: ' + str(path))
        self.db.execute('INSERT OR IGNORE INTO resolutions VALUES(?,?,?)',
                        (str(manifest), value, str(path)))
        return str(path)

    def expand(self, task):
        path, kind = Path(task['path']), task['kind']
        self.owner, self.parent = task['owner'], str(path)
        if kind in DIRECTORIES:
            self.expand_directory(path, task['root_alias'])
            return 0
        before = signature(path)
        opener = gzip.open if path.suffix == '.gz' else open
        number = 0
        with opener(path, 'rt', encoding='utf-8') as stream:
            items = enumerate((json.loads(line) for line in stream if line.strip()), 1) if kind in JSONL else [(1, json.load(stream))]
            for number, item in items:
                try:
                    if kind == 'audio-records':
                        for slot in item.get('audio_slots', []):
                            ref = slot['ref']
                            key = ref['dataset_id'] + '@' + ref['version']
                            self.db.execute('INSERT OR IGNORE INTO record_refs VALUES(?,?,?,?)',
                                            (str(path), key, ref['split'], ref['cut_id']))
                            if excluded(key):
                                raise ValueError('excluded_wenetspeech_dependency: ' + key)
                    if kind == 'audio-index':
                        self.db.execute('INSERT OR IGNORE INTO memberships VALUES(?,?)',
                                        (str(path), item['cut_id']))
                    paths_in_item(item, lambda value: self.reference(value, path, task['root_alias']),
                                  self.config['roots'], kind, path)
                except (KeyError, TypeError, ValueError) as error:
                    issue(self.db, path, str(error), f'row {number}')
                if number % 1000 == 0:
                    self.db.execute('UPDATE tasks SET records=? WHERE path=?', (number, str(path)))
                    self.db.commit()
        if signature(path) != before:
            raise ValueError('manifest_changed_during_scan')
        return number

    def expand_directory(self, path, alias):
        visited = set()
        for directory, dirs, names in os.walk(path, followlinks=True):
            directory = Path(directory)
            real = directory.resolve()
            if real in visited:
                dirs[:] = []
                issue(self.db, directory, 'directory_alias_or_cycle', path)
                continue
            visited.add(real)
            dirs[:] = [name for name in dirs if name not in PRIVATE | {'.cache'} and not excluded(name)]
            for name in names:
                child = directory / name
                # Known structured files inside source trees may also contain
                # runtime references. Non-JSON ancillary files remain opaque.
                child_kind = ('auto-lhotse' if name.endswith(('.jsonl', '.jsonl.gz')) else None)
                self.add(child, child_kind, alias)


def snapshot_cos(work):
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = [s.decode(errors='replace') for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
        except OSError:
            continue
        if not args or Path(args[0]).name in {'bash', 'sh', 'tini', 'timeout'}:
            continue
        scripts = [a for a in args[1:3] if a.endswith('.py')]
        if any('cos_' in s or ('cos-' in s and ('repair.py' in s or 'supervise.py' in s)) for s in scripts):
            matches.append({'pid': int(proc.name), 'scripts': scripts})
    record = {'checked_at': time.time(), 'processes': matches, 'status': 'stopped' if not matches else 'running'}
    save(work / 'cos-status.json', record)
    if matches:
        raise RuntimeError('COS processes resumed; pause their supervisors and trees before migration')


def init(args):
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    if (work / 'config.json').exists():
        raise ValueError('already initialized; use scan/transfer to resume')
    snapshot_cos(work)
    specs = list(load_catalog(args.catalog))
    roots = load_roots(args.roots)
    selected, exclusions = [], []
    for spec in specs:
        reason = ('wenetspeech_family' if excluded(spec.key) or excluded(spec.derived_from or '') else
                  'download_planned' if spec.provenance.get('inventory_status') == 'download_planned' else
                  'deferred_wenetspeech_dependency' if any(excluded(a.relative_path) for a in spec.artifacts) else None)
        if reason:
            exclusions.append({'key': spec.key, 'reason': reason})
        elif not args.dataset or spec.key in args.dataset:
            selected.append(spec)
    config = {'run': args.run, 'host': args.host, 'destination': args.destination,
              'receiver': f'{args.destination}/migration/{args.run}/aidc_transfer.py',
              'roots': {k: str(p) for k, p in roots.items()},
              'datasets': [s.to_dict() for s in selected], 'exclusions': exclusions,
              'anchors': [], 'explicit': {}, 'created_at': time.time(),
              'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()}
    # Pin current YAML bytes, including uncommitted declarations, as evidence.
    for directory in (args.catalog, args.views):
        for path in declaration_files(directory):
            target = work / 'original-registry' / directory.name / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(args.roots, work / 'original-registry/roots.json')
    # Directory artifacts define tree-preserving layouts before any child is
    # encountered. Files shared by declarations retain the first canonical path.
    for spec in selected:
        for artifact in spec.artifacts:
            path = roots[artifact.root_alias] / artifact.relative_path
            if artifact.kind in DIRECTORIES:
                base = Path('datasets') / spec.dataset_id
                base /= ('versions/' + spec.version if artifact.kind == 'lhotse-manifest-dir' else 'source/' + spec.version)
                config['anchors'].append({'path': str(path), 'target': str(base / path.name)})
    for spec in selected:
        for artifact in spec.artifacts:
            path = roots[artifact.root_alias] / artifact.relative_path
            if artifact.kind in DIRECTORIES:
                continue
            containing = [a for a in config['anchors'] if path.is_relative_to(a['path'])]
            if containing:
                anchor = max(containing, key=lambda a: len(a['path']))
                target = str(Path(anchor['target']) / path.relative_to(anchor['path']))
            else:
                layer = 'source' if 'archive' in artifact.kind or artifact.kind == 'verification-trials' else 'versions'
                target = str(Path('datasets') / spec.dataset_id / layer / spec.version / artifact.name / path.name)
            config['explicit'].setdefault(str(path), target)
    save(work / 'config.json', config)
    db = database(work)
    inventory = MigrationInventory(db, config)
    for spec in selected:
        inventory.owner = spec.key
        for artifact in spec.artifacts:
            path = roots[artifact.root_alias] / artifact.relative_path
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (spec.key, artifact.name, str(path), artifact.kind))
            if artifact.kind not in DIRECTORIES | JSON | JSONL | PLAIN:
                issue(db, path, 'unsupported_artifact_kind', artifact.kind)
            inventory.add(path, artifact.kind, artifact.root_alias, artifact.sha256, artifact.expected_bytes)
    db.commit()
    db.close()
    print(json.dumps({'selected_versions': len(selected), 'excluded_versions': len(exclusions)}))


def scan(args):
    config = config_at(args.work)
    db = database(args.work)
    inventory = MigrationInventory(db, config)
    with (args.work / 'scan.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            # Parse manifests before huge source directories to discover shared
            # dependencies early; uploads consume committed objects meanwhile.
            task = db.execute("SELECT * FROM tasks WHERE status='pending' ORDER BY kind='source-directory',rowid LIMIT 1").fetchone()
            if task is None:
                break
            print(json.dumps({'scan': task['path'], 'kind': task['kind']}), flush=True)
            try:
                count = inventory.expand(task)
                db.execute("UPDATE tasks SET status='complete',records=? WHERE path=?", (count, task['path']))
            except (OSError, ValueError, EOFError, KeyError) as error:
                issue(db, task['path'], str(error))
                db.execute("UPDATE tasks SET status='failed' WHERE path=?", (task['path'],))
            db.commit()
        # Validate all AudioRecord IDs against the declared audio index, keeping
        # the join in SQLite rather than loading millions of IDs into memory.
        for row in db.execute('SELECT DISTINCT spec,split FROM record_refs').fetchall():
            spec = next((s for s in config['datasets'] if s['dataset_id'] + '@' + s['version'] == row['spec']), None)
            split = spec.get('splits', {}).get(row['split'], {}) if spec else {}
            artifact = db.execute('SELECT path FROM artifacts WHERE spec=? AND name=?',
                                  (row['spec'], split.get('audio_index_artifact', ''))).fetchone()
            if artifact is None:
                for ref in db.execute('SELECT DISTINCT manifest FROM record_refs WHERE spec=? AND split=?', tuple(row)):
                    issue(db, ref['manifest'], 'unresolved_audio_record_reference', row['spec'] + ':' + row['split'])
            else:
                db.execute('''INSERT OR IGNORE INTO edges SELECT DISTINCT manifest,?
                              FROM record_refs WHERE spec=? AND split=?''',
                           (artifact['path'], row['spec'], row['split']))
                missing = db.execute('''SELECT r.manifest,count(*) AS n FROM record_refs r
                   WHERE r.spec=? AND r.split=? AND NOT EXISTS
                   (SELECT 1 FROM memberships m WHERE m.manifest=? AND m.cut_id=r.cut_id)
                   GROUP BY r.manifest''', (row['spec'], row['split'], artifact['path'])).fetchall()
                for ref in missing:
                    issue(db, ref['manifest'], 'missing_audio_index_ids', ref['n'])
        db.execute("INSERT OR REPLACE INTO meta VALUES('scan_complete','true')")
        db.commit()
    db.close()


def transfer_target(row, config):
    if row['kind'] in JSONL | JSON:
        return f'migration/{config["run"]}/original-manifests/{row["id"]}/{Path(row["source"]).name}'
    return row['target']


def build_batches(db, config, batch_bytes, chunk_bytes):
    pending = db.execute("SELECT * FROM objects WHERE status='pending' ORDER BY id LIMIT 50000").fetchall()
    jobs, members, total = [], [], 0

    def queue(rows):
        number = db.execute("INSERT INTO batches(status) VALUES('pending')").lastrowid
        plan = {'run': config['run'], 'batch': f'b{number:08d}', 'files': rows}
        db.execute('UPDATE batches SET plan=?,bytes=? WHERE id=?',
                   (json.dumps(plan), sum(r['length'] for r in rows), number))
        jobs.append(number)

    for row in pending:
        member = {'id': row['id'], 'source': row['source'], 'target': transfer_target(row, config),
                  'signature': object_signature(row), 'length': row['size'], 'expected': row['expected']}
        if row['size'] > batch_bytes:
            if members:
                queue(members)
                members, total = [], 0
            for offset in range(0, row['size'], chunk_bytes):
                part = {**member, 'offset': offset, 'length': min(chunk_bytes, row['size'] - offset),
                        'expected': None, 'target': f'.incoming/{config["run"]}/chunks/{row["id"]}/{offset}'}
                queue([part])
            db.execute("UPDATE objects SET status='chunked' WHERE id=?", (row['id'],))
        else:
            if members and total + row['size'] > batch_bytes:
                queue(members)
                members, total = [], 0
            members.append(member)
            total += row['size']
            db.execute("UPDATE objects SET status='queued' WHERE id=?", (row['id'],))
    if members:
        queue(members)
    db.commit()
    return jobs


def transfer_job(config, plan, progress):
    started = time.monotonic()
    return send(config, plan, progress), time.monotonic() - started


def assemble_ready(db, config, work):
    for row in db.execute("SELECT * FROM objects WHERE status='chunked'").fetchall():
        parts = []
        unfinished = False
        for batch in db.execute("SELECT * FROM batches WHERE plan LIKE ?", (f'%"id": {row["id"]},%',)):
            plan = json.loads(batch['plan'])
            if plan['files'][0]['id'] != row['id']:
                continue
            if batch['status'] != 'complete':
                unfinished = True
                break
            receipt = json.loads((work / 'receipts' / f'{batch["id"]}.json').read_text())
            parts.append((plan['files'][0]['offset'], receipt['files'][0]))
        if unfinished or not parts:
            continue
        if signature(row['source']) != object_signature(row):
            db.execute("UPDATE objects SET status='failed' WHERE id=?", (row['id'],))
            issue(db, row['source'], 'source_changed_before_assembly')
            continue
        plan = {'id': row['id'], 'target': transfer_target(row, config),
                'size': row['size'], 'expected': row['expected'],
                'parts': [p for _, p in sorted(parts)]}
        result = subprocess.run(remote_command(config, 'assemble'), input=encoded(plan), capture_output=True, check=True)
        receipt = json.loads(result.stdout)
        if signature(row['source']) != object_signature(row):
            db.execute("UPDATE objects SET status='failed' WHERE id=?", (row['id'],))
            issue(db, row['source'], 'source_changed_during_assembly')
            db.commit()
            continue
        db.execute("UPDATE objects SET status='complete',sha256=? WHERE id=?", (receipt['sha256'], row['id']))
        db.commit()


def status(work):
    db = sqlite3.connect(Path(work) / 'migration.sqlite', timeout=60)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute('SELECT status,count(*) AS files,coalesce(sum(size),0) AS bytes FROM objects GROUP BY status')]
    result = {'at': time.time(), 'files': rows,
              'scan_complete': bool(db.execute("SELECT 1 FROM meta WHERE key='scan_complete'").fetchone()),
              'tasks': [dict(r) for r in db.execute('SELECT status,count(*) AS count,sum(records) AS records FROM tasks GROUP BY status')],
              'issues': db.execute('SELECT count(*) FROM issues').fetchone()[0],
              'batches': [dict(r) for r in db.execute('SELECT status,count(*) AS count,sum(bytes) AS bytes FROM batches GROUP BY status')]}
    db.close()
    save(Path(work) / 'progress.json', result)
    return result


def transfer(args):
    config = config_at(args.work)
    snapshot_cos(args.work)
    db = database(args.work)
    started, last_report = time.monotonic(), 0
    meter = {'bytes': 0}
    meter_lock = threading.Lock()
    def progress(size):
        with meter_lock:
            meter['bytes'] += size
    stages, stage_start, stage_bytes = [], started, 0
    workers = 4 if args.tune else args.workers
    capacity = 16 if args.tune else args.workers
    cpu_start = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
    with (args.work / 'transfer.lock').open('w') as lock, ThreadPoolExecutor(capacity) as pool:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db.execute("UPDATE batches SET status='pending' WHERE status='running'")
        db.commit()
        futures = {}
        while True:
            elapsed = time.monotonic() - started
            stopping = args.seconds and elapsed >= args.seconds
            if args.tune and len(stages) < 3 and time.monotonic() - stage_start >= 60:
                cpu = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
                delta = [a - b for a, b in zip(cpu, cpu_start)]
                period = time.monotonic() - stage_start
                measurement = {'workers': workers, 'seconds': period,
                               'bytes': meter['bytes'] - stage_bytes,
                               'bytes_per_second': (meter['bytes'] - stage_bytes) / period,
                               'cpu_busy_fraction': 1 - (delta[3] + delta[4]) / max(sum(delta), 1),
                               'iowait_fraction': delta[4] / max(sum(delta), 1)}
                stages.append(measurement)
                workers = (8 if len(stages) == 1 else 16) if len(stages) < 3 else max(stages, key=lambda s: s['bytes_per_second'])['workers']
                save(args.work / 'throughput-tuning.json', {'stages': stages, 'selected_workers': workers})
                print(json.dumps({'tuning': measurement, 'next_workers': workers}), flush=True)
                stage_start, stage_bytes, cpu_start = time.monotonic(), meter['bytes'], cpu
            if not stopping:
                if db.execute("SELECT count(*) FROM batches WHERE status='pending'").fetchone()[0] < workers:
                    build_batches(db, config, args.batch_gib * GIB, args.chunk_gib * GIB)
                slots = max(0, workers - len(futures))
                for batch in db.execute("SELECT * FROM batches WHERE status='pending' ORDER BY id LIMIT ?", (slots,)).fetchall():
                    plan = json.loads(batch['plan'])
                    futures[pool.submit(transfer_job, config, plan, progress)] = (batch['id'], plan)
                    db.execute("UPDATE batches SET status='running' WHERE id=?", (batch['id'],))
                db.commit()
            if futures:
                completed, _ = wait(futures, timeout=2, return_when=FIRST_COMPLETED)
                for future in completed:
                    number, plan = futures.pop(future)
                    try:
                        receipt, duration = future.result()
                        save(args.work / 'receipts' / f'{number}.json', receipt)
                        db.execute("UPDATE batches SET status='complete',elapsed=? WHERE id=?", (duration, number))
                        for source, received in zip(plan['files'], receipt['files']):
                            if 'offset' not in source:
                                db.execute("UPDATE objects SET status='complete',sha256=? WHERE id=?", (received['sha256'], source['id']))
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                        db.execute("UPDATE batches SET status='failed',error=? WHERE id=?", (str(error), number))
                        print(json.dumps({'batch_failed': number, 'error': str(error)}), flush=True)
                    db.commit()
            elif stopping:
                break
            else:
                assemble_ready(db, config, args.work)
                if (db.execute("SELECT 1 FROM meta WHERE key='scan_complete'").fetchone()
                        and not db.execute("SELECT 1 FROM objects WHERE status='pending' LIMIT 1").fetchone()):
                    break
                time.sleep(2)
            if time.monotonic() - last_report > 30:
                snapshot = status(args.work)
                snapshot.update(streamed_bytes=meter['bytes'], workers=workers,
                                elapsed_seconds=elapsed,
                                average_bytes_per_second=meter['bytes'] / max(elapsed, 1))
                save(args.work / 'progress.json', snapshot)
                print(json.dumps(snapshot), flush=True)
                last_report = time.monotonic()
        assemble_ready(db, config, args.work)
    db.close()
    print(json.dumps(status(args.work)), flush=True)


def install_receiver(args):
    config = config_at(args.work)
    directory = f'{config["destination"]}/migration/{config["run"]}'
    subprocess.run(ssh(config['host'], ['mkdir', '-p', directory]), check=True)
    for name in ('aidc_transfer.py',):
        data = (Path(__file__).parent / name).read_bytes()
        # The receiver is pinned for this run, with exclusive creation.
        code = 'import sys,pathlib; p=pathlib.Path(sys.argv[1]); d=sys.stdin.buffer.read(); assert not p.exists() or p.read_bytes()==d; p.write_bytes(d)'
        subprocess.run(ssh(config['host'], ['python3', '-c', code, directory + '/' + name]), input=data, check=True)


def finalize_remote(args):
    config = config_at(args.work)
    db = database(args.work)
    if not db.execute("SELECT 1 FROM meta WHERE key='scan_complete'").fetchone():
        raise ValueError('scan has not completed')
    snapshot = args.work / 'migration-snapshot.sqlite'
    with sqlite3.connect(snapshot) as output:
        db.backup(output)
    db.close()
    remote = f'migration/{config["run"]}'
    repo = Path(__file__).resolve().parents[1]
    sources = [(snapshot, remote + '/migration.sqlite'),
               (args.work / 'config.json', remote + '/config.json')]
    for path in (args.work / 'original-registry').rglob('*'):
        if path.is_file():
            sources.append((path, remote + '/' + str(path.relative_to(args.work))))
    for name in ('aidc_migrate.py', 'aidc_transfer.py', 'aidc_finalize.py', 'cos_sync_catalog.py', 'cos_backup.py'):
        sources.append((repo / 'scripts' / name, remote + '/runtime/scripts/' + name))
    for path in (repo / 'src/audio_data_contract').rglob('*'):
        if path.is_file() and path.suffix in {'.py', '.json'}:
            sources.append((path, remote + '/runtime/src/' + str(path.relative_to(repo / 'src'))))
    import ruamel.yaml
    yaml_root = Path(ruamel.yaml.__file__).parent
    for path in yaml_root.rglob('*.py'):
        sources.append((path, remote + '/runtime/vendor/ruamel/yaml/' + str(path.relative_to(yaml_root))))
    members = [{'source': str(path.resolve()), 'target': target, 'signature': signature(path),
                'length': path.stat().st_size} for path, target in sources]
    key = hashlib.sha256(encoded(members)).hexdigest()[:16]
    send(config, {'run': config['run'], 'batch': 'finalize-' + key, 'files': members})
    absolute = str(Path(config['destination']) / remote)
    command = ['env', 'PYTHONPATH=' + absolute + '/runtime/src:' + absolute + '/runtime/vendor',
               'python3', absolute + '/runtime/scripts/aidc_finalize.py', '--work', absolute]
    result = subprocess.run(ssh(config['host'], command), check=True, capture_output=True)
    print(result.stdout.decode(), end='')
    save(args.work / 'verification.json', json.loads(result.stdout))


def run_pipeline(args):
    scan_process = subprocess.Popen([sys.executable, '-u', __file__, 'scan', '--work', str(args.work)])
    transfer(args)
    if scan_process.wait():
        raise RuntimeError('inventory process failed')
    finalize_remote(args)


def watch(args):
    """Finish a run whose scanner and uploader are already detached."""
    with (args.work / 'watch.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save(args.work / 'controller.json', {'pid': os.getpid(), 'status': 'waiting_for_scan_and_transfer'})
        while True:
            running = []
            for name in ('scan', 'transfer'):
                pid_file = args.work / (name + '.pid')
                if not pid_file.exists():
                    continue
                process = Path('/proc') / pid_file.read_text().strip()
                try:
                    command = (process / 'cmdline').read_bytes().split(b'\0')
                    live = b'scripts/aidc_migrate.py' in command and name.encode() in command
                except OSError:
                    live = False
                if live:
                    running.append(name)
            if not running:
                break
            time.sleep(10)
        snapshot = status(args.work)
        incomplete = [r for r in snapshot['files'] if r['status'] not in {'complete', 'excluded'}]
        if not snapshot['scan_complete'] or incomplete:
            save(args.work / 'controller.json', {'pid': os.getpid(), 'status': 'needs_attention', 'progress': snapshot})
            raise RuntimeError('scan or transfer stopped before completion; checkpoints retained')
        save(args.work / 'controller.json', {'pid': os.getpid(), 'status': 'finalizing'})
        try:
            finalize_remote(args)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            details = str(error)
            if isinstance(error, subprocess.CalledProcessError) and error.stderr:
                details += '\n' + error.stderr.decode(errors='replace')
            save(args.work / 'controller.json', {'pid': os.getpid(), 'status': 'needs_attention', 'error': details})
            raise
        save(args.work / 'controller.json', {'pid': os.getpid(), 'status': 'complete',
                                            'verification': json.loads((args.work / 'verification.json').read_text())})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'scan', 'transfer', 'status', 'install-receiver', 'finalize', 'run', 'watch'])
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=Path('catalog'))
    parser.add_argument('--views', type=Path, default=Path('views'))
    parser.add_argument('--roots', type=Path, default=Path('roots.json'))
    parser.add_argument('--host', default='aidc-dev')
    parser.add_argument('--destination', default='/workspace/data')
    parser.add_argument('--run', default='aidc-20260923')
    parser.add_argument('--dataset', action='append')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--batch-gib', type=int, default=8)
    parser.add_argument('--chunk-gib', type=int, default=1)
    parser.add_argument('--seconds', type=int, default=0)
    parser.add_argument('--tune', action='store_true')
    args = parser.parse_args()
    args.work = args.work.resolve()
    if args.command == 'status':
        print(json.dumps(status(args.work), indent=2))
    else:
        {'init': init, 'scan': scan, 'transfer': transfer, 'install-receiver': install_receiver,
         'finalize': finalize_remote, 'run': run_pipeline, 'watch': watch}[args.command](args)


if __name__ == '__main__':
    main()
