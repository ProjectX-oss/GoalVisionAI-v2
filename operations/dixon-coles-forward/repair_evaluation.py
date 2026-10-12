"""Operator-only one-file successor; reuse the reviewed DC install primitives."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

HELPER_SHA = 'de1dcaacd2a477d3baf6cf4d3d6b0e175b2bbb8d664bb643e61a80ea54c5b608'
helper = Path(__file__).with_name('update.py')
if hashlib.sha256(helper.read_bytes()).hexdigest() != HELPER_SHA:
    raise ValueError('REVIEWED_HELPER_HASH_MISMATCH')
spec = importlib.util.spec_from_file_location('_reviewed_dc_installer', helper)
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
BASE = Path('/opt/goalvision-dixon-coles-forward-ebd0924-20261004')
TARGET = Path('/opt/goalvision-dixon-coles-forward-verify-dd2e1c1-20261012')
SYSTEM = Path('/etc/systemd/system')
SERVICE = 'goalvision-dixon-coles-forward.service'
TIMER = SERVICE.replace('.service', '.timer')
PATCH = 'app/dixon_coles_forward/service.py'
PATCH_BASE_SHA = '30c079aebe047c37f12cdf6090ecb802d983de34842138949959bcc9ace62ce2'
UNITS = (SERVICE, 'goalvision-dixon-coles-research.service', 'goalvision-adaptive-learning-observer.service',
    'goalvision-adaptive-learning.service', 'goalvision-admin-alerts.service',
    'goalvision-lab-v2-discover.service', 'goalvision-lab-combo-settle.service',
    'goalvision-lab-live-evening.service', 'goalvision-lab-weekly-stats.service')
JOURNALS = Path('/var/lib/goalvision-operator-recovery')

def manifest(root):
    h.safe(root)
    result = {}
    for p in sorted(root.rglob('*')):
        h.safe(p)
        if p.is_file() and '__pycache__' not in p.parts:
            result[str(p.relative_to(root))] = h.sha(p)
    return result

def configs():
    result = {}
    for p in SYSTEM.glob('goalvision*'):
        h.safe(p)
        if p.is_file(): result[str(p)] = h.sha(p)
        elif p.is_dir():
            for f in p.rglob('*'):
                h.safe(f)
                if f.is_file(): result[str(f)] = h.sha(f)
    return result

def routes():
    fields = ('Id','WorkingDirectory','EnvironmentFiles','DropInPaths','FragmentPath',
              'User','Group','ExecStart','TimeoutStartUSec','CPUQuotaPerSecUSec','MemoryMax')
    raw = h.control('show', *UNITS, '--property='+','.join(fields))
    result = {}
    for block in raw.strip().split('\n\n'):
        v = dict(s.split('=',1) for s in block.splitlines() if '=' in s)
        identity = v.pop('Id')
        v['ExecStart'] = v['ExecStart'].split(' ; ignore_errors=')[0]
        result[identity] = v
    if set(result) != set(UNITS): raise ValueError('LOADED_UNIT_SET_MISMATCH')
    return result

def override():
    return SYSTEM/(SERVICE+'.d')/'90-evaluation-verification.conf'

def dropin():
    return ('[Service]\nWorkingDirectory='+str(TARGET/'application')+'\n').encode()

def expected_manifest(meta):
    return {**meta['base_manifest'], PATCH: meta['patch_sha256']}

def verify_configuration(meta, state):
    expected_files = dict(meta['configuration_files'])
    expected_routes = json.loads(json.dumps(meta['routes']))
    if state == 'ENABLED':
        expected_files[str(override())] = hashlib.sha256(dropin()).hexdigest()
        expected_routes[SERVICE]['WorkingDirectory'] = str(TARGET/'application')
        expected_routes[SERVICE]['DropInPaths'] = str(override())
    if configs() != expected_files or routes() != expected_routes:
        raise ValueError('CONFIGURATION_OR_ROUTE_DRIFT')
    if h.prop(SERVICE, 'Environment') != meta['forward_environment']:
        raise ValueError('FORWARD_ENVIRONMENT_DRIFT')
    if h.prop(TIMER, 'UnitFileState') != meta['timer_unit_file_state']:
        raise ValueError('TIMER_ENABLEMENT_DRIFT')

def validate(package):
    h.safe(package)
    meta = json.loads((package/'metadata.json').read_text())
    if meta['base'] != str(BASE) or meta['target'] != str(TARGET) or meta['patch'] != PATCH:
        raise ValueError('PACKAGE_SCOPE_MISMATCH')
    if set(meta['package_files']) != {'repair_evaluation.py', 'update.py', 'service.py'}:
        raise ValueError('PACKAGE_FILE_SET_MISMATCH')
    if meta['patch_sha256'] != meta['package_files']['service.py']:
        raise ValueError('PATCH_HASH_MISMATCH')
    if meta['base_manifest'].get(PATCH) != PATCH_BASE_SHA:
        raise ValueError('BASE_PATCH_HASH_MISMATCH')
    for name, expected in meta['package_files'].items():
        path = package/name; h.safe(path)
        if path.parent != package or h.sha(path) != expected:
            raise ValueError('PACKAGE_FILE_HASH_MISMATCH')
    if h.sha(BASE/'application'/PATCH) != PATCH_BASE_SHA or manifest(BASE/'application') != meta['base_manifest']:
        raise ValueError('BASE_APPLICATION_DRIFT')
    h.safe(override())
    state = 'ENABLED' if override().exists() else 'BASE'
    if state == 'ENABLED':
        if override().read_bytes() != dropin() or manifest(TARGET/'application') != expected_manifest(meta):
            raise ValueError('INSTALLED_REPAIR_DRIFT')
    verify_configuration(meta, state); h.disabled_admin()
    return meta, state

def stage(package, meta):
    h.safe(TARGET)
    if TARGET.exists():
        if manifest(TARGET/'application') != expected_manifest(meta): raise ValueError('EXISTING_TARGET_DRIFT')
        return
    with tempfile.TemporaryDirectory(prefix='.goalvision-dc-verify-', dir=TARGET.parent) as tmp:
        destination = Path(tmp)/'release'; destination.mkdir()
        shutil.copytree(BASE/'application', destination/'application', ignore=shutil.ignore_patterns('__pycache__'))
        patch = destination/'application'/PATCH; patch.chmod(0o644)
        shutil.copyfile(package/'service.py', patch)
        if manifest(destination/'application') != expected_manifest(meta): raise ValueError('ASSEMBLED_MANIFEST_MISMATCH')
        for p in destination.rglob('*'): p.chmod(0o755 if p.is_dir() else 0o444)
        destination.chmod(0o755); os.replace(destination, TARGET)

def atomic(path, data):
    h.safe(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.reviewed-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.chmod(name,0o644); os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def route(meta):
    before = h.prop(TIMER,'ActiveState')
    if before not in {'active','inactive'}: raise ValueError('TIMER_TRANSITION_IN_PROGRESS')
    wrote = False; stopped = False
    journal = JOURNALS/('dc-forward-verify-20261012-'+str(time.time_ns())+'.json')
    state = {'timer_before':before,'route_written':False,'automatic_rollback':False}
    atomic(journal,(json.dumps(state)+'\n').encode())
    try:
        h.control('stop',TIMER); stopped = True
        deadline = time.monotonic()+75
        while h.prop(SERVICE,'MainPID') != '0' or h.prop(SERVICE,'ActiveState') not in {'inactive','failed'}:
            if time.monotonic() >= deadline: raise RuntimeError('NATURAL_DRAIN_TIMEOUT')
            time.sleep(.5)
        verify_configuration(meta,'BASE'); h.disabled_admin()
        # Mark the mutation boundary before replacing the route; failures thereafter pause.
        wrote = True; state['route_written'] = True
        atomic(override(),dropin()); h.control('daemon-reload')
        verify_configuration(meta,'ENABLED')
        if before == 'active': h.control('start',TIMER)
        if h.prop(TIMER,'ActiveState') != before: raise ValueError('TIMER_ACTIVITY_NOT_RESTORED')
        state['status']='COMPLETED'
        atomic(journal,(json.dumps(state)+'\n').encode())
    except BaseException:
        state['status']='OPERATOR_REVIEW_REQUIRED' if wrote else 'NO_ROUTE_WRITTEN'
        if wrote:
            h.control('stop',TIMER)
        elif stopped and before == 'active':
            h.control('start',TIMER)
        atomic(journal,(json.dumps(state)+'\n').encode())
        if wrote: raise RuntimeError('PARTIAL_INSTALL_NO_AUTOMATIC_ROLLBACK; journal='+str(journal)) from None
        raise

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args(argv)
    if not a.apply:
        _, state=validate(a.package);print('DC_FORWARD_REPAIR_PLAN_VALIDATED; mode='+state);return
    if os.geteuid()!=0: raise PermissionError('OPERATOR_SUDO_REQUIRED')
    h.safe(h.INSTALL_LOCK)
    with os.fdopen(os.open(h.INSTALL_LOCK, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600), 'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        meta,state=validate(a.package)
        if state=='BASE':
            print('[1/2] Verifying and staging the exact one-file research successor...',flush=True);stage(a.package,meta)
            print('[2/2] Pausing only the DC forward timer and draining naturally...',flush=True);route(meta)
        validate(a.package)
    print('DC_FORWARD_VERIFICATION_REPAIR_DEPLOYED')
    print('Research numerical checks retained; duplicate verification removed.')
    print('Existing timer state/schedule and 25% CPU / 50s limits retained.')
    print('PREMATCH, LIVE, ADMIN, Official, champion and databases unchanged; no manual cycle/API/send.')

if __name__=='__main__': main()
