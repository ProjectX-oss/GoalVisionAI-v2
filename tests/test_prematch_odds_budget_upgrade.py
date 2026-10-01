"""Disposable release routing tests; never call systemd."""
import importlib.util
import json
from pathlib import Path
import pytest


@pytest.fixture
def setup(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / 'operations/odds-budget/update.py'
    spec = importlib.util.spec_from_file_location('odds_update', source)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    base = tmp_path / 'base'
    package = tmp_path / 'package'
    override = tmp_path / 'unit/99-odds.conf'
    override.parent.mkdir()
    monkeypatch.setattr(m, 'BASE', base)
    monkeypatch.setattr(m, 'OVERRIDE', override)
    package.mkdir()
    (package / 'update.py').write_bytes(source.read_bytes())
    for name in m.FILES:
        old, new = base / 'application' / name, package / 'overlay' / name
        old.parent.mkdir(parents=True, exist_ok=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        old.write_text('old = True\n')
        new.write_text('new = True\n')
    (base / 'release.env').write_bytes(m.environment(base))
    meta = dict(source_commit='a'*40, base_manifest=m.tree(base / 'application'),
                files={name:m.sha(package / 'overlay' / name) for name in m.FILES},
                updater_sha256=m.sha(package / 'update.py'))
    (package / 'metadata.json').write_text(json.dumps(meta))
    state = dict(timer='active', service='inactive', fail_reload=False)
    calls = []
    def control(*args):
        calls.append(args)
        if args[0] == 'show':
            unit, key = args[1], args[3]
            if key == 'ActiveState':
                return state['timer' if unit == m.TIMER else 'service']
            if unit == m.SERVICE and key == 'EnvironmentFiles':
                env = (override.read_text().split('EnvironmentFile=')[-1].strip()
                       if override.exists() else str(base / 'release.env'))
                return env + ' (ignore_errors=no)'
            return 'unchanged'
        if args[0] in ('start', 'stop'):
            assert args[1] == m.TIMER
            state['timer'] = 'active' if args[0] == 'start' else 'inactive'
        if args[0] == 'daemon-reload' and state['fail_reload']:
            state['fail_reload'] = False
            raise RuntimeError('Injected reload failure')
        return ''
    monkeypatch.setattr(m, 'control', control)
    return m, package, state, calls


def test_apply_idempotency_and_rollback(setup):
    m, package, state, calls = setup
    before = m.tree(m.BASE / 'application')
    meta, target = m.validate(package)
    assert not calls
    m.apply(package)
    assert m.OVERRIDE.read_bytes() == m.dropin(target)
    assert m.tree(m.BASE / 'application') == before
    assert m.tree(target / 'application') == dict(before, **meta['files'])
    m.apply(package)
    m.apply(package, rollback=True)
    assert not m.OVERRIDE.exists()
    assert state['timer'] == 'active'
    assert all(call != ('start', m.SERVICE) for call in calls)


def test_reload_failure_restores_base_and_timer(setup):
    m, package, state, _ = setup
    state['fail_reload'] = True
    with pytest.raises(RuntimeError, match='Injected'):
        m.apply(package)
    assert not m.OVERRIDE.exists() and state['timer'] == 'active'
    m.apply(package)  # verified staged release can be reused


def test_running_discovery_is_not_killed(setup, monkeypatch):
    m, package, state, calls = setup
    state['service'] = 'activating'
    ticks = iter([0, 61])
    monkeypatch.setattr(m.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError, match='DISCOVERY_RUNNING'):
        m.apply(package)
    assert not m.OVERRIDE.exists() and state['timer'] == 'active'
    assert ('stop', m.SERVICE) not in calls


@pytest.mark.parametrize('where', ['package', 'base'])
def test_tamper_refuses_before_service_controls(setup, where):
    m, package, state, calls = setup
    root = package / 'overlay' if where == 'package' else m.BASE / 'application'
    (root / m.FILES[0]).write_text('tampered')
    with pytest.raises(ValueError):
        m.apply(package)
    assert not calls and state['timer'] == 'active'


def test_disabled_timer_stays_disabled(setup):
    m, package, state, calls = setup
    state['timer'] = 'inactive'
    m.apply(package)
    assert state['timer'] == 'inactive'
    assert ('start', m.TIMER) not in calls
