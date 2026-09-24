#!/usr/bin/env python3
"""Uncompressed, checked tar streams over independent SSH connections.

This file is also the standalone (stdlib-only) remote receiver. No shell command
from a data manifest is executed. Sources and unrelated destination files are
never removed or overwritten.
"""

import argparse
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

BLOCK = 4 * 1024 * 1024


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('wb') as out:
        out.write(encoded(value) + b'\n')
        out.flush()
        os.fsync(out.fileno())
    tmp.replace(path)


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            sha.update(block)
    return sha.hexdigest()


def signature(path):
    info = Path(path).stat()
    if not Path(path).is_file():
        raise ValueError(f'not a regular file: {path}')
    return [info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino]


def safe_path(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError(f'unsafe target: {relative}')
    path = root / rel
    if path.resolve() != path:
        raise ValueError(f'symlink in target: {relative}')
    return path


def publish(staged, target, sha):
    target.parent.mkdir(parents=True, exist_ok=True)
    # link() is an atomic no-clobber publication, including when two batches
    # contain the same shared file. Never use replace() on a dataset file.
    try:
        os.link(staged, target)
    except FileExistsError:
        if target.stat().st_size != staged.stat().st_size or digest(target) != sha:
            raise ValueError(f'destination conflict: {target}')
    staged.unlink()


class HashReader:
    def __init__(self, stream):
        self.stream = stream
        self.sha = hashlib.sha256()

    def read(self, size=-1):
        value = self.stream.read(size)
        self.sha.update(value)
        return value


def tar_bytes(archive, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(data))


def write_stream(stream, plan):
    results = []
    with tarfile.open(fileobj=stream, mode='w|', bufsize=BLOCK) as archive:
        tar_bytes(archive, 'plan.json', encoded(plan))
        for i, row in enumerate(plan['files']):
            if signature(row['source']) != row['signature']:
                raise ValueError(f"source changed before transfer: {row['source']}")
            info = tarfile.TarInfo(f'files/{i}')
            info.size = row['length']
            info.mode = 0o644
            with open(row['source'], 'rb') as source:
                source.seek(row.get('offset', 0))
                reader = HashReader(source)
                archive.addfile(info, reader)
            if signature(row['source']) != row['signature']:
                raise ValueError(f"source changed during transfer: {row['source']}")
            sha = reader.sha.hexdigest()
            if row.get('expected') and sha != row['expected']:
                raise ValueError(f"catalog checksum mismatch: {row['source']}")
            results.append({'target': row['target'], 'size': row['length'],
                            'sha256': sha})
        # No receiver publication is possible without this final commit member.
        tar_bytes(archive, 'checksums.json', encoded(results))
    return results


def receive(root, run, batch, stream):
    incoming = safe_path(root, f'.incoming/{run}/{batch}')
    incoming.mkdir(parents=True, exist_ok=True)
    actual = []
    with tarfile.open(fileobj=stream, mode='r|', bufsize=BLOCK) as archive:
        member = archive.next()
        if member is None or member.name != 'plan.json' or member.size > 100_000_000:
            raise ValueError('missing transfer plan')
        plan = json.load(archive.extractfile(member))
        if plan['run'] != run or plan['batch'] != batch:
            raise ValueError('wrong transfer identity')
        for i, row in enumerate(plan['files']):
            safe_path(root, row['target'])
            if not (row['target'].startswith('datasets/')
                    or row['target'].startswith(f'migration/{run}/')
                    or row['target'].startswith(f'.incoming/{run}/chunks/')):
                raise ValueError('target outside migration scope')
            member = archive.next()
            if (member is None or member.name != f'files/{i}'
                    or not member.isfile() or member.size != row['length']):
                raise ValueError('unexpected tar member or size')
            sha = hashlib.sha256()
            with archive.extractfile(member) as source, (incoming / str(i)).open('wb') as out:
                for block in iter(lambda: source.read(BLOCK), b''):
                    sha.update(block)
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            actual.append({'target': row['target'], 'size': member.size,
                           'sha256': sha.hexdigest()})
        member = archive.next()
        if member is None or member.name != 'checksums.json':
            raise ValueError('interrupted stream: missing checksums')
        expected = json.load(archive.extractfile(member))
        if expected != actual:
            raise ValueError('stream checksum mismatch')
        if archive.next() is not None:
            raise ValueError('unexpected extra tar member')
    for i, row in enumerate(actual):
        publish(incoming / str(i), safe_path(root, row['target']), row['sha256'])
    receipt = {'plan_sha256': hashlib.sha256(encoded(plan)).hexdigest(), 'files': actual}
    save(safe_path(root, f'migration/{run}/receipts/{batch}.json'), receipt)
    incoming.rmdir()
    return receipt


def assemble(root, run, plan):
    target = safe_path(root, plan['target'])
    receipt_path = safe_path(root, f'migration/{run}/assembled/{plan["id"]}.json')
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if (receipt['target'] != plan['target'] or receipt['size'] != plan['size']
                or not target.is_file() or target.stat().st_size != receipt['size']
                or digest(target) != receipt['sha256']):
            raise ValueError('assembled file changed since completion')
        return receipt
    temporary = safe_path(root, f'.incoming/{run}/assembled/{plan["id"]}')
    temporary.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    size = 0
    with temporary.open('wb') as out:
        for part in plan['parts']:
            local = hashlib.sha256()
            count = 0
            with safe_path(root, part['target']).open('rb') as source:
                for block in iter(lambda: source.read(BLOCK), b''):
                    out.write(block)
                    local.update(block)
                    sha.update(block)
                    count += len(block)
            if count != part['size'] or local.hexdigest() != part['sha256']:
                raise ValueError('changed or missing chunk')
            size += count
        out.flush()
        os.fsync(out.fileno())
    if size != plan['size'] or (plan.get('expected') and sha.hexdigest() != plan['expected']):
        raise ValueError('assembled checksum or size mismatch')
    publish(temporary, target, sha.hexdigest())
    result = {'target': plan['target'], 'size': size, 'sha256': sha.hexdigest()}
    save(receipt_path, result)
    # Chunks remain available for interrupted assembly; successful assembly
    # keeps the receipts, and releases only this run's redundant chunk bytes.
    for part in plan['parts']:
        safe_path(root, part['target']).unlink()
    return result


def ssh(host, command):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'Compression=no',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
            '-o', 'ConnectTimeout=20', '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=4', host, shlex.join(command)]


def remote_command(config, action, *extra):
    return ssh(config['host'], ['python3', config['receiver'], action,
                                '--root', config['destination'], '--run', config['run'],
                                *extra])


def send(config, plan, progress=None):
    for row in plan['files']:
        if signature(row['source']) != row['signature']:
            raise ValueError(f"source changed since inventory: {row['source']}")
    previous = subprocess.run(remote_command(config, 'receipt', '--batch', plan['batch']),
                              capture_output=True, check=True)
    receipt = json.loads(previous.stdout)
    plan_sha = hashlib.sha256(encoded(plan)).hexdigest()
    if receipt:
        if receipt['plan_sha256'] != plan_sha:
            raise ValueError('resume plan mismatch')
        return receipt
    proc = subprocess.Popen(remote_command(config, 'receive', '--batch', plan['batch']),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        class Sink:
            def write(self, data):
                count = proc.stdin.write(data)
                if progress:
                    progress(count)
                return count
        write_stream(Sink(), plan)
        proc.stdin.close()
        proc.stdin = None
        out, err = proc.communicate()
        if proc.returncode:
            raise RuntimeError(err.decode(errors='replace'))
        receipt = json.loads(out)
        if receipt['plan_sha256'] != plan_sha:
            raise ValueError('receiver acknowledged wrong plan')
        return receipt
    except BaseException:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        proc.communicate()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['receive', 'receipt', 'assemble'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--batch')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == 'receive':
        result = receive(root, args.run, args.batch, sys.stdin.buffer)
    elif args.action == 'receipt':
        path = safe_path(root, f'migration/{args.run}/receipts/{args.batch}.json')
        result = json.loads(path.read_text()) if path.exists() else None
    else:
        result = assemble(root, args.run, json.load(sys.stdin))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
