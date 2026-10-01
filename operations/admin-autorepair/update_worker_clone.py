"""Worker-only reviewed-source clone fix; explicit --apply is required."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal

BASE = Path('/opt/goalvision-admin-autorepair-releases/admin-io-startup-0a3e42a-20261001')
OVERRIDE = Path('/etc/systemd/system/goalvision-admin-autorepair.service.d/zzz-admin-worker-clone-20261001.conf')


def engine(package: Path):
    """Verify package code before loading the shared tested route transaction."""
    meta = json.loads((package/'metadata.json').read_text())
    helper = package/'update_io_startup.py'
    for path, key in ((package/'update.py', 'updater_sha256'), (helper, 'helper_sha256')):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != meta[key]:
            raise ValueError('PACKAGE_CODE_HASH_MISMATCH')
    spec = importlib.util.spec_from_file_location('admin_clone_transaction', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    worker = dict(module.SPECS['worker'], base=BASE, route_base=BASE, override=OVERRIDE)
    module.SPECS = {'worker': worker}
    module.PROTECTED = (*module.PROTECTED, 'goalvision-admin-alerts.service')
    module.RELEASE_PREFIX = 'admin-worker-clone'
    module.STATUS_PREFIX = 'ADMIN_WORKER_CLONE'
    module.UNCHANGED_MESSAGE = 'Monitor and PREMATCH routes unchanged. No job retry, manual cycle or test message.'
    # There is no manual worker execution or monitor scan at deployment.
    module.post_route = lambda targets: None
    return module


def main():
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
        module.apply(package, args.rollback)


if __name__ == '__main__':
    main()
