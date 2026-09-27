#!/usr/bin/env python3
"""Operations-only timer deployment. No application imports or network calls."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calendar_proof import NAMES, OLD, TARGET, evaluate, proof

PACKAGE = Path(__file__).resolve().parent
UNIT_ROOT = Path('/etc/systemd/system')
STATE = Path('/var/lib/goalvision-prematch-timer-stagger')
UNIT_SEARCH_ROOTS = (Path('/etc/systemd/system'), Path('/run/systemd/system'), Path('/usr/lib/systemd/system'))
ADMIN_CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
ADMIN_STATE = Path('/var/lib/goalvision-admin-alerts')
OWNED = '95-goalvision-prematch-timer-stagger.conf'
CHANGED = NAMES[1:]
STABLE = ('Id', 'LoadState', 'FragmentPath', 'UnitFileState', 'Unit', 'AccuracyUSec',
          'RandomizedDelayUSec', 'Persistent', 'Requires', 'Wants', 'Conflicts', 'BindsTo',
          'PartOf', 'ConsistsOf', 'BoundBy', 'PropagatesStopTo', 'OnFailure', 'OnSuccess', 'Triggers',
          'TimersMonotonic')
DYNAMIC = ('DropInPaths', 'NeedDaemonReload', 'ActiveState', 'SubState', 'TimersCalendar',
           'NextElapseUSecRealtime', 'LastTriggerUSec', 'InvocationID', 'ExecMainStatus', 'Result')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path):
    require(not any(p.is_symlink() for p in [path, *path.parents]), 'SYMLINK_REFUSED:' + str(path))
    require(path.is_file(), 'FILE_MISSING:' + str(path))
    return path


def verify_package(root, digest):
    require(re.fullmatch('[a-f0-9]{64}', digest or '') is not None, 'TRUSTED_MANIFEST_DIGEST_REQUIRED')
    require(sha(regular(root/'SHA256SUMS')) == digest, 'MANIFEST_TAMPER')
    entries = {}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        require(name not in entries and not Path(name).is_absolute() and '..' not in Path(name).parts, 'BAD_MANIFEST')
        require(sha(regular(root/name)) == expected, 'PACKAGE_TAMPER:' + name)
        entries[name] = expected
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    require(actual == set(entries), 'PACKAGE_INVENTORY_DRIFT')
    return digest


def sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    require(not any(p.is_symlink() for p in [path, *path.parents]), 'SYMLINK_REFUSED')
    fd, tmp = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        sync(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Host:
    def show(self, unit):
        require(unit in BASELINE['units'], 'UNIT_NOT_ALLOWED')
        result = subprocess.run(['/usr/bin/systemctl', 'show', unit, '--property='+','.join(STABLE+DYNAMIC)],
                                check=True, capture_output=True, text=True, timeout=30)
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

    def mutate(self, action, unit=None):
        require((action == 'daemon-reload' and unit is None) or
                (action == 'restart' and unit in CHANGED), 'TIMER_ONLY_CONTROL')
        subprocess.run(['/usr/bin/systemctl', action, *([unit] if unit else [])],
                       check=True, capture_output=True, text=True, timeout=60)

    def admin(self):
        # Never open the live SQLite file through SQLite. Only deserialize a
        # stable byte copy under the existing monitor lock, opened read-only.
        config = json.loads(regular(ADMIN_CONFIG).read_bytes())
        enabled = config.get('sender', {}).get('enabled')
        require(type(enabled) is bool, 'ADMIN_SENDER_STATE_UNKNOWN')
        with regular(ADMIN_STATE/'scan.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            dbpath = regular(ADMIN_STATE/'admin.sqlite')
            require(not any(Path(str(dbpath)+s).exists() for s in ('-wal', '-shm', '-journal')), 'ADMIN_SNAPSHOT_UNSAFE')
            raw = dbpath.read_bytes()
            require(raw[:16] == b'SQLite format 3\x00' and raw[18:20] == b'\x01\x01', 'ADMIN_DB_FORMAT')
            db = sqlite3.connect(':memory:')
            try:
                db.deserialize(raw)
                db.execute('PRAGMA query_only=ON')
                require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'ADMIN_INTEGRITY')
                epochs = db.execute('SELECT id,activated_at,policy FROM notification_epochs').fetchall()
            finally:
                db.close()
        fenced = (ADMIN_STATE/'DISABLED').exists()
        require(not enabled or (len(epochs) == 1 and not fenced), 'ADMIN_ENABLED_STATE_INCONSISTENT')
        return {'sender_enabled': enabled, 'monitor_fenced': fenced, 'notification_epochs': epochs,
                'config_sha256': sha(ADMIN_CONFIG), 'transport': 'NOT_CONTACTED'}


def calendar_of(properties):
    return re.findall(r'OnCalendar=(.*?) ; next_elapse=', properties.get('TimersCalendar', ''))


def dropin(unit):
    return UNIT_ROOT/(unit+'.d')/OWNED


def payload(unit):
    return ('# Owned by goalvision-prematch-timer-stagger v1\n[Timer]\nOnCalendar=\nOnCalendar='+TARGET[unit]+'\n').encode()


def inspect(host, mode='original', reload_pending=False):
    require(BASELINE['deployment']['target_calendars'] == TARGET and
            BASELINE['deployment']['changed_timers'] == list(CHANGED), 'DEPLOYMENT_BASELINE_DRIFT')
    require(Path('/etc/timezone').read_text().strip() == BASELINE['timezone'] and
            sha(Path('/etc/localtime')) == BASELINE['localtime_sha256'], 'TIMEZONE_DRIFT')
    units = {}
    for unit, pin in BASELINE['units'].items():
        props = host.show(unit)
        for key in STABLE:
            actual_value, pinned_value = props.get(key, ''), pin['properties'].get(key, '')
            if key in ('Requires', 'Wants', 'Conflicts', 'BindsTo', 'PartOf', 'ConsistsOf', 'BoundBy', 'PropagatesStopTo', 'Triggers', 'OnFailure', 'OnSuccess'):
                actual_value, pinned_value = sorted(actual_value.split()), sorted(pinned_value.split())
            require(actual_value == pinned_value, 'UNIT_PROPERTY_DRIFT:'+unit+':'+key)
        require(props['LoadState'] == 'loaded', 'UNIT_NOT_LOADED:'+unit)
        for path, digest in pin['files'].items():
            require(sha(regular(Path(path))) == digest, 'UNIT_HASH_DRIFT:'+path)
        expected_dropins = pin['properties']['DropInPaths'].split()
        owned = dropin(unit)
        if unit in CHANGED:
            if mode == 'installed':
                require(regular(owned).read_bytes() == payload(unit), 'OWNED_DROPIN_DRIFT:'+unit)
                expected_dropins.append(str(owned))
            elif mode == 'original':
                require(not owned.exists() and not owned.is_symlink(), 'OWNED_DROPIN_ALREADY_EXISTS:'+unit)
            elif owned.exists():
                require(regular(owned).read_bytes() == payload(unit), 'OWNED_DROPIN_DRIFT:'+unit)
        actual = props['DropInPaths'].split()
        if mode == 'recovery':
            actual = [p for p in actual if p != str(owned)]
        require(sorted(actual) == sorted(expected_dropins), 'DROPIN_DRIFT:'+unit)
        # Detect on-disk additions even before systemd reports reload drift.
        for root in UNIT_SEARCH_ROOTS:
            found = {str(p) for p in (Path(root)/(unit+'.d')).glob('*.conf')}
            permitted = set(pin['properties']['DropInPaths'].split()) | ({str(owned)} if mode != 'original' and unit in CHANGED else set())
            require(found <= permitted, 'UNLOADED_DROPIN_DRIFT:'+unit)
        if reload_pending and unit not in CHANGED:
            require(props['NeedDaemonReload'] == 'no', 'UNRELATED_RELOAD_DRIFT:'+unit)
        if not reload_pending:
            require(props['NeedDaemonReload'] == 'no', 'NEED_DAEMON_RELOAD:'+unit)
            if unit in OLD:
                require(calendar_of(props) == [(TARGET if mode == 'installed' else OLD)[unit]], 'CALENDAR_DRIFT:'+unit)
        if unit.endswith('.timer'):
            require(props['ActiveState'] in ('active', 'inactive'), 'TIMER_TRANSITION:'+unit)
            require(props.get('UnitFileState') in ('enabled', 'disabled'), 'UNSUPPORTED_TIMER_ENABLE_STATE:'+unit)
        units[unit] = props
    for unit in CHANGED:
        for key in ('ConsistsOf', 'BoundBy', 'PropagatesStopTo', 'OnFailure', 'OnSuccess'):
            require(not units[unit].get(key), 'TIMER_PROPAGATION_REFUSED:'+unit+':'+key)
    return units


def timestamp(text):
    if not text or text == 'n/a':
        return None
    result = subprocess.run(['/usr/bin/date', '--date='+text, '+%s'], check=True, capture_output=True, text=True, timeout=5)
    return datetime.fromtimestamp(int(result.stdout), timezone.utc)


def safe_rearm(host, unit, expression):
    p = host.show(unit)
    if p['ActiveState'] == 'inactive':
        return
    now = datetime.now(timezone.utc)
    require(not any(abs((t-now).total_seconds()) < 10 for t in evaluate(expression, now-timedelta(seconds=11), 2)),
            'CALENDAR_BOUNDARY_RETRY_LATER:'+unit)
    if p.get('Persistent') == 'yes':
        last = timestamp(p.get('LastTriggerUSec'))
        # Nine days includes the last weekly tick, DST included.
        events = evaluate(expression, now-timedelta(days=9), 1400 if unit == NAMES[1] else 500)
        prior = [t for t in events if t <= now]
        require(prior and last and last >= max(prior), 'PERSISTENT_CATCHUP_RISK_RETRY_AFTER_NORMAL_RUN:'+unit)


def verify_next(host, unit, expression, active, deadline):
    while True:
        p = host.show(unit)
        require(p['ActiveState'] == active, 'ACTIVE_STATE_DRIFT:'+unit)
        if active == 'inactive':
            require(not timestamp(p.get('NextElapseUSecRealtime')), 'INACTIVE_TIMER_ARMED:'+unit)
            return p
        now = datetime.now(timezone.utc)
        actual = timestamp(p.get('NextElapseUSecRealtime'))
        expected = evaluate(expression, now-timedelta(seconds=2), 3)
        if actual in expected and actual > now-timedelta(seconds=2):
            return p
        require(time.monotonic() < deadline, 'NEXT_ELAPSE_UNVERIFIED:'+unit)
        # A normally firing worker may hold its timer in running state. Never
        # stop it; allow it to finish and systemd to arm the next calendar tick.
        time.sleep(2)


def read_transaction():
    path = STATE/'transaction.json'
    return json.loads(regular(path).read_text()) if path.exists() else None


def save_transaction(tx):
    atomic(STATE/'transaction.json', (json.dumps(tx, indent=2, sort_keys=True)+'\n').encode())


@contextmanager
def deployment_lock():
    require(os.geteuid() == 0, 'ROOT_OPERATOR_REQUIRED')
    require(not STATE.is_symlink(), 'STATE_SYMLINK')
    STATE.mkdir(mode=0o700, exist_ok=True)
    require(STATE.stat().st_uid == 0 and not STATE.stat().st_mode & 0o022, 'UNSAFE_STATE_DIRECTORY')
    regular_lock = STATE/'operation.lock'
    require(not regular_lock.is_symlink(), 'LOCK_SYMLINK')
    with regular_lock.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def restore(host, tx):
    require(tx['manifest'] == MANIFEST, 'RECOVERY_PACKAGE_MISMATCH')
    inspect(host, 'recovery', reload_pending=True)
    tx['phase'] = 'rolling_back'
    tx['reload_pending'] = tx.get('reload_pending', False) or any(dropin(u).exists() for u in CHANGED)
    save_transaction(tx)
    # If a boundary was crossed, wait for a NORMAL run to make persistent
    # re-arming safe. No worker control, timer stop, or timestamp-file writes.
    deadline = time.monotonic()+900
    while True:
        try:
            for unit in CHANGED:
                safe_rearm(host, unit, OLD[unit])
            break
        except ValueError as exc:
            require(time.monotonic() < deadline, 'ROLLBACK_PENDING:'+str(exc))
            time.sleep(2)
    changed = False
    for unit in CHANGED:
        path = dropin(unit)
        if path.exists():
            require(regular(path).read_bytes() == payload(unit), 'REFUSE_REMOVE_FOREIGN_DROPIN')
            path.unlink()
            sync(path.parent)
            changed = True
    # reload_pending remains durable across a crash between unlink and reload.
    if changed or tx.get('reload_pending'):
        host.mutate('daemon-reload')
        for unit in CHANGED:
            if tx['timers'][unit]['ActiveState'] == 'active':
                safe_rearm(host, unit, OLD[unit])
                host.mutate('restart', unit)
    units = inspect(host, 'original')
    verify_states(host, tx, OLD, units)
    tx.update(phase='rolled_back', reload_pending=False, rolled_back_at=datetime.now(timezone.utc).isoformat())
    save_transaction(tx)
    return {'phase': tx['phase'], 'units': units}


def verify_states(host, tx, schedules, units):
    deadline = time.monotonic()+900
    for unit in NAMES:
        require(units[unit]['UnitFileState'] == tx['timers'][unit]['UnitFileState'], 'ENABLE_STATE_CHANGED:'+unit)
        require(units[unit]['ActiveState'] == tx['timers'][unit]['ActiveState'], 'ACTIVE_STATE_CHANGED:'+unit)
        if unit in CHANGED:
            units[unit] = verify_next(host, unit, schedules[unit], tx['timers'][unit]['ActiveState'], deadline)


def change(host, action):
    if action == 'install' and read_transaction() is None:
        require(proof(local_zone=BASELINE['timezone'])['zero_collisions'], 'TARGET_CALENDAR_COLLISION')
    with deployment_lock():
        tx = read_transaction()
        if action == 'rollback':
            require(tx is not None, 'NO_PACKAGE_TRANSACTION')
            if tx['phase'] == 'rolled_back':
                return {'phase': tx['phase'], 'units': inspect(host)}
            return restore(host, tx)
        if tx and tx['phase'] not in ('rolled_back',):
            if tx['phase'] == 'installed':
                return {'phase': 'installed', 'units': inspect(host, 'installed')}
            # Recover, then require a fresh check/install; never silently resume.
            return restore(host, tx)
        require(proof(local_zone=BASELINE['timezone'])['zero_collisions'], 'TARGET_CALENDAR_COLLISION')
        check_result = check(host)
        require(check_result['collision_proof']['zero_collisions'], 'TARGET_CALENDAR_COLLISION')
        for unit in CHANGED:
            require((PACKAGE/'drop-ins'/(unit+'.conf')).read_bytes() == payload(unit), 'PAYLOAD_MISMATCH')
            safe_rearm(host, unit, TARGET[unit])
        units = inspect(host)
        tx = {'schema': 1, 'phase': 'installing', 'manifest': MANIFEST,
              'reload_pending': False, 'started_at': datetime.now(timezone.utc).isoformat(),
              'admin_before': check_result['admin'],
              'timers': {u: {k: units[u][k] for k in ('ActiveState', 'UnitFileState')} for u in NAMES}}
        save_transaction(tx)
        try:
            for unit in CHANGED:
                path = dropin(unit)
                require(not path.exists() and not path.is_symlink(), 'DROPIN_RACE')
                path.parent.mkdir(exist_ok=True)
                sync(path.parent.parent)
                atomic(path, payload(unit))
                tx['reload_pending'] = True
                save_transaction(tx)
            for unit in CHANGED:
                safe_rearm(host, unit, TARGET[unit])
            host.mutate('daemon-reload')
            for unit in CHANGED:
                if tx['timers'][unit]['ActiveState'] == 'active':
                    safe_rearm(host, unit, TARGET[unit])
                    host.mutate('restart', unit)
            units = inspect(host, 'installed')
            verify_states(host, tx, TARGET, units)
            admin_after = host.admin()
            require(admin_after == tx['admin_before'], 'ADMIN_STATE_CHANGED_EXTERNALLY')
            tx.update(phase='installed', reload_pending=False, installed_at=datetime.now(timezone.utc).isoformat())
            save_transaction(tx)
            return {'phase': 'installed', 'units': units, 'admin': admin_after}
        except BaseException:
            restore(host, tx)
            raise


def check(host):
    tx = read_transaction()
    require(not tx or tx['phase'] == 'rolled_back', 'TRANSACTION_PRESENT_USE_STATUS_OR_ROLLBACK')
    units = inspect(host)
    report = proof(local_zone=BASELINE['timezone'])
    require(report['zero_collisions'], 'TARGET_CALENDAR_COLLISION')
    admin = host.admin()
    return {'phase': 'preflight_passed', 'units': units, 'admin': admin, 'collision_proof': report}


def status(host):
    tx = read_transaction()
    phase = tx['phase'] if tx else 'not_installed'
    units = inspect(host, 'installed' if phase == 'installed' else 'original' if phase in ('not_installed', 'rolled_back') else 'recovery',
                    reload_pending=phase in ('installing', 'rolling_back'))
    return {'phase': phase, 'transaction': tx, 'units': units, 'admin': host.admin(),
            'collision_proof': proof(local_zone=BASELINE['timezone'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'install', 'status', 'rollback', 'evidence', 'proof'))
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--since', help='ISO 8601 UTC start; defaults to successful installation time')
    args = parser.parse_args()
    global BASELINE, MANIFEST
    MANIFEST = verify_package(PACKAGE, args.manifest_sha256)
    BASELINE = json.loads((PACKAGE/'baseline.json').read_text())
    host = Host()
    if args.action in ('install', 'rollback'):
        def interrupted(signum, frame):
            raise InterruptedError('SIGNAL:'+str(signum))
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        result = change(host, args.action)
    elif args.action == 'check':
        result = check(host)
    elif args.action == 'status':
        result = status(host)
    elif args.action == 'proof':
        result = proof(local_zone=BASELINE['timezone'])
    else:
        from forward_evidence import evidence
        tx = read_transaction()
        since = args.since or (tx or {}).get('installed_at')
        require(since is not None, 'EVIDENCE_START_REQUIRED')
        result = evidence(host, since)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.action == 'proof' and not result['zero_collisions']:
        return 2
    if args.action == 'evidence' and result['verdict'] != 'PASS':
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'REFUSED', 'reason': str(exc)}), file=sys.stderr)
        sys.exit(1)
