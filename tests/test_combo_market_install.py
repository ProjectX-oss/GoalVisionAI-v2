"""Second-lane installer rehearsals; fake systemd and disposable releases only."""
from types import SimpleNamespace
import json
import pytest
from tests import test_prematch_settlement_upgrade as prior


@pytest.fixture
def rig(tmp_path, monkeypatch):
    value = prior.rig.__wrapped__(tmp_path, monkeypatch, SimpleNamespace(param="combo-market-parallel"))
    value.meta["runtime_import_smoke"] = {"status": "ISOLATED_COMBO_IMPORT_PASS"}
    (value.package/"metadata.json").write_text(json.dumps(value.meta))
    return value


def test_apply_replay_rollback(rig):
    prior.test_apply_replay_rollback_preserves_mixed_timer_states(rig)
    mod = rig.mod
    enabled = mod.environment(mod.BASE)
    disabled = mod.environment(mod.BASE, True)
    assert disabled == enabled.replace(b"GOALVISION_COMBO_MARKET_PARALLEL=1", b"GOALVISION_COMBO_MARKET_PARALLEL=0")
    for flag in ("GOALVISION_COMBO_CONSERVATIVE_AGREEMENT", "GOALVISION_COMBO_BOT_ROUTING",
                 "GOALVISION_LAB_SINGLE_MIN_ODDS_150", "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130",
                 "GOALVISION_LAB_SETTLEMENT_REPLIES", "GOALVISION_LAB_EARLY_COMBO_LOSS",
                 "GOALVISION_LAB_TODAY_ONLY"):
        assert (flag+"=1\n").encode() in disabled


@pytest.mark.parametrize("failure_kind", ["reload", "timer", "second_dropin"])
def test_failure_recovery(rig, monkeypatch, failure_kind):
    prior.test_partial_change_failure_restores_all_routes_and_timers(rig, monkeypatch, failure_kind)


def test_busy_services_not_killed(rig, monkeypatch):
    prior.test_busy_service_is_not_killed_and_all_timers_restored(rig, monkeypatch)


@pytest.mark.parametrize("tamper", ["overlay", "updater", "base", "environment", "unexpected_file"])
def test_tamper_rejected(rig, tamper):
    prior.test_tamper_refused_before_timer_controls(rig, tamper)


@pytest.mark.parametrize("where", ["overlay", "destination", "override", "base_child"])
def test_symlinks(rig, where):
    prior.test_symlinks_refused(rig, where)


@pytest.mark.parametrize("unit", ["goalvision-admin-alerts.service", "goalvision-dixon-coles-forward.service"])
def test_protected_route_drift(rig, unit):
    rig.loaded[unit] = "unreviewed"
    with pytest.raises(ValueError, match="PREPARED_CONFIGURATION_DRIFT"):
        rig.mod.apply(rig.package)
    assert not rig.calls


def test_partial_existing_override(rig):
    prior.test_partial_existing_override_refuses_without_controls(rig)


def test_rollback_drift(rig):
    prior.test_rollback_refuses_changed_dropin(rig)


def test_admin_disabled(rig, monkeypatch):
    prior.test_admin_codex_must_remain_disabled(rig, monkeypatch)


def test_missing_recipient(rig, monkeypatch):
    prior.test_combo_bot_missing_configuration_prevents_every_mutation(rig, monkeypatch)


def test_no_unverified_import_package(rig):
    del rig.meta["runtime_import_smoke"]
    (rig.package/"metadata.json").write_text(json.dumps(rig.meta))
    with pytest.raises(ValueError, match="PACKAGE_IMPORT_PROOF_REQUIRED"):
        rig.mod.apply(rig.package)
    assert not rig.calls
