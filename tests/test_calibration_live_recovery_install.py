"""Offline operator package tests. Never invoke systemd, network or production DBs."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def installer(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("recovery_install_test",
        ROOT / "operations/calibration-live-recovery/install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "BASE", tmp_path / "base")
    monkeypatch.setattr(mod, "TARGET", tmp_path / "target")
    monkeypatch.setattr(mod, "SYSTEMD", tmp_path / "systemd")
    monkeypatch.setattr(mod, "JOURNALS", tmp_path / "journals")
    mod.BASE.mkdir()
    (mod.BASE / "release.env").write_text(
        "PYTHONPATH=" + str(mod.BASE / "application") + "\nUNCHANGED_FLAG=1\n")
    for name in (*mod.FILES, "app/untouched.py", "app/frozen_plan.json"):
        p = mod.BASE / "application" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("original:" + name)
    package = tmp_path / "package"
    package.mkdir()
    for name in ("install.py", "runtime_helpers.py"):
        (package / name).write_text("reviewed-script")
    for name in mod.FILES:
        p = package / "overlay" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("reviewed:" + name)
    meta = {"schema": mod.SCHEMA, "source_commit": "a"*40,
        "base": str(mod.BASE), "target": str(mod.TARGET),
        "smoke": {"status": "EXACT_BASE_RECOVERY_PASS"},
        "scripts": {n:mod.h.sha(package/n) for n in ("install.py", "runtime_helpers.py")},
        "files": {n:mod.h.sha(package/"overlay"/n) for n in mod.FILES},
        "base_manifest": mod.manifest(mod.BASE/"application"),
        "base_environment": (mod.BASE/"release.env").read_text(),
        "units": {}, "systemd_files": {}, "timer_configurations": {}}
    (package/"metadata.json").write_text(json.dumps(meta))
    monkeypatch.setattr(mod, "verify_configuration", lambda *a: None)
    monkeypatch.setattr(mod.h, "disabled_worker", lambda: None)
    states = {u:"active" for u in mod.TIMERS}
    states[mod.TIMERS[-1]] = "inactive"
    calls = []
    def control(*args):
        calls.append(args)
        if args[0] in {"stop", "start"}:
            assert args[1] in mod.TIMERS
            states[args[1]] = "inactive" if args[0] == "stop" else "active"
        else:
            assert args == ("daemon-reload",)
        return ""
    def prop(unit, key):
        assert key == "ActiveState"
        return states[unit] if unit in states else "inactive"
    monkeypatch.setattr(mod.h, "control", control)
    monkeypatch.setattr(mod.h, "property_of", prop)
    return mod, package, meta, states, calls

def test_assembly_changes_only_four_files_and_preserves_assets_flags(installer, tmp_path):
    mod, package, meta, _, calls = installer
    stage=tmp_path/"stage";stage.mkdir()
    before=mod.manifest(mod.BASE)
    mod.assemble(package,meta,stage)
    actual=mod.manifest(stage/"application")
    changed={n for n in actual if actual[n] != meta["base_manifest"][n]}
    assert changed == set(mod.FILES)
    assert (stage/"release.env").read_text().splitlines()[1:] == ["UNCHANGED_FLAG=1"]
    assert mod.manifest(mod.BASE) == before and not calls

@pytest.mark.parametrize("kind", ["overlay", "script", "base", "environment", "extra_file"])
def test_tampering_fails_before_systemd(installer, kind):
    mod, package, meta, _, calls = installer
    path = {"overlay":package/"overlay"/mod.FILES[0],
            "script":package/"install.py",
            "base":mod.BASE/"application/app/untouched.py",
            "environment":mod.BASE/"release.env",
            "extra_file":mod.BASE/"application/app/unreviewed.py"}[kind]
    path.write_text("tampered")
    with pytest.raises(ValueError):
        mod.validate(package)
    assert not calls

def test_target_drift_fails_closed(installer):
    mod, package, meta, _, calls = installer
    mod.TARGET.mkdir()
    mod.assemble(package, meta, mod.TARGET)
    (mod.TARGET/"application/app/untouched.py").write_text("changed")
    with pytest.raises(ValueError, match="RELEASE_HASH_DRIFT"):
        mod.validate(package)
    assert not calls

def test_symlink_overlay_rejected(installer, tmp_path):
    mod, package, _, _, calls = installer
    p=package/"overlay"/mod.FILES[0];p.unlink()
    external=tmp_path/"external";external.write_text("untrusted")
    p.symlink_to(external)
    with pytest.raises(ValueError, match="SYMLINK"):
        mod.validate(package)
    assert not calls

def test_operator_route_preserves_timer_states_and_never_touches_live(installer):
    mod, _, meta, states, calls = installer
    previous=dict(states)
    mod.route(meta)
    assert states == previous
    assert mod.mode() == "ENABLED"
    assert all("live-evening" not in str(c) for c in calls)
    assert all(c[0] not in {"enable", "disable", "restart"} for c in calls)
    assert all(c[1].endswith(".timer") for c in calls if c[0] in {"start","stop"})

def test_busy_service_timeout_restores_timers_without_routes(installer, monkeypatch):
    mod, _, meta, states, calls = installer
    previous=dict(states)
    original=mod.h.property_of
    monkeypatch.setattr(mod.h, "property_of",
        lambda u,k: "active" if u in mod.SERVICES else original(u,k))
    monkeypatch.setattr(mod, "DRAIN_SECONDS", -1)
    with pytest.raises(TimeoutError):
        mod.route(meta)
    assert states == previous and mod.mode() == "BASE"
    assert ("daemon-reload",) not in calls

def test_partial_route_failure_does_not_rollback_or_resume_timers(installer, monkeypatch):
    mod, _, meta, states, calls = installer
    original=mod.h.atomic
    def fail_second(path, data):
        if path == mod.override(mod.SERVICES[1]):
            raise OSError("injected write failure")
        return original(path,data)
    monkeypatch.setattr(mod.h,"atomic",fail_second)
    with pytest.raises(RuntimeError, match="NO_AUTOMATIC_ROLLBACK"):
        mod.route(meta)
    assert mod.override(mod.SERVICES[0]).read_bytes() == mod.dropin()
    assert all(v=="inactive" for v in states.values())
    assert not any(c[0]=="start" for c in calls)

def test_reload_failure_keeps_timers_paused_for_operator(installer, monkeypatch):
    mod, _, meta, states, calls = installer
    original=mod.h.control
    def fail(*args):
        if args == ("daemon-reload",):
            raise OSError("injected reload failure")
        return original(*args)
    monkeypatch.setattr(mod.h,"control",fail)
    with pytest.raises(RuntimeError, match="NO_AUTOMATIC_ROLLBACK"):
        mod.route(meta)
    assert all(mod.override(u).exists() for u in mod.SERVICES)
    assert all(v=="inactive" for v in states.values())

def test_already_applied_never_restarts_or_stages(installer, monkeypatch):
    mod, package, meta, _, calls = installer
    monkeypatch.setattr(mod,"validate",lambda p:(meta,"ENABLED"))
    monkeypatch.setattr(mod,"stage_release",lambda *a:pytest.fail("staging"))
    mod.apply(package)
    assert not calls

def test_partial_dropins_are_not_treated_as_installed(installer):
    mod, package, _, _, calls = installer
    p=mod.override(mod.SERVICES[0]);p.parent.mkdir(parents=True)
    p.write_bytes(mod.dropin())
    with pytest.raises(ValueError, match="PARTIAL_DEPLOYMENT"):
        mod.validate(package)
    assert not calls

def test_nonroot_apply_refused_before_validation(installer, monkeypatch):
    mod, _, _, _, calls = installer
    monkeypatch.setattr(mod.os,"geteuid",lambda:1000)
    with pytest.raises(SystemExit, match="ROOT_REQUIRED"):
        mod.main(["--apply"])
    assert not calls
