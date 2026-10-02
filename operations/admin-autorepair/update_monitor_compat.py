"""Monitor-only compatibility update; ADMIN Codex must remain explicitly disabled."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal

OVERRIDE = Path('/etc/systemd/system/goalvision-admin-alerts.service.d/zzzzz-admin-monitor-compat-20261002.conf')
CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
MARKER = Path('/var/lib/goalvision-admin-autorepair/DISABLED')
WORKER = 'goalvision-admin-autorepair.service'
TIMER = 'goalvision-admin-autorepair.timer'


def require_codex_disabled(module) -> None:
    if CONFIG.is_symlink() or MARKER.is_symlink():
        raise ValueError('AUTOREPAIR_STATE_SYMLINK')
    config = json.loads(CONFIG.read_text())
    if (config.get('autorepair', {}).get('enabled') is not False
            or not MARKER.is_file()
            or module.prop(TIMER, 'ActiveState') != 'inactive'
            or module.prop(TIMER, 'UnitFileState') not in ('disabled', 'masked')
            or module.prop(WORKER, 'ActiveState') not in ('inactive', 'failed')
            or module.prop(WORKER, 'MainPID') != '0'):
        raise ValueError('ADMIN_CODEX_NOT_DISABLED')


def configure(module):
    module.SPECS = {'monitor': dict(module.SPECS['monitor'], override=OVERRIDE)}
    module.PROTECTED = (*module.PROTECTED, WORKER)
    module.RELEASE_PREFIX = 'admin-monitor-compat'
    module.STATUS_PREFIX = 'ADMIN_MONITOR_COMPAT'
    module.UNCHANGED_MESSAGE = 'Codex remains DISABLED. Worker and PREMATCH routes unchanged. No manual cycle or test send.'
    module.post_route = lambda targets: require_codex_disabled(module)
    return module


def engine(package: Path):
    meta = json.loads((package/'metadata.json').read_text())
    helper = package/'update_compat.py'
    for path, key in ((package/'update.py','updater_sha256'), (helper,'helper_sha256')):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != meta[key]:
            raise ValueError('PACKAGE_CODE_HASH_MISMATCH')
    spec = importlib.util.spec_from_file_location('admin_monitor_transaction', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return configure(module)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    module = engine(package)
    if not args.apply:
        _, targets = module.validate(package)
        print('PLAN_VALIDATED='+json.dumps({k:str(v) for k,v in targets.items()},sort_keys=True))
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('OPERATOR_INTERRUPTED')
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/goalvision-admin-status-update.lock','a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_codex_disabled(module)
        module.apply(package, args.rollback)
        require_codex_disabled(module)
        print('ADMIN_CODEX_STILL_DISABLED')
        print('ADMIN_ALERT_SUMMARY='+json.dumps(module.diagnostic(),sort_keys=True))


if __name__ == '__main__':
    main()
