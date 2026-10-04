"""Reuse transactional installer rehearsals; no systemd or sudo on the host."""
from types import SimpleNamespace
import json
import pytest
from tests import test_prematch_settlement_upgrade as prior

@pytest.fixture
def rig(tmp_path, monkeypatch):
    value = prior.rig.__wrapped__(tmp_path, monkeypatch, SimpleNamespace(param="combo-conservative"))
    mod = value.mod
    value.meta["protected_variants"] = [{
        "commands": mod.stable_commands(mod.PROTECTED),
        "routes": mod.routes(mod.PROTECTED),
    }]
    value.meta["runtime_import_smoke"] = {"status": "ISOLATED_COMBO_IMPORT_PASS"}
    (value.package/"metadata.json").write_text(json.dumps(value.meta))
    monkeypatch.setattr(mod, "monitor_repaired", lambda: True)
    return value

def test_apply_replay_rollback(rig):
    prior.test_apply_replay_rollback_preserves_mixed_timer_states(rig)
    mod = rig.mod
    enabled = mod.environment(mod.BASE)
    assert mod.environment(mod.BASE, True) == enabled.replace(
        b"GOALVISION_COMBO_CONSERVATIVE_AGREEMENT=1", b"GOALVISION_COMBO_CONSERVATIVE_AGREEMENT=0")
    assert b"GOALVISION_LAB_SINGLE_MIN_ODDS_150=1" in enabled
    assert b"GOALVISION_COMBO_BOT_ROUTING=1" in enabled
    assert b"GOALVISION_LAB_SETTLEMENT_REPLIES=1" in enabled

@pytest.mark.parametrize("failure_kind", ["reload", "timer", "second_dropin"])
def test_failure_recovery(rig, monkeypatch, failure_kind):
    prior.test_partial_change_failure_restores_all_routes_and_timers(rig, monkeypatch, failure_kind)

def test_busy_services_not_killed(rig, monkeypatch):
    prior.test_busy_service_is_not_killed_and_all_timers_restored(rig, monkeypatch)

@pytest.mark.parametrize("tamper", ["overlay", "updater", "base", "environment", "unexpected_file"])
def test_tamper_rejected(rig, tamper):
    prior.test_tamper_refused_before_timer_controls(rig, tamper)

def test_monitor_first_required_before_mutations(rig, monkeypatch):
    monkeypatch.setattr(rig.mod, "monitor_repaired", lambda: False)
    with pytest.raises(ValueError, match="INSTALL_ADMIN_HEALTH_PROJECTION_FIRST"):
        rig.mod.apply(rig.package)
    assert not rig.calls and not any(p.exists() for p in rig.overrides.values())

def test_unreviewed_research_route_refused(rig, monkeypatch):
    original = rig.mod.property_of
    monkeypatch.setattr(rig.mod, "property_of", lambda unit, key:
        "unreviewed" if unit == "goalvision-dixon-coles-forward.service" and key == "EnvironmentFiles"
        else original(unit, key))
    with pytest.raises(ValueError, match="PREPARED_CONFIGURATION_DRIFT"):
        rig.mod.apply(rig.package)
    assert not rig.calls

def test_exact_reviewed_monitor_transition_only(rig, monkeypatch):
    mod = rig.mod
    commands = mod.stable_commands(mod.SERVICES+mod.PROTECTED)
    routes = mod.routes(mod.PROTECTED)
    routes[mod.MONITOR]["WorkingDirectory"] = str(mod.MONITOR_BASE)
    commands[mod.MONITOR]["WorkingDirectory"] = str(mod.MONITOR_BASE)
    commands[mod.MONITOR]["ExecStart"] = str(mod.MONITOR_BASE/"run.py")
    variants = mod.protected_variants(commands, routes)
    assert len(variants) == 2
    assert variants[1]["routes"][mod.MONITOR]["WorkingDirectory"] == str(mod.MONITOR_TARGET)
    assert str(mod.MONITOR_OVERRIDE) in variants[1]["routes"][mod.MONITOR]["DropInPaths"]
    for state in variants:
        monkeypatch.setattr(mod, "stable_commands", lambda units, state=state: state["commands"])
        monkeypatch.setattr(mod, "routes", lambda units, state=state: state["routes"])
        mod.verify_protected_configuration({"protected_variants": variants})
    monkeypatch.setattr(mod, "routes", lambda units: {})
    with pytest.raises(ValueError, match="PREPARED_CONFIGURATION_DRIFT"):
        mod.verify_protected_configuration({"protected_variants": variants})

def test_all_numeric_resources_are_packaged(rig):
    expected = {
        "app/dixon_coles_forward/plan_20261003.json",
        "app/dixon_coles_research/plan_20261003.json",
        "app/dixon_coles_constrained/protocol_20261003.json",
    }
    assert expected <= set(rig.mod.FILES)
    assert all(name in rig.mod.tree(rig.package/"overlay") for name in expected)
