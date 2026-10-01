"""Reviewed PREMATCH quality upgrade. Default is read-only; --apply is operator-only."""
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

BASE = Path('/opt/goalvision-prematch-today-scope-f5d7968-20261001')
ROUTE_BASES = {
    'goalvision-lab-v2-discover.service': BASE / 'release.env',
    'goalvision-adaptive-learning-observer.service': Path('/opt/goalvision-prematch-accuracy-delivery-fc4a740-r4-20261001/release.env'),
    'goalvision-lab-combo-settle.service': Path('/opt/goalvision-prematch-accuracy-delivery-fc4a740-r4-20261001/release.env'),
    'goalvision-adaptive-learning.service': Path('/opt/goalvision-prematch-priority-3cb8ada-20260930/research.env'),
}
SERVICES = tuple(ROUTE_BASES)
TIMERS = tuple(u.replace('.service', '.timer') for u in SERVICES)
OVERRIDES = {u: Path('/etc/systemd/system') / (u + '.d') / 'zzzzz-quality-20261001.conf' for u in SERVICES}
PROTECTED = ('goalvision-lab-weekly-stats.service', 'goalvision-admin-alerts.service',
             'goalvision-admin-autorepair.service', 'goalvision-lab-combo-discover.service')
FILES = (
    'app/adaptive_lab/automl.py', 'app/adaptive_lab/calibration_research.py',
    'app/adaptive_lab/contracts.py', 'app/adaptive_lab/coordinator.py',
    'app/adaptive_lab/datasets.py', 'app/adaptive_lab/governance.py',
    'app/adaptive_lab/health.py', 'app/adaptive_lab/metrics.py',
    'app/adaptive_lab/models.py', 'app/adaptive_lab/observations.py',
    'app/adaptive_lab/observer.py', 'app/adaptive_lab/performance.py',
    'app/adaptive_lab/policy.py', 'app/adaptive_lab/prematch.py',
    'app/lab_combo/service.py', 'app/lab_v2_shadow/accuracy_combo.py',
    'app/lab_v2_shadow/audit.py', 'app/lab_v2_shadow/cli.py',
    'app/lab_v2_shadow/public_presentation.py', 'app/lab_v2_shadow/publication.py',
    'app/lab_v2_shadow/publication_policy.py',
)
BUSY = {'active', 'activating', 'deactivating', 'reloading'}
ROUTE_KEYS = ('EnvironmentFiles', 'WorkingDirectory', 'DropInPaths')
INVARIANT_KEYS = ('WorkingDirectory', 'ExecStart', 'User', 'Group')
DRAIN_SECONDS = 60

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*.py')}

def reject_symlinks(root):
    if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('SYMLINK_REVIEW_REQUIRED')

def control(*args):
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True,
                          text=True, timeout=15).stdout.strip()

def property_of(unit, key):
    return control('show', unit, '-p', key, '--value')

def routes(units):
    return {u: {k: property_of(u, k) for k in ROUTE_KEYS} for u in units}

def stable_commands(units):
    # ExecStart includes transient pid/start/exit data: compare the configured argv only.
    values = {}
    for unit in units:
        props = {k: property_of(unit, k) for k in INVARIANT_KEYS}
        props['ExecStart'] = props['ExecStart'].split(' ; ignore_errors=')[0]
        values[unit] = props
    return values

def environment(target):
    return ('PYTHONPATH=' + str(target / 'application') + '\n'
            'GOALVISION_LAB_ACCURACY_COMBOS=1\nGOALVISION_LAB_TODAY_ONLY=1\n').encode()

def dropin(target):
    return ('[Service]\nEnvironmentFile=\nEnvironmentFile=' + str(target / 'release.env') + '\n').encode()

def atomic(path, data):
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.quality-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            os.fchmod(out.fileno(), 0o644)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def validate(package):
    reject_symlinks(package)
    meta = json.loads((package / 'metadata.json').read_text())
    commit = meta['source_commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('INVALID_COMMIT')
    if set(meta['files']) != set(FILES) or sha(package / 'update.py') != meta['updater_sha256']:
        raise ValueError('PACKAGE_CONTRACT_MISMATCH')
    for name in FILES:
        if sha(package / 'overlay' / name) != meta['files'][name]:
            raise ValueError('PACKAGE_HASH_MISMATCH')
    reject_symlinks(BASE)
    if tree(BASE / 'application') != meta['base_manifest'] or (BASE / 'release.env').read_bytes() != environment(BASE):
        raise ValueError('BASE_SOURCE_OR_ENV_DRIFT')
    # Also pin the observer/settlement and research rollback sources.
    expected_sources = {str(p) for p in ROUTE_BASES.values()}
    if set(meta['route_sources']) != expected_sources:
        raise ValueError('ROUTE_SOURCE_SET_MISMATCH')
    for env_path, expected in meta['route_sources'].items():
        env = Path(env_path)
        app = env.parent / ('research' if env.name == 'research.env' else 'application')
        reject_symlinks(env.parent)
        if sha(env) != expected['environment_sha256'] or tree(app) != expected['manifest']:
            raise ValueError('ROLLBACK_SOURCE_DRIFT')
    if stable_commands(SERVICES) != meta['expected_commands'] or routes(PROTECTED) != meta['protected_routes']:
        raise ValueError('PREPARED_CONFIGURATION_DRIFT')
    for override in OVERRIDES.values():
        if override.is_symlink() or override.parent.is_symlink():
            raise ValueError('OVERRIDE_SYMLINK')
    return meta, BASE.parent / ('goalvision-prematch-quality-' + commit[:7] + '-20261001')

def verify_routes(target=None):
    for unit, original in ROUTE_BASES.items():
        expected = str(target / 'release.env') if target else str(original)
        if property_of(unit, 'EnvironmentFiles') != expected + ' (ignore_errors=no)':
            raise ValueError('PREMATCH_ROUTE_MISMATCH:' + unit)

def verify_release(target, expected):
    reject_symlinks(target)
    if tree(target / 'application') != expected or (target / 'release.env').read_bytes() != environment(target):
        raise ValueError('RELEASE_DRIFT')

def restore_timers(states):
    failures = []
    for timer, was_active in states.items():
        try:
            if was_active:
                control('start', timer)
            elif property_of(timer, 'ActiveState') != 'inactive':
                control('stop', timer)
            expected = 'active' if was_active else 'inactive'
            if property_of(timer, 'ActiveState') != expected:
                failures.append(timer)
        except BaseException:
            failures.append(timer)
    if failures:
        raise RuntimeError('TIMER_RESTORE_FAILED:' + ','.join(failures))

def route(target, *, rollback=False):
    previous = {u: p.read_bytes() if p.exists() else None for u, p in OVERRIDES.items()}
    old_routes = routes(SERVICES)
    invariants = stable_commands(SERVICES)
    protected = routes(PROTECTED)
    states = {}
    for timer in TIMERS:
        state = property_of(timer, 'ActiveState')
        if state not in ('active', 'inactive'):
            raise ValueError('TIMER_STATE_REVIEW_REQUIRED:' + timer)
        states[timer] = state == 'active'
    changed = []
    try:
        for timer in TIMERS:
            control('stop', timer)
        deadline = time.monotonic() + DRAIN_SECONDS
        while any(property_of(unit, 'ActiveState') in BUSY for unit in SERVICES):
            if time.monotonic() >= deadline:
                raise TimeoutError('PREMATCH_RUNNING_RETRY_AFTER_COMPLETION')
            time.sleep(.2)
        if routes(SERVICES) != old_routes or stable_commands(SERVICES) != invariants:
            raise ValueError('CONCURRENT_ROUTE_CHANGE')
        for unit, path in OVERRIDES.items():
            if rollback:
                path.unlink()
            else:
                atomic(path, dropin(target))
            changed.append(unit)
        control('daemon-reload')
        verify_routes(None if rollback else target)
        if stable_commands(SERVICES) != invariants or routes(PROTECTED) != protected:
            raise ValueError('UNRELATED_CONFIGURATION_CHANGED')
        restore_timers(states)
    except BaseException:
        recovery_errors = []
        # Re-pause before restoring to avoid a mixed route during timer recovery.
        for timer in TIMERS:
            try:
                control('stop', timer)
            except BaseException:
                recovery_errors.append('TIMER_PAUSE')
        for unit in reversed(changed):
            try:
                if previous[unit] is None:
                    OVERRIDES[unit].unlink(missing_ok=True)
                else:
                    atomic(OVERRIDES[unit], previous[unit])
            except BaseException:
                recovery_errors.append('DROPIN_RESTORE')
        if changed:
            try:
                control('daemon-reload')
                if routes(SERVICES) != old_routes:
                    recovery_errors.append('ROUTE_RESTORE')
            except BaseException:
                recovery_errors.append('RELOAD')
        try:
            restore_timers(states)
        except BaseException:
            recovery_errors.append('TIMER_RESTORE')
        if recovery_errors:
            raise RuntimeError('RECOVERY_REVIEW_REQUIRED:' + ','.join(recovery_errors)) from None
        raise

def apply(package, *, rollback=False):
    meta, target = validate(package)
    expected = dict(meta['base_manifest'], **meta['files'])
    reject_symlinks(target)
    if rollback:
        if any(p.read_bytes() != dropin(target) for p in OVERRIDES.values()):
            raise ValueError('ROLLBACK_DROPIN_DRIFT')
        verify_release(target, expected)
        verify_routes(target)
        route(target, rollback=True)
        print('PREMATCH_QUALITY_ROLLBACK=PASS')
        return
    if any(p.exists() for p in OVERRIDES.values()):
        if not all(p.exists() and p.read_bytes() == dropin(target) for p in OVERRIDES.values()):
            raise ValueError('PARTIAL_OR_UNREVIEWED_OVERRIDE')
        verify_release(target, expected)
        verify_routes(target)
        print('PREMATCH_QUALITY_ALREADY_DEPLOYED')
        return
    verify_routes()
    if target.exists():
        verify_release(target, expected)
    else:
        stage = Path(tempfile.mkdtemp(prefix='.prematch-quality-', dir=BASE.parent))
        try:
            shutil.copytree(BASE / 'application', stage / 'application',
                            ignore=shutil.ignore_patterns('__pycache__'))
            for name in FILES:
                destination = stage / 'application' / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(package / 'overlay' / name, destination)
            atomic(stage / 'release.env', environment(target))
            atomic(stage / 'QUALITY_DEPLOYMENT.json', (json.dumps(meta, sort_keys=True) + '\n').encode())
            reject_symlinks(stage)
            if tree(stage / 'application') != expected:
                raise ValueError('STAGE_HASH_MISMATCH')
            os.chmod(stage, 0o755)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    route(target)
    print('PREMATCH_QUALITY_DEPLOYED')
    print('prematch_release=' + str(target))
    print('Discovery, observer, settlement and research routes updated.')
    print('Today-only Lab; no odds floor; performance/readiness/manual-promotion guards.')
    print('ADMIN and weekly routes unchanged. No manual cycle, provider call or test send.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if not args.apply:
        meta, target = validate(package)
        overrides = [p.exists() for p in OVERRIDES.values()]
        if any(overrides) and not all(overrides):
            raise ValueError('PARTIAL_OVERRIDE')
        verify_routes(target if all(overrides) else None)
        if all(overrides):
            verify_release(target, dict(meta['base_manifest'], **meta['files']))
        print('PREMATCH_QUALITY_PLAN_VALIDATED=' + str(target))
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
