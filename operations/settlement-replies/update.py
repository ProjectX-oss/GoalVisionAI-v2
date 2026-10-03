"""Reviewed SINGLE/COMBO result replies to the confirmed original prediction. Default is read-only; --apply is operator-only."""
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

BASE = Path('/opt/goalvision-prematch-combo-bot-9a3b198-20261003')
SERVICES = ('goalvision-lab-v2-discover.service', 'goalvision-adaptive-learning-observer.service',
            'goalvision-lab-combo-settle.service', 'goalvision-adaptive-learning.service')
ROUTE_BASES = {unit: BASE / 'release.env' for unit in SERVICES}
TIMERS = tuple(u.replace('.service', '.timer') for u in SERVICES)
OVERRIDES = {u: Path('/etc/systemd/system') / (u + '.d') / 'zzzzzzzzzzzz-settlement-replies-20261003.conf' for u in SERVICES}
PROTECTED = ('goalvision-lab-weekly-stats.service', 'goalvision-admin-alerts.service',
             'goalvision-admin-autorepair.service', 'goalvision-lab-combo-discover.service')
PLAN_ASSET = 'app/adaptive_lab/calendar_plan_20261002.json'
FILES = ('app/lab_combo/settlement_reply.py', 'app/lab_combo/presentation.py',
         'app/lab_combo/service.py')
ADMIN_CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
ADMIN_DISABLED = Path('/var/lib/goalvision-admin-autorepair/DISABLED')
BUSY = {'active', 'activating', 'deactivating', 'reloading'}
ROUTE_KEYS = ('EnvironmentFiles', 'WorkingDirectory', 'DropInPaths')
INVARIANT_KEYS = ('WorkingDirectory', 'ExecStart', 'User', 'Group')
DRAIN_SECONDS = 45

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(root):
    files = list(root.rglob('*.py'))
    # The frozen plan is executable configuration and belongs in the manifest.
    files += list(root.rglob('calendar_plan_20261002.json'))
    return {str(p.relative_to(root)): sha(p) for p in files}

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
        if props['ExecStart'].count('{ path=') != 1 or ' ; ignore_errors=' not in props['ExecStart']:
            raise ValueError('UNREVIEWED_COMMAND_REPRESENTATION')
        props['ExecStart'] = props['ExecStart'].split(' ; ignore_errors=')[0]
        values[unit] = props
    return values

def base_environment(target):
    return ('PYTHONPATH=' + str(target / 'application') + '\n'
            'GOALVISION_LAB_ACCURACY_COMBOS=1\nGOALVISION_LAB_TODAY_ONLY=1\n'
            'GOALVISION_LAB_EARLY_COMBO_LOSS=1\nGOALVISION_LAB_SINGLE_MIN_ODDS_130=1\n'
            'GOALVISION_LAB_DEVIG_RESEARCH=1\nGOALVISION_LAB_CALIBRATION_READINESS=1\n'
            'GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130=1\nGOALVISION_COMBO_BOT_ROUTING=1\n').encode()

def expected_route_sources(base_manifest, files):
    return {str(BASE / 'release.env'): {
        'environment_sha256': hashlib.sha256(base_environment(BASE)).hexdigest(),
        'manifest': dict(base_manifest)}}

def environment(target, rollback=False):
    return base_environment(target) + (
        'GOALVISION_LAB_SETTLEMENT_REPLIES=' + ('0' if rollback else '1') + '\n').encode()

def check_configuration(package):
    code = ("import sys; sys.path.insert(0, " + repr(str(BASE / 'application')) + "); "
            "from app.lab_combo.bot_routing import load_config; load_config(); "
            "from telegram import ReplyParameters; ReplyParameters(message_id=1, allow_sending_without_reply=True)")
    result = subprocess.run(['/home/arvis/GoalVisionAI/.venv/bin/python', '-I', '-c', code],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError('COMBO_PRIVATE_RECIPIENT_CONFIGURATION_REQUIRED')

def dropin(target, rollback=False):
    env = target / ('rollback.env' if rollback else 'release.env')
    return ('[Service]\nEnvironmentFile=\nEnvironmentFile=' + str(env) + '\n').encode()

def disabled_worker():
    timer = 'goalvision-admin-autorepair.timer'
    worker = 'goalvision-admin-autorepair.service'
    if (property_of(timer, 'ActiveState') != 'inactive'
            or property_of(timer, 'UnitFileState') != 'disabled'
            or property_of(worker, 'ActiveState') != 'inactive'
            or property_of(worker, 'MainPID') != '0'):
        raise ValueError('ADMIN_CODEX_DISABLED_GUARD')

    # Root apply can additionally inspect the installed root-owned guard files.
    # A normal-user plan validates systemd only and reports this limitation.
    if os.geteuid() == 0:
        config = json.loads(ADMIN_CONFIG.read_text())
        if config.get('autorepair', {}).get('enabled') is not False or not ADMIN_DISABLED.is_file():
            raise ValueError('ADMIN_CODEX_ROOT_GUARD')

def atomic(path, data):
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.settlement-replies-', dir=path.parent)
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
    disabled_worker()
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
    if tree(BASE / 'application') != meta['base_manifest'] or (BASE / 'release.env').read_bytes() != base_environment(BASE):
        raise ValueError('BASE_SOURCE_OR_ENV_DRIFT')
    # Pin the exact installed COMBO routing application and frozen plan.
    expected_sources = {str(p) for p in ROUTE_BASES.values()}
    if set(meta['route_sources']) != expected_sources:
        raise ValueError('ROUTE_SOURCE_SET_MISMATCH')
    if meta['route_sources'] != expected_route_sources(meta['base_manifest'], meta['files']):
        raise ValueError('ROUTE_SOURCE_CONTRACT_MISMATCH')
    for env_path, expected in meta['route_sources'].items():
        env = Path(env_path)
        app = env.parent / ('research' if env.name == 'research.env' else 'application')
        reject_symlinks(env.parent)
        if sha(env) != expected['environment_sha256'] or tree(app) != expected['manifest']:
            raise ValueError('ROLLBACK_SOURCE_DRIFT')
    if stable_commands(SERVICES + PROTECTED) != meta['expected_commands'] or routes(PROTECTED) != meta['protected_routes']:
        raise ValueError('PREPARED_CONFIGURATION_DRIFT')
    for override in OVERRIDES.values():
        if override.is_symlink() or override.parent.is_symlink():
            raise ValueError('OVERRIDE_SYMLINK')
    return meta, BASE.parent / ('goalvision-prematch-settlement-replies-' + commit[:7] + '-20261003')

def verify_routes(target=None, rollback=False):
    for unit, original in ROUTE_BASES.items():
        expected = str(target / ('rollback.env' if rollback else 'release.env')) if target else str(original)
        if property_of(unit, 'EnvironmentFiles') != expected + ' (ignore_errors=no)':
            raise ValueError('PREMATCH_ROUTE_MISMATCH:' + unit)

def verify_release(target, expected):
    reject_symlinks(target)
    if (tree(target / 'application') != expected
            or (target / 'release.env').read_bytes() != environment(target)
            or (target / 'rollback.env').read_bytes() != environment(target, True)):
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
    invariants = stable_commands(SERVICES + PROTECTED)
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
        if routes(SERVICES) != old_routes or stable_commands(SERVICES + PROTECTED) != invariants:
            raise ValueError('CONCURRENT_ROUTE_CHANGE')
        for unit, path in OVERRIDES.items():
            atomic(path, dropin(target, rollback))
            changed.append(unit)
        control('daemon-reload')
        verify_routes(target, rollback)
        if stable_commands(SERVICES + PROTECTED) != invariants or routes(PROTECTED) != protected:
            raise ValueError('UNRELATED_CONFIGURATION_CHANGED')
        disabled_worker()
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

def current_mode(target):
    present = [p.exists() for p in OVERRIDES.values()]
    if not any(present):
        verify_routes()
        return 'BASE'
    if all(present):
        for rollback, mode in ((False, 'ENABLED'), (True, 'ROLLBACK')):
            if all(p.read_bytes() == dropin(target, rollback) for p in OVERRIDES.values()):
                verify_routes(target, rollback)
                return mode
    raise ValueError('PARTIAL_OR_UNREVIEWED_OVERRIDE')

def apply(package, *, rollback=False):
    meta, target = validate(package)
    expected = dict(meta['base_manifest'], **meta['files'])
    reject_symlinks(target)
    mode = current_mode(target)
    if not rollback:
        check_configuration(package)
    if mode != 'BASE':
        verify_release(target, expected)
    wanted = 'ROLLBACK' if rollback else 'ENABLED'
    if mode == wanted or (rollback and mode == 'BASE'):
        print('SETTLEMENT_REPLIES_ALREADY_' + mode)
        return
    if target.exists():
        verify_release(target, expected)
    else:
        stage = Path(tempfile.mkdtemp(prefix='.settlement-replies-', dir=BASE.parent))
        try:
            shutil.copytree(BASE / 'application', stage / 'application',
                            ignore=shutil.ignore_patterns('__pycache__'))
            for name in FILES:
                destination = stage / 'application' / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(package / 'overlay' / name, destination)
            atomic(stage / 'release.env', environment(target))
            atomic(stage / 'rollback.env', environment(target, True))
            atomic(stage / 'SETTLEMENT_REPLIES_DEPLOYMENT.json', (json.dumps(meta, sort_keys=True) + '\n').encode())
            reject_symlinks(stage)
            if tree(stage / 'application') != expected:
                raise ValueError('STAGE_HASH_MISMATCH')
            os.chmod(stage, 0o755)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    route(target, rollback=rollback)
    print('PREMATCH_SETTLEMENT_REPLIES_COMPAT_ROLLBACK' if rollback else 'PREMATCH_SETTLEMENT_REPLIES_DEPLOYED')
    print('prematch_release=' + str(target))
    print('PREMATCH SINGLE minimum=1.30; COMBO per-leg minimum=1.30.')
    print('Result replies=' + ('DISABLED' if rollback else 'ENABLED; SINGLE and COMBO; text and photos'))
    print('COMBO bot/private recipient and existing statistics periods retained.')
    print('No additional combined-odds floor. Existing quality and correlation checks retained.')
    print('Calibration readiness=ENABLED; de-vig research=ENABLED; champion unchanged.')
    print('Early COMBO loss=ENABLED; installed settlement behavior and remaining-leg tracking retained.')
    print('ADMIN Codex remains DISABLED; ADMIN and weekly routes unchanged.')
    print('No manual cycle, provider call or test send.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if not args.apply:
        meta, target = validate(package)
        mode = current_mode(target)
        if mode != 'BASE':
            verify_release(target, dict(meta['base_manifest'], **meta['files']))
        print('SETTLEMENT_REPLIES_PLAN_VALIDATED=' + str(target))
        print('current_mode=' + mode + '; ADMIN_CODEX_SYSTEMD_DISABLED=PASS')
        print('ROOT_GUARD=PASS' if os.geteuid() == 0 else 'ROOT_GUARD=CHECKED_AT_APPLY')
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
