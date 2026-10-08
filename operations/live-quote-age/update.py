"""Read-only by default; explicit root apply routes only the existing LIVE Lab worker."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time

HERE = Path(__file__).resolve().parent
helper_path = HERE / 'base_update.py'
if not helper_path.exists():
    helper_path = HERE.parent / 'live-evening' / 'update.py'
spec = importlib.util.spec_from_file_location('live_age_base', helper_path)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

BASE = Path('/opt/goalvision-live-evening-4f547cf-20261007')
SERVICE = 'goalvision-lab-live-evening.service'
TIMER = 'goalvision-lab-live-evening.timer'
PROTECTED = h.SERVICES + h.PROTECTED
FILES = ('app/adaptive_lab/daypart.py', 'app/adaptive_lab/worker.py',
         'app/live_lab/engine.py', 'app/live_lab/service.py', 'app/live_lab/runner.py')
OVERRIDE = Path('/etc/systemd/system') / (SERVICE + '.d') / 'zzzzzzzzzzzzzzzzzzzzzzzz-live-quote-age-20261008.conf'
METADATA = 'LIVE_QUOTE_AGE_DEPLOYMENT.json'


def environment(target):
    return h.environment(target) + b'GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC=1\n'


def timer_configuration():
    units = (TIMER,) + h.TIMERS + tuple(u.replace('.service', '.timer') for u in h.PROTECTED)
    return {unit: h.control('cat', unit) for unit in units}


def verify_protected(meta):
    if h.routes(PROTECTED) != meta['protected_routes']:
        raise ValueError('PROTECTED_ROUTE_DRIFT')
    if h.stable_commands((SERVICE,) + PROTECTED) != meta['expected_commands']:
        raise ValueError('COMMAND_DRIFT')
    if timer_configuration() != meta['timer_configuration']:
        raise ValueError('TIMER_CONFIGURATION_DRIFT')
    if h.property_of(TIMER, 'UnitFileState') != 'enabled':
        raise ValueError('LIVE_TIMER_MUST_REMAIN_ENABLED')


def verify_release(target, meta):
    h.reject_symlinks(target)
    if (h.tree(target/'application') != dict(meta['base_manifest'], **meta['files'])
            or (target/'release.env').read_bytes() != environment(target)
            or json.loads((target/METADATA).read_text()) != meta):
        raise ValueError('RELEASE_DRIFT')


def current_mode(target, meta):
    route = h.routes((SERVICE,))[SERVICE]
    if not OVERRIDE.exists():
        if OVERRIDE.is_symlink() or route != meta['base_route']:
            raise ValueError('BASE_LIVE_ROUTE_DRIFT')
        return 'BASE'
    expected = {**meta['base_route'],
                'EnvironmentFiles':str(target/'release.env')+' (ignore_errors=no)',
                'DropInPaths':str(OVERRIDE)}
    if (OVERRIDE.is_symlink() or OVERRIDE.parent.is_symlink()
            or OVERRIDE.read_bytes() != h.dropin(target) or route != expected):
        raise ValueError('PARTIAL_OR_UNREVIEWED_OVERRIDE')
    return 'ENABLED'


def validate(package):
    h.disabled_worker()
    h.reject_symlinks(package)
    h.reject_symlinks(BASE)
    meta = json.loads((package/'metadata.json').read_text())
    commit = meta['source_commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('INVALID_COMMIT')
    if meta.get('runtime_import_smoke', {}).get('status') != 'ISOLATED_LIVE_QUOTE_AGE_PASS':
        raise ValueError('PACKAGE_SMOKE_REQUIRED')
    for name in ('update.py', 'base_update.py'):
        if h.sha(package/name) != meta['scripts'][name]:
            raise ValueError('SCRIPT_HASH_MISMATCH')
    if set(meta['files']) != set(FILES):
        raise ValueError('OVERLAY_SET_MISMATCH')
    for name in FILES:
        if h.sha(package/'overlay'/name) != meta['files'][name]:
            raise ValueError('OVERLAY_HASH_MISMATCH')
    if (h.tree(BASE/'application') != meta['base_manifest']
            or (BASE/'release.env').read_bytes() != h.environment(BASE)):
        raise ValueError('BASE_RELEASE_DRIFT')
    if meta['base_route'] != {'EnvironmentFiles':str(BASE/'release.env')+' (ignore_errors=no)',
                             'WorkingDirectory':'/home/arvis/GoalVisionAI', 'DropInPaths':''}:
        raise ValueError('BASE_ROUTE_CONTRACT')
    if OVERRIDE.is_symlink() or OVERRIDE.parent.is_symlink():
        raise ValueError('OVERRIDE_SYMLINK')
    verify_protected(meta)
    target = BASE.parent / ('goalvision-live-quote-age-'+commit[:7]+'-20261008')
    mode = current_mode(target, meta)
    if target.exists() or mode == 'ENABLED':
        verify_release(target, meta)
    return meta, target, mode


def route(target, meta):
    """Transactional installer recovery only; never model rollback or manual cycle."""
    was_active = h.property_of(TIMER, 'ActiveState') == 'active'
    changed = False
    try:
        h.control('stop', TIMER)
        deadline = time.monotonic() + 180
        while h.property_of(SERVICE, 'ActiveState') in h.BUSY:
            if time.monotonic() >= deadline:
                raise TimeoutError('LIVE_RUNNING_RETRY_AFTER_COMPLETION')
            time.sleep(.2)
        verify_protected(meta)
        if current_mode(target, meta) != 'BASE':
            raise ValueError('CONCURRENT_ROUTE_CHANGE')
        OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
        if OVERRIDE.parent.is_symlink():
            raise ValueError('OVERRIDE_SYMLINK')
        changed = True
        h.atomic(OVERRIDE, h.dropin(target))
        h.control('daemon-reload')
        if current_mode(target, meta) != 'ENABLED':
            raise ValueError('LIVE_ROUTE_NOT_LOADED')
        verify_protected(meta)
        h.disabled_worker()
        h.restore_timers({TIMER:was_active})
    except BaseException:
        # Restore only this installation's partial configuration on error.
        if changed:
            OVERRIDE.unlink(missing_ok=True)
            h.control('daemon-reload')
        if current_mode(target, meta) != 'BASE':
            raise RuntimeError('INSTALL_RECOVERY_REQUIRES_OPERATOR') from None
        h.restore_timers({TIMER:was_active})
        raise


def apply(package):
    meta, target, mode = validate(package)
    if mode == 'ENABLED':
        print('LIVE_QUOTE_AGE_ALREADY_ENABLED')
        return
    if not target.exists():
        stage = Path(tempfile.mkdtemp(prefix='.live-quote-age-', dir=BASE.parent))
        try:
            shutil.copytree(BASE/'application', stage/'application',
                            ignore=shutil.ignore_patterns('__pycache__'))
            for name in FILES:
                dest = stage/'application'/name
                dest.chmod(0o644)
                shutil.copyfile(package/'overlay'/name, dest)
            h.atomic(stage/'release.env', environment(target))
            h.atomic(stage/METADATA, (json.dumps(meta, sort_keys=True)+'\n').encode())
            if h.tree(stage/'application') != dict(meta['base_manifest'], **meta['files']):
                raise ValueError('STAGE_HASH_MISMATCH')
            os.chmod(stage, 0o755)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    verify_release(target, meta)
    route(target, meta)
    print('LAB_LIVE_QUOTE_AGE_DIAGNOSTIC_DEPLOYED')
    print('live_release='+str(target))
    print('LIVE quote age=DIAGNOSTIC ONLY; no maximum age veto.')
    print('Final quote refresh, state/event freshness, score/minute match and active market checks retained.')
    print('LIVE=18:00-23:00 Riga; pending results continue outside discovery; shared quota limits unchanged.')
    print('PREMATCH/COMBO routes and policies, champion, Official and research unchanged; ADMIN Codex disabled.')
    print('No manual cycle/provider call/test send. Existing historical evidence retained.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if not args.apply:
        _, target, mode = validate(HERE)
        print('LIVE_QUOTE_AGE_PLAN_VALIDATED='+str(target))
        print('current_mode='+mode+'; ADMIN_CODEX_SYSTEMD_DISABLED=PASS')
        print('ROOT_GUARD=PASS' if os.geteuid()==0 else 'ROOT_GUARD=CHECKED_AT_APPLY')
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Installation interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/goalvision-prematch-accuracy-combo.lock','a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apply(HERE)


if __name__ == '__main__':
    main()
