"""Standalone ADMIN-only upgrade and separately confirmed sender activation."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.admin_alerts.activation import enable, projection, readiness, write_config
from app.admin_alerts.store import Store

TARGET = Path('/opt/goalvision-admin-alerts')
BACKUP = Path('/opt/goalvision-admin-alerts-v1-3-v1-2-rollback')
STAGE = Path('/opt/goalvision-admin-alerts-v1-3-stage')
TRANSACTION = Path('/opt/goalvision-admin-alerts-v1-3-transaction.json')
CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
STATE = Path('/var/lib/goalvision-admin-alerts')
UNIT_ROOT = Path('/etc/systemd/system')
ADMIN = ('goalvision-admin-alerts.timer', 'goalvision-admin-alerts.service')
CONFIRM = 'ENABLE_PRIVATE_ADMIN_NEW_INCIDENTS_ONLY'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entries(path: Path) -> dict:
    return {name: value for value, name in (line.split('  ', 1) for line in path.read_text().splitlines())}


def verify(root: Path, manifest: dict) -> None:
    if root.is_symlink() or root.resolve() != root:
        raise ValueError('UNSAFE_ROOT')
    for name, value in manifest.items():
        path = root/name
        if path.is_symlink() or root not in path.resolve().parents or sha(path) != value:
            raise ValueError('PACKAGE_HASH_MISMATCH')
    actual = {str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'SHA256SUMS'}
    if actual != set(manifest):
        raise ValueError('UNMANIFESTED_FILES')


def systemctl(action: str, *units: str) -> str:
    """Control interface structurally rejects every non-ADMIN unit and reload."""
    if action not in ('show', 'stop', 'start') or any(u not in ADMIN for u in units):
        raise ValueError('ADMIN_UNITS_ONLY')
    args = ['/usr/bin/systemctl', action, *units]
    if action == 'show':
        args += ['--property=ActiveState', '--value']
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=50).stdout.strip()


@contextmanager
def scan_lock():
    with (STATE/'scan.lock').open('rb') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


@contextmanager
def snapshot(*, locked: bool = False):
    """Read live bytes under existing lock; SQLite reads only an in-memory copy."""
    def read():
        path = STATE/'admin.sqlite'
        if path.is_symlink() or any(Path(str(path)+s).exists() for s in ('-wal','-shm','-journal')):
            raise ValueError('UNSAFE_DATABASE_SNAPSHOT')
        raw = path.read_bytes()
        if raw[:16] != b'SQLite format 3\x00' or raw[18:20] != b'\x01\x01':
            raise ValueError('UNSUPPORTED_DATABASE_FORMAT')
        return raw
    if locked:
        raw = read()
    else:
        with scan_lock():
            raw = read()
    db = sqlite3.connect(':memory:')
    try:
        db.deserialize(raw)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('DATABASE_INTEGRITY')
        yield db
    finally:
        db.close()


def inspect(package: Path, *, installed: str | None = None) -> dict:
    verify(package, entries(package/'SHA256SUMS'))
    baseline = json.loads((package/'upgrade-baseline.json').read_text())
    for name, expected in baseline['admin_units'].items():
        if name not in ADMIN or sha(UNIT_ROOT/name) != expected:
            raise ValueError('ADMIN_UNIT_DRIFT')
    manifest = entries(package/('v1-2-SHA256SUMS' if installed == 'v1.2' else 'SHA256SUMS'))
    if installed:
        verify(TARGET, manifest)
    config = json.loads(CONFIG.read_text())
    with snapshot() as db:
        review = projection(db, config)
    review['monitor_fenced'] = (STATE/'DISABLED').exists()
    review['timer_active'] = systemctl('show', ADMIN[0]) == 'active'
    return review


def fence() -> None:
    with (STATE/'DISABLED').open('ab') as handle:
        handle.flush()
        os.fsync(handle.fileno())
    sync(STATE)


def sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exchange(first: Path, second: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renameat2(-100, os.fsencode(first), -100, os.fsencode(second), 2):
        raise OSError(ctypes.get_errno(), 'ADMIN_EXCHANGE_FAILED')
    sync(first.parent)


def change(package: Path, action: str, confirm: str | None = None) -> dict:
    if os.geteuid() != 0:
        raise ValueError('ROOT_OPERATOR_REQUIRED')
    if action == 'enable-sender' and confirm != CONFIRM:
        raise ValueError('EXPLICIT_CONFIRMATION_REQUIRED')
    with (STATE/'operation-v1-3.lock').open('a') as operation:
        fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action == 'disable-sender':
            # Emergency disable does not depend on token readiness or a readable DB.
            verify(package, entries(package/'SHA256SUMS'))
            verify(TARGET, entries(package/'SHA256SUMS'))
            review = {'timer_active': systemctl('show', ADMIN[0]) == 'active',
                      'monitor_fenced': (STATE/'DISABLED').exists()}
        else:
            review = inspect(package, installed='v1.2' if action == 'upgrade' else 'v1.3')
        if action in ('upgrade', 'enable-sender') and review['sender_enabled'] is not False:
            raise ValueError('SENDER_MUST_BE_FALSE')
        if action == 'enable-sender' and (review['notification_epoch'] or review['monitor_fenced']):
            raise ValueError('ACTIVATION_REPLAY_OR_FENCE_REQUIRES_REVIEW')
        if action == 'upgrade':
            if any(p.exists() for p in (STAGE, BACKUP, TRANSACTION)) or review['monitor_fenced']:
                raise ValueError('EXISTING_TRANSACTION_OR_FENCE')
            shutil.copytree(package, STAGE, ignore=shutil.ignore_patterns('__pycache__'))
            for path in STAGE.rglob('*'):
                if path.is_file():
                    os.chmod(path, 0o644)
                    with path.open('rb') as handle:
                        os.fsync(handle.fileno())
                elif path.is_dir():
                    os.chmod(path, 0o755)
            os.chmod(STAGE, 0o755)
            for directory in sorted([STAGE, *(p for p in STAGE.rglob('*') if p.is_dir())], key=lambda p: len(p.parts), reverse=True):
                sync(directory)
            verify(STAGE, entries(package/'SHA256SUMS'))
            STAGE.rename(BACKUP)
            sync(BACKUP.parent)
            with TRANSACTION.open('x') as handle:
                json.dump({'base': 'd811177fdd11e25b087f036584d33c0e0328906b', 'timer_active': review['timer_active']}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            sync(TRANSACTION.parent)
        if action == 'rollback':
            verify(BACKUP, entries(package/'v1-2-SHA256SUMS'))
        try:
            # Persistent fence comes first: failures and reboot cannot run old logic.
            fence()
            systemctl('stop', ADMIN[0])
            systemctl('stop', ADMIN[1])
            with scan_lock():
                config = json.loads(CONFIG.read_text())
                if action in ('upgrade', 'enable-sender') and config['sender']['enabled'] is not False:
                    raise ValueError('CONFIG_CHANGED_DURING_OPERATION')
                if action == 'upgrade':
                    verify(TARGET, entries(package/'v1-2-SHA256SUMS'))
                    verify(BACKUP, entries(package/'SHA256SUMS'))
                    with snapshot(locked=True) as db:
                        projection(db, config)
                    exchange(TARGET, BACKUP)
                    verify(TARGET, entries(package/'SHA256SUMS'))
                elif action == 'enable-sender':
                    store = Store(STATE)
                    try:
                        enable(CONFIG, store.db, time.time())
                    finally:
                        store.close()
                elif action in ('disable-sender', 'rollback'):
                    config['sender']['enabled'] = False
                    write_config(CONFIG, config)
                    if json.loads(CONFIG.read_text())['sender']['enabled'] is not False:
                        raise ValueError('DISABLE_VERIFICATION_FAILED')
                    if action == 'rollback':
                        exchange(TARGET, BACKUP)
                        verify(TARGET, entries(package/'v1-2-SHA256SUMS'))
                if action != 'rollback' and not review['monitor_fenced']:
                    (STATE/'DISABLED').unlink()
                    sync(STATE)
            if review['timer_active'] and action != 'rollback':
                systemctl('start', ADMIN[0])
            return {'status': action.upper(), 'sender_enabled': action == 'enable-sender',
                    'monitor_fenced': action == 'rollback', 'prematch_controls': 0, 'telegram_sends': 0}
        except BaseException:
            if action == 'enable-sender':
                # Also fail closed if a later fence removal or timer start fails.
                # Keep the epoch audit; replay requires an explicit operator review.
                fence()
                systemctl('stop', ADMIN[0])
                systemctl('stop', ADMIN[1])
                with scan_lock():
                    disabled = json.loads(CONFIG.read_text())
                    disabled['sender']['enabled'] = False
                    write_config(CONFIG, disabled)
            raise



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check','upgrade','status','prepare-enable','enable-sender','disable-sender','rollback'))
    parser.add_argument('--confirm')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    try:
        if args.action in ('check', 'status', 'prepare-enable'):
            review = inspect(package, installed='v1.2' if args.action == 'check' else 'v1.3')
            if args.action == 'check' and review['sender_enabled'] is not False:
                raise ValueError('SENDER_MUST_BE_FALSE')
            print(json.dumps({'status': args.action.upper(), **review}, sort_keys=True))
        else:
            print(json.dumps(change(package, args.action, args.confirm), sort_keys=True))
        return 0
    except Exception:
        # Never expose config, IDs, paths from secrets, exceptions or subprocess output.
        print(json.dumps({'status': 'BLOCKED', 'action': args.action,
                          'reason': 'ADMIN_PREFLIGHT_OR_TRANSACTION_FAILED_OPERATOR_REVIEW_REQUIRED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
