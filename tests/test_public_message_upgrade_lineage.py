"""Public formatter upgrade and emergency disable have distinct recovery targets.

All administration is fake, all stores are disposable, and no application cycle
is invoked. These tests run against the helper descended from ac2ffec.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from test_prematch_reviewed_upgrade import prepared, upgrade
from test_prematch_v2_rollout import rollout

STAGES = ('timer-stop', 'gate-write', 'drain', 'dropin-write', 'verify',
          'reload', 'gate-cleanup', 'timer-restore')


@pytest.fixture
def public_package(prepared):
    r = prepared
    r.upgrade_manifest['preserve_new_picks'] = True
    r.upgrade_manifest['previous_protected_stdout'] = True
    for s in r.services:
        r.module.write_atomic(r.etc / (s + '.d') / r.module.DROPIN,
                              upgrade.render(r.upgrade_manifest, s, previous=True, send=True))
    r.before = r.files()
    r.upgrade_manifest['expected_dropins'] = {
        s: hashlib.sha256(b).hexdigest() for s, b in r.before.items()}
    r.calls.clear()
    return r


def assert_administration_only(r) -> None:
    assert all(call[0] in ('systemctl', 'systemd-analyze') for call in r.calls)
    assert all(set(call[2:]).issubset(r.original_timers)
               for call in r.calls if call[:2] == ('systemctl', 'start'))
    assert not any(call[:2] in (('systemctl', 'restart'), ('systemctl', 'enable')) for call in r.calls)


def inject_stage(r, monkeypatch, stage: str, *, persistent: bool = False) -> list[str]:
    """Fail at the actual boundary, including partially successful timer start."""
    failures: list[str] = []
    originals = r.files()
    r.timer_start_configurations = []
    write = r.module.write_atomic
    drain = upgrade.drain
    unlink = Path.unlink

    def fail() -> None:
        if persistent or not failures:
            failures.append(stage)
            raise RuntimeError('injected ' + stage)

    def run(*args):
        if args[:2] == ('systemctl', 'start'):
            r.timer_start_configurations.append(r.files())
        if stage == 'timer-stop' and args[:2] == ('systemctl', 'stop'):
            fail()
        if stage == 'verify' and args[0] == 'systemd-analyze':
            fail()
        if (stage == 'reload' and args == ('systemctl', 'daemon-reload')
                and all(p.exists() for p in upgrade.gates().values())
                and r.files() != originals):
            fail()
        if stage == 'timer-restore' and args[:2] == ('systemctl', 'start'):
            r.run(*args)  # Start succeeded but status/command response failed.
            fail()
        return r.run(*args)

    def write_atomic(path, content):
        if stage == 'gate-write' and path == list(upgrade.gates().values())[1]:
            fail()
        if stage == 'dropin-write' and path == r.etc / (r.services[1] + '.d') / r.module.DROPIN:
            fail()
        return write(path, content)

    def drained():
        if stage == 'drain':
            fail()
        return drain()

    def unlinked(path, *args, **kwargs):
        if stage == 'gate-cleanup' and path == list(upgrade.gates().values())[1]:
            fail()
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(r.module, 'run', run)
    monkeypatch.setattr(r.module, 'write_atomic', write_atomic)
    monkeypatch.setattr(upgrade, 'drain', drained)
    monkeypatch.setattr(Path, 'unlink', unlinked)
    return failures


def test_formatter_upgrade_preserves_all_capabilities_and_only_environment(public_package):
    r = public_package
    r.upgrade()
    assert upgrade.state(r.upgrade_manifest, r.files()) == (False, True, True, True)
    old = r.upgrade_manifest['previous']['release_environment_file'].encode()
    new = r.upgrade_manifest['proposed']['release_environment_file'].encode()
    assert r.files() == {s: b.replace(old, new) for s, b in r.before.items()}
    assert b'StandardOutput=append:' in r.files()[r.services[0]]
    assert r.timer_states == r.original_timers
    assert_administration_only(r)
    r.upgrade('recover')
    assert r.files() == r.before


@pytest.mark.parametrize('stage', STAGES)
def test_formatter_failure_restores_exact_send_enabled_bytes(public_package, monkeypatch, stage):
    r = public_package
    failures = inject_stage(r, monkeypatch, stage)
    with pytest.raises(RuntimeError):
        r.upgrade()
    assert failures
    assert r.files() == r.before
    assert upgrade.state(r.upgrade_manifest, r.files()) == (True, True, True, True)
    assert r.timer_states == r.original_timers
    assert not upgrade.JOURNAL.exists()
    assert_administration_only(r)


def test_disable_is_monotonic_idempotent_and_history_independent(public_package, monkeypatch):
    r = public_package
    r.upgrade()
    monkeypatch.setattr(upgrade, 'require_history', lambda m: pytest.fail('disable must not require history clearance'))
    for _ in range(3):
        r.upgrade('disable-new-picks')
        assert upgrade.state(r.upgrade_manifest, r.files()) == (False, False, True, True)
        assert all(b'--send' not in b for b in r.files().values())
        assert r.timer_states == r.original_timers
        assert not upgrade.JOURNAL.exists()
    assert_administration_only(r)


@pytest.mark.parametrize('stage', STAGES)
def test_disable_failure_always_recovers_no_send(public_package, monkeypatch, stage):
    r = public_package
    r.upgrade()
    failures = inject_stage(r, monkeypatch, stage)
    with pytest.raises(RuntimeError):
        r.upgrade('disable-new-picks')
    assert failures
    assert all(b'--send' not in value for config in r.timer_start_configurations for value in config.values())
    assert upgrade.state(r.upgrade_manifest, r.files()) == (False, False, True, True)
    assert all(b'--send' not in b for b in r.files().values())
    assert r.timer_states == r.original_timers
    assert not upgrade.JOURNAL.exists()
    assert not any(p.exists() for p in upgrade.gates().values())
    assert_administration_only(r)


@pytest.mark.parametrize('stage', STAGES)
def test_failed_automatic_disable_recovery_retains_safe_journal(public_package, monkeypatch, stage):
    r = public_package
    r.upgrade()
    # Force the transaction to fail before mutation, then fail a selected boundary
    # in automatic recovery. Persistent failures also exercise final fencing.
    with monkeypatch.context() as faults:
        inject_stage(r, faults, stage, persistent=True)
        first_drain = upgrade.drain
        first = True
        def fail_transaction():
            nonlocal first
            if first:
                first = False
                raise RuntimeError('initial transaction failure')
            return first_drain()
        faults.setattr(upgrade, 'drain', fail_transaction)
        with pytest.raises(RuntimeError):
            r.upgrade('disable-new-picks')
    assert all(b'--send' not in value for config in r.timer_start_configurations for value in config.values())
    data = json.loads(upgrade.JOURNAL.read_text())
    assert data['action'] == 'disable-new-picks'
    assert '--send' in data['before'][r.services[0]]
    assert all('--send' not in b for b in data['recovery'].values())
    # A permanently unwritable gate cannot be manufactured, but timers must be
    # stopped. A permanently failing timer stop must leave all gates loaded.
    assert (all(p.exists() for p in upgrade.gates().values())
            or not any(v == 'active' for v in r.timer_states.values()))
    if stage != 'gate-write':
        assert all(p.exists() for p in upgrade.gates().values())
    if stage != 'timer-stop':
        assert not any(v == 'active' for v in r.timer_states.values())
    for call in r.calls:
        if call[:2] == ('systemctl', 'start'):
            assert set(call[2:]).issubset(r.original_timers)
    r.upgrade('recover')
    assert upgrade.state(r.upgrade_manifest, r.files()) == (False, False, True, True)
    assert all(b'--send' not in b for b in r.files().values())
    assert r.timer_states == r.original_timers
    assert not upgrade.JOURNAL.exists()
    assert not any(p.exists() for p in upgrade.gates().values())
    assert_administration_only(r)


@pytest.mark.parametrize('target', ['missing', 'before'])
def test_unsafe_legacy_disable_journal_fails_closed(public_package, monkeypatch, target):
    r = public_package
    r.upgrade()
    with monkeypatch.context() as faults:
        inject_stage(r, faults, 'verify', persistent=True)
        with pytest.raises(RuntimeError):
            r.upgrade('disable-new-picks')
    data = json.loads(upgrade.JOURNAL.read_text())
    if target == 'missing':
        data.pop('recovery')
    else:
        data['recovery'] = data['before']
    upgrade.save_journal(data)
    before = r.files()
    r.calls.clear()
    with pytest.raises(SystemExit, match='Invalid recovery target'):
        r.upgrade('recover')
    assert r.files() == before
    assert upgrade.JOURNAL.exists()
    assert not any(v == 'active' for v in r.timer_states.values())
    assert not any(call[:2] == ('systemctl', 'start') for call in r.calls)


@pytest.mark.parametrize('drift', ['old-package', 'nonboolean-opt-in', 'unknown-release', 'mixed-release'])
def test_state_recognition_stays_fail_closed(public_package, drift):
    r = public_package
    if drift == 'old-package':
        r.upgrade_manifest.pop('preserve_new_picks')
    elif drift == 'nonboolean-opt-in':
        r.upgrade_manifest['preserve_new_picks'] = 'true'
    else:
        s = r.services[0]
        content = upgrade.render(r.upgrade_manifest, s, send=True)
        if drift == 'unknown-release':
            content = content.replace(b'EnvironmentFile=', b'EnvironmentFile=/unknown')
        (r.etc / (s + '.d') / r.module.DROPIN).write_bytes(content)
    before = r.files()
    with pytest.raises(SystemExit, match='Unknown or mixed'):
        r.upgrade()
    assert r.files() == before
    assert not any(call[:2] == ('systemctl', 'stop') for call in r.calls)


def test_public_package_cli_lock_rejects_concurrent_installer(public_package, monkeypatch, tmp_path):
    r = public_package
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(r.upgrade_manifest))
    monkeypatch.setattr(upgrade.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(sys, 'argv', ['installer', str(manifest), 'upgrade', '--sha256', upgrade.sha(manifest)])
    with r.module.installer_lock():
        with pytest.raises(SystemExit, match='Another PREMATCH'):
            upgrade.main()
    assert r.files() == r.before
    assert not r.calls


def test_unknown_recovery_dropin_is_rejected(public_package, monkeypatch):
    r = public_package
    r.upgrade()
    with monkeypatch.context() as faults:
        inject_stage(r, faults, 'verify', persistent=True)
        with pytest.raises(RuntimeError):
            r.upgrade('disable-new-picks')
    r.loaded_dropins[r.services[0]] += ' /unknown.conf'
    before = r.files()
    r.calls.clear()
    with pytest.raises(SystemExit, match='Unknown effective recovery drop-ins'):
        r.upgrade('recover')
    assert r.files() == before
    assert upgrade.JOURNAL.exists()
    assert not any(call[:2] == ('systemctl', 'start') for call in r.calls)
