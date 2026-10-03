"""Offline failure recovery for the compatible four-route settlement operator upgrade."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

@pytest.fixture(params=["prematch-settlement", "prematch-single-floor", "prematch-devig", "calibration-observer", "combo-leg-floor", "combo-bot", "settlement-replies"])
def rig(tmp_path, monkeypatch, request):
    source = Path(__file__).parents[1] / "operations" / request.param / "update.py"
    spec = importlib.util.spec_from_file_location("quality_update", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    base = tmp_path / "base"
    (base / "application/app").mkdir(parents=True)
    (base / "application/app/original.py").write_text("BASE = True\n")
    monkeypatch.setattr(mod, "BASE", base)
    if hasattr(mod, "check_configuration"):
        plan = base / "application" / mod.PLAN_ASSET
        plan.parent.mkdir(parents=True)
        plan.write_text('{"frozen": true}')
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
    if hasattr(mod, "CALIBRATION_BASE"):
        calibration_base = tmp_path / "calibration-base"
        mod.shutil.copytree(base / "application", calibration_base / "application")
        for name in mod.CALIBRATION_FILES:
            p = calibration_base / "application" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((package / "overlay" / name).read_bytes())
        monkeypatch.setattr(mod, "CALIBRATION_BASE", calibration_base)
        (calibration_base / "release.env").write_bytes(
            mod.base_environment(calibration_base) + b"GOALVISION_LAB_CALIBRATION_READINESS=1\n")
        route_bases["goalvision-adaptive-learning-observer.service"] = calibration_base / "release.env"
    meta = {
        "source_commit": "a" * 40, "updater_sha256": mod.sha(package / "update.py"),
        "files": {name: mod.sha(package / "overlay" / name) for name in mod.FILES},
        "base_manifest": mod.tree(base / "application"),
        "route_sources": {str(env): {
            "environment_sha256": mod.sha(env),
            "manifest": mod.tree(env.parent / "application"),
        } for env in set(route_bases.values())},
    }
    if request.param == "combo-bot":
        (package / "configure.py").write_text("REVIEWED = True\n")
        meta["configure_sha256"] = mod.sha(package / "configure.py")
    if hasattr(mod, "check_configuration"):
        monkeypatch.setattr(mod, "check_configuration", lambda package: None)
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
                           calls=calls, failure=failure, overrides=overrides, base=base, loaded=loaded)

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
    assert (target / 'rollback.env').read_bytes() == m.environment(target, True)
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
        rig.failure["start"] = m.TIMERS[min(1, len(m.TIMERS)-1)]
    else:
        original = m.atomic
        target = rig.overrides[m.SERVICES[min(1, len(m.SERVICES)-1)]]
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
    rig.busy.add(rig.mod.SERVICES[min(1, len(rig.mod.SERVICES)-1)])
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
    if len(rig.mod.SERVICES) == 1:
        pytest.skip('A single route cannot have a partial multi-route override')
    target = rig.mod.validate(rig.package)[1]
    rig.overrides[rig.mod.SERVICES[0]].write_bytes(rig.mod.dropin(target))
    with pytest.raises(ValueError, match="PARTIAL_OR_UNREVIEWED"):
        rig.mod.apply(rig.package)
    assert rig.calls == []

def test_rollback_refuses_changed_dropin(rig):
    m = rig.mod
    m.apply(rig.package)
    rig.overrides[m.SERVICES[min(1, len(m.SERVICES)-1)]].write_text("[Service]\nEnvironmentFile=/unreviewed\n")
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
    expected_early = b'1' if ('app/lab_v2_shadow/single_odds_policy.py' in m.FILES or 'app/adaptive_lab/devig_research.py' in m.FILES or 'app/adaptive_lab/calendar_monitor.py' in m.FILES or 'app/lab_combo/bot_routing.py' in m.FILES or 'app/lab_combo/settlement_reply.py' in m.FILES) else b'0'
    assert b'GOALVISION_LAB_EARLY_COMBO_LOSS=' + expected_early + b'\n' in (target / 'rollback.env').read_bytes()
    assert all('rollback.env' in p.read_text() for p in rig.overrides.values())



def test_single_floor_environment_is_explicit_and_rollback_compatible(rig):
    m = rig.mod
    if 'app/lab_v2_shadow/single_odds_policy.py' not in m.FILES:
        return
    target = m.validate(rig.package)[1]
    assert b'GOALVISION_LAB_SINGLE_MIN_ODDS_130=1\n' in m.environment(target)
    assert b'GOALVISION_LAB_SINGLE_MIN_ODDS_130=0\n' in m.environment(target, True)
    assert b'GOALVISION_LAB_EARLY_COMBO_LOSS=1\n' in m.environment(target)
    assert b'GOALVISION_LAB_EARLY_COMBO_LOSS=1\n' in m.environment(target, True)
    assert b'GOALVISION_LAB_EARLY_COMBO_LOSS=1\n' in m.base_environment(m.BASE)
    assert b'GOALVISION_LAB_ACCURACY_COMBOS=1\n' in m.environment(target, True)


@pytest.mark.parametrize('scope', ['one_route', 'all_routes'])
def test_old_or_mixed_base_route_refused_before_controls(rig, scope):
    units = rig.mod.SERVICES[:1] if scope == 'one_route' else rig.mod.SERVICES
    for unit in units:
        rig.loaded[unit] = '/opt/unreviewed-earlier-release/release.env (ignore_errors=no)'
    with pytest.raises(ValueError, match='PREMATCH_ROUTE_MISMATCH'):
        rig.mod.apply(rig.package)
    assert rig.calls == []
    assert not any(p.exists() for p in rig.overrides.values())
    assert not rig.mod.validate(rig.package)[1].exists()


def test_devig_rollback_only_disables_research(rig):
    m = rig.mod
    if 'app/adaptive_lab/devig_research.py' not in m.FILES:
        return
    target = m.validate(rig.package)[1]
    enabled = m.environment(target)
    disabled = m.environment(target, True)
    assert enabled.replace(b'GOALVISION_LAB_DEVIG_RESEARCH=1', b'GOALVISION_LAB_DEVIG_RESEARCH=0') == disabled
    for flag in ('SINGLE_MIN_ODDS_130', 'TODAY_ONLY', 'EARLY_COMBO_LOSS', 'ACCURACY_COMBOS'):
        assert ('GOALVISION_LAB_'+flag+'=1\n').encode() in disabled


def test_calendar_rollback_only_disables_readiness_and_keeps_all_other_flags(rig):
    m=rig.mod
    if "app/adaptive_lab/calendar_monitor.py" not in m.FILES or len(m.SERVICES) != 1:
        return
    assert m.SERVICES==("goalvision-adaptive-learning-observer.service",)
    assert {"goalvision-lab-v2-discover.service","goalvision-lab-combo-settle.service",
            "goalvision-adaptive-learning.service","goalvision-admin-alerts.service"} <= set(m.PROTECTED)
    target=m.validate(rig.package)[1]
    assert m.environment(target).replace(b"CALIBRATION_READINESS=1",b"CALIBRATION_READINESS=0")==m.environment(target,True)
    for flag in ("DEVIG_RESEARCH","SINGLE_MIN_ODDS_130","TODAY_ONLY","EARLY_COMBO_LOSS","ACCURACY_COMBOS"):
        assert ("GOALVISION_LAB_"+flag+"=1\n").encode() in m.environment(target,True)


def test_calendar_plan_asset_is_hashed_in_release_and_rollback(rig):
    m=rig.mod
    if not hasattr(m,"PLAN_ASSET"):
        return
    m.apply(rig.package)
    target=m.validate(rig.package)[1]
    (target/"application"/m.PLAN_ASSET).write_text("{}")
    controls=len(rig.calls)
    with pytest.raises(ValueError,match="RELEASE_DRIFT"):
        m.apply(rig.package,rollback=True)
    assert len(rig.calls)==controls


@pytest.mark.parametrize("guard",["enabled","missing_marker","valid"])
def test_calendar_root_guard_inspects_installed_admin_files(rig,monkeypatch,tmp_path,guard):
    m=rig.mod
    if not hasattr(m,"ADMIN_CONFIG"):
        return
    config,marker=tmp_path/"admin.json",tmp_path/"DISABLED"
    config.write_text(json.dumps({"autorepair":{"enabled":guard=="enabled"}}))
    if guard!="missing_marker":
        marker.write_text("")
    monkeypatch.setattr(m,"ADMIN_CONFIG",config)
    monkeypatch.setattr(m,"ADMIN_DISABLED",marker)
    monkeypatch.setattr(m.os,"geteuid",lambda:0)
    if guard=="valid":
        m.disabled_worker()
    else:
        with pytest.raises(ValueError,match="ADMIN_CODEX_ROOT_GUARD"):
            m.apply(rig.package)
        assert rig.calls==[]


def test_protected_route_drift_blocks_before_timer_controls(rig):
    rig.loaded[rig.mod.PROTECTED[0]]="unreviewed"
    with pytest.raises(ValueError,match="PREPARED_CONFIGURATION_DRIFT"):
        rig.mod.apply(rig.package)
    assert rig.calls==[]


def test_combo_leg_floor_rollback_retains_approved_readiness_and_other_flags(rig):
    m=rig.mod
    if "app/lab_combo/odds_policy.py" not in m.FILES:
        return
    assert set(m.SERVICES)=={"goalvision-lab-v2-discover.service",
        "goalvision-adaptive-learning-observer.service","goalvision-lab-combo-settle.service",
        "goalvision-adaptive-learning.service"}
    target=m.validate(rig.package)[1]
    assert m.environment(target).replace(b"COMBO_LEG_MIN_ODDS_130=1",b"COMBO_LEG_MIN_ODDS_130=0")==m.environment(target,True)
    for flag in ("CALIBRATION_READINESS","DEVIG_RESEARCH","SINGLE_MIN_ODDS_130",
                 "TODAY_ONLY","EARLY_COMBO_LOSS","ACCURACY_COMBOS"):
        assert ("GOALVISION_LAB_"+flag+"=1\n").encode() in m.environment(target,True)


@pytest.mark.parametrize("rig", ["combo-leg-floor"], indirect=True)
def test_installed_calibration_source_is_exactly_pinned(rig):
    m=rig.mod
    observer="goalvision-adaptive-learning-observer.service"
    assert len(set(m.ROUTE_BASES.values()))==2
    assert m.ROUTE_BASES[observer]==m.CALIBRATION_BASE/"release.env"
    assert rig.meta["route_sources"]==m.expected_route_sources(rig.meta["base_manifest"],rig.meta["files"])
    m.verify_routes()
    m.apply(rig.package)
    target=m.validate(rig.package)[1]
    assert b"GOALVISION_LAB_CALIBRATION_READINESS=1\n" in (target/"release.env").read_bytes()
    m.apply(rig.package,rollback=True)
    assert b"GOALVISION_LAB_CALIBRATION_READINESS=1\n" in (target/"rollback.env").read_bytes()
    assert b"GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130=0\n" in (target/"rollback.env").read_bytes()


@pytest.mark.parametrize("rig", ["combo-leg-floor"], indirect=True)
@pytest.mark.parametrize("tamper", ["plan","observer","environment","unexpected_python"])
def test_installed_calibration_source_drift_refused_before_controls(rig,tamper):
    m=rig.mod
    if tamper=="environment":
        p=m.CALIBRATION_BASE/"release.env"
    elif tamper=="plan":
        p=m.CALIBRATION_BASE/"application"/m.PLAN_ASSET
    elif tamper=="observer":
        p=m.CALIBRATION_BASE/"application/app/adaptive_lab/observer.py"
    else:
        p=m.CALIBRATION_BASE/"application/app/unreviewed.py"
    p.write_text("unreviewed")
    with pytest.raises(ValueError,match="ROLLBACK_SOURCE_DRIFT"):
        m.apply(rig.package)
    assert not rig.calls and not any(p.exists() for p in rig.overrides.values())


@pytest.mark.parametrize("rig", ["combo-leg-floor"], indirect=True)
@pytest.mark.parametrize("tamper", ["manifest","environment"])
def test_observed_calibration_drift_cannot_be_reblessed_in_metadata(rig,tamper):
    m=rig.mod
    env=m.CALIBRATION_BASE/"release.env"
    meta=json.loads((rig.package/"metadata.json").read_text())
    if tamper=="environment":
        env.write_bytes(env.read_bytes().replace(b"CALIBRATION_READINESS=1",b"CALIBRATION_READINESS=0"))
        meta["route_sources"][str(env)]["environment_sha256"]=m.sha(env)
    else:
        (m.CALIBRATION_BASE/"application"/m.PLAN_ASSET).write_text("{}")
        meta["route_sources"][str(env)]["manifest"]=m.tree(m.CALIBRATION_BASE/"application")
    (rig.package/"metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError,match="ROUTE_SOURCE_CONTRACT_MISMATCH"):
        m.apply(rig.package)
    assert not rig.calls


@pytest.mark.parametrize("rig", ["combo-leg-floor"], indirect=True)
def test_r2_does_not_accept_prior_all_devig_route_state(rig):
    rig.loaded["goalvision-adaptive-learning-observer.service"]=str(rig.base/"release.env")+" (ignore_errors=no)"
    with pytest.raises(ValueError,match="PREMATCH_ROUTE_MISMATCH"):
        rig.mod.apply(rig.package)
    assert not rig.calls and not any(p.exists() for p in rig.overrides.values())


def test_combo_bot_missing_configuration_prevents_every_mutation(rig,monkeypatch):
    m=rig.mod
    if not hasattr(m,"check_configuration"):
        return
    def blocked(package):
        raise ValueError("COMBO_PRIVATE_RECIPIENT_CONFIGURATION_REQUIRED")
    monkeypatch.setattr(m,"check_configuration",blocked)
    with pytest.raises(ValueError,match="COMBO_PRIVATE_RECIPIENT"):
        m.apply(rig.package)
    assert not rig.calls and not any(p.exists() for p in rig.overrides.values())
    assert not m.validate(rig.package)[1].exists()


def test_combo_bot_setup_hash_cannot_be_replaced(rig):
    m=rig.mod
    if "configure_sha256" not in rig.meta:
        return
    (rig.package/"configure.py").write_text("UNREVIEWED = True\n")
    with pytest.raises(ValueError,match="CONFIGURE_HASH_MISMATCH"):
        m.validate(rig.package)
    assert not rig.calls


def test_combo_bot_rollback_pauses_new_sends_and_keeps_both_floors(rig):
    m=rig.mod
    if "app/lab_combo/bot_routing.py" not in m.FILES:
        return
    m.apply(rig.package)
    m.apply(rig.package,rollback=True)
    content=(m.validate(rig.package)[1]/"rollback.env").read_text()
    for flag in ("GOALVISION_LAB_SINGLE_MIN_ODDS_130=1","GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130=1",
                 "GOALVISION_LAB_EARLY_COMBO_LOSS=1","GOALVISION_COMBO_BOT_ROUTING=0"):
        assert flag in content


@pytest.mark.parametrize("rig", ["settlement-replies"], indirect=True)
def test_reply_rollback_only_disables_attachment_and_keeps_current_policy(rig):
    m = rig.mod
    m.apply(rig.package)
    target = m.validate(rig.package)[1]
    enabled = (target/"release.env").read_text()
    m.apply(rig.package, rollback=True)
    disabled = (target/"rollback.env").read_text()
    assert disabled == enabled.replace("GOALVISION_LAB_SETTLEMENT_REPLIES=1", "GOALVISION_LAB_SETTLEMENT_REPLIES=0")
    for flag in ("GOALVISION_COMBO_BOT_ROUTING", "GOALVISION_LAB_TODAY_ONLY",
                 "GOALVISION_LAB_EARLY_COMBO_LOSS", "GOALVISION_LAB_SINGLE_MIN_ODDS_130",
                 "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130", "GOALVISION_LAB_DEVIG_RESEARCH",
                 "GOALVISION_LAB_CALIBRATION_READINESS"):
        assert flag+"=1\n" in disabled
