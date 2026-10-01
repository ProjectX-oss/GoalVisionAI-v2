"""Narrow ADMIN notification upgrade. Default verifies only; --apply needs root."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

BASE = Path('/opt/goalvision-admin-alerts-releases/admin-autorepair-89428e0-r4-20261001')
OVERRIDE = Path('/etc/systemd/system/goalvision-admin-alerts.service.d/40-autorepair.conf')
MODULE = Path('app/admin_alerts/operator_jobs.py')
TIMER = 'goalvision-admin-alerts.timer'
SERVICE = 'goalvision-admin-alerts.service'
OLD_MODULE_SHA = '3042d6855326ca68324f7b252552c287a9049cecb3264dd7b6923cd75e3cfd99'
OLD_ROUTE_SHA = 'ce3bc7b9bff8868c6628b739b5733d303447270d753a7dbccc2204836e1fbdf6'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def control(*args: str) -> str:
    result = subprocess.run(['/usr/bin/systemctl', *args], check=True,
                            capture_output=True, text=True, timeout=60)
    return result.stdout.strip()


def atomic(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.status-upgrade-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o644)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate(package: Path) -> tuple[dict, Path]:
    meta = json.loads((package/'metadata.json').read_text())
    commit = meta['source_commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('INVALID_COMMIT')
    if sha(package/'operator_jobs.py') != meta['module_sha256']:
        raise ValueError('PACKAGE_HASH_MISMATCH')
    if sha(package/'update.py') != meta['updater_sha256']:
        raise ValueError('UPDATER_HASH_MISMATCH')
    destination = BASE.parent/('admin-status-lv-'+commit[:7]+'-20261001')
    if BASE.is_symlink() or OVERRIDE.is_symlink():
        raise ValueError('UNEXPECTED_SYMLINK')
    if sha(BASE/MODULE) != OLD_MODULE_SHA:
        raise ValueError('BASE_MODULE_DRIFT')
    manifest = json.loads((BASE/'manifest.json').read_text())
    actual = {str(p.relative_to(BASE)): sha(p) for p in BASE.rglob('*.py')}
    if actual != manifest or any(p.is_symlink() for p in BASE.rglob('*')):
        raise ValueError('BASE_MANIFEST_MISMATCH')
    return meta, destination


def route(target: Path, content: bytes) -> None:
    """Drain only ADMIN; preserve timer state and restore the prior route on failure."""
    previous = OVERRIDE.read_bytes()
    old_target = control('show', SERVICE, '-p', 'WorkingDirectory', '--value')
    active = control('show', TIMER, '-p', 'ActiveState', '--value') == 'active'
    switched = False
    try:
        control('stop', TIMER)
        deadline = time.monotonic()+60
        while control('show', SERVICE, '-p', 'ActiveState', '--value') in (
                'active', 'activating', 'deactivating', 'reloading'):
            if time.monotonic() >= deadline:
                raise TimeoutError('ADMIN_DRAIN_TIMEOUT')
            time.sleep(.2)
        atomic(OVERRIDE, content)
        switched = True
        control('daemon-reload')
        if control('show', SERVICE, '-p', 'WorkingDirectory', '--value') != str(target):
            raise ValueError('ADMIN_ROUTE_VERIFY_FAILED')
        if str(target/'run.py') not in control('show', SERVICE, '-p', 'ExecStart', '--value'):
            raise ValueError('ADMIN_EXEC_VERIFY_FAILED')
        if active:
            control('start', TIMER)
            if control('show', TIMER, '-p', 'ActiveState', '--value') != 'active':
                raise ValueError('ADMIN_TIMER_RESTORE_FAILED')
    except BaseException:
        if switched:
            atomic(OVERRIDE, previous)
            control('daemon-reload')
            if control('show', SERVICE, '-p', 'WorkingDirectory', '--value') != old_target:
                raise RuntimeError('ROLLBACK_ROUTE_VERIFY_FAILED')
        if active:
            control('start', TIMER)
        raise


def apply(package: Path, rollback: bool = False) -> None:
    meta, destination = validate(package)
    current = control('show', SERVICE, '-p', 'WorkingDirectory', '--value')
    if rollback:
        backup = destination/'previous-admin-dropin.conf'
        if current != str(destination) or sha(backup) != OLD_ROUTE_SHA:
            raise ValueError('ROLLBACK_STATE_MISMATCH')
        route(BASE, backup.read_bytes())
        print('ADMIN_STATUS_LV_ROLLBACK=PASS')
        return
    if current != str(BASE) or sha(OVERRIDE) != OLD_ROUTE_SHA:
        raise ValueError('ADMIN_ROUTE_DRIFT')
    if destination.exists():
        raise ValueError('DESTINATION_EXISTS_REVIEW_REQUIRED')
    original = OVERRIDE.read_bytes()
    stage = Path(tempfile.mkdtemp(prefix='.admin-status-lv-', dir=BASE.parent))
    try:
        shutil.copytree(BASE, stage, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(package/'operator_jobs.py', stage/MODULE)
        manifest = json.loads((stage/'manifest.json').read_text())
        manifest[str(MODULE)] = meta['module_sha256']
        atomic(stage/'manifest.json', (json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode())
        atomic(stage/'previous-admin-dropin.conf', original)
        atomic(stage/'status-update.json', (json.dumps(meta, sort_keys=True, indent=2)+'\n').encode())
        actual = {str(p.relative_to(stage)): sha(p) for p in stage.rglob('*.py')}
        if actual != manifest:
            raise ValueError('STAGE_HASH_MISMATCH')
        os.chmod(stage, 0o755)
        os.rename(stage, destination)
        route(destination, original.replace(str(BASE).encode(), str(destination).encode()))
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print('ADMIN_STATUS_LV_DEPLOYED')
    print('admin_release='+str(destination))
    print('Worker and PREMATCH routes unchanged. No test message sent.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if not args.apply:
        _, destination = validate(package)
        print('PLAN_VALIDATED='+str(destination))
        return 0
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    with open('/run/lock/goalvision-admin-status-update.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        apply(package, args.rollback)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
