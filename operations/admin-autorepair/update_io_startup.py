"""Two-service ADMIN repair; default verifies only. No PREMATCH controls."""
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

SPECS = {
    'monitor': {
        'base': Path('/opt/goalvision-admin-alerts-releases/admin-delivery-cleanup-160bb67-20261001'),
        'route_base': Path('/opt/goalvision-admin-alerts-releases/admin-delivery-cleanup-160bb67-20261001'),
        'service': 'goalvision-admin-alerts.service', 'timer': 'goalvision-admin-alerts.timer',
        'module': 'app/admin_alerts/sources.py',
        'override': Path('/etc/systemd/system/goalvision-admin-alerts.service.d/zz-admin-io-startup-20261001.conf'),
        'args': ' --config /etc/goalvision-admin-alerts/admin-alerts.json',
    },
    'worker': {
        'base': Path('/opt/goalvision-admin-autorepair-releases/admin-autorepair-89428e0-r4-20261001'),
        'route_base': Path('/opt/goalvision-admin-autorepair'),
        'service': 'goalvision-admin-autorepair.service', 'timer': 'goalvision-admin-autorepair.timer',
        'module': 'app/admin_autorepair/worker.py',
        'override': Path('/etc/systemd/system/goalvision-admin-autorepair.service.d/zz-admin-io-startup-20261001.conf'),
        'args': '',
    },
}
PROTECTED = ('goalvision-lab-v2-discover.service', 'goalvision-lab-combo-settle.service',
             'goalvision-adaptive-learning-observer.service', 'goalvision-adaptive-learning.service',
             'goalvision-lab-weekly-stats.service')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*.py')}

def control(*args):
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True,
                          text=True, timeout=30).stdout.strip()

def prop(unit, name):
    return control('show', unit, '-p', name, '--value')

def protected_routes():
    return {unit: {k: prop(unit, k) for k in ('WorkingDirectory', 'EnvironmentFiles', 'DropInPaths')}
            for unit in PROTECTED}

def dropin(spec, target):
    return ('[Service]\nWorkingDirectory='+str(target)+'\nExecStart=\nExecStart=/usr/bin/python3 -I '
            +str(target/'run.py')+spec['args']+'\n').encode()

def atomic(path, data):
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.admin-io-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def validate(package):
    meta = json.loads((package/'metadata.json').read_text())
    commit = meta['source_commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('INVALID_COMMIT')
    if set(meta['files']) != set(SPECS) or sha(package/'update.py') != meta['updater_sha256']:
        raise ValueError('PACKAGE_METADATA_MISMATCH')
    targets = {}
    for name, spec in SPECS.items():
        base = spec['base']
        if spec['route_base'].resolve() != base.resolve():
            raise ValueError('BASE_ROUTE_ALIAS_DRIFT')
        if base.is_symlink() or spec['override'].is_symlink() or any(p.is_symlink() for p in base.rglob('*')):
            raise ValueError('UNEXPECTED_SYMLINK')
        manifest = json.loads((base/'manifest.json').read_text())
        if tree(base) != manifest or manifest != meta['base_manifests'][name]:
            raise ValueError('BASE_MANIFEST_DRIFT')
        if sha(package/'overlay'/name/spec['module']) != meta['files'][name]:
            raise ValueError('OVERLAY_HASH_MISMATCH')
        targets[name] = base.parent/('admin-io-startup-'+commit[:7]+'-20261001')
    return meta, targets

def verify_route(spec, target):
    if (prop(spec['service'], 'WorkingDirectory') != str(target)
            or str(target/'run.py') not in prop(spec['service'], 'ExecStart')):
        raise ValueError('ADMIN_ROUTE_MISMATCH')

def readback(target):
    """Run the pure read adapter as ADMIN; no scan/store/sender/worker invocation."""
    program = """
import json, sqlite3, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.admin_alerts.sources import tail
cfg=json.loads(Path('/etc/goalvision-admin-alerts/admin-alerts.json').read_text())
db=sqlite3.connect('file:/var/lib/goalvision-admin-alerts/admin.sqlite?mode=ro',uri=True,isolation_level=None,timeout=.2)
row=db.execute("SELECT value FROM metadata WHERE key='stdout'").fetchone()
db.close()
records,issues,state,size=tail(Path(cfg['stdout']),json.loads(row[0]) if row else {},time.time(),running=True)
reasons=[event.facts.get('reason') for event in issues]
print(json.dumps({'read_available':'READ_UNAVAILABLE' not in reasons,'records':len(records),'bytes':size,'reasons':reasons}))
"""
    result = subprocess.run(['/usr/sbin/runuser', '-u', 'goalvision-admin-alerts', '--',
        '/usr/bin/python3', '-I', '-c', program, str(target)], check=True,
        capture_output=True, text=True, timeout=10)
    evidence = json.loads(result.stdout)
    if evidence.get('read_available') is not True:
        raise ValueError('ADMIN_STDOUT_READBACK_FAILED')
    return evidence

def stage(package, meta, targets):
    for name, spec in SPECS.items():
        target = targets[name]
        expected = dict(meta['base_manifests'][name], **{spec['module']:meta['files'][name]})
        if target.exists():
            if (target.is_symlink() or tree(target) != expected or json.loads((target/'manifest.json').read_text()) != expected
                    or any(p.is_symlink() for p in target.rglob('*'))):
                raise ValueError('STAGED_RELEASE_DRIFT')
            continue
        temporary = Path(tempfile.mkdtemp(prefix='.admin-io-', dir=target.parent))
        try:
            shutil.copytree(spec['base'], temporary, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(package/'overlay'/name/spec['module'], temporary/spec['module'])
            atomic(temporary/'manifest.json', (json.dumps(expected, sort_keys=True, indent=2)+'\n').encode())
            atomic(temporary/'io-startup-package.json', (json.dumps(meta, sort_keys=True)+'\n').encode())
            if tree(temporary) != expected:
                raise ValueError('STAGE_HASH_MISMATCH')
            os.chmod(temporary, 0o755)
            os.rename(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

def route(targets, rollback=False):
    previous = {n:s['override'].read_bytes() if s['override'].exists() else None for n,s in SPECS.items()}
    old_dirs = {n:prop(s['service'], 'WorkingDirectory') for n,s in SPECS.items()}
    active = {n:prop(s['timer'], 'ActiveState') == 'active' for n,s in SPECS.items()}
    protected = protected_routes()
    switched = False
    try:
        for spec in SPECS.values():
            control('stop', spec['timer'])
        deadline = time.monotonic()+60
        while any(prop(s['service'], 'ActiveState') in ('active','activating','deactivating','reloading')
                  for s in SPECS.values()):
            if time.monotonic() >= deadline:
                raise TimeoutError('ADMIN_JOB_RUNNING_RETRY_AFTER_COMPLETION')
            time.sleep(.2)
        for name, spec in SPECS.items():
            if (prop(spec['service'], 'WorkingDirectory') != old_dirs[name]
                    or (spec['override'].read_bytes() if spec['override'].exists() else None) != previous[name]):
                raise ValueError('CONCURRENT_ADMIN_ROUTE_CHANGE')
        switched = True
        for name, spec in SPECS.items():
            if rollback:
                spec['override'].unlink()
            else:
                spec['override'].parent.mkdir(parents=True, exist_ok=True)
                atomic(spec['override'], dropin(spec, targets[name]))
        control('daemon-reload')
        for name, spec in SPECS.items():
            verify_route(spec, spec['route_base'] if rollback else targets[name])
        if protected_routes() != protected:
            raise ValueError('PREMATCH_ROUTE_CHANGED')
        if not rollback:
            print('ADMIN_STDOUT_READBACK='+json.dumps(readback(targets['monitor']),sort_keys=True))
        for name, spec in SPECS.items():
            if active[name]:
                control('start', spec['timer'])
                if prop(spec['timer'], 'ActiveState') != 'active':
                    raise ValueError('ADMIN_TIMER_RESTORE_FAILED')
    except BaseException:
        if switched:
            for name, spec in SPECS.items():
                if previous[name] is None:
                    spec['override'].unlink(missing_ok=True)
                else:
                    atomic(spec['override'], previous[name])
            control('daemon-reload')
            if any(prop(s['service'], 'WorkingDirectory') != old_dirs[n] for n,s in SPECS.items()):
                raise RuntimeError('ROLLBACK_ROUTE_VERIFY_FAILED')
        for name, spec in SPECS.items():
            if active[name]:
                control('start', spec['timer'])
        raise

def apply(package, rollback=False):
    meta, targets = validate(package)
    present = [spec['override'].exists() for spec in SPECS.values()]
    if any(present):
        if not all(present):
            raise ValueError('PARTIAL_OVERRIDE_REVIEW_REQUIRED')
        for name, spec in SPECS.items():
            if spec['override'].read_bytes() != dropin(spec, targets[name]):
                raise ValueError('OVERRIDE_DRIFT')
            verify_route(spec, targets[name])
        stage(package, meta, targets)  # Verify already staged immutable files.
        if not rollback:
            print('ADMIN_IO_STARTUP_ALREADY_DEPLOYED')
            return
    else:
        if rollback:
            raise ValueError('NOT_DEPLOYED')
        for spec in SPECS.values():
            verify_route(spec, spec['route_base'])
        stage(package, meta, targets)
    route(targets, rollback)
    print('ADMIN_IO_STARTUP_ROLLBACK=PASS' if rollback else 'ADMIN_IO_STARTUP_DEPLOYED')
    for name, target in targets.items():
        print(name+'_release='+str(SPECS[name]['route_base'] if rollback else target))
    print('PREMATCH routes unchanged. No job retry, manual cycle or test message.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if not args.apply:
        _, targets = validate(package)
        print('PLAN_VALIDATED='+json.dumps({k:str(v) for k,v in targets.items()},sort_keys=True))
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('OPERATOR_INTERRUPTED')
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/goalvision-admin-status-update.lock','a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        apply(package, args.rollback)

if __name__ == '__main__':
    main()
