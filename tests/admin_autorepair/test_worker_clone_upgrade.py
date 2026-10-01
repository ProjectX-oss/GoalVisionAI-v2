"""Worker-only upgrade reuses the ADMIN transaction without monitor controls."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def worker_upgrade(tmp_path, monkeypatch):
    root = Path(__file__).parents[2]/'operations/admin-autorepair'
    spec = importlib.util.spec_from_file_location('clone_upgrade', root/'update_worker_clone.py')
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    package = tmp_path/'package'
    package.mkdir()
    (package/'update.py').write_bytes((root/'update_worker_clone.py').read_bytes())
    (package/'update_io_startup.py').write_bytes((root/'update_io_startup.py').read_bytes())
    sha = lambda p: wrapper.hashlib.sha256(p.read_bytes()).hexdigest()
    meta = {'source_commit':'b'*40, 'updater_sha256':sha(package/'update.py'),
            'helper_sha256':sha(package/'update_io_startup.py')}
    (package/'metadata.json').write_text(json.dumps(meta))
    base = tmp_path/'worker'/'base'
    override = tmp_path/'units'/'clone.conf'
    monkeypatch.setattr(wrapper, 'BASE', base)
    monkeypatch.setattr(wrapper, 'OVERRIDE', override)
    module = wrapper.engine(package)
    worker = module.SPECS['worker']
    source = base/worker['module']
    source.parent.mkdir(parents=True)
    source.write_text('old = True\n')
    (base/'run.py').write_text('pass\n')
    (base/'manifest.json').write_text(json.dumps(module.tree(base)))
    overlay = package/'overlay'/'worker'/worker['module']
    overlay.parent.mkdir(parents=True)
    overlay.write_text('new = True\n')
    meta.update(base_manifests={'worker':module.tree(base)}, files={'worker':sha(overlay)})
    (package/'metadata.json').write_text(json.dumps(meta))
    states = {worker['timer']:'active', worker['service']:'inactive'}
    calls, flags = [], {'reload_failure':False, 'protected_drift':False}
    protected_keys = {'WorkingDirectory':'/protected', 'EnvironmentFiles':'/protected/config',
                      'DropInPaths':'/protected/dropin'}
    def control(*args):
        calls.append(args)
        if args[0] == 'show':
            unit, key = args[1], args[3]
            if unit in module.PROTECTED:
                if flags['protected_drift'] and override.exists():
                    return 'DRIFT'
                return protected_keys[key]
            assert unit in states
            if key == 'ActiveState':
                return states[unit]
            target = base
            if override.exists():
                target = Path(next(x.split('=',1)[1] for x in override.read_text().splitlines()
                                   if x.startswith('WorkingDirectory=')))
            return str(target) if key == 'WorkingDirectory' else '/usr/bin/python3 -I '+str(target/'run.py')
        if args[0] in ('stop','start'):
            assert args[1] == worker['timer']
            states[args[1]] = 'active' if args[0] == 'start' else 'inactive'
        elif args[0] == 'daemon-reload' and flags['reload_failure']:
            flags['reload_failure'] = False
            raise RuntimeError('INJECTED_RELOAD')
        return ''
    monkeypatch.setattr(module, 'control', control)
    def forbidden(*args):
        pytest.fail('Worker-only deployment must not probe or invoke any job or monitor')
    monkeypatch.setattr(module, 'readback', forbidden)
    return wrapper, module, package, states, calls, flags


def test_worker_only_apply_idempotency_rollback(worker_upgrade):
    wrapper, m, package, states, calls, flags = worker_upgrade
    assert set(m.SPECS) == {'worker'}
    assert 'goalvision-admin-alerts.service' in m.PROTECTED
    old = m.tree(wrapper.BASE)
    _, targets = m.validate(package)
    assert targets['worker'].name == 'admin-worker-clone-bbbbbbb-20261001'
    m.apply(package)
    assert wrapper.OVERRIDE.read_bytes() == m.dropin(m.SPECS['worker'], targets['worker'])
    assert m.tree(wrapper.BASE) == old
    m.apply(package)
    m.apply(package, rollback=True)
    assert not wrapper.OVERRIDE.exists()
    assert states[m.SPECS['worker']['timer']] == 'active'
    assert all(c[1] == m.SPECS['worker']['timer'] for c in calls if c[0] in ('start','stop'))


@pytest.mark.parametrize('reason',['reload_failure','protected_drift'])
def test_worker_upgrade_failure_restores_route_and_timer(worker_upgrade, reason):
    wrapper, m, package, states, calls, flags = worker_upgrade
    flags[reason] = True
    with pytest.raises((RuntimeError, ValueError)):
        m.apply(package)
    assert not wrapper.OVERRIDE.exists()
    assert states[m.SPECS['worker']['timer']] == 'active'


def test_active_worker_is_not_killed(worker_upgrade, monkeypatch):
    wrapper, m, package, states, calls, flags = worker_upgrade
    states[m.SPECS['worker']['service']] = 'activating'
    ticks = iter([0,61])
    monkeypatch.setattr(m.time,'monotonic',lambda:next(ticks))
    with pytest.raises(TimeoutError,match='ADMIN_JOB_RUNNING'):
        m.apply(package)
    assert not wrapper.OVERRIDE.exists()
    assert states[m.SPECS['worker']['timer']] == 'active'


def test_inactive_worker_timer_stays_inactive(worker_upgrade):
    wrapper, m, package, states, calls, flags = worker_upgrade
    states[m.SPECS['worker']['timer']] = 'inactive'
    m.apply(package)
    assert states[m.SPECS['worker']['timer']] == 'inactive'
    assert not any(c[0] == 'start' for c in calls)


@pytest.mark.parametrize('name',['update.py','update_io_startup.py'])
def test_package_code_hash_checked_before_import(worker_upgrade, name):
    wrapper, m, package, states, calls, flags = worker_upgrade
    (package/name).write_text('raise AssertionError("must not execute")\n')
    with pytest.raises(ValueError,match='PACKAGE_CODE_HASH'):
        wrapper.engine(package)
    assert not calls
