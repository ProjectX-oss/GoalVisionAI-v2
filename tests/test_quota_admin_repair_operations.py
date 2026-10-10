"""Isolated installation transaction; all systemd and transport boundaries faked."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


@pytest.fixture
def setup(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1]/"operations/quota-admin-repair"
    spec = importlib.util.spec_from_file_location("quota_admin_test", source/"update.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "SYSTEMD", tmp_path/"systemd")
    m.SYSTEMD.mkdir()
    monkeypatch.setattr(m, "BASES", {k:tmp_path/("base-"+k) for k in m.BASES})
    monkeypatch.setattr(m, "TARGETS", {k:tmp_path/("target-"+k) for k in m.TARGETS})
    package = tmp_path/"package"
    package.mkdir()
    for name in ("update.py", "runtime_helpers.py"):
        shutil.copyfile(source/name, package/name)
    for key, root in m.BASES.items():
        app = root if key == "admin" else root/"application"
        module = m.OVERLAYS["admin" if key == "admin" else "reader"]
        path = app/module
        path.parent.mkdir(parents=True)
        path.write_text("# original "+key+"\n")
        (app/"reviewed_competitions.json").write_text('{"reviewed":true}\n')
        (app/"calendar.json").write_text('{"sealed":true}\n')
        (app/"asset.html").write_text("original asset")
        if key == "admin":
            (root/"run.py").write_text("# pinned launcher\n")
            (root/"manifest.json").write_text("{}")
        else:
            (root/"release.env").write_text("PYTHONPATH="+str(app)+"\nKEEP_POLICY=1\n")
    for kind, name in m.OVERLAYS.items():
        path = package/"overlay"/kind/name
        path.parent.mkdir(parents=True)
        path.write_text("# reviewed fix "+kind+"\n")
    initial = {}
    for unit in m.ALL_UNITS:
        (m.SYSTEMD/unit).write_text("original "+unit)
        key = m.route_key(unit)
        initial[unit] = {
            "WorkingDirectory": str(m.BASES["admin"]) if unit == m.ADMIN else "/working",
            "ExecStart": "{ path=/python ; argv[]=/python "+str(m.BASES[key]/"run.py"),
            "EnvironmentFiles": "" if unit == m.ADMIN else str(m.BASES[key]/"release.env")+" (ignore_errors=no)",
            "DropInPaths": "", "User": "test", "Group": "test",
        }
    state = {"calls": [], "loaded": initial, "busy": False,
             "active": {u:True for u in m.TIMERS},
             "timers": {u:{"configuration":"unchanged","UnitFileState":"enabled"} for u in m.ALL_TIMERS}}
    monkeypatch.setattr(m, "configured_units", lambda: deepcopy(state["loaded"]))
    monkeypatch.setattr(m, "timer_configurations", lambda: deepcopy(state["timers"]))
    monkeypatch.setattr(m.h, "disabled_worker", lambda: None)
    def prop(unit, key):
        if key == "ActiveState":
            if unit in state["active"]:
                return "active" if state["active"][unit] else "inactive"
            return "active" if state["busy"] else "inactive"
        raise AssertionError("UNEXPECTED_PROPERTY:"+key)
    monkeypatch.setattr(m.h, "property_of", prop)
    def control(command, *args):
        state["calls"].append((command, *args))
        if command in ("stop", "start"):
            assert len(args) == 1 and args[0] in m.TIMERS
            state["active"][args[0]] = command == "start"
        elif command == "daemon-reload":
            state["loaded"] = m.expected_units(state["meta"], m.mode())
        else:
            raise AssertionError("UNEXPECTED_SYSTEMD_COMMAND")
        return ""
    monkeypatch.setattr(m.h, "control", control)
    meta = {
        "schema": "QUOTA_ADMIN_REPAIR_PACKAGE_V1", "source_commits": m.SOURCE_COMMITS,
        "bases": {k:str(v) for k,v in m.BASES.items()},
        "targets": {k:str(v) for k,v in m.TARGETS.items()},
        "scripts": {p:m.h.sha(package/p) for p in ("update.py","runtime_helpers.py")},
        "overlay_hashes": {k:m.h.sha(package/"overlay"/k/v) for k,v in m.OVERLAYS.items()},
        "base_manifests": {k:m.manifest(v if k=="admin" else v/"application") for k,v in m.BASES.items()},
        "base_environments": {k:(v/"release.env").read_text() for k,v in m.BASES.items() if k!="admin"},
        "units": deepcopy(initial), "systemd_files": m.configuration_files(),
        "timer_configurations": deepcopy(state["timers"]),
        "smoke": {"status":"THREE_RELEASES_OFFLINE_PASS"},
    }
    state["meta"] = meta
    (package/"metadata.json").write_text(json.dumps(meta))
    return m, package, meta, state


def test_preflight_is_readonly(setup):
    m, package, meta, state = setup
    before = m.configuration_files()
    assert m.validate(package)[1] == "BASE"
    assert m.configuration_files() == before
    assert state["calls"] == []
    assert not any(path.exists() for path in m.TARGETS.values())


def test_full_apply_preserves_assets_policy_timer_states_and_is_idempotent(setup, capsys):
    m, package, meta, state = setup
    inactive = m.PREMATCH[-1].replace(".service", ".timer")
    state["active"][inactive] = False
    before = dict(state["active"])
    m.apply(package)
    assert m.validate(package)[1] == "ENABLED"
    assert state["active"] == before
    for key, root in m.TARGETS.items():
        app = root if key == "admin" else root/"application"
        assert (app/"reviewed_competitions.json").read_text() == '{"reviewed":true}\n'
        assert (app/"asset.html").read_text() == "original asset"
        if key != "admin":
            assert (root/"release.env").read_text().splitlines()[1:] == ["KEEP_POLICY=1"]
    count = len(state["calls"])
    m.apply(package)
    assert len(state["calls"]) == count
    assert "ALREADY_DEPLOYED" in capsys.readouterr().out
    assert all(not args or args[0].endswith(".timer") for cmd,*args in state["calls"] if cmd in ("start","stop"))


@pytest.mark.parametrize("kind", ["reader","admin"])
def test_modified_overlay_is_rejected_before_staging(setup, kind):
    m, package, _, state = setup
    (package/"overlay"/kind/m.OVERLAYS[kind]).write_text("unreviewed")
    with pytest.raises(ValueError, match="OVERLAY_HASH"):
        m.apply(package)
    assert state["calls"] == []


@pytest.mark.parametrize("key", ["prematch","live","admin"])
def test_modified_base_assets_are_rejected(setup, key):
    m, package, _, state = setup
    root = m.BASES[key] if key=="admin" else m.BASES[key]/"application"
    (root/"reviewed_competitions.json").write_text("{}")
    with pytest.raises(ValueError, match="BASE_RELEASE_HASH"):
        m.apply(package)
    assert state["calls"] == []


def test_script_and_environment_drift_rejected(setup):
    m, package, _, state = setup
    (m.BASES["live"]/"release.env").write_text("WRONG=1\n")
    with pytest.raises(ValueError, match="BASE_ENVIRONMENT"):
        m.validate(package)
    assert state["calls"] == []


def test_partial_routes_require_review(setup):
    m, package, _, state = setup
    path = m.override(m.LIVE)
    path.parent.mkdir()
    path.write_bytes(m.dropin(m.LIVE))
    with pytest.raises(ValueError, match="PARTIAL_DEPLOYMENT"):
        m.apply(package)
    assert state["calls"] == []


def test_base_symlink_refused(setup):
    m, package, _, state = setup
    link = m.BASES["prematch"]/"application"/"linked"
    link.symlink_to(m.BASES["live"])
    with pytest.raises(ValueError, match="SYMLINK"):
        m.validate(package)
    assert state["calls"] == []


def test_timer_config_drift_refused(setup):
    m, package, _, state = setup
    state["timers"][m.TIMERS[0]]["configuration"] = "unreviewed"
    with pytest.raises(ValueError, match="TIMER_CONFIGURATION"):
        m.apply(package)
    assert state["calls"] == []


def test_unrelated_systemd_file_drift_refused(setup):
    m, package, _, state = setup
    (m.SYSTEMD/"goalvision-official.service").write_text("changed externally")
    with pytest.raises(ValueError, match="SYSTEMD_CONFIGURATION"):
        m.apply(package)
    assert state["calls"] == []


def test_busy_timeout_restores_timers_without_route_changes(setup, monkeypatch):
    m, package, meta, state = setup
    state["busy"] = True
    monkeypatch.setattr(m, "DRAIN_SECONDS", 0)
    with pytest.raises(TimeoutError, match="NATURAL_COMPLETION"):
        m.apply(package)
    assert all(state["active"].values())
    assert m.configuration_files() == meta["systemd_files"]
    assert m.mode() == "BASE"
    assert not any(call[0] == "daemon-reload" for call in state["calls"])


def test_mid_write_failure_restores_all_routes_and_timers(setup, monkeypatch):
    m, package, meta, state = setup
    original = m.h.atomic
    def fail(path, data):
        if path == m.override(m.LIVE):
            raise OSError("synthetic write failure")
        return original(path, data)
    monkeypatch.setattr(m.h, "atomic", fail)
    with pytest.raises(OSError, match="synthetic"):
        m.apply(package)
    assert all(state["active"].values())
    assert m.configuration_files() == meta["systemd_files"]
    assert m.configured_units() == meta["units"]
    assert m.mode() == "BASE"


def test_reload_failure_restores_routes_without_service_restart(setup, monkeypatch):
    m, package, meta, state = setup
    original = m.h.control
    failed = []
    def fail(command, *args):
        if command == "daemon-reload" and not failed:
            failed.append(True)
            raise OSError("synthetic reload failure")
        return original(command, *args)
    monkeypatch.setattr(m.h, "control", fail)
    with pytest.raises(OSError, match="reload"):
        m.apply(package)
    assert m.configured_units() == meta["units"]
    assert m.mode() == "BASE"
    assert all(state["active"].values())


def test_timer_restore_failure_recovers_old_configuration(setup, monkeypatch):
    m, package, meta, state = setup
    original = m.h.control
    failed = []
    def fail(command, *args):
        if command == "start" and not failed:
            failed.append(True)
            raise OSError("synthetic resume failure")
        return original(command, *args)
    monkeypatch.setattr(m.h, "control", fail)
    with pytest.raises(RuntimeError, match="TIMER_RESTORE_FAILED"):
        m.apply(package)
    assert m.mode() == "BASE"
    assert m.configured_units() == meta["units"]
    assert all(state["active"].values())


def test_inactive_live_is_not_enabled_by_install(setup):
    m, package, _, state = setup
    state["active"][m.LIVE.replace(".service",".timer")] = False
    with pytest.raises(ValueError, match="LIVE_TIMER_NOT_ACTIVE"):
        m.apply(package)
    assert state["calls"] == []


def test_stage_tamper_is_rejected_before_timer_pause(setup):
    m, package, meta, state = setup
    m.stage_releases(package, meta)
    path = m.TARGETS["live"]/"application"/m.OVERLAYS["reader"]
    path.chmod(0o644)
    path.write_text("tampered")
    with pytest.raises(ValueError, match="RELEASE_HASH_DRIFT"):
        m.apply(package)
    assert state["calls"] == []


def test_admin_disabled_guard_blocks_apply(setup, monkeypatch):
    m, package, _, state = setup
    def refused():
        raise ValueError("ADMIN_CODEX_ROOT_GUARD")
    monkeypatch.setattr(m.h, "disabled_worker", refused)
    with pytest.raises(ValueError, match="ADMIN_CODEX"):
        m.apply(package)
    assert state["calls"] == []


def test_missing_smoke_proof_blocks_apply(setup):
    m, package, meta, state = setup
    meta["smoke"]["status"] = "PENDING"
    (package/"metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="PACKAGE_CONTRACT"):
        m.apply(package)
    assert state["calls"] == []


@pytest.mark.parametrize("name", ["update.py", "runtime_helpers.py"])
def test_changed_installer_hash_refused(setup, name):
    m, package, _, state = setup
    (package/name).write_text("# modified")
    with pytest.raises(ValueError, match="SCRIPT_HASH"):
        m.validate(package)
    assert state["calls"] == []


def test_persistent_lab_timer_failure_still_restores_admin_monitor(setup, monkeypatch):
    m, package, meta, state = setup
    original = m.h.control
    failed_timer = m.TIMERS[0]
    def fail(command, *args):
        if command == "start" and args == (failed_timer,):
            raise OSError("persistent resume failure")
        return original(command, *args)
    monkeypatch.setattr(m.h, "control", fail)
    with pytest.raises(RuntimeError, match="INSTALL_RECOVERY_REQUIRES_OPERATOR:TIMER_RESTORE"):
        m.apply(package)
    assert m.mode() == "BASE"
    assert m.configured_units() == meta["units"]
    assert state["active"][m.ADMIN.replace(".service", ".timer")]
    assert all(active for timer, active in state["active"].items() if timer != failed_timer)
