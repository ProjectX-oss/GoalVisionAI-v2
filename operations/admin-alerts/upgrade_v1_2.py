"""ADMIN-only v1/v1.2 exchange. Check is read-only; no daemon-reload is needed."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sqlite3
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.admin_alerts.invalidation import eligible
from app.admin_alerts.output_contracts import CONTRACTS

TARGET = Path('/opt/goalvision-admin-alerts')
BACKUP = Path('/opt/goalvision-admin-alerts-v1-2-v1-rollback')
STAGE = Path('/opt/goalvision-admin-alerts-v1-2-stage')
TRANSACTION = Path('/opt/goalvision-admin-alerts-v1-2-transaction.json')
CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
STATE = Path('/var/lib/goalvision-admin-alerts')
UNIT_ROOT = Path('/etc/systemd/system')
ADMIN = ('goalvision-admin-alerts.timer', 'goalvision-admin-alerts.service')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entries(path: Path) -> dict[str, str]:
    return {name: digest for digest, name in (line.split('  ', 1) for line in path.read_text().splitlines())}


def verify(root: Path, manifest: dict[str, str]) -> None:
    if root.is_symlink() or root.resolve() != root or not root.is_dir():
        raise ValueError('UNSAFE_PACKAGE_ROOT')
    for name, expected in manifest.items():
        path = root/name
        if path.is_symlink() or root not in path.resolve().parents or sha(path) != expected:
            raise ValueError('FILE_HASH_MISMATCH')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
              and '__pycache__' not in p.parts and p.name != 'SHA256SUMS'}
    if actual != set(manifest):
        raise ValueError('UNMANIFESTED_FILES')


def systemctl(*args: str) -> str:
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True,
                          text=True, timeout=50).stdout.strip()


def disabled_sender() -> str:
    data = json.loads(CONFIG.read_text())
    if data.get('sender', {}).get('enabled') is not False:
        raise ValueError('SENDER_MUST_BE_EXPLICITLY_DISABLED')
    return sha(CONFIG)


def drift_review() -> None:
    names = systemctl('list-units', '--all', '--plain', '--no-legend', '--type=service,timer')
    units = [line.split()[0] for line in names.splitlines() if line.strip()]
    if not units or 'NeedDaemonReload=yes' in systemctl('show', *units, '--property=Id,NeedDaemonReload'):
        raise ValueError('LOADED_STATE_DRIFT_REVIEW_REQUIRED')
    if systemctl('show', *ADMIN, '--property=DropInPaths', '--value').strip():
        raise ValueError('ADMIN_DROPINS_REQUIRE_REVIEW')


def review_database(expected_incidents: list[str], *, scan_locked: bool = False) -> dict:
    """Read under ADMIN's existing scan lock; SQLite operates only in memory.

    Refuse WAL/hot journals instead of risking an incomplete immutable snapshot
    or allowing SQLite to create shared-memory/recovery files on the live host.
    """
    path = STATE/'admin.sqlite'
    with (STATE/'scan.lock').open('rb') as handle:
        if not scan_locked:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            raise ValueError('LIVE_DATABASE_SIDECARS_REQUIRE_REVIEW')
        raw = path.read_bytes()
    if len(raw) < 100 or raw[:16] != b'SQLite format 3\x00' or raw[18:20] != b'\x01\x01':
        raise ValueError('LIVE_DATABASE_SNAPSHOT_UNSUPPORTED')
    db = sqlite3.connect(':memory:')
    try:
        db.deserialize(raw)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('ADMIN_DATABASE_INTEGRITY')
        if (db.execute('SELECT 1 FROM attempts LIMIT 1').fetchone()
                or db.execute("SELECT 1 FROM outbox WHERE attempts!=0 OR acknowledged!=0 OR receipt IS NOT NULL OR state IN ('SENT','ATTEMPTING','UNCERTAIN') LIMIT 1").fetchone()
                or db.execute("SELECT 1 FROM incidents WHERE last_sent!=0 OR notified_state!='' LIMIT 1").fetchone()):
            raise ValueError('ADMIN_DELIVERY_HISTORY_REQUIRES_REVIEW')
        rows = db.execute("SELECT * FROM incidents WHERE rule='MISSING_OUTPUT' AND state IN ('OPEN','REPEATED','ESCALATED')").fetchall()
        candidates = [row for row in rows if eligible(db, row)]
        # Package metadata pins operator observations; eligibility stays generic.
        if not expected_incidents or not set(expected_incidents).issubset({r['id'] for r in candidates}):
            raise ValueError('OBSERVED_LEGACY_INCIDENTS_NOT_ELIGIBLE')
        for row in candidates:
            notifications = db.execute('SELECT state,attempts,acknowledged,receipt FROM outbox WHERE incident=?', (row['id'],)).fetchall()
            if not notifications or any(tuple(n) != ('PENDING', 0, 0, None) for n in notifications):
                raise ValueError('LEGACY_OUTBOX_REQUIRES_REVIEW')
        return {'eligible_incidents': [r['id'] for r in candidates], 'admin_delivery_attempts': 0,
                'live_database': 'READ_ONLY_VERIFIED'}
    finally:
        db.close()


def preflight(package: Path, *, rollback: bool = False) -> dict:
    verify(package, entries(package/'SHA256SUMS'))
    baseline = json.loads((package/'upgrade-baseline.json').read_text())
    for path, digest in baseline['protected_sha256'].items():
        if sha(Path(path)) != digest:
            raise ValueError('PREMATCH_PROTECTED_FILE_DRIFT')
    # ADMIN unit files remain byte-identical; there is no daemon-reload operation.
    for name in ADMIN:
        if sha(UNIT_ROOT/name) != baseline['admin_units'][name]:
            raise ValueError('ADMIN_UNIT_DRIFT')
    old = entries(package/'v1-SHA256SUMS')
    new = entries(package/'SHA256SUMS')
    if rollback:
        transaction = json.loads(TRANSACTION.read_text())
        if sha(CONFIG) != transaction['config_sha256']:
            raise ValueError('CONFIG_CHANGED_SINCE_UPGRADE')
        try:
            verify(TARGET, new)
            verify(BACKUP, old)
            exchanged = True
        except (OSError, ValueError):
            verify(TARGET, old)  # interrupted before exchange, or rollback already exchanged
            verify(BACKUP, new)
            exchanged = False
    else:
        verify(TARGET, old)
        if sha(TARGET/'SHA256SUMS') != sha(package/'v1-SHA256SUMS'):
            raise ValueError('INSTALLED_V1_MANIFEST_DRIFT')
        if any(p.exists() for p in (BACKUP, STAGE, TRANSACTION)):
            raise ValueError('PRIOR_TRANSACTION_REQUIRES_ROLLBACK_REVIEW')
        exchanged = False
    config_sha = disabled_sender()
    if not (STATE/'admin.sqlite').is_file() or (STATE/'admin.sqlite').is_symlink():
        raise ValueError('EXISTING_ADMIN_DATABASE_REQUIRED')
    drift_review()
    for unit, contract in CONTRACTS.items():
        if contract.source == 'NONE' and systemctl('show', unit, '--property=StandardOutput', '--value') != 'null':
            raise ValueError('REVIEWED_NONE_CONTRACT_ROUTE_DRIFT')
    database_review = {} if rollback else review_database(baseline['operator_observed_incidents'])
    active = systemctl('show', ADMIN[0], '--property=ActiveState', '--value')
    if active not in ('active', 'inactive'):
        raise ValueError('ADMIN_TIMER_STATE_UNSTABLE')
    return {**database_review, 'config_sha256': config_sha, 'timer_active': active == 'active', 'exchanged': exchanged}


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exchange(first: Path, second: Path) -> None:
    """Linux RENAME_EXCHANGE: either complete directory is visible, never a gap."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(first), -100, os.fsencode(second), 2):
        raise OSError(ctypes.get_errno(), 'ADMIN_DIRECTORY_EXCHANGE_FAILED')
    sync_directory(first.parent)


def save_transaction(value: dict) -> None:
    temporary = TRANSACTION.with_suffix('.tmp')
    with temporary.open('x') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(TRANSACTION)
    sync_directory(TRANSACTION.parent)


def apply(package: Path, *, rollback: bool = False) -> None:
    if os.geteuid() != 0:
        raise ValueError('ROOT_OPERATOR_REQUIRED')
    # A separate ADMIN transaction lock; does not open/migrate/restore the database.
    with (STATE/'upgrade.lock').open('a') as operation:
        fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        review = preflight(package, rollback=rollback)
        if rollback:
            transaction = json.loads(TRANSACTION.read_text())
        else:
            shutil.copytree(package, STAGE, ignore=shutil.ignore_patterns('__pycache__'))
            for path in STAGE.rglob('*'):
                if path.is_file():
                    os.chmod(path, 0o755 if path.name == 'disable-admin-alerts' else 0o644)
                    with path.open('rb') as handle:
                        os.fsync(handle.fileno())
                elif path.is_dir():
                    os.chmod(path, 0o755)
            os.chmod(STAGE, 0o755)
            for directory in sorted((p for p in STAGE.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                sync_directory(directory)
            sync_directory(STAGE)
            verify(STAGE, entries(package/'SHA256SUMS'))
            STAGE.rename(BACKUP)
            sync_directory(BACKUP.parent)
            transaction = review
            save_transaction(transaction)
        systemctl('stop', ADMIN[0])
        systemctl('stop', ADMIN[1])
        swapped = False
        try:
            with (STATE/'scan.lock').open('a') as scan_lock:
                fcntl.flock(scan_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if disabled_sender() != transaction['config_sha256']:
                    raise ValueError('CONFIG_CHANGED_DURING_UPGRADE')
                drift_review()
                if not rollback:
                    review_database(json.loads((package/'upgrade-baseline.json').read_text())['operator_observed_incidents'], scan_locked=True)
                # Recheck the exact files under the scan lock immediately before exchange.
                current_manifest = 'SHA256SUMS' if rollback and review['exchanged'] else 'v1-SHA256SUMS'
                backup_manifest = 'v1-SHA256SUMS' if rollback and review['exchanged'] else 'SHA256SUMS'
                verify(TARGET, entries(package/current_manifest))
                verify(BACKUP, entries(package/backup_manifest))
                if rollback:
                    # v1 cannot understand INVALIDATED. Keep it fenced across
                    # reboot via the existing ConditionPathExists/scan marker.
                    with (STATE/'DISABLED').open('ab') as marker:
                        marker.flush()
                        os.fsync(marker.fileno())
                    sync_directory(STATE)
                if not rollback or review['exchanged']:
                    exchange(TARGET, BACKUP)
                    swapped = True
                verify(TARGET, entries(package/('v1-SHA256SUMS' if rollback else 'SHA256SUMS')))
                disabled_sender()
            if transaction['timer_active'] and not rollback:
                systemctl('start', ADMIN[0])
        except BaseException:
            if swapped:
                systemctl('stop', ADMIN[0])
                systemctl('stop', ADMIN[1])
                exchange(TARGET, BACKUP)
            # Fail closed. Rollback also leaves ADMIN stopped: v1 cannot handle INVALIDATED.
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'upgrade', 'rollback'))
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    try:
        if args.action == 'check':
            review = preflight(package)
        else:
            apply(package, rollback=args.action == 'rollback')
        print(json.dumps({'status': 'CHECKED' if args.action == 'check' else args.action.upper(),
                          'sender_enabled': False, 'prematch_mutations': 0, 'daemon_reload': False,
                          **(review if args.action == 'check' else {})}))
        return 0
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'BLOCKED', 'action': args.action,
                          'reason': 'LIVE_ADMIN_STATE_REQUIRES_OPERATOR_PREFLIGHT' if isinstance(error, PermissionError) else 'Required hashes, database eligibility, disabled sender or loaded-state checks failed; no bypass permitted.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
