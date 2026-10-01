"""File-backed narrow upgrade, rollback and failure recovery; systemd is fake."""
import importlib.util
import json
from pathlib import Path
import pytest


@pytest.fixture(params=['update_status_language.py','update_delivery_cleanup.py'])
def upgrade(tmp_path, monkeypatch, request):
    spec = importlib.util.spec_from_file_location('status_upgrade',
        'operations/admin-autorepair/'+request.param)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = tmp_path/'releases'/'base'
    (base/'app/admin_alerts').mkdir(parents=True)
    (base/module.MODULE).write_text('OLD = 1\n')
    (base/'run.py').write_text('UNCHANGED = 1\n')
    (base/'manifest.json').write_text(json.dumps({
        str(p.relative_to(base)): module.sha(p) for p in base.rglob('*.py')}))
    override = tmp_path/'40-autorepair.conf'
    override.write_text('[Service]\nWorkingDirectory='+str(base)+
                       '\nExecStart='+str(base/'run.py')+'\n')
    package = tmp_path/'package'
    package.mkdir()
    (package/module.MODULE.name).write_text('NEW = 2\n')
    (package/'update.py').write_text('# fixture updater\n')
    (package/'metadata.json').write_text(json.dumps({
        'source_commit':'a'*40, 'module_sha256':module.sha(package/module.MODULE.name),
        'updater_sha256':module.sha(package/'update.py')}))
    monkeypatch.setattr(module, 'BASE', base)
    monkeypatch.setattr(module, 'OVERRIDE', override)
    monkeypatch.setattr(module, 'OLD_MODULE_SHA', module.sha(base/module.MODULE))
    monkeypatch.setattr(module, 'OLD_ROUTE_SHA', module.sha(override))
    state = {'active':True, 'route':str(base), 'fail_reload':False, 'busy':False}
    calls = []
    def control(*args):
        calls.append(args)
        if args == ('stop', module.TIMER):
            state['active'] = False
        elif args == ('start', module.TIMER):
            state['active'] = True
        elif args == ('daemon-reload',):
            if state['fail_reload']:
                state['fail_reload'] = False
                raise RuntimeError('INJECTED_RELOAD_FAILURE')
            state['route'] = next(line.split('=',1)[1]
                for line in override.read_text().splitlines() if line.startswith('WorkingDirectory='))
        elif args[:2] == ('show', module.TIMER):
            return 'active' if state['active'] else 'inactive'
        elif args[:2] == ('show', module.SERVICE):
            if args[3] == 'WorkingDirectory':
                return state['route']
            if args[3] == 'ExecStart':
                return state['route']+'/run.py'
            return 'active' if state['busy'] else 'inactive'
        else:
            raise AssertionError('UNEXPECTED_SYSTEMD_OPERATION:'+repr(args))
        return ''
    monkeypatch.setattr(module, 'control', control)
    return module, package, state, calls


def test_upgrade_changes_only_notification_module_and_rollback(upgrade):
    module, package, state, calls = upgrade
    original = module.OVERRIDE.read_bytes()
    base_before = {str(p.relative_to(module.BASE)):p.read_bytes()
                   for p in module.BASE.rglob('*') if p.is_file()}
    module.apply(package)
    release = Path(state['route'])
    assert release != module.BASE and state['active']
    assert (release/module.MODULE).read_text() == 'NEW = 2\n'
    assert (release/'run.py').read_text() == 'UNCHANGED = 1\n'
    assert base_before == {str(p.relative_to(module.BASE)):p.read_bytes()
                          for p in module.BASE.rglob('*') if p.is_file()}
    module.apply(package, rollback=True)
    assert module.OVERRIDE.read_bytes() == original
    assert state['route'] == str(module.BASE) and state['active']
    assert all(c[0] == 'show' or c == ('daemon-reload',) or
               c in [('start',module.TIMER),('stop',module.TIMER)] for c in calls)


def test_route_failure_restores_previous_route_and_timer(upgrade):
    module, package, state, calls = upgrade
    original = module.OVERRIDE.read_bytes()
    state['fail_reload'] = True
    with pytest.raises(RuntimeError, match='INJECTED'):
        module.apply(package)
    assert module.OVERRIDE.read_bytes() == original
    assert state['route'] == str(module.BASE) and state['active']


def test_package_drift_refused_before_service_control(upgrade):
    module, package, state, calls = upgrade
    (package/module.MODULE.name).write_text('TAMPERED = 1\n')
    with pytest.raises(ValueError, match='PACKAGE_HASH'):
        module.apply(package)
    assert calls == []


def test_busy_admin_timeout_restores_timer_without_route_change(upgrade, monkeypatch):
    module, package, state, calls = upgrade
    original = module.OVERRIDE.read_bytes()
    state['busy'] = True
    ticks = iter([0, 61])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError, match='ADMIN_DRAIN'):
        module.apply(package)
    assert module.OVERRIDE.read_bytes() == original
    assert state['active'] and ('stop',module.SERVICE) not in calls


def test_initially_inactive_timer_stays_inactive(upgrade):
    module, package, state, calls = upgrade
    state['active'] = False
    module.apply(package)
    assert not state['active'] and ('start',module.TIMER) not in calls
