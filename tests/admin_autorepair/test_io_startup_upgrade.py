"""Synthetic ADMIN release routing; never call systemd, runuser or Codex."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def installation(tmp_path, monkeypatch):
    source = Path(__file__).parents[2]/'operations/admin-autorepair/update_io_startup.py'
    spec = importlib.util.spec_from_file_location('admin_io_update', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    specs = {}
    package = tmp_path/'package'
    package.mkdir()
    (package/'update.py').write_bytes(source.read_bytes())
    for name, original in module.SPECS.items():
        base = tmp_path/name/'base'
        module_path = base/original['module']
        module_path.parent.mkdir(parents=True)
        module_path.write_text('old = True\n')
        (base/'run.py').write_text('pass\n')
        (base/'manifest.json').write_text(json.dumps(module.tree(base)))
        overlay = package/'overlay'/name/original['module']
        overlay.parent.mkdir(parents=True)
        overlay.write_text('new = True\n')
        specs[name] = dict(original, base=base, route_base=base,
                           override=tmp_path/'units'/name/'override.conf')
    monkeypatch.setattr(module, 'SPECS', specs)
    meta = {'source_commit':'a'*40, 'base_manifests':{n:module.tree(s['base']) for n,s in specs.items()},
            'files':{n:module.sha(package/'overlay'/n/s['module']) for n,s in specs.items()},
            'updater_sha256':module.sha(package/'update.py')}
    (package/'metadata.json').write_text(json.dumps(meta))
    states = {s['timer']:'active' for s in specs.values()}
    states.update({s['service']:'inactive' for s in specs.values()})
    flags = {'reload':False, 'readback':False}
    calls, probes = [], []
    def control(*args):
        calls.append(args)
        if args[0] == 'show':
            unit, key = args[1], args[3]
            if key == 'ActiveState':
                return states[unit]
            for s in specs.values():
                if unit == s['service']:
                    target = s['route_base']
                    if s['override'].exists():
                        text = s['override'].read_text()
                        target = Path(next(line.split('=',1)[1] for line in text.splitlines()
                                           if line.startswith('WorkingDirectory=')))
                    if key == 'WorkingDirectory':
                        return str(target)
                    if key == 'ExecStart':
                        return '/usr/bin/python3 -I '+str(target/'run.py')+s['args']
            return 'protected-unchanged'
        if args[0] in ('start','stop'):
            assert args[1] in {s['timer'] for s in specs.values()}
            states[args[1]] = 'active' if args[0] == 'start' else 'inactive'
        if args[0] == 'daemon-reload' and flags['reload']:
            flags['reload'] = False
            raise RuntimeError('INJECTED_RELOAD')
        return ''
    def probe(target):
        probes.append(target)
        if flags['readback']:
            raise ValueError('ADMIN_STDOUT_READBACK_FAILED')
        return {'read_available':True}
    monkeypatch.setattr(module, 'control', control)
    monkeypatch.setattr(module, 'readback', probe)
    return module, package, states, flags, calls, probes


def test_apply_replay_rollback_preserve_sources_and_inactive_timer(installation):
    m, package, states, flags, calls, probes = installation
    states[m.SPECS['worker']['timer']] = 'inactive'
    before = {n:m.tree(s['base']) for n,s in m.SPECS.items()}
    meta, targets = m.validate(package)
    assert not calls
    m.apply(package)
    for n,s in m.SPECS.items():
        assert s['override'].read_bytes() == m.dropin(s, targets[n])
        assert m.tree(s['base']) == before[n]
        assert m.tree(targets[n]) == dict(before[n], **{s['module']:meta['files'][n]})
    m.apply(package)
    assert len(probes) == 1
    m.apply(package, rollback=True)
    assert all(not s['override'].exists() for s in m.SPECS.values())
    assert states[m.SPECS['monitor']['timer']] == 'active'
    assert states[m.SPECS['worker']['timer']] == 'inactive'
    assert all(call != ('start',m.SPECS['worker']['timer']) for call in calls)


def test_active_worker_refuses_without_kill_and_restores_timers(installation, monkeypatch):
    m, package, states, flags, calls, probes = installation
    states[m.SPECS['worker']['service']] = 'activating'
    ticks = iter([0,61])
    monkeypatch.setattr(m.time,'monotonic',lambda:next(ticks))
    with pytest.raises(TimeoutError, match='ADMIN_JOB_RUNNING'):
        m.apply(package)
    assert all(not s['override'].exists() for s in m.SPECS.values())
    assert all(states[s['timer']] == 'active' for s in m.SPECS.values())
    assert not probes


@pytest.mark.parametrize('failure',['reload','readback','second_dropin'])
def test_partial_apply_failure_restores_both_routes(installation, monkeypatch, failure):
    m, package, states, flags, calls, probes = installation
    if failure == 'second_dropin':
        atomic = m.atomic
        def fail(path,data):
            if path == m.SPECS['worker']['override']:
                raise OSError('INJECTED_SECOND_DROPIN')
            atomic(path,data)
        monkeypatch.setattr(m,'atomic',fail)
    else:
        flags[failure] = True
    with pytest.raises((RuntimeError, ValueError, OSError)):
        m.apply(package)
    assert all(not s['override'].exists() for s in m.SPECS.values())
    assert all(states[s['timer']] == 'active' for s in m.SPECS.values())


@pytest.mark.parametrize('where',['overlay','base','updater'])
def test_hash_drift_refused_before_controls(installation, where):
    m, package, states, flags, calls, probes = installation
    s = m.SPECS['worker']
    target = {'overlay':package/'overlay'/'worker'/s['module'],
              'base':s['base']/s['module'],'updater':package/'update.py'}[where]
    target.write_text('tampered\n')
    with pytest.raises(ValueError):
        m.apply(package)
    assert not calls


def test_partial_override_refuses_without_timer_changes(installation):
    m, package, states, flags, calls, probes = installation
    meta, targets = m.validate(package)
    s = m.SPECS['monitor']
    s['override'].parent.mkdir(parents=True)
    s['override'].write_bytes(m.dropin(s,targets['monitor']))
    with pytest.raises(ValueError, match='PARTIAL_OVERRIDE'):
        m.apply(package)
    assert not any(c[0] in ('start','stop') for c in calls)


def test_stage_symlink_refused(installation):
    m, package, states, flags, calls, probes = installation
    _, targets = m.validate(package)
    targets['monitor'].symlink_to(m.SPECS['monitor']['base'],target_is_directory=True)
    with pytest.raises(ValueError, match='STAGED_RELEASE_DRIFT'):
        m.apply(package)
    assert not any(c[0] in ('start','stop') for c in calls)


def test_worker_base_alias_drift_refused_before_controls(installation):
    m, package, states, flags, calls, probes = installation
    m.SPECS['worker']['route_base'] = m.SPECS['monitor']['base']
    with pytest.raises(ValueError, match='BASE_ROUTE_ALIAS_DRIFT'):
        m.apply(package)
    assert not calls
