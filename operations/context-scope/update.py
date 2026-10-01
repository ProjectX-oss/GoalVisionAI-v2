"""Discovery-only context scope-index hotfix. Default verifies without changes."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

BASE = Path('/opt/goalvision-prematch-accuracy-combo-c490866-20261001')
OVERRIDE = Path('/etc/systemd/system/goalvision-lab-v2-discover.service.d/zzz-context-scope-20261001.conf')
SERVICE = 'goalvision-lab-v2-discover.service'
TIMER = 'goalvision-lab-v2-discover.timer'
FILES = ('app/prematch_football_context/capture/repository.py',
         'app/prematch_football_context/snapshot/service.py')
PROTECTED = ('goalvision-lab-combo-settle.service', 'goalvision-adaptive-learning-observer.service',
             'goalvision-lab-weekly-stats.service', 'goalvision-adaptive-learning.service',
             'goalvision-admin-alerts.service', 'goalvision-admin-autorepair.service')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*.py')}

def control(*args):
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True,
                          text=True, timeout=60).stdout.strip()

def property_of(unit, key):
    return control('show', unit, '-p', key, '--value')

def environment(target):
    return ('PYTHONPATH=' + str(target / 'application') + '\n'
            + 'GOALVISION_LAB_ACCURACY_COMBOS=1\n').encode()

def dropin(target):
    return ('[Service]\nEnvironmentFile=\nEnvironmentFile=' + str(target / 'release.env') + '\n').encode()

def atomic(path, data):
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.context-scope-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o644)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def validate(package):
    meta = json.loads((package / 'metadata.json').read_text())
    commit = meta['source_commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('INVALID_COMMIT')
    if set(meta['files']) != set(FILES):
        raise ValueError('UNEXPECTED_OVERLAY')
    if sha(package / 'update.py') != meta['updater_sha256']:
        raise ValueError('UPDATER_HASH_MISMATCH')
    for name in FILES:
        if sha(package / 'overlay' / name) != meta['files'][name]:
            raise ValueError('PACKAGE_HASH_MISMATCH')
    if BASE.is_symlink() or OVERRIDE.is_symlink():
        raise ValueError('UNEXPECTED_SYMLINK')
    if any(p.is_symlink() for p in (BASE / 'application').rglob('*')):
        raise ValueError('BASE_SYMLINK')
    if tree(BASE / 'application') != meta['base_manifest']:
        raise ValueError('BASE_SOURCE_DRIFT')
    if (BASE / 'release.env').read_bytes() != environment(BASE):
        raise ValueError('BASE_ENVIRONMENT_DRIFT')
    return meta, BASE.parent / ('goalvision-prematch-context-scope-' + commit[:7] + '-20261001')

def protected_routes():
    return {u: {k: property_of(u, k) for k in ('EnvironmentFiles', 'WorkingDirectory', 'DropInPaths')}
            for u in PROTECTED}

def verify_route(target):
    if property_of(SERVICE, 'EnvironmentFiles') != str(target / 'release.env') + ' (ignore_errors=no)':
        raise ValueError('DISCOVERY_ROUTE_MISMATCH')

def route(target, *, rollback=False):
    previous = OVERRIDE.read_bytes() if OVERRIDE.exists() else None
    old_route = property_of(SERVICE, 'EnvironmentFiles')
    other_routes = protected_routes()
    active = property_of(TIMER, 'ActiveState') == 'active'
    changed = False
    try:
        control('stop', TIMER)
        deadline = time.monotonic() + 60
        while property_of(SERVICE, 'ActiveState') in ('active', 'activating', 'deactivating', 'reloading'):
            if time.monotonic() >= deadline:
                raise TimeoutError('DISCOVERY_RUNNING_RETRY_AFTER_COMPLETION')
            time.sleep(.2)
        if property_of(SERVICE, 'EnvironmentFiles') != old_route:
            raise ValueError('CONCURRENT_ROUTE_CHANGE')
        if rollback:
            OVERRIDE.unlink()
        else:
            atomic(OVERRIDE, dropin(target))
        changed = True
        control('daemon-reload')
        verify_route(BASE if rollback else target)
        if protected_routes() != other_routes:
            raise ValueError('UNRELATED_ROUTE_CHANGED')
        if active:
            control('start', TIMER)
            if property_of(TIMER, 'ActiveState') != 'active':
                raise ValueError('TIMER_RESTORE_FAILED')
    except BaseException:
        if changed:
            if previous is None:
                OVERRIDE.unlink(missing_ok=True)
            else:
                atomic(OVERRIDE, previous)
            control('daemon-reload')
            if property_of(SERVICE, 'EnvironmentFiles') != old_route:
                raise RuntimeError('ROLLBACK_ROUTE_VERIFY_FAILED')
        if active:
            control('start', TIMER)
        raise

def apply(package, *, rollback=False):
    meta, destination = validate(package)
    expected = dict(meta['base_manifest'], **meta['files'])
    if rollback:
        if OVERRIDE.read_bytes() != dropin(destination):
            raise ValueError('ROLLBACK_DROPIN_DRIFT')
        verify_route(destination)
        route(destination, rollback=True)
        print('PREMATCH_CONTEXT_SCOPE_ROLLBACK=PASS')
        return
    if OVERRIDE.exists():
        if (OVERRIDE.read_bytes() == dropin(destination)
                and tree(destination / 'application') == expected
                and (destination / 'release.env').read_bytes() == environment(destination)):
            verify_route(destination)
            print('PREMATCH_CONTEXT_SCOPE_ALREADY_DEPLOYED')
            return
        raise ValueError('EXISTING_OVERRIDE_REVIEW_REQUIRED')
    verify_route(BASE)
    if destination.exists():
        if (tree(destination / 'application') != expected
                or (destination / 'release.env').read_bytes() != environment(destination)):
            raise ValueError('DESTINATION_DRIFT')
    else:
        stage = Path(tempfile.mkdtemp(prefix='.prematch-context-scope-', dir=BASE.parent))
        try:
            shutil.copytree(BASE / 'application', stage / 'application',
                            ignore=shutil.ignore_patterns('__pycache__'))
            for name in FILES:
                shutil.copyfile(package / 'overlay' / name, stage / 'application' / name)
            atomic(stage / 'release.env', environment(destination))
            atomic(stage / 'CONTEXT_SCOPE_DEPLOYMENT.json', (json.dumps(meta, sort_keys=True) + '\n').encode())
            if tree(stage / 'application') != expected:
                raise ValueError('STAGE_HASH_MISMATCH')
            os.chmod(stage, 0o755)
            os.rename(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    route(destination)
    print('PREMATCH_CONTEXT_SCOPE_DEPLOYED')
    print('discovery_release=' + str(destination))
    print('Validated context scope index enabled; selection policy unchanged.')
    print('Other service routes unchanged. No manual provider calls or test Telegram sends.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if not args.apply:
        _, target = validate(package)
        print('PLAN_VALIDATED=' + str(target))
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/goalvision-prematch-accuracy-combo.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apply(package, rollback=args.rollback)

if __name__ == '__main__':
    main()
