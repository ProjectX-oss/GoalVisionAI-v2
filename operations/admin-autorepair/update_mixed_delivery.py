"""Operator-only ADMIN mixed delivery classification repair; no scans or history rewrites."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal

OVERRIDE = Path('/etc/systemd/system/goalvision-admin-alerts.service.d/zzzzzzzz-admin-mixed-delivery-20261004.conf')
CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
MARKER = Path('/var/lib/goalvision-admin-autorepair/DISABLED')
WORKER = 'goalvision-admin-autorepair.service'
TIMER = 'goalvision-admin-autorepair.timer'
BASE = Path('/opt/goalvision-admin-alerts-releases/admin-health-projection-99e40ac-20261004')
MODULES = ('app/admin_alerts/rules.py',)
PREMATCH_TARGET = Path('/opt/goalvision-prematch-combo-aggregate-cb6b7c6-20261004')
RESEARCH = ('goalvision-dixon-coles-research.service', 'goalvision-dixon-coles-forward.service')


def require_codex_runtime_disabled(module):
    if (module.prop(TIMER, 'ActiveState') != 'inactive'
            or module.prop(TIMER, 'UnitFileState') not in ('disabled', 'masked')
            or module.prop(WORKER, 'ActiveState') not in ('inactive', 'failed')
            or module.prop(WORKER, 'MainPID') != '0'):
        raise ValueError('ADMIN_CODEX_NOT_DISABLED')


def require_codex_disabled(module):
    require_codex_runtime_disabled(module)
    if CONFIG.is_symlink() or MARKER.is_symlink():
        raise ValueError('AUTOREPAIR_STATE_SYMLINK')
    config = json.loads(CONFIG.read_text())
    if config.get('autorepair', {}).get('enabled') is not False or not MARKER.is_file():
        raise ValueError('ADMIN_CODEX_NOT_DISABLED')


def configure(module):
    module.SPECS = {'monitor': dict(module.SPECS['monitor'], override=OVERRIDE,
        base=BASE, route_base=BASE, modules=MODULES)}
    module.PROTECTED = (*module.PROTECTED, WORKER, *RESEARCH)
    module.RELEASE_PREFIX = 'admin-mixed-delivery'
    module.RELEASE_DATE = '20261004'
    module.STATUS_PREFIX = 'ADMIN_MIXED_DELIVERY'
    module.UNCHANGED_MESSAGE = ('Mixed receipt/rejection accounting=ENABLED; genuine uncertainty, integrity alerts and history retained. '
        'ADMIN Codex remains DISABLED; PREMATCH, worker, research and weekly routes unchanged. '
        'No manual cycle, provider call or test send.')
    module.post_route = lambda targets: require_codex_disabled(module)
    return module


def protected_timers(module):
    return {unit.replace('.service', '.timer'): {
        key: module.prop(unit.replace('.service', '.timer'), key)
        for key in ('ActiveState', 'UnitFileState')}
        for unit in module.PROTECTED}


def verify_preparation(module, meta, targets):
    require_codex_runtime_disabled(module)
    if module.protected_routes() != meta['protected_routes_at_preparation']:
        verify_reviewed_prematch(module, meta)
    if protected_timers(module) != meta['protected_timers_at_preparation']:
        raise ValueError('PROTECTED_TIMER_CHANGED_SINCE_PREPARATION')
    if meta.get('runtime_import_smoke', {}).get('status') != 'ISOLATED_MONITOR_IMPORT_PASS':
        raise ValueError('PACKAGE_IMPORT_PROOF_REQUIRED')
    spec = module.SPECS['monitor']
    if spec['override'].exists():
        if spec['override'].read_bytes() != module.dropin(spec, targets['monitor']):
            raise ValueError('OVERRIDE_DRIFT')
        module.verify_route(spec, targets['monitor'])
    else:
        module.verify_route(spec, BASE)


def verify_reviewed_prematch(module, meta):
    """Allow only the separately reviewed COMBO repair; never ignore route drift."""
    import copy
    proof = meta.get('reviewed_prematch') or {}
    target = PREMATCH_TARGET
    units = ('goalvision-lab-v2-discover.service', 'goalvision-adaptive-learning-observer.service',
             'goalvision-lab-combo-settle.service', 'goalvision-adaptive-learning.service')
    if proof.get('target') != str(target):
        raise ValueError('PROTECTED_ROUTE_CHANGED_SINCE_PREPARATION')
    expected = copy.deepcopy(meta['protected_routes_at_preparation'])
    for unit in units:
        override = '/etc/systemd/system/' + unit + '.d/zzzzzzzzzzzzzzzzz-combo-aggregate-20261004.conf'
        expected[unit]['EnvironmentFiles'] = str(target/'release.env') + ' (ignore_errors=no)'
        expected[unit]['DropInPaths'] = ' '.join([*expected[unit]['DropInPaths'].split(), override])
    if module.protected_routes() != expected:
        raise ValueError('PROTECTED_ROUTE_CHANGED_SINCE_PREPARATION')
    if target.is_symlink() or any(p.is_symlink() for p in target.rglob('*')):
        raise ValueError('REVIEWED_PREMATCH_SYMLINK')
    manifest = {str(p.relative_to(target/'application')): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (target/'application').rglob('*') if p.suffix in ('.py', '.json')}
    if (manifest != proof.get('manifest') or
            hashlib.sha256((target/'release.env').read_bytes()).hexdigest() != proof.get('environment_sha256')):
        raise ValueError('REVIEWED_PREMATCH_HASH_DRIFT')


def engine(package):
    meta = json.loads((package/'metadata.json').read_text())
    helper = package/'update_compat.py'
    for path, key in ((package/'update.py', 'updater_sha256'), (helper, 'helper_sha256')):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != meta[key]:
            raise ValueError('PACKAGE_CODE_HASH_MISMATCH')
    spec = importlib.util.spec_from_file_location('admin_health_transaction', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return configure(module)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    module = engine(package)
    meta, targets = module.validate(package)
    verify_preparation(module, meta, targets)
    if not args.apply:
        print('ADMIN_MIXED_DELIVERY_PREFLIGHT='+json.dumps({'status': 'READ_ONLY_PASS',
            'target': str(targets['monitor']), 'root_guard_checked': False,
            'no_deployment': True}, sort_keys=True))
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('OPERATOR_INTERRUPTED')
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/goalvision-admin-status-update.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_codex_disabled(module)
        verify_preparation(module, meta, targets)
        # Executed inside the route transaction; mismatch restores the old route.
        def post_route(_):
            require_codex_disabled(module)
            verify_preparation(module, meta, targets)
        module.post_route = post_route
        module.apply(package, False)
        require_codex_disabled(module)
        print('ADMIN_CODEX_STILL_DISABLED')


if __name__ == '__main__':
    main()
