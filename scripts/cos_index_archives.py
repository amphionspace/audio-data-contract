#!/usr/bin/env python3
"""Hash large source archive members without extracting them to disk.

Expose member locations only after the full source object is verified in COS.
This lets unpacked copies reuse the source archive while keeping recovery paths.
"""

import argparse
import fcntl
import hashlib
import json
import sqlite3
import tarfile
import time
import zipfile
from pathlib import Path

from cos_backup import HashingReader, digest_file, signature
from cos_sync_catalog import connect, file_signature, issue

SUFFIXES = ('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.tar', '.zip')


def archive_format(path):
    return next((suffix[1:] for suffix in SUFFIXES if str(path).lower().endswith(suffix)), None)


def publish_members(db):
    ready = db.execute("""SELECT a.*,f.object_key FROM archive_index a JOIN files f
        ON f.path=a.path AND f.sha256=a.sha256
        WHERE a.status='indexed' AND f.status='verified' AND f.member=''""").fetchall()
    for row in ready:
        while members := db.execute('SELECT * FROM archive_members WHERE archive=? LIMIT 512', (row['path'],)).fetchall():
            for member in members:
                db.execute('INSERT OR IGNORE INTO contents VALUES(?,?,?,?,?)',
                           (member['size'], member['sha256'], row['object_key'], member['member'], row['container_format']))
                db.execute('DELETE FROM archive_members WHERE archive=? AND member=?',
                           (row['path'], member['member']))
            db.commit()
        db.execute("UPDATE archive_index SET status='published' WHERE path=?", (row['path'],))
        db.commit()


def index_archive(db, row):
    path = Path(row['path'])
    before = file_signature(row)
    if signature(path) != before:
        raise ValueError('archive_changed_since_inventory')
    fmt = archive_format(path)
    if fmt is None:
        raise ValueError('unsupported_archive_format')
    db.execute('DELETE FROM archive_members WHERE archive=?', (str(path),))
    db.execute('INSERT OR REPLACE INTO archive_index VALUES(?,?,?,?,?)',
               (str(path), None, fmt, 'scanning', 0))
    db.commit()
    count, last = 0, time.monotonic()
    last_commit = last

    def member(name, size, stream):
        nonlocal count, last, last_commit
        if size >= 64 * 1024**2:
            db.commit()
        sha, read = hashlib.sha256(), 0
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            sha.update(block)
            read += len(block)
        if read != size:
            raise ValueError('short_archive_member')
        # Duplicate names cannot be restored unambiguously by name.
        db.execute('INSERT INTO archive_members VALUES(?,?,?,?)',
                   (str(path), name, size, sha.hexdigest()))
        count += 1
        if count % 128 == 0 or time.monotonic() - last_commit > 2:
            db.commit()
            last_commit = time.monotonic()
            if time.monotonic() - last > 30:
                print(json.dumps({'stage': 'archive_members', 'path': str(path), 'members': count}), flush=True)
                last = time.monotonic()

    if fmt == 'zip':
        archive_sha = digest_file(path)
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    with archive.open(info) as stream:
                        member(info.filename, info.file_size, stream)
    else:
        with path.open('rb') as source:
            reader = HashingReader(source)
            with tarfile.open(fileobj=reader, mode='r|*') as archive:
                for info in archive:
                    if info.isfile():
                        with archive.extractfile(info) as stream:
                            member(info.name, info.size, stream)
            db.commit()
            # Include trailing bytes that the tar parser does not consume.
            while reader.read(8 * 1024**2):
                pass
            archive_sha = reader.sha.hexdigest()
    if signature(path) != before:
        raise ValueError('archive_changed_during_index')
    if row['expected'] and row['expected'] != archive_sha:
        raise ValueError('catalog_archive_hash_mismatch')
    if row['sha256'] and row['sha256'] != archive_sha:
        raise ValueError('uploaded_archive_hash_mismatch')
    db.execute('INSERT OR REPLACE INTO hashes VALUES(?,?,?,?,?)',
               (before['device'], before['inode'], before['size'], before['mtime_ns'], archive_sha))
    db.execute("UPDATE archive_index SET sha256=?,status='indexed',member_count=? WHERE path=?",
               (archive_sha, count, str(path)))
    db.commit()
    publish_members(db)
    print(json.dumps({'stage': 'archive_indexed', 'path': str(path), 'members': count,
                      'sha256': archive_sha}), flush=True)


def run(work):
    db = connect(work)
    db.execute("INSERT OR REPLACE INTO meta VALUES('archive_scan','running')")
    db.commit()
    while True:
        publish_members(db)
        candidates = db.execute("""SELECT f.* FROM files f LEFT JOIN archive_index a
            ON a.path=f.path WHERE f.status IN ('pending','verified','failed')
            AND f.category='archive' AND f.size>=134217728
            AND (a.path IS NULL OR a.status='scanning') ORDER BY f.size DESC""").fetchall()
        candidates = [row for row in candidates if archive_format(row['path'])]
        if not candidates:
            if dict(db.execute('SELECT key,value FROM meta')).get('scan') == 'done':
                db.execute("INSERT OR REPLACE INTO meta VALUES('archive_scan','done')")
                db.commit()
                break
            time.sleep(5)
            continue
        row = candidates[0]
        print(json.dumps({'stage': 'index_archive', 'path': row['path'], 'bytes': row['size']}), flush=True)
        try:
            index_archive(db, row)
        except (OSError, ValueError, EOFError, tarfile.TarError, zipfile.BadZipFile, sqlite3.IntegrityError) as exc:
            db.rollback()
            issue(db, row['path'], 'archive_index_failed', type(exc).__name__)
            db.execute('INSERT OR REPLACE INTO archive_index VALUES(?,?,?,?,?)',
                       (row['path'], None, archive_format(row['path']), 'failed', 0))
            db.execute('DELETE FROM archive_members WHERE archive=?', (row['path'],))
            db.commit()
    db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    with (args.work / 'archive-index.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.work)


if __name__ == '__main__':
    main()
