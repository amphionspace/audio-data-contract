#!/usr/bin/env python3
"""Expand all catalog dependencies and stream deduplicated COS batches.

Run init once, then scan and upload concurrently. SQLite stores recovery paths;
only plans, checkpoints and a compressed index are staged. Never delete sources.
"""

import argparse
import fcntl
import gzip
import json
import os
import sqlite3
import subprocess
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from cos_backup import digest_file, encoded, save, signature, upload, verify_head

from audio_data_contract import load_catalog
from audio_data_contract.audio_prepare import _parse
from audio_data_contract.roots import load_roots

DIRECTORIES = {"source-directory", "hf-dataset-snapshot", "hf-dataset-directory",
               "lhotse-manifest-dir", "simulated-meeting-directory",
               "meeting-dataset-directory"}
MANIFESTS = {"lhotse-recordings", "lhotse-cuts", "audio-index", "audio-records", "sharegpt-jsonl",
             "target-asr-jsonl", "extraction-inventory"}
SELF_CONTAINED = {"lhotse-supervisions", "metadata", "json-metadata", "jsonl-metadata",
                  "quality-report", "license", "archive", "source-archive",
                  "source-archive-part", "repaired-source-archive", "dataset-state",
                  "dataset-preparation-status", "verification-trials"}
ARCHIVES = (".tar", ".tar.gz", ".tgz", ".tar.xz", ".zip", ".7z", ".parquet")
AUDIO = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".sph"}
PRIVATE = {".git", ".ssh", ".aws", ".config", ".env", "credentials.json",
           "credentials", "id_rsa", "id_ed25519", "token", "tokens.json"}


class BackupConnection(sqlite3.Connection):
    """Queue writers across processes instead of racing SQLite's busy timeout."""

    def __init__(self, database, *args, **kwargs):
        super().__init__(database, *args, **kwargs)
        self.writer = os.open(str(database) + '.writer.lock', os.O_CREAT | os.O_RDWR, 0o600)
        self.writer_locked = False

    def acquire_writer(self):
        if not self.writer_locked:
            fcntl.flock(self.writer, fcntl.LOCK_EX)
            self.writer_locked = True

    def release_writer(self):
        if self.writer_locked:
            fcntl.flock(self.writer, fcntl.LOCK_UN)
            self.writer_locked = False

    def execute(self, sql, parameters=()):
        if sql.lstrip().split(None, 1)[0].upper() in {
            'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'ALTER', 'CREATE', 'BEGIN',
        }:
            self.acquire_writer()
        return super().execute(sql, parameters)

    def executescript(self, sql):
        self.acquire_writer()
        return super().executescript(sql)

    def commit(self):
        super().commit()
        self.release_writer()

    def rollback(self):
        super().rollback()
        self.release_writer()

    def close(self):
        super().close()
        self.release_writer()
        if self.writer is not None:
            os.close(self.writer)
            self.writer = None


def connect(work):
    db = sqlite3.connect(work / "inventory.sqlite", timeout=60, factory=BackupConnection)
    db.acquire_writer()
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=60000")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS files(
      path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, device INTEGER,
      inode INTEGER, category TEXT, expected TEXT, sha256 TEXT,
      status TEXT NOT NULL DEFAULT 'pending', object_key TEXT, member TEXT);
    CREATE INDEX IF NOT EXISTS files_pending ON files(status,category);
    CREATE INDEX IF NOT EXISTS files_inode ON files(device,inode,size,mtime_ns);
    CREATE TABLE IF NOT EXISTS hashes(device INTEGER,inode INTEGER,size INTEGER,
      mtime_ns INTEGER,sha256 TEXT,PRIMARY KEY(device,inode,size,mtime_ns));
    CREATE TABLE IF NOT EXISTS contents(size INTEGER,sha256 TEXT,object_key TEXT,
      member TEXT,PRIMARY KEY(size,sha256));
    CREATE TABLE IF NOT EXISTS tasks(path TEXT,kind TEXT,root_alias TEXT,
      status TEXT DEFAULT 'pending',PRIMARY KEY(path,kind));
    CREATE TABLE IF NOT EXISTS issues(path TEXT,reason TEXT,context TEXT,
      PRIMARY KEY(path,reason,context));
    CREATE TABLE IF NOT EXISTS resolutions(manifest TEXT,reference TEXT,path TEXT,
      PRIMARY KEY(manifest,reference,path));
    CREATE TABLE IF NOT EXISTS batches(number INTEGER PRIMARY KEY,plan TEXT,
      status TEXT DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS archive_index(path TEXT PRIMARY KEY,sha256 TEXT,
      container_format TEXT,status TEXT,member_count INTEGER);
    CREATE TABLE IF NOT EXISTS archive_members(archive TEXT,member TEXT,size INTEGER,
      sha256 TEXT,PRIMARY KEY(archive,member));
    """)
    for table in ('files', 'contents'):
        columns = {r['name'] for r in db.execute('PRAGMA table_info(' + table + ')')}
        if 'container_format' not in columns:
            db.execute('ALTER TABLE ' + table + ' ADD COLUMN container_format TEXT')
            db.execute("UPDATE " + table + " SET container_format=CASE WHEN member='' THEN 'raw' ELSE 'tar.zst' END WHERE member IS NOT NULL")
    db.commit()
    return db


def issue(db, path, reason, context=""):
    db.execute("INSERT OR IGNORE INTO issues VALUES(?,?,?)",
               (str(path), reason, str(context)))


def category(path):
    if str(path).lower().endswith(ARCHIVES):
        return "archive"
    return "audio" if path.suffix.lower() in AUDIO else "metadata"


class Inventory:
    def __init__(self, db, roots, allowed, datasets=()):
        self.db, self.roots = db, roots
        self.allowed = [Path(p).resolve() for p in allowed]
        self.seen = OrderedDict()
        self.count = 0
        self.last_report = time.monotonic()
        self.last_commit = self.last_report
        self.datasets = {(s['dataset_id'], s['version']): s for s in datasets}

    def safe(self, path):
        absolute = Path(os.path.abspath(path))
        resolved = absolute.resolve()
        if any(p in PRIVATE or p.startswith('.env.') for p in absolute.parts + resolved.parts):
            raise ValueError("private_path")
        if absolute.suffix in {".pem", ".key"}:
            raise ValueError("private_path")
        if not any(resolved.is_relative_to(root) for root in self.allowed):
            raise ValueError("outside_data_roots")
        return absolute

    def add(self, path, kind=None, root_alias="", expected=None, expected_bytes=None):
        if time.monotonic() - self.last_commit > 1:
            self.db.commit()
            self.last_commit = time.monotonic()
        spelling = str(path)
        cache_key = (spelling, kind, expected, expected_bytes)
        if cache_key in self.seen:
            return self.seen[cache_key]
        try:
            path = self.safe(path)
            if path.name.endswith((".aria2", ".incomplete", ".partial", ".part", ".lock")):
                raise ValueError("unfinished_download")
            if path.is_dir():
                self.db.execute("INSERT OR IGNORE INTO tasks(path,kind,root_alias) VALUES(?,?,?)",
                                (str(path), kind or "source-directory", root_alias))
                return str(path)
            sig = signature(path)
            if expected_bytes is not None and sig['size'] != expected_bytes:
                raise ValueError("catalog_size_mismatch")
            row = (str(path), sig['size'], sig['mtime_ns'], sig['device'], sig['inode'],
                   "archive" if kind and "archive" in kind else category(path), expected)
            self.db.execute("""INSERT OR IGNORE INTO files
                (path,size,mtime_ns,device,inode,category,expected) VALUES(?,?,?,?,?,?,?)""", row)
            if expected:
                existing = self.db.execute('SELECT expected FROM files WHERE path=?', (str(path),)).fetchone()[0]
                if existing and existing != expected:
                    raise ValueError('conflicting_catalog_hashes')
                self.db.execute('UPDATE files SET expected=? WHERE path=?', (expected, str(path)))
            if kind in MANIFESTS or kind == "auto-lhotse":
                self.db.execute("INSERT OR IGNORE INTO tasks(path,kind,root_alias) VALUES(?,?,?)",
                                (str(path), kind, root_alias))
            resolved = str(path.resolve())
            if resolved != str(path):
                self.db.execute("""INSERT OR IGNORE INTO files
                    (path,size,mtime_ns,device,inode,category,expected) VALUES(?,?,?,?,?,?,?)""",
                                (resolved, *row[1:]))
            result = str(path)
        except (OSError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            issue(self.db, spelling, reason)
            result = None
        self.seen[cache_key] = result
        if len(self.seen) > 100000:
            self.seen.popitem(last=False)
        self.count += 1
        if self.count % 100 == 0:
            self.db.commit()
            self.last_commit = time.monotonic()
        if time.monotonic() - self.last_report > 30:
            self.db.commit()
            print(json.dumps({"stage": "inventory", "visited": self.count,
                              "current": spelling}), flush=True)
            self.last_report = time.monotonic()
        return result

    def reference(self, value, manifest, root_alias, kind=None):
        if not isinstance(value, str) or not value or "://" in value:
            issue(self.db, manifest, "unsupported_reference")
            return
        path = Path(value)
        if not path.is_absolute():
            candidates = {manifest.parent / path}
            if root_alias in self.roots:
                root = self.roots[root_alias]
                candidates.add(root / path)
                for parent in manifest.parents:
                    if parent.is_relative_to(root):
                        candidates.add(parent / path)
            matches = {p.resolve() for p in candidates if p.exists()}
            if len(matches) != 1:
                issue(self.db, value, "relative_path_missing_or_ambiguous", manifest)
                return
            path = matches.pop()
            self.db.execute("INSERT OR IGNORE INTO resolutions VALUES(?,?,?)",
                            (str(manifest), value, str(path)))
        self.add(path, kind, root_alias)

    def lhotse(self, item, manifest, root_alias):
        if not isinstance(item, dict):
            issue(self.db, manifest, "unsupported_lhotse_item")
            return
        for source in item.get('sources', []):
            try:
                if source['type'] == 'file':
                    self.reference(source['source'], manifest, root_alias)
                else:
                    sentinel = Path('/__cos_relative_source__')
                    _, path, _ = _parse(source, sentinel, extract=True)
                    value = str(path.relative_to(sentinel)) if path.is_relative_to(sentinel) else str(path)
                    self.reference(value, manifest, root_alias, 'source-archive')
            except (ValueError, KeyError):
                issue(self.db, manifest, "unsupported_audio_command")
        if 'storage_type' in item:
            storage = item['storage_type']
            value = item.get('storage_path')
            if value:
                if storage in {'numpy_files', 'lilcom_files'}:
                    value = str(Path(value) / item['storage_key'])
                self.reference(value, manifest, root_alias)
            elif not storage.startswith('memory'):
                issue(self.db, manifest, "unsupported_feature_storage", storage)
        for value in item.values():
            if isinstance(value, dict):
                self.lhotse(value, manifest, root_alias)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, dict):
                        self.lhotse(child, manifest, root_alias)

    def expand(self, task):
        path, kind, alias = Path(task['path']), task['kind'], task['root_alias']
        if kind in DIRECTORIES:
            def failed(exc):
                issue(self.db, exc.filename, type(exc).__name__, path)
            for directory, dirs, names in os.walk(path, onerror=failed, followlinks=False):
                dirs[:] = [name for name in dirs if name not in PRIVATE | {'.cache'}]
                for name in list(dirs):
                    child = Path(directory) / name
                    if child.is_symlink():
                        issue(self.db, child, 'symlink_directory_not_expanded', path)
                        dirs.remove(name)
                for name in names:
                    child = Path(directory) / name
                    child_kind = ('auto-lhotse' if kind == 'lhotse-manifest-dir'
                                  and name.endswith(('.jsonl', '.jsonl.gz')) else None)
                    self.add(child, child_kind, alias)
            return
        before = signature(path)
        opener = gzip.open if path.name.endswith('.gz') else open
        with opener(path, 'rt', encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if kind in {'lhotse-recordings', 'lhotse-cuts', 'auto-lhotse'}:
                        self.lhotse(item, path, alias)
                    elif kind == 'audio-index':
                        root = item.get('root_alias', alias)
                        if root not in self.roots:
                            issue(self.db, path, 'unconfigured_root', root)
                        else:
                            self.add(self.roots[root] / item['relative_path'])
                    elif kind == 'audio-records':
                        for slot in item.get('audio_slots', []):
                            ref = slot['ref']
                            spec = self.datasets.get((ref['dataset_id'], ref['version']))
                            split = spec.get('splits', {}).get(ref['split'], {}) if spec else {}
                            if not split.get('audio_index_artifact'):
                                issue(self.db, path, 'unresolved_audio_record_reference',
                                      ref['dataset_id'] + '@' + ref['version'] + ':' + ref['split'])
                    elif kind == 'sharegpt-jsonl':
                        for value in item.get('audios', []):
                            self.reference(value, path, alias)
                    elif kind == 'target-asr-jsonl':
                        for field in ('mix_wav', 'enroll_wav'):
                            self.reference(item[field], path, alias)
                    elif kind == 'extraction-inventory':
                        self.add(path.parent.parent / item['path'])
                except (ValueError, KeyError, TypeError):
                    issue(self.db, path, 'invalid_manifest_row', str(number))
                if number % 1000 == 0:
                    self.db.commit()
        if signature(path) != before:
            issue(self.db, path, 'manifest_changed_during_scan')


def cos_client(config):
    from qcloud_cos import CosConfig, CosS3Client
    return CosS3Client(CosConfig(
        Region=config['region'], SecretId=os.environ['COS_SecretID'],
        SecretKey=os.environ['COS_SecretKey'], Token=os.environ.get('COS_Token'),
        Scheme='https', VerifySSL=True, AutoSwitchDomainOnRetry=False, Timeout=60))


def init(args):
    if (args.work / 'config.json').exists():
        raise ValueError('already initialized; use scan/upload to resume')
    args.work.mkdir(parents=True, exist_ok=True)
    roots = load_roots(args.roots)
    catalog = load_catalog(args.catalog)
    allowed = [str(p) for p in roots.values()] + [str(p.resolve()) for p in args.allow_root]
    config = {'roots': {k: str(p) for k, p in roots.items()}, 'allowed': allowed,
              'bucket': args.bucket, 'region': args.region, 'prefix': args.prefix,
              'datasets': [s.to_dict() for s in catalog]}
    db = connect(args.work)
    inv = Inventory(db, roots, allowed, config['datasets'])
    for spec in catalog:
        if spec.provenance.get('inventory_status') == 'download_planned':
            verified = False
            for artifact in spec.artifacts:
                if artifact.kind == 'dataset-state' and artifact.root_alias in roots:
                    try:
                        state = json.loads((roots[artifact.root_alias] / artifact.relative_path).read_text())
                        verified |= state.get('state') == 'verified'
                        journal = state.get('metadata', {}).get('verification_journal')
                        if journal:
                            inv.add(journal)
                    except (OSError, ValueError):
                        pass
            if not verified:
                issue(db, spec.key, 'source_download_not_complete')
        for artifact in spec.artifacts:
            if artifact.root_alias not in roots:
                issue(db, spec.key, 'unconfigured_root', artifact.root_alias)
                continue
            path = roots[artifact.root_alias] / artifact.relative_path
            if artifact.kind not in DIRECTORIES | MANIFESTS | SELF_CONTAINED:
                issue(db, path, 'unsupported_artifact_kind', artifact.kind)
            inv.add(path, artifact.kind, artifact.root_alias,
                    artifact.sha256, artifact.expected_bytes)
    repo = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().split('\0')
    files += ['scripts/cos_backup.py', 'scripts/cos_sync_catalog.py',
              'scripts/cos_index_archives.py', 'docs/cos-upload-plan.md',
              'tests/test_cos_backup.py', 'tests/test_cos_sync_catalog.py']
    for name in filter(None, files):
        if (repo / name).is_file():
            inv.add(repo / name)
    inv.add(repo / 'reports', 'source-directory', 'audio_data_contract')
    for journal in args.hash_journal:
        with journal.open() as stream:
            for line in stream:
                row = json.loads(line)
                alias, relative = row['path'].split(':', 1)
                sig = dict(zip(('size', 'mtime_ns', 'device', 'inode'), row['signature']))
                path = roots[alias] / relative
                if signature(path) == sig:
                    db.execute('INSERT OR IGNORE INTO hashes VALUES(?,?,?,?,?)',
                               (sig['device'], sig['inode'], sig['size'], sig['mtime_ns'], row['sha256']))
    if args.reuse:
        client = cos_client(config)
        try:
            for receipt in args.reuse:
                old = json.loads(receipt.read_text())
                for shard in old['shards']:
                    verify_head(client.head_object(Bucket=args.bucket, Key=shard['key']),
                                shard, old['plan_sha256'])
                    for item in shard['files']:
                        member = '' if shard['format'] == 'raw' else 'files/' + item['sha256']
                        db.execute('INSERT OR IGNORE INTO contents VALUES(?,?,?,?,?)',
                                   (item['size'], item['sha256'], shard['key'], member, shard['format']))
                        for source in item['sources']:
                            sig = source['signature']
                            try:
                                if signature(source['path']) != sig:
                                    continue
                            except (OSError, ValueError):
                                continue
                            db.execute('INSERT OR IGNORE INTO hashes VALUES(?,?,?,?,?)',
                                       (sig['device'], sig['inode'], sig['size'], sig['mtime_ns'], item['sha256']))
        finally:
            client._session.close()
    db.execute("INSERT OR REPLACE INTO meta VALUES('scan','pending')")
    db.commit()
    save(args.work / 'config.json', config)
    print(json.dumps({'stage': 'initialized', 'datasets': len(config['datasets']),
                      'files': db.execute('SELECT count(*) FROM files').fetchone()[0]}), flush=True)
    db.close()


def scan(args, config):
    db = connect(args.work)
    inv = Inventory(db, {k: Path(v) for k, v in config['roots'].items()},
                    config['allowed'], config['datasets'])
    db.execute("INSERT OR REPLACE INTO meta VALUES('scan','running')")
    db.commit()
    while task := db.execute("SELECT * FROM tasks WHERE status='pending' LIMIT 1").fetchone():
        print(json.dumps({'stage': 'scan', 'path': task['path'], 'kind': task['kind']}), flush=True)
        try:
            inv.expand(task)
            task_status = 'done'
        except (OSError, ValueError, EOFError) as exc:
            issue(db, task['path'], type(exc).__name__, task['kind'])
            task_status = 'failed'
        db.execute('UPDATE tasks SET status=? WHERE path=? AND kind=?',
                   (task_status, task['path'], task['kind']))
        db.commit()
    db.execute("INSERT OR REPLACE INTO meta VALUES('scan','done')")
    db.commit()
    print(json.dumps({'stage': 'scan_complete'}), flush=True)
    db.close()


def file_signature(row):
    return {k: row[k] for k in ('size', 'mtime_ns', 'device', 'inode')}


def hash_row(row):
    sig = file_signature(row)
    if signature(row['path']) != sig:
        raise ValueError('source_changed_since_inventory')
    sha = row['sha256'] or digest_file(row['path'])
    if signature(row['path']) != sig:
        raise ValueError('source_changed_during_hash')
    if row['expected'] and row['expected'] != sha:
        raise ValueError('catalog_hash_mismatch')
    return sha


def plan_batch(db, work, config, args):
    rows, size = [], 0
    # Both selections use files_pending; sorting all pending paths costs minutes
    # once the inventory contains tens of millions of files.
    candidates = db.execute("SELECT * FROM files WHERE status='pending' AND category='metadata' LIMIT 5000").fetchall()
    if not candidates:
        candidates = db.execute("SELECT * FROM files WHERE status='pending' LIMIT 5000").fetchall()
    for source in candidates:
        row = dict(source)
        raw = row['category'] == 'archive' and row['size'] >= 128 * 1024**2
        if rows and (raw or size + row['size'] > args.shard_bytes):
            break
        rows.append(row)
        size += row['size']
        if raw or size >= args.shard_bytes:
            break
    if not rows:
        return None
    physical = {}
    for row in rows:
        key = tuple(row[k] for k in ('device', 'inode', 'size', 'mtime_ns'))
        cached = db.execute('SELECT sha256 FROM hashes WHERE device=? AND inode=? AND size=? AND mtime_ns=?', key).fetchone()
        row['sha256'] = cached[0] if cached else None
        physical.setdefault(key, []).append(row)
    objects = {}
    with ThreadPoolExecutor(args.hash_workers) as pool:
        futures = [(group, pool.submit(hash_row, group[0])) for group in physical.values()]
        for number, (group, future) in enumerate(futures, 1):
            try:
                if not future.done():
                    db.commit()
                sha = future.result()
                for row in group:
                    if row['expected'] and row['expected'] != sha:
                        raise ValueError('catalog_hash_mismatch')
                    if signature(row['path']) != file_signature(row):
                        raise ValueError('source_changed_since_inventory')
            except (OSError, ValueError) as exc:
                for row in group:
                    issue(db, row['path'], str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
                    db.execute("UPDATE files SET status='failed' WHERE path=?", (row['path'],))
                db.commit()
                continue
            for row in group:
                db.execute('INSERT OR REPLACE INTO hashes VALUES(?,?,?,?,?)',
                           (row['device'], row['inode'], row['size'], row['mtime_ns'], sha))
                db.execute('UPDATE files SET sha256=? WHERE path=?', (sha, row['path']))
            previous = db.execute('SELECT * FROM contents WHERE size=? AND sha256=?', (group[0]['size'], sha)).fetchone()
            if previous:
                for row in group:
                    db.execute("UPDATE files SET status='verified',object_key=?,member=?,container_format=? WHERE path=?",
                               (previous['object_key'], previous['member'], previous['container_format'], row['path']))
            else:
                item = objects.setdefault((group[0]['size'], sha), {
                    'sha256': sha, 'size': group[0]['size'], 'category': group[0]['category'], 'sources': []})
                item['sources'].extend({'path': row['path'], 'signature': file_signature(row),
                                        'category': row['category']} for row in group)
            if number % 64 == 0:
                db.commit()
    db.commit()
    if not objects:
        return False
    files = list(objects.values())
    raw = len(files) == 1 and files[0]['category'] == 'archive' and files[0]['size'] >= 128 * 1024**2
    number = db.execute('SELECT coalesce(max(number),-1)+1 FROM batches').fetchone()[0]
    path = work / 'batches' / f'{number:06d}' / 'plan.json'
    plan = {'schema_version': 'cos-backup-plan/1', 'datasets': [], 'roots': config['roots'],
            'jobs': [{'category': 'mixed', 'format': 'raw' if raw else 'tar.zst', 'files': files}],
            'compression_level': 3, 'summary': {'unique_contents': len(files),
            'unique_bytes': sum(f['size'] for f in files)}}
    save(path, plan)
    db.execute('INSERT INTO batches(number,plan) VALUES(?,?)', (number, str(path)))
    db.commit()
    return db.execute('SELECT * FROM batches WHERE number=?', (number,)).fetchone()


def transfer_batch(db, batch, config, args):
    plan_path = Path(batch['plan'])
    transfer = SimpleNamespace(plan=plan_path, bucket=config['bucket'], region=config['region'],
                               prefix=config['prefix'] + '/batches', part_mib=args.part_mib,
                               workers=args.workers)
    upload(transfer)
    complete = json.loads((plan_path.parent / 'upload/complete.json').read_text())
    for shard in complete['shards']:
        for number, item in enumerate(shard['files'], 1):
            member = '' if shard['format'] == 'raw' else 'files/' + item['sha256']
            db.execute('INSERT OR REPLACE INTO contents VALUES(?,?,?,?,?)',
                       (item['size'], item['sha256'], shard['key'], member, shard['format']))
            for source in item['sources']:
                db.execute("UPDATE files SET status='verified',object_key=?,member=?,container_format=? WHERE path=?",
                           (shard['key'], member, shard['format'], source['path']))
            if number % 128 == 0:
                db.commit()
    db.execute("UPDATE batches SET status='verified' WHERE number=?", (batch['number'],))
    db.commit()


def status(db, count_files=True):
    result = {'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'scan': dict(db.execute('SELECT key,value FROM meta')).get('scan'),
            # The files table is append-only; rowids are assigned by SQLite.
            'discovered_paths': db.execute('SELECT coalesce(max(rowid),0) FROM files').fetchone()[0],
            'tasks': [dict(r) for r in db.execute('SELECT status,count(*) AS tasks FROM tasks GROUP BY status')],
            'issues': db.execute('SELECT count(*) FROM issues').fetchone()[0],
            'archive_index': [dict(r) for r in db.execute('SELECT status,count(*) AS archives,sum(member_count) AS members FROM archive_index GROUP BY status')],
            'batches': [dict(r) for r in db.execute('SELECT status,count(*) AS batches FROM batches GROUP BY status')]}
    if count_files:
        result['files'] = [dict(r) for r in db.execute('SELECT status,count(*) AS files,sum(size) AS bytes FROM files NOT INDEXED GROUP BY status')]
    return result


def publish_index(db, work, config):
    index = work / 'recovery-index.jsonl.gz'
    path = work / 'index-upload/plan.json'
    if not path.exists():
        with gzip.open(index, 'wb', compresslevel=1) as out:
            out.write(encoded({'type': 'catalog', **config}) + b'\n')
            for table in ('files', 'issues', 'resolutions', 'tasks', 'archive_index'):
                for row in db.execute('SELECT * FROM ' + table):
                    out.write(encoded({'type': table, **dict(row)}) + b'\n')
        sha = digest_file(index)
        plan = {'schema_version': 'cos-backup-plan/1', 'roots': config['roots'], 'datasets': [],
                'compression_level': 3, 'summary': status(db), 'jobs': [{'format': 'raw',
                'category': 'metadata', 'files': [{'sha256': sha, 'size': index.stat().st_size,
                'category': 'metadata', 'sources': [{'path': str(index), 'signature': signature(index)}]}]}]}
        save(path, plan)
    upload(SimpleNamespace(plan=path, bucket=config['bucket'], region=config['region'],
                           prefix=config['prefix'] + '/index', part_mib=32, workers=4))
    result = status(db)
    result['status'] = 'complete' if not result['issues'] else 'completed_available_files_with_gaps'
    result['index_receipt'] = str(path.parent / 'upload/complete.json')
    save(work / 'result.json', result)


def transfer(args, config):
    from cos_index_archives import publish_members
    db = connect(args.work)
    while True:
        publish_members(db)
        save(args.work / 'progress.json', status(db, count_files=False))
        batch = db.execute("SELECT * FROM batches WHERE status='pending' ORDER BY number LIMIT 1").fetchone()
        if batch is None:
            batch = plan_batch(db, args.work, config, args)
        if batch is False:
            continue
        if batch is None:
            stages = dict(db.execute('SELECT key,value FROM meta'))
            if stages.get('scan') == 'done' and stages.get('archive_scan') == 'done':
                publish_index(db, args.work, config)
                break
            time.sleep(5)
            continue
        print(json.dumps({'stage': 'upload_batch', 'batch': batch['number']}), flush=True)
        transfer_batch(db, batch, config, args)
    db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'scan', 'upload', 'status'])
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=Path('catalog'))
    parser.add_argument('--roots', type=Path, default=Path('roots.json'))
    parser.add_argument('--bucket')
    parser.add_argument('--region', default='ap-guangzhou')
    parser.add_argument('--prefix', default='audio-data-contract/v1/full-catalog-20260914')
    parser.add_argument('--allow-root', type=Path, action='append', default=[])
    parser.add_argument('--hash-journal', type=Path, action='append', default=[])
    parser.add_argument('--reuse', type=Path, action='append', default=[])
    parser.add_argument('--shard-bytes', type=int, default=4 * 1024**3)
    parser.add_argument('--hash-workers', type=int, default=2)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--part-mib', type=int, default=32)
    parser.add_argument('--count-files', action='store_true', help='Include a full inventory size/count scan in status')
    args = parser.parse_args()
    args.work = args.work.resolve()
    if min(args.shard_bytes, args.hash_workers, args.workers, args.part_mib) < 1:
        parser.error('sizes and worker counts must be positive')
    if args.command == 'init' and not args.bucket:
        parser.error('init requires --bucket')
    args.work.mkdir(parents=True, exist_ok=True)
    with (args.work / (args.command + '.lock')).open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'init':
            init(args)
        else:
            config = json.loads((args.work / 'config.json').read_text())
            if args.command == 'status':
                print(json.dumps(status(connect(args.work), count_files=args.count_files), ensure_ascii=False, indent=2))
            else:
                {'scan': scan, 'upload': transfer}[args.command](args, config)


if __name__ == '__main__':
    from qcloud_cos.cos_exception import CosClientError, CosServiceError
    try:
        main()
    except (CosClientError, CosServiceError) as exc:
        print(json.dumps({'error': type(exc).__name__,
                          'status': exc.get_status_code() if isinstance(exc, CosServiceError) else None,
                          'code': exc.get_error_code() if isinstance(exc, CosServiceError) else None}), flush=True)
        raise SystemExit(1) from None
