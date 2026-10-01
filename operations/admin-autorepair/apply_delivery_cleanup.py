"""Install recurrence protection, then retire one proven historical false alert."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import time

ROOT = Path('/var/lib/goalvision-admin-alerts')
HEALTH = Path('/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED_FOR_ADMIN_STATE')
    update = load('delivery_upgrade', package/'update.py')
    cleanup = load('delivery_cleanup', package/'cleanup.py')
    meta, destination = update.validate(package)
    for name in ('cleanup.py','apply.py'):
        if update.sha(package/name) != meta['extra_sha256'][name]:
            raise ValueError('PACKAGE_HASH_MISMATCH:'+name)
    health = sqlite3.connect('file:'+str(HEALTH)+'?mode=ro', uri=True, timeout=5)
    health.execute('PRAGMA query_only=ON')
    if not args.apply:
        db = sqlite3.connect('file:'+str(ROOT/'admin.sqlite')+'?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        proof = cleanup.inspect(db, health)
        print('CLEANUP_PLAN='+('ALREADY_INVALIDATED' if proof is None else '9_RECORDS_PROVEN'))
        db.close()
        health.close()
        return
    with open('/run/lock/goalvision-admin-status-update.lock', 'a') as deployment_lock:
        fcntl.flock(deployment_lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        current = update.control('show', update.SERVICE, '-p', 'WorkingDirectory', '--value')
        if current != str(destination):
            update.apply(package)
        if (update.control('show', update.SERVICE, '-p', 'WorkingDirectory', '--value') != str(destination)
                or update.sha(destination/update.MODULE) != meta['module_sha256']):
            raise ValueError('RECURRENCE_PROTECTION_NOT_LOADED')
        active = update.control('show',update.TIMER,'-p','ActiveState','--value') == 'active'
        try:
            update.control('stop',update.TIMER)
            deadline = time.monotonic()+60
            while update.control('show',update.SERVICE,'-p','ActiveState','--value') in (
                    'active','activating','deactivating','reloading'):
                if time.monotonic() >= deadline:
                    raise TimeoutError('ADMIN_DRAIN_TIMEOUT')
                time.sleep(.2)
            with (ROOT/'scan.lock').open('a') as scan_lock:
                fcntl.flock(scan_lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
                db = sqlite3.connect('file:'+str(ROOT/'admin.sqlite')+'?mode=rw',uri=True,timeout=5)
                db.row_factory = sqlite3.Row
                try:
                    proof = cleanup.inspect(db,health)
                    if proof is not None:
                        backup = ROOT/('before-delivery-cleanup-'+str(time.time_ns())+'.sqlite')
                        with backup.open('xb'):
                            os.chmod(backup,0o600)
                        backup_db = sqlite3.connect(backup)
                        try:
                            db.backup(backup_db)
                        finally:
                            backup_db.close()
                        print('BACKUP_CREATED='+str(backup))
                    print('FALSE_DELIVERY_INCIDENT='+cleanup.retire(db,health,time.time()))
                finally:
                    db.close()
        finally:
            health.close()
            if active:
                update.control('start',update.TIMER)
    print('ADMIN_FALSE_DELIVERY_CLEANUP=PASS')
    print('Sent alerts/receipts preserved. No test message sent.')


if __name__ == '__main__':
    main()
