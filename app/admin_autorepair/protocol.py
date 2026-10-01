"""Bounded, allowlisted spool protocol shared by ADMIN and the local worker."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Iterator

SPOOL = Path('/var/lib/goalvision-admin-autorepair')
LIMIT = 65536
DIRECTORIES = ('queue', 'running', 'status', 'jobs', 'done')
TERMINAL = ('COMPLETED', 'FAILED', 'TIMEOUT')
OUTCOMES = ('PATCH_READY', 'NO_CODE_CHANGE', 'DIAGNOSIS_ONLY', 'CODEX_FAILED', 'TIMEOUT')
MODES = ('FIX_ALLOWED', 'DIAGNOSE_ONLY')
TARGETS = ('ADMIN', 'PREMATCH')
HEX = re.compile(r'[0-9a-f]{24}')


def job_id(incident: str, episode: int) -> str:
    """Stable episode identity independent of delivery generation and scan time."""
    return hashlib.sha256(f'autorepair-v1:{incident}:{episode}'.encode()).hexdigest()[:24]


def safe_reference(value: object) -> str:
    """Only opaque hex identifiers survive; other identifiers become fingerprints."""
    if isinstance(value, str) and re.fullmatch(r'[0-9a-f]{24,64}', value):
        return value
    return 'UNKNOWN' if value in (None, 'UNKNOWN') else hashlib.sha256(str(value).encode()).hexdigest()[:24]


def finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e12


def check_spool(root: Path) -> None:
    """Require installer-created real directories, never follow spool symlinks."""
    if not root.is_absolute() or root.resolve() != root:
        raise ValueError('INVALID_SPOOL')
    for path in (root, *(root / name for name in DIRECTORIES)):
        if path.is_symlink() or not path.is_dir():
            raise ValueError('INVALID_SPOOL')


@contextmanager
def spool_lock(root: Path, name: str = 'handoff', *, blocking: bool = True) -> Iterator[int]:
    """Cross-user flock; worker lock also survives in a live child process."""
    path = root / (name + '.lock')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o660)
        os.fchmod(fd, 0o660)
    except FileExistsError:
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield fd
    finally:
        os.close(fd)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def move(source: Path, destination: Path) -> None:
    """Same-filesystem durable atomic handoff."""
    os.replace(source, destination)
    sync_directory(source.parent)
    sync_directory(destination.parent)


def atomic_json(path: Path, value: dict) -> None:
    """Publish a complete bounded document with shared group access."""
    data = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(data) > LIMIT:
        raise ValueError('DOCUMENT_TOO_LARGE')
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o660)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict:
    """Reject links, devices, oversized and non-object input before interpretation."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError('INVALID_DOCUMENT')
        raw = handle.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('INVALID_DOCUMENT')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('INVALID_DOCUMENT')
    return value


def validate_bundle(value: dict) -> dict:
    """Validate by reconstructing the producer allowlist; reject extra fields."""
    from app.admin_alerts.autorepair import bundle
    required = {'version', 'job_id', 'incident_id', 'episode', 'generation', 'service', 'rule',
                'severity', 'invocation', 'cycle', 'object_id', 'facts', 'created_at', 'target', 'mode'}
    if set(value) != required or value.get('version') != 1:
        raise ValueError('INVALID_JOB')
    if (not isinstance(value['incident_id'], str) or not HEX.fullmatch(value['incident_id'])
            or any(type(value[k]) is not int or not 1 <= value[k] <= 10**9 for k in ('episode', 'generation'))
            or not finite(value['created_at'])):
        raise ValueError('INVALID_JOB')
    row = {**value, 'id': value['incident_id'], 'evidence': json.dumps({'cycle': value['cycle'], 'facts': value['facts']})}
    if bundle(row, value['created_at']) != value:
        raise ValueError('INVALID_JOB')
    return value


def validate_status(value: dict, bundle: dict) -> dict:
    """Only fixed machine state and bounded measurements can reach the operator."""
    keys = {'version', 'job_id', 'state', 'started_at', 'heartbeat_at', 'finished_at', 'sequence',
            'outcome', 'changed_files', 'elapsed_seconds', 'source_commit', 'diff_check', 'failure'}
    if set(value) != keys or value['version'] != 1 or value['job_id'] != bundle['job_id']:
        raise ValueError('INVALID_STATUS')
    if (value['state'] not in ('STARTED', 'RUNNING', *TERMINAL)
            or value['outcome'] not in ('', *OUTCOMES)
            or value['failure'] not in ('', 'WORKER_ERROR', 'WORKER_INTERRUPTED', 'CODEX_EXIT',
                                       'DIAGNOSE_EDIT', 'GIT_MUTATION', 'DIFF_CHECK', 'TIMEOUT')
            or value['diff_check'] not in ('NOT_RUN', 'PASS', 'FAIL')
            or not isinstance(value['source_commit'], str)
            or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64}|UNKNOWN)', value['source_commit'])
            or any(not finite(value[k]) for k in ('started_at', 'heartbeat_at', 'finished_at', 'elapsed_seconds'))
            or any(type(value[k]) is not int or not 0 <= value[k] <= 10**9 for k in ('sequence', 'changed_files'))
            or value['sequence'] < 1 or value['heartbeat_at'] < value['started_at']
            or (value['state'] in TERMINAL and (not value['outcome'] or value['finished_at'] < value['started_at']))):
        raise ValueError('INVALID_STATUS')
    return value
