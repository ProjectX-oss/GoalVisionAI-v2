"""Disconnect ADMIN Auto-Repair; default is preview, --apply requires root."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
MARKER = Path('/var/lib/goalvision-admin-autorepair/DISABLED')
SCAN_LOCK = Path('/var/lib/goalvision-admin-alerts/scan.lock')
TIMER = 'goalvision-admin-autorepair.timer'
WORKER = 'goalvision-admin-autorepair.service'
MONITOR_TIMER = 'goalvision-admin-alerts.timer'


def control(*args: str) -> str:
    return subprocess.run(['/usr/bin/systemctl', *args], check=True,
        capture_output=True, text=True, timeout=20).stdout.strip()


def prop(unit: str, key: str) -> str:
    return control('show', unit, '-p', key, '--value')


def write_atomic(path: Path, data: bytes, mode: int, uid: int, gid: int) -> None:
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, name = tempfile.mkstemp(prefix='.autorepair-off-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchown(output.fileno(), uid, gid)
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def scan_lock():
    fd = os.open(SCAN_LOCK, os.O_WRONLY | os.O_NOFOLLOW)
    try:
        deadline = time.monotonic()+45
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('WORKER_STOPPED_MONITOR_BUSY_RETRY_SAME_COMMAND')
                time.sleep(.1)
        yield
    finally:
        os.close(fd)


def disable() -> dict:
    """Stop execution first; preserve queued/history evidence and monitor settings."""
    monitor_before = prop(MONITOR_TIMER, 'ActiveState')
    if MARKER.parent.is_symlink() or MARKER.is_symlink():
        raise ValueError('SYMLINK_DISABLE_MARKER')
    write_atomic(MARKER, b'OPERATOR_DISABLED_ADMIN_AUTOREPAIR_20261002\n', 0o644, 0, 0)
    control('disable', '--now', TIMER)
    # KillMode=control-group on the reviewed unit includes any Codex child.
    control('stop', WORKER)
    with scan_lock():
        if CONFIG.is_symlink():
            raise ValueError('SYMLINK_CONFIGURATION')
        metadata = CONFIG.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 131072:
            raise ValueError('CONFIGURATION_SHAPE')
        original = CONFIG.read_bytes()
        config = json.loads(original)
        if not isinstance(config, dict) or not isinstance(config.get('autorepair'), dict):
            raise ValueError('AUTOREPAIR_CONFIGURATION_SHAPE')
        before_other = {k:v for k,v in config.items() if k != 'autorepair'}
        before_repair = {k:v for k,v in config['autorepair'].items() if k != 'enabled'}
        if config['autorepair'].get('enabled') is not False:
            backup = CONFIG.parent / ('admin-alerts.before-autorepair-off-'+str(time.time_ns())+'.json')
            write_atomic(backup, original, 0o600, 0, 0)
            config['autorepair']['enabled'] = False
            write_atomic(CONFIG, (json.dumps(config, indent=2, sort_keys=True)+'\n').encode(),
                         stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)
        after = json.loads(CONFIG.read_bytes())
        if (after.get('autorepair', {}).get('enabled') is not False
                or {k:v for k,v in after.items() if k != 'autorepair'} != before_other
                or {k:v for k,v in after['autorepair'].items() if k != 'enabled'} != before_repair):
            raise ValueError('CONFIGURATION_READBACK_FAILED')
    result = {
        'autorepair_enabled': False,
        'worker_timer': prop(TIMER, 'ActiveState'),
        'worker_timer_enablement': prop(TIMER, 'UnitFileState'),
        'worker_service': prop(WORKER, 'ActiveState'),
        'worker_main_pid': int(prop(WORKER, 'MainPID')),
        'disabled_marker': MARKER.is_file(),
        'monitor_timer_unchanged': prop(MONITOR_TIMER, 'ActiveState') == monitor_before,
        'history_preserved': True,
    }
    if (result['worker_timer'] != 'inactive'
            or result['worker_timer_enablement'] not in ('disabled','masked')
            or result['worker_service'] not in ('inactive','failed')
            or result['worker_main_pid'] != 0 or not result['disabled_marker']
            or not result['monitor_timer_unchanged']):
        raise ValueError('DISABLE_READBACK_FAILED')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('PLAN=Disable ADMIN queue/status dispatch, timer and worker; retain monitor and history.')
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    with open('/run/lock/goalvision-admin-status-update.lock','a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = disable()
    print('ADMIN_CODEX_DISABLED')
    print('ADMIN_AUTOREPAIR_READBACK='+json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
