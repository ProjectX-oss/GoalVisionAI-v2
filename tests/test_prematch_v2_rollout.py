"""Deterministic disposable rollout rehearsals; every administrative call is fake."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'docs/operations/install_prematch_v2.py'


@pytest.fixture
def rollout(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('reviewed_installer', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    etc = tmp_path / 'systemd'
    etc.mkdir()
    monkeypatch.setattr(module, 'SYSTEMD', etc)
    runtime = tmp_path / 'runtime-systemd'
    runtime.mkdir()
    monkeypatch.setattr(module, 'RUNTIME_SYSTEMD', runtime)
    monkeypatch.setattr(module, 'INSTALLER_LOCK', tmp_path / 'installer.lock')
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    release = tmp_path / 'release'
    reviewed = release / 'docs/operations/install_prematch_v2.py'
    reviewed.parent.mkdir(parents=True)
    reviewed.write_bytes(SOURCE.read_bytes())
    environment = tmp_path / 'release.env'
    environment.write_text('PYTHONPATH=' + str(release) + '\n')
    services = list(module.SERVICES)
    timers = [s.removesuffix('.service') + '.timer' for s in services]
    fingerprints = {}
    for unit in services + timers:
        path = etc / unit
        path.write_text('synthetic original ' + unit)
        fingerprints[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    ledger = tmp_path / 'var/lab_combo/ledger.db'
    ledger.parent.mkdir(parents=True)
    with sqlite3.connect(ledger) as connection:
        connection.execute('CREATE TABLE evidence (kind TEXT, identity TEXT, document TEXT, PRIMARY KEY(kind, identity))')
    value = {
        'release': str(release), 'commit': 'synthetic-commit', 'regression_status': 'PASSED',
        'installed_fingerprints': fingerprints, 'services': services, 'discovery_service': services[0],
        'release_environment_file': str(environment),
        'release_environment_sha256': hashlib.sha256(environment.read_bytes()).hexdigest(),
        'ledger': str(ledger),
        'discovery_command': ['/unchanged/python', '-P', '-m', 'app.lab_v2_shadow', 'controlled-cycle',
                              '--send', '--max-calls', '400', '--settlement-reserve', '100'],
        'observation_arguments': ['--football-context-root', str(tmp_path / 'evidence'),
                                  '--football-context-registry', str(tmp_path / 'registry.sqlite')],
    }
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(value))
    calls = []
    timer_states = dict(zip(timers, ['active', 'inactive', 'active', 'failed']))
    original_timers = timer_states.copy()
    loaded_dropins = {unit: '' for unit in services + timers}

    def run(*args):
        calls.append(args)
        if args[0] == 'git':
            return 'synthetic-commit' if args[-1] == 'HEAD' else ''
        if args[:2] == ('systemctl', 'show'):
            if args[4] == 'ActiveState':
                return timer_states.get(args[2], 'inactive')
            if args[4] == 'LoadState':
                return 'loaded'
            if args[4] == 'WorkingDirectory':
                return str(tmp_path)
            if args[4] == 'FragmentPath':
                return str(etc / args[2])
            if args[4] == 'DropInPaths':
                return loaded_dropins[args[2]]
        if args[:2] in [('systemctl', 'stop'), ('systemctl', 'start')]:
            assert all(unit in timers for unit in args[2:]), 'Never stop/start a service or unrelated timer'
            for unit in args[2:]:
                timer_states[unit] = 'active' if args[1] == 'start' else 'inactive'
        if args == ('systemctl', 'daemon-reload'):
            for service in services:
                path = etc / (service + '.d') / module.DROPIN
                gate = runtime / (service + '.d') / module.START_GATE
                loaded_dropins[service] = ' '.join(str(p) for p in (path, gate) if p.exists())
        return ''

    def invoke(action='apply'):
        monkeypatch.setattr(sys, 'argv', ['installer', str(manifest), action])
        module.main()

    def files():
        return {service: (etc / (service + '.d') / module.DROPIN).read_bytes() for service in services}

    def append(kind, identity, document):
        with sqlite3.connect(ledger) as connection:
            connection.execute('INSERT INTO evidence VALUES (?,?,?)', (kind, identity, json.dumps(document)))

    monkeypatch.setattr(module, 'run', run)
    return SimpleNamespace(module=module, manifest=manifest, value=value, services=services, etc=etc,
                           calls=calls, run=run, invoke=invoke, files=files, append=append, ledger=ledger,
                           timer_states=timer_states, original_timers=original_timers, loaded_dropins=loaded_dropins)


def test_install_waits_at_boundary_and_only_restores_existing_timers(rollout, monkeypatch):
    r = rollout
    states = iter(['activating', 'active', 'deactivating', 'inactive', 'inactive'])

    def draining(*args):
        if args[:3] == ('systemctl', 'show', r.services[0]) and args[4] == 'ActiveState':
            return next(states)
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', draining)
    r.invoke()
    content = r.files()[r.services[0]].decode()
    assert '--max-calls 400 --settlement-reserve 100' in content
    assert '--football-context-root' in content and '--label-v2-selections' in content
    assert r.timer_states == r.original_timers
    assert not any(call[:2] == ('systemctl', 'restart') for call in r.calls)
    assert ('systemctl', 'daemon-reload') in r.calls


@pytest.mark.parametrize('actions', [
    ['disable-new-picks', 'disable-data-labels'],
    ['disable-data-labels', 'disable-new-picks'],
    ['disable-new-picks'] * 3 + ['disable-data-labels'] * 3,
    ['disable-data-labels'] * 3 + ['disable-new-picks'] * 3,
])
def test_disable_actions_are_monotonic_and_idempotent(rollout, actions):
    r = rollout
    r.invoke()
    original = r.files()
    prior = (True, True, True)
    for action in actions:
        r.calls.clear()
        r.invoke(action)
        content = r.files()[r.services[0]]
        current = r.module.discovery_state(r.value, content)
        assert all(not after or before for before, after in zip(prior, current))
        expected = (False, prior[1], prior[2]) if action == 'disable-new-picks' else (prior[0], False, False)
        assert current == expected
        assert all(r.files()[service] == original[service] for service in r.services[1:])
        assert not any(service in call for call in r.calls for service in r.services[1:])
        assert r.timer_states == r.original_timers
        prior = current
    assert prior == (False, False, False)


@pytest.mark.parametrize('action', ['disable-data-labels', 'disable-new-picks', 'rollback'])
def test_unexpected_owned_command_drift_refused(rollout, action):
    r = rollout
    r.invoke()
    path = r.etc / (r.services[0] + '.d') / r.module.DROPIN
    path.write_bytes(path.read_bytes().replace(b'--max-calls 400', b'--max-calls 401'))
    before = r.files()
    r.calls.clear()
    with pytest.raises(SystemExit, match='configuration drift'):
        r.invoke(action)
    assert r.files() == before
    assert not any(call[:2] == ('systemctl', 'stop') for call in r.calls)


def test_unknown_effective_dropin_refused(rollout):
    r = rollout
    r.invoke()
    before = r.files()
    r.loaded_dropins[r.services[0]] += ' /run/systemd/system/unreviewed.conf'
    with pytest.raises(SystemExit, match='effective service drop-ins'):
        r.invoke('disable-new-picks')
    assert r.files() == before


def test_receipt_appears_during_drain_and_rollback_refused(rollout, monkeypatch):
    r = rollout
    r.invoke()
    r.append('single_prediction', 'p1', {'selection_origin': {'label': 'synthetic'}})
    before = r.files()
    drained = False

    def drain(*args):
        nonlocal drained
        if args[:3] == ('systemctl', 'show', r.services[0]) and args[4] == 'ActiveState' and not drained:
            assert not any(state == 'active' for state in r.timer_states.values())
            r.append('receipt', 'single_prediction:p1', {'sent': True, 'status': 'SENT'})
            drained = True
            return 'active'
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', drain)
    with pytest.raises(SystemExit, match='Keep compatible settlement'):
        r.invoke('rollback')
    assert drained and r.files() == before
    assert r.timer_states == r.original_timers
    with sqlite3.connect(r.ledger) as connection:
        assert connection.execute('SELECT count(*) FROM evidence').fetchone()[0] == 2


@pytest.mark.parametrize('kind,document', [
    ('claim', {'prediction_id': 'p1'}),
    ('delivery_unknown', {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'}),
    ('receipt', {'sent': True, 'status': 'SENT'}),
    ('receipt', {'sent': False}),
    ('economic_claim', {'publication_identity': 'single_prediction:p1'}),
])
def test_potentially_delivered_labelled_send_refuses_rollback(rollout, kind, document):
    r = rollout
    r.invoke()
    r.append('single_prediction', 'p1', {'selection_origin': {'label': 'synthetic'}})
    r.append(kind, 'SINGLE:1:HOME' if kind == 'economic_claim' else 'single_prediction:p1', document)
    before, evidence = r.files(), r.ledger.read_bytes()
    with pytest.raises(SystemExit, match='Keep compatible settlement'):
        r.invoke('rollback')
    assert r.files() == before and r.ledger.read_bytes() == evidence
    assert r.timer_states == r.original_timers


def test_drained_rollback_without_incompatible_publication_preserves_evidence(rollout):
    r = rollout
    r.invoke()
    r.append('single_prediction', 'labelled-unsent', {'selection_origin': {'label': 'synthetic'}})
    r.append('single_prediction', 'legacy', {'prediction_id': 'legacy'})
    r.append('receipt', 'single_prediction:legacy', {'sent': True})
    evidence = r.ledger.read_bytes()
    unrelated = r.etc / 'unrelated.service'
    unrelated.write_text('unrelated configuration')
    r.invoke('rollback')
    assert not any((r.etc / (s + '.d') / r.module.DROPIN).exists() for s in r.services)
    assert r.ledger.read_bytes() == evidence
    assert unrelated.read_text() == 'unrelated configuration'
    assert r.timer_states == r.original_timers


@pytest.mark.parametrize('failure', ['database', 'busy', 'verify', 'reload', 'restarted', 'drain_timeout'])
def test_guard_or_install_failure_restores_configuration_and_timers(rollout, monkeypatch, failure):
    r = rollout
    r.invoke()
    before = r.files()
    blocker = None
    if failure == 'database':
        r.ledger.write_bytes(b'invalid sqlite')
    elif failure == 'busy':
        blocker = sqlite3.connect(r.ledger)
        blocker.execute('BEGIN IMMEDIATE')
        connect = r.module.sqlite3.connect
        monkeypatch.setattr(r.module.sqlite3, 'connect', lambda *a, **kw: connect(*a, **{**kw, 'timeout': 0}))
    checks = 0
    failed = False

    def fail(*args):
        nonlocal checks, failed
        if args[:3] == ('systemctl', 'show', r.services[0]) and args[4] == 'ActiveState':
            checks += 1
            if failure == 'drain_timeout' or (failure == 'restarted' and checks == 2):
                return 'active'
        if not failed and ((failure == 'verify' and args[0] == 'systemd-analyze')
                           or (failure == 'reload' and args == ('systemctl', 'daemon-reload'))):
            failed = True
            raise RuntimeError('synthetic verification/reload failure')
        return r.run(*args)

    if failure == 'drain_timeout':
        times = iter([0, 1801])
        monkeypatch.setattr(r.module.time, 'monotonic', lambda: next(times))
    monkeypatch.setattr(r.module, 'run', fail)
    try:
        with pytest.raises((RuntimeError, sqlite3.DatabaseError)):
            r.invoke('rollback')
        assert r.files() == before
        assert r.timer_states == r.original_timers
    finally:
        if blocker:
            blocker.close()


def test_new_publisher_cannot_claim_during_rollback_or_reload(rollout, monkeypatch):
    r = rollout
    r.invoke()
    r.append('single_prediction', 'p1', {'selection_origin': {'label': 'synthetic'}})
    checked = []

    def competing_publisher(*args):
        if args[0] == 'systemd-analyze' or (checked and args == ('systemctl', 'daemon-reload')):
            with sqlite3.connect(r.ledger, timeout=0) as connection:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    connection.execute('INSERT INTO evidence VALUES (?,?,?)', ('claim', 'single_prediction:p1', '{}'))
            checked.append(args[0])
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', competing_publisher)
    r.invoke('rollback')
    assert checked == ['systemd-analyze', 'systemctl', 'systemctl']


def test_concurrent_installer_process_cannot_interleave(rollout, monkeypatch):
    r = rollout
    competed = False

    def contender(*args):
        nonlocal competed
        if args[:2] == ('systemctl', 'stop') and not competed:
            competed = True
            # Separate process, different manifest/package identity, same fixed host lock.
            script = '''import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('installer', sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.INSTALLER_LOCK = pathlib.Path(sys.argv[2])
with m.installer_lock():
    raise AssertionError('Competing installer acquired the lock')
'''
            result = subprocess.run([sys.executable, '-c', script, str(SOURCE), str(r.module.INSTALLER_LOCK)],
                                    text=True, capture_output=True, timeout=10)
            assert result.returncode == 1
            assert 'Another PREMATCH installer operation is running.' in result.stderr
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', contender)
    r.invoke()
    assert competed
    # The persistent lock inode can be acquired again after a complete operation.
    r.invoke('disable-new-picks')


def test_apply_verification_failure_restores_absent_configuration(rollout, monkeypatch):
    r = rollout

    def fail(*args):
        if args[0] == 'systemd-analyze':
            raise RuntimeError('synthetic verify rejection')
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', fail)
    with pytest.raises(RuntimeError):
        r.invoke()
    assert not any((r.etc / (s + '.d') / r.module.DROPIN).exists() for s in r.services)
    assert r.timer_states == r.original_timers


def test_no_privilege_means_no_service_change(rollout, monkeypatch):
    r = rollout
    monkeypatch.setattr(r.module.os, 'geteuid', lambda: 1001)
    with pytest.raises(SystemExit, match='Root is required'):
        r.invoke()
    assert r.calls == []


@pytest.mark.parametrize('drift', ['environment', 'installer', 'base_unit', 'missing_fingerprints', 'command'])
def test_release_and_manifest_drift_fail_closed(rollout, drift):
    r = rollout
    if drift == 'environment':
        Path(r.value['release_environment_file']).write_text('PYTHONPATH=/unreviewed\n')
    elif drift == 'installer':
        (Path(r.value['release']) / 'docs/operations/install_prematch_v2.py').write_text('unreviewed')
    elif drift == 'base_unit':
        (r.etc / r.services[0]).write_text('unreviewed')
    elif drift == 'missing_fingerprints':
        r.value['installed_fingerprints'] = {}
    else:
        r.value['discovery_command'].append('--send')
    r.manifest.write_text(json.dumps(r.value))
    with pytest.raises(SystemExit):
        r.invoke()
    assert not any(call[:2] == ('systemctl', 'stop') for call in r.calls)


@pytest.mark.parametrize('fault', ['not_loaded', 'changed', 'existing'])
def test_start_gate_failure_refuses_rollback_and_restores_timers(rollout, monkeypatch, fault):
    r = rollout
    r.invoke()
    before = r.files()
    gate = r.module.RUNTIME_SYSTEMD / (r.services[0] + '.d') / r.module.START_GATE
    if fault == 'existing':
        gate.parent.mkdir()
        gate.write_text('operator-owned gate')

    def gate_fault(*args):
        result = r.run(*args)
        if args == ('systemctl', 'daemon-reload') and gate.exists():
            if fault == 'not_loaded':
                r.loaded_dropins[r.services[0]] = str(r.etc / (r.services[0] + '.d') / r.module.DROPIN)
            elif fault == 'changed':
                gate.write_text('changed gate')
        return result

    monkeypatch.setattr(r.module, 'run', gate_fault)
    with pytest.raises(SystemExit):
        r.invoke('rollback')
    assert r.files() == before
    assert r.timer_states == r.original_timers
    if fault == 'existing':
        assert gate.read_text() == 'operator-owned gate'
    else:
        assert not gate.exists()


@pytest.mark.parametrize('reload_number', [2, 3])
def test_failure_after_rollback_mutation_keeps_writer_fence_during_recovery(rollout, monkeypatch, reload_number):
    r = rollout
    r.invoke()
    before = r.files()
    reloads = 0

    def fail(*args):
        nonlocal reloads
        if args == ('systemctl', 'daemon-reload'):
            reloads += 1
            if reloads >= 2:
                with sqlite3.connect(r.ledger, timeout=0) as connection:
                    with pytest.raises(sqlite3.OperationalError, match='locked'):
                        connection.execute('BEGIN IMMEDIATE')
            if reloads == reload_number:
                raise RuntimeError('reload failed after mutation')
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', fail)
    with pytest.raises(RuntimeError, match='reload failed'):
        r.invoke('rollback')
    assert reloads > reload_number
    assert r.files() == before
    assert r.timer_states == r.original_timers
    assert not list(r.module.RUNTIME_SYSTEMD.glob('*/*.conf'))


def test_gate_blocks_new_systemd_starts_through_drain_and_mutation(rollout, monkeypatch):
    r = rollout
    r.invoke()
    observed = []

    def observe(*args):
        if ((args[:2] == ('systemctl', 'show') and args[4] == 'ActiveState' and args[2] in r.services)
                or args[0] == 'systemd-analyze'):
            for service in r.services:
                gate = r.module.RUNTIME_SYSTEMD / (service + '.d') / r.module.START_GATE
                assert gate.read_bytes() == r.module.start_gate_content()
                assert str(gate) in r.loaded_dropins[service]
                # ConditionPathExists=!existing-lock is false: a newly requested
                # start skips ExecStart, while the existing process is untouched.
                assert r.module.INSTALLER_LOCK.exists()
            observed.append(args)
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', observe)
    r.invoke('rollback')
    assert len(observed) == 9  # two idle checks over four services plus verify
    assert not list(r.module.RUNTIME_SYSTEMD.glob('*/*.conf'))


def test_timer_that_does_not_pause_fails_closed(rollout, monkeypatch):
    r = rollout
    r.invoke()
    before = r.files()

    def stop_fails(*args):
        result = r.run(*args)
        if args[:2] == ('systemctl', 'stop'):
            r.timer_states[args[2]] = 'active'
        return result

    monkeypatch.setattr(r.module, 'run', stop_fails)
    with pytest.raises(RuntimeError, match='did not pause'):
        r.invoke('rollback')
    assert r.files() == before
    assert r.timer_states == r.original_timers


def test_drift_during_drain_is_preserved_and_refused(rollout, monkeypatch):
    r = rollout
    r.invoke()
    before = r.files()
    path = r.etc / (r.services[0] + '.d') / r.module.DROPIN

    def drift(*args):
        if args[:3] == ('systemctl', 'show', r.services[0]) and args[4] == 'ActiveState':
            path.write_bytes(before[r.services[0]] + b'# concurrent operator edit\n')
        return r.run(*args)

    monkeypatch.setattr(r.module, 'run', drift)
    with pytest.raises(SystemExit, match='changed during operation'):
        r.invoke('disable-new-picks')
    assert path.read_bytes().endswith(b'# concurrent operator edit\n')
    assert all(r.files()[service] == before[service] for service in r.services[1:])
    assert r.timer_states == r.original_timers


@pytest.mark.parametrize('action', ['disable-new-picks', 'disable-data-labels'])
def test_legacy_disabled_labels_never_reenabled(rollout, action):
    r = rollout
    r.invoke()
    path = r.etc / (r.services[0] + '.d') / r.module.DROPIN
    path.write_bytes(r.module.dropin(r.value, r.services[0], send=False, observe=True, labels=False))
    r.invoke(action)
    content = path.read_bytes()
    assert b'--send' not in content and b'--label-v2-selections' not in content


def test_wrong_rollback_ledger_refused_before_timer_changes(rollout):
    r = rollout
    r.invoke()
    before = r.files()
    r.value['ledger'] = str(r.ledger.parent / 'wrong.db')
    r.manifest.write_text(json.dumps(r.value))
    r.calls.clear()
    with pytest.raises(SystemExit, match='Rollback ledger does not match'):
        r.invoke('rollback')
    assert r.files() == before
    assert not any(call[:2] == ('systemctl', 'stop') for call in r.calls)
