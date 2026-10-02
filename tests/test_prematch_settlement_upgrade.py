"""Offline failure recovery for the compatible four-route settlement operator upgrade."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

@pytest.fixture
def rig(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "operations/prematch-settlement/update.py"
    spec = importlib.util.spec_from_file_location("quality_update", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    base = tmp_path / "base"
    (base / "application/app").mkdir(parents=True)
    (base / "application/app/original.py").write_text("BASE = True\n")
    monkeypatch.setattr(mod, "BASE", base)
    (base / "release.env").write_bytes(mod.base_environment(base))
    route_bases = {u: base / "release.env" for u in mod.SERVICES}
    monkeypatch.setattr(mod, "ROUTE_BASES", route_bases)
    overrides = {u: tmp_path / "systemd" / (u + ".d") / "quality.conf" for u in mod.SERVICES}
    for p in overrides.values():
        p.parent.mkdir(parents=True)
    monkeypatch.setattr(mod, "OVERRIDES", overrides)
    package = tmp_path / "package"
    package.mkdir()
    (package / "update.py").write_bytes(source.read_bytes())
    for name in mod.FILES:
        p = package / "overlay" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("REVIEWED = True\n")
    meta = {
        "source_commit": "a" * 40, "updater_sha256": mod.sha(package / "update.py"),
        "files": {name: mod.sha(package / "overlay" / name) for name in mod.FILES},
        "base_manifest": mod.tree(base / "application"),
        "route_sources": {str(base / "release.env"): {
            "environment_sha256": mod.sha(base / "release.env"),
            "manifest": mod.tree(base / "application"),
        }},
    }
    (package / "metadata.json").write_text(json.dumps(meta))
    state = {t: "active" for t in mod.TIMERS}
    busy = set()
    calls = []
    loaded = {u: str(route_bases[u]) + " (ignore_errors=no)" for u in mod.SERVICES}
    failure = {"reload": False, "start": None, "write": None}
    def prop(unit, key):
        if unit == 'goalvision-admin-autorepair.timer':
            return 'inactive' if key == 'ActiveState' else 'disabled' if key == 'UnitFileState' else 'unchanged'
        if unit == 'goalvision-admin-autorepair.service' and key in {'ActiveState', 'MainPID'}:
            return 'inactive' if key == 'ActiveState' else '0'
        if key == "EnvironmentFiles":
            return loaded.get(unit, "protected")
        if key == "ActiveState":
            return state[unit] if unit in state else "active" if unit in busy else "inactive"
        if key == "DropInPaths":
            return ("base " + str(overrides[unit]) if unit in overrides and overrides[unit].exists()
                    else "base")
        if key == "ExecStart":
            return "{ path=/python ; argv[]=/python reviewed ; ignore_errors=no ; pid=0 }"
        return "unchanged"
    def control(*args):
        calls.append(args)
        if args[0] == "stop":
            assert args[1] in mod.TIMERS, "Never stop a service"
            state[args[1]] = "inactive"
        elif args[0] == "start":
            assert args[1] in mod.TIMERS, "Never start a service"
            if failure["start"] == args[1]:
                failure["start"] = None
                raise RuntimeError("synthetic timer failure")
            state[args[1]] = "active"
        elif args[0] == "daemon-reload":
            if failure["reload"]:
                failure["reload"] = False
                raise RuntimeError("synthetic reload failure")
            for unit, path in overrides.items():
                loaded[unit] = ((path.read_text().split("EnvironmentFile=")[-1].strip()
                                if path.exists() else str(route_bases[unit])) + " (ignore_errors=no)")
        else:
            raise AssertionError(args)
        return ""
    monkeypatch.setattr(mod, "property_of", prop)
    monkeypatch.setattr(mod, "control", control)
    meta["expected_commands"] = mod.stable_commands(mod.SERVICES + mod.PROTECTED)
    meta["protected_routes"] = mod.routes(mod.PROTECTED)
    (package / "metadata.json").write_text(json.dumps(meta))
    return SimpleNamespace(mod=mod, package=package, meta=meta, state=state, busy=busy,
                           calls=calls, failure=failure, overrides=overrides, base=base)

def test_apply_replay_rollback_preserves_mixed_timer_states(rig):
    m = rig.mod
    rig.state[m.TIMERS[-1]] = "inactive"
    before = dict(rig.state)
    m.apply(rig.package)
    assert rig.state == before
    target = m.validate(rig.package)[1]
    m.verify_routes(target)
    expected = dict(rig.meta["base_manifest"], **rig.meta["files"])
    m.verify_release(target, expected)
    calls = len(rig.calls)
    m.apply(rig.package)
    assert len(rig.calls) == calls
    m.apply(rig.package, rollback=True)
    m.verify_routes(target, rollback=True)
    assert rig.state == before
    assert all(p.read_bytes() == m.dropin(target, True) for p in rig.overrides.values())
    assert (target / 'rollback.env').read_bytes().endswith(b'GOALVISION_LAB_EARLY_COMBO_LOSS=0\n')
    m.apply(rig.package)
    m.verify_routes(target)
    assert target.exists()  # Evidence/release retained for review.

@pytest.mark.parametrize("failure_kind", ["reload", "timer", "second_dropin"])
def test_partial_change_failure_restores_all_routes_and_timers(rig, monkeypatch, failure_kind):
    m = rig.mod
    original_states = dict(rig.state)
    if failure_kind == "reload":
        rig.failure["reload"] = True
    elif failure_kind == "timer":
        rig.failure["start"] = m.TIMERS[1]
    else:
        original = m.atomic
        target = rig.overrides[m.SERVICES[1]]
        def fail_once(path, data):
            if path == target:
                raise RuntimeError("synthetic atomic failure")
            return original(path, data)
        monkeypatch.setattr(m, "atomic", fail_once)
    with pytest.raises(RuntimeError):
        m.apply(rig.package)
    m.verify_routes()
    assert rig.state == original_states
    assert not any(p.exists() for p in rig.overrides.values())

def test_busy_service_is_not_killed_and_all_timers_restored(rig, monkeypatch):
    rig.busy.add(rig.mod.SERVICES[1])
    monkeypatch.setattr(rig.mod, "DRAIN_SECONDS", 0)
    with pytest.raises(TimeoutError, match="PREMATCH_RUNNING"):
        rig.mod.apply(rig.package)
    assert all(s == "active" for s in rig.state.values())
    assert not any(p.exists() for p in rig.overrides.values())
    assert not any(c[0] == "daemon-reload" for c in rig.calls)

@pytest.mark.parametrize("tamper", ["overlay", "updater", "base", "environment", "unexpected_file"])
def test_tamper_refused_before_timer_controls(rig, tamper):
    m = rig.mod
    if tamper == "overlay":
        (rig.package / "overlay" / m.FILES[0]).write_text("bad")
    elif tamper == "updater":
        (rig.package / "update.py").write_text("bad")
    elif tamper == "base":
        (rig.base / "application/app/original.py").write_text("bad")
    elif tamper == "environment":
        (rig.base / "release.env").write_text("bad")
    else:
        meta = dict(rig.meta, files={**rig.meta["files"], "../escape.py": "bad"})
        (rig.package / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError):
        m.apply(rig.package)
    assert rig.calls == []

@pytest.mark.parametrize("where", ["overlay", "destination", "override", "base_child"])
def test_symlinks_refused(rig, where):
    m = rig.mod
    target = m.validate(rig.package)[1]
    external = rig.base.parent / "external"
    external.mkdir()
    if where == "overlay":
        p = rig.package / "overlay" / m.FILES[0]
        p.unlink()
    elif where == "destination":
        p = target
    elif where == "override":
        p = rig.overrides[m.SERVICES[0]]
    else:
        p = rig.base / "application/app/link"
    p.symlink_to(external)
    with pytest.raises(ValueError, match="SYMLINK"):
        m.apply(rig.package)
    assert rig.calls == []

def test_partial_existing_override_refuses_without_controls(rig):
    target = rig.mod.validate(rig.package)[1]
    rig.overrides[rig.mod.SERVICES[0]].write_bytes(rig.mod.dropin(target))
    with pytest.raises(ValueError, match="PARTIAL_OR_UNREVIEWED"):
        rig.mod.apply(rig.package)
    assert rig.calls == []

def test_rollback_refuses_changed_dropin(rig):
    m = rig.mod
    m.apply(rig.package)
    rig.overrides[m.SERVICES[1]].write_text("[Service]\nEnvironmentFile=/unreviewed\n")
    count = len(rig.calls)
    with pytest.raises(ValueError, match="PARTIAL_OR_UNREVIEWED_OVERRIDE"):
        m.apply(rig.package, rollback=True)
    assert len(rig.calls) == count


def test_symlink_in_staged_tree_is_refused_before_route(rig, monkeypatch):
    m = rig.mod
    original = m.shutil.copytree
    external = rig.base.parent / "external-stage"
    external.mkdir()
    def inject(src, dst, *args, **kwargs):
        result = original(src, dst, *args, **kwargs)
        (Path(dst) / "unreviewed-link").symlink_to(external)
        return result
    monkeypatch.setattr(m.shutil, "copytree", inject)
    with pytest.raises(ValueError, match="SYMLINK"):
        m.apply(rig.package)
    assert rig.calls == [] and external.exists()


def test_admin_codex_must_remain_disabled(rig, monkeypatch):
    original = rig.mod.property_of
    def enabled(unit, key):
        if unit == 'goalvision-admin-autorepair.timer' and key == 'UnitFileState':
            return 'enabled'
        return original(unit, key)
    monkeypatch.setattr(rig.mod, 'property_of', enabled)
    with pytest.raises(ValueError, match='ADMIN_CODEX_DISABLED_GUARD'):
        rig.mod.apply(rig.package)
    assert not rig.calls


def test_rollback_keeps_compatible_reader_sources(rig):
    m = rig.mod
    m.apply(rig.package)
    target = m.validate(rig.package)[1]
    before = m.tree(target / 'application')
    m.apply(rig.package, rollback=True)
    assert m.tree(target / 'application') == before
    assert b'GOALVISION_LAB_EARLY_COMBO_LOSS=0' in (target / 'rollback.env').read_bytes()
    assert all('rollback.env' in p.read_text() for p in rig.overrides.values())
