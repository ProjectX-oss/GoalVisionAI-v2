"""Exact-base evidence operator release; no route or flag broadening."""
from types import SimpleNamespace
import json
import pytest
from tests import test_prematch_settlement_upgrade as prior

@pytest.fixture
def rig(tmp_path, monkeypatch):
    v=prior.rig.__wrapped__(tmp_path,monkeypatch,SimpleNamespace(param="prematch-evidence"))
    v.meta["runtime_import_smoke"]={"status":"ISOLATED_PREMATCH_EVIDENCE_IMPORT_PASS"}
    (v.package/"metadata.json").write_text(json.dumps(v.meta))
    return v

def test_apply_replay_keeps_private_and_public_flags_and_timer_states(rig):
    m=rig.mod
    rig.state[m.TIMERS[-1]]="inactive"
    states=dict(rig.state)
    m.apply(rig.package)
    assert rig.state==states
    target=m.validate(rig.package)[1]
    m.verify_routes(target)
    m.verify_release(target,dict(rig.meta["base_manifest"],**rig.meta["files"]))
    calls=len(rig.calls)
    m.apply(rig.package)
    assert len(rig.calls)==calls
    assert set(m.FILES)=={"app/lab_v2_shadow/runner.py",
        "app/lab_v2_shadow/global_evaluation.py", "app/adaptive_lab/performance.py",
        "app/dixon_coles_forward/incremental.py", "app/dixon_coles_forward/incremental_plan_20261004.json"}
    assert m.environment(target).replace(str(target).encode(),str(m.BASE).encode())==m.base_environment(m.BASE)
    for flag in ("GOALVISION_PRIVATE_SINGLE_170","GOALVISION_LAB_SINGLE_MIN_ODDS_150",
                 "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130","GOALVISION_LAB_TODAY_ONLY",
                 "GOALVISION_LAB_EARLY_COMBO_LOSS","GOALVISION_LAB_SETTLEMENT_REPLIES",
                 "GOALVISION_COMBO_MARKET_PARALLEL","GOALVISION_COMBO_CONSERVATIVE_AGREEMENT"):
        assert (flag+"=1\n").encode() in m.environment(target)

def test_rollback_not_prepared(rig):
    with pytest.raises(ValueError,match="ROLLBACK_NOT_PREPARED"):
        rig.mod.apply(rig.package,rollback=True)
    assert not rig.calls

@pytest.mark.parametrize("failure_kind",["reload","timer","second_dropin"])
def test_failure_restores_routes_and_timer_states(rig,monkeypatch,failure_kind):
    prior.test_partial_change_failure_restores_all_routes_and_timers(rig,monkeypatch,failure_kind)

def test_busy_workers_never_killed(rig,monkeypatch):
    prior.test_busy_service_is_not_killed_and_all_timers_restored(rig,monkeypatch)

@pytest.mark.parametrize("tamper",["overlay","updater","base","environment","unexpected_file"])
def test_hash_or_environment_drift_blocks_before_controls(rig,tamper):
    prior.test_tamper_refused_before_timer_controls(rig,tamper)

@pytest.mark.parametrize("where",["overlay","destination","override","base_child"])
def test_symlink_blocks_before_controls(rig,where):
    prior.test_symlinks_refused(rig,where)

@pytest.mark.parametrize("scope",["one_route","all_routes"])
def test_mixed_or_old_routes_block_before_controls(rig,scope):
    prior.test_old_or_mixed_base_route_refused_before_controls(rig,scope)

def test_admin_stays_disabled(rig,monkeypatch):
    prior.test_admin_codex_must_remain_disabled(rig,monkeypatch)


def test_partial_existing_override_blocks_without_controls(rig):
    prior.test_partial_existing_override_refuses_without_controls(rig)


def test_protected_route_drift_blocks_without_controls(rig):
    prior.test_protected_route_drift_blocks_before_timer_controls(rig)


def test_staged_symlink_blocks_before_routes(rig,monkeypatch):
    prior.test_symlink_in_staged_tree_is_refused_before_route(rig,monkeypatch)


@pytest.mark.parametrize("guard",["enabled","missing_marker","valid"])
def test_operator_root_checks_admin_guard_files(rig,monkeypatch,tmp_path,guard):
    prior.test_calendar_root_guard_inspects_installed_admin_files(rig,monkeypatch,tmp_path,guard)


def test_missing_incremental_plan_blocks_without_controls(rig):
    (rig.package/"overlay/app/dixon_coles_forward/incremental_plan_20261004.json").unlink()
    with pytest.raises(FileNotFoundError):
        rig.mod.apply(rig.package)
    assert not rig.calls


def test_missing_import_proof_blocks_without_controls(rig):
    rig.meta["runtime_import_smoke"]={}
    (rig.package/"metadata.json").write_text(json.dumps(rig.meta))
    with pytest.raises(ValueError,match="PACKAGE_IMPORT_PROOF_REQUIRED"):
        rig.mod.apply(rig.package)
    assert not rig.calls


def test_default_plan_does_not_apply_or_control_timers(rig,monkeypatch,capsys):
    monkeypatch.setattr(rig.mod,"__file__",str(rig.package/"update.py"))
    monkeypatch.setattr("sys.argv",["prematch-evidence.py"])
    rig.mod.main()
    assert "PREMATCH_EVIDENCE_PLAN_VALIDATED=" in capsys.readouterr().out
    assert not rig.calls
    assert not rig.mod.validate(rig.package)[1].exists()


def test_changed_commands_block_before_controls(rig,monkeypatch):
    original=rig.mod.property_of
    def changed(unit,key):
        if unit==rig.mod.SERVICES[0] and key=="ExecStart":
            return "{ path=/python ; argv[]=/python other ; ignore_errors=no ; pid=0 }"
        return original(unit,key)
    monkeypatch.setattr(rig.mod,"property_of",changed)
    with pytest.raises(ValueError,match="PREPARED_CONFIGURATION_DRIFT"):
        rig.mod.apply(rig.package)
    assert not rig.calls
