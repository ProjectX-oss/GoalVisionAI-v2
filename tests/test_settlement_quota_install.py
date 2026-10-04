"""Fake systemd rehearsals for the narrowly scoped settlement quota package."""
from types import SimpleNamespace
import json
import pytest
from tests import test_prematch_settlement_upgrade as prior

@pytest.fixture
def rig(tmp_path,monkeypatch):
    v=prior.rig.__wrapped__(tmp_path,monkeypatch,SimpleNamespace(param='settlement-quota-reserve'))
    v.meta['runtime_import_smoke']={'status':'ISOLATED_COMBO_IMPORT_PASS'}
    (v.package/'metadata.json').write_text(json.dumps(v.meta))
    return v


def test_apply_replay_and_explicit_compat_restore_preserve_flags(rig):
    prior.test_apply_replay_rollback_preserves_mixed_timer_states(rig)
    m=rig.mod
    assert set(m.FILES)=={'app/adaptive_lab/quota.py','app/lab_combo/cli.py'}
    for flag in ('GOALVISION_COMBO_MARKET_PARALLEL','GOALVISION_COMBO_CONSERVATIVE_AGREEMENT',
                 'GOALVISION_LAB_SINGLE_MIN_ODDS_150','GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130',
                 'GOALVISION_LAB_TODAY_ONLY','GOALVISION_LAB_EARLY_COMBO_LOSS','GOALVISION_LAB_SETTLEMENT_REPLIES'):
        assert (flag+'=1\n').encode() in m.environment(m.BASE,True)
    assert m.environment(m.BASE,True)==m.base_environment(m.BASE)

@pytest.mark.parametrize('failure_kind',['reload','timer','second_dropin'])
def test_transaction_failure(rig,monkeypatch,failure_kind):
    prior.test_partial_change_failure_restores_all_routes_and_timers(rig,monkeypatch,failure_kind)

def test_busy(rig,monkeypatch):prior.test_busy_service_is_not_killed_and_all_timers_restored(rig,monkeypatch)

@pytest.mark.parametrize('tamper',['overlay','updater','base','environment','unexpected_file'])
def test_tamper(rig,tamper):prior.test_tamper_refused_before_timer_controls(rig,tamper)

@pytest.mark.parametrize('where',['overlay','destination','override','base_child'])
def test_symlink(rig,where):prior.test_symlinks_refused(rig,where)

def test_disabled_admin(rig,monkeypatch):prior.test_admin_codex_must_remain_disabled(rig,monkeypatch)

def test_protected_route(rig):
    rig.loaded['goalvision-dixon-coles-forward.service']='unexpected'
    with pytest.raises(ValueError,match='PREPARED_CONFIGURATION_DRIFT'):rig.mod.apply(rig.package)
    assert not rig.calls
