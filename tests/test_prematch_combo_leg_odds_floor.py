"""COMBO 1.30 leg-floor boundaries and delivery/history isolation, offline only."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json

import pytest

from app.lab_combo.odds_policy import (
    ENVIRONMENT_FLAG, FLOOR_POLICY, BELOW_FLOOR, minimum_combo_leg_odds,
    combo_leg_odds_blocker, combo_odds_blocker,
)
from app.lab_combo.service import LabComboService
from app.lab_v2_shadow.accuracy_combo import POLICY, review_accuracy_combo
from app.lab_v2_shadow.publication import prepare_v2_publications
from tests.test_lab_accuracy_combo import candidates, prepare
from tests.test_lab_v2_shadow import NOW, bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger, config, Transport


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG, "1")
    monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_130", "1")


def quote(item, odds):
    item.update(captured_odds=odds, offered_odds=odds,
                edge=str(Decimal(item["ensemble_probability"])-1/Decimal(odds)))
    bind_candidate_evidence(item)
    return item


def deliver(store, value, transport=None):
    return asyncio.run(LabComboService(store,None,clock=lambda:NOW).publish_experimental(
        "combo_prediction",value["prediction_id"],config(),transport or Transport()))


@pytest.mark.parametrize("odds,allowed", [
    ("1.05",False),("1.29",False),("1.299999999999999999999999999",False),
    ("1.30",True),("1.3000",True),("1.31",True),
])
def test_each_leg_boundary_inclusive_without_display_rounding(ledger,odds,allowed):
    rows=candidates()
    quote(rows[0],odds)
    result=prepare(ledger,rows)
    diag=result["combo_diagnostics"]
    assert diag["policy"]==FLOOR_POLICY and diag["minimum_combo_leg_decimal_odds"]=="1.30"
    assert bool(result["combos"]) is allowed
    if not allowed:
        assert diag["rejection_counts"][BELOW_FLOOR]==1
        assert diag["eligible_fixture_count"]==2
        assert not ledger.all("prediction")
    else:
        value,=result["combos"]
        assert value["combo_selection_policy"]==FLOOR_POLICY
        assert review_accuracy_combo(value,now=NOW)["eligible"]
        assert "Katras likmes koef. ≥1.30." in ledger.get("preview",value["prediction_id"])["message"]
        transport=Transport()
        assert deliver(ledger,value,transport)["sent"] and len(transport.calls)==1


def test_filter_before_per_fixture_ranking_uses_eligible_alternative(ledger):
    rows=candidates()
    quote(rows[0],"1.05")
    alternative=deepcopy(rows[0])
    alternative.update(candidate_id="alternative-over-floor",market="UNDER_2_5",ensemble_probability=".70")
    alternative["signals"][0].update(market="UNDER_2_5",selection="UNDER_2_5",probability=".70")
    quote(alternative,"1.30")
    value,=prepare(ledger,[*rows,alternative])["combos"]
    assert alternative["candidate_id"] in {leg["candidate_id"] for leg in value["legs"]}
    assert rows[0]["candidate_id"] not in {leg["candidate_id"] for leg in value["legs"]}
    assert all(Decimal(leg["captured_odds"])>=Decimal("1.30") for leg in value["legs"])


def test_large_combined_odds_cannot_hide_one_low_leg(ledger):
    rows=candidates()
    for item,odds in zip(rows,("1.29","2.50","2.50")):
        quote(item,odds)
    result=prepare(ledger,rows)
    assert not result["combos"] and result["combo_diagnostics"]["rejection_counts"][BELOW_FLOOR]==1


def test_nine_qualifying_fixtures_remain_disjoint_and_deterministic(ledger):
    rows=candidates(9)
    result=prepare(ledger,rows)
    assert len(result["combos"])==3
    assert len({leg["fixture_id"] for c in result["combos"] for leg in c["legs"]})==9
    assert prepare(ledger,list(reversed(rows)))["combos"]==result["combos"]


@pytest.mark.parametrize("failure",["stale","hard_failure","shared_team","tracking","low_probability"])
def test_floor_never_bypasses_existing_quality(ledger,failure):
    rows=candidates()
    if failure=="stale":
        rows[2]["provider_origin_timestamp_utc"]=(NOW-timedelta(hours=6)).isoformat()
        bind_candidate_evidence(rows[2])
    elif failure=="hard_failure":
        rows[2]["hard_failures"].append("INVALID_FIXTURE")
    elif failure=="shared_team":
        rows[2]["home_team_id"]=rows[0]["home_team_id"]
        bind_candidate_evidence(rows[2])
    elif failure=="tracking":
        rows[2]["candidate_lane"]="TRACKING"
    else:
        rows[2]["ensemble_probability"]=".54"
        quote(rows[2],"1.30")
    assert not prepare(ledger,rows)["combos"]


@pytest.mark.parametrize("legacy", [False,True])
def test_prepared_low_combo_cannot_bypass_preclaim_guard(ledger,monkeypatch,legacy):
    monkeypatch.setenv(ENVIRONMENT_FLAG,"0")
    value,=prepare(ledger,[quote(r,"1.05") for r in candidates()])["combos"]
    if legacy:
        value={k:v for k,v in value.items() if k!="combo_selection_policy"}
        value.update(prediction_id="legacy-low-combo",policy="legacy")
        ledger.append("prediction",value["prediction_id"],value)
        ledger.append("preview",value["prediction_id"],{"message":"frozen legacy preview"})
    before=deepcopy(ledger.get("preview",value["prediction_id"]))
    monkeypatch.setenv(ENVIRONMENT_FLAG,"1")
    transport=Transport()
    result=deliver(ledger,value,transport)
    assert result["status"]==BELOW_FLOOR and not result["transport_attempted"] and not result["claim_persisted"]
    assert not transport.calls and not ledger.all("claim")
    assert ledger.get("preview",value["prediction_id"])==before


def test_other_legacy_sender_checks_floor_before_source_review(ledger):
    from tests.test_lab_no_minimum_odds_policy import _combo_legs
    value={"prediction_id":"old-direct-low","legs":_combo_legs()}
    ledger.append("prediction",value["prediction_id"],value)
    transport=Transport()
    result=asyncio.run(LabComboService(ledger,None,clock=lambda:NOW).publish(
        value["prediction_id"],config(),transport))
    assert result["status"]==BELOW_FLOOR and not transport.calls and not ledger.all("claim")


def test_policy_identity_preserves_old_preview_and_cross_policy_fixture_dedup(ledger,monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG,"0")
    old,=prepare(ledger)["combos"]
    preview=deepcopy(ledger.get("preview",old["prediction_id"]))
    monkeypatch.setenv(ENVIRONMENT_FLAG,"1")
    new,=prepare(ledger)["combos"]
    assert old["policy"]==POLICY and new["policy"]==FLOOR_POLICY
    assert old["prediction_id"]!=new["prediction_id"]
    assert ledger.get("preview",old["prediction_id"])==preview
    ledger.claim_publication("combo_prediction",old,{"prediction_id":old["prediction_id"]})
    assert not prepare(ledger)["combos"]
    assert deliver(ledger,old)["status"]=="DELIVERY_ALREADY_CLAIMED"


def test_frozen_floor_contract_cannot_be_removed_on_rollback(ledger,monkeypatch):
    value,=prepare(ledger)["combos"]
    monkeypatch.setenv(ENVIRONMENT_FLAG,"0")
    altered=deepcopy(value);altered.pop("minimum_combo_leg_decimal_odds")
    assert "COMBO_FLOOR_POLICY_INVALID" in review_accuracy_combo(altered,now=NOW)["rejection_reasons"]
    assert review_accuracy_combo(value,now=NOW)["eligible"]


@pytest.mark.parametrize("invalid",[None,"NaN","Infinity","-1","1","bad"])
def test_invalid_current_odds_rejected(invalid):
    assert combo_leg_odds_blocker(invalid,minimum=minimum_combo_leg_odds())=="INVALID_CURRENT_DECIMAL_ODDS"


def test_invalid_configuration_cannot_disable_floor(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG,"true")
    with pytest.raises(ValueError,match="INVALID_LAB_COMBO_LEG_MIN_ODDS_CONFIGURATION"):
        minimum_combo_leg_odds()


def test_legacy_selection_paths_apply_same_floor():
    from app.lab_combo.engine import select_combo
    from app.lab_combo.experimental import select_combo_batch
    from tests.test_lab_no_minimum_odds_policy import _combo_legs
    legs=_combo_legs()
    assert select_combo(legs,NOW)==(None,[BELOW_FLOOR])
    for leg in legs:
        leg["odds"]="1.30"
    value,=select_combo(legs,NOW)[:1]
    assert Decimal(value["combined_odds"])==Decimal("1.30")**3
    rows=[dict(r,decision="APPROVED",stage="READY_TO_PUBLISH",market_context_edge=".05") for r in candidates()]
    assert len(select_combo_batch(rows,used_leg_keys=set(),now=NOW))==1
    quote(rows[0],"1.29")
    assert not select_combo_batch(rows,used_leg_keys=set(),now=NOW)


def test_rollback_restores_only_combo_floor_and_single_stays_130(ledger,monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG,"0")
    result=prepare(ledger,[quote(r,"1.05") for r in candidates()])
    assert not result["singles"] and len(result["combos"])==1
    assert result["minimum_published_decimal_odds"]=="1.30"
    assert result["combos"][0]["policy"]==POLICY


def test_historical_low_combo_still_settles_and_publishes_result(ledger,monkeypatch):
    from tests.test_lab_combo_early_loss import Provider,payload
    monkeypatch.setenv(ENVIRONMENT_FLAG,"0")
    old,=prepare(ledger,[quote(r,"1.05") for r in candidates()])["combos"]
    transport=Transport();assert deliver(ledger,old,transport)["sent"]
    original=deepcopy(ledger.get("prediction",old["prediction_id"]))
    monkeypatch.setenv(ENVIRONMENT_FLAG,"1")
    later=NOW+timedelta(hours=12)
    service=LabComboService(ledger,None,clock=lambda:later,early_combo_loss=True)
    provider=Provider({leg["fixture_id"]:payload(leg["fixture_id"],score=(2,2)) for leg in old["legs"]})
    asyncio.run(service.check_results(provider))
    assert ledger.get("settlement",old["prediction_id"])["status"]=="WON"
    assert asyncio.run(service.publish_experimental("combo_settlement",old["prediction_id"],config(),transport))["sent"]
    assert len(transport.calls)==2 and ledger.get("prediction",old["prediction_id"])==original


@pytest.mark.parametrize("odds,sends,reason",[("1.29",0,BELOW_FLOOR),("1.30",4,"COMBO_READY")])
def test_controlled_fake_cycle_persists_floor_diagnostics(tmp_path,monkeypatch,capsys,odds,sends,reason):
    from app.lab_v2_shadow import cli
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from tests.test_lab_v2_shadow import (_install_controlled_cycle_fakes,
        _DeterministicReadyRunner,_RecordingTransport,_controlled_cycle_arguments)
    monkeypatch.chdir(tmp_path);_install_controlled_cycle_fakes(monkeypatch)
    original=_DeterministicReadyRunner.run
    async def report(self,**kwargs):
        result=await original(self,**kwargs)
        return {**result,"candidate_markets":[quote(r,odds) for r in candidates()],"ready_candidate_count":0}
    monkeypatch.setattr(_DeterministicReadyRunner,"run",report)
    assert cli.main([*_controlled_cycle_arguments(send=True),"--accuracy-combos"])==0
    value=json.loads(capsys.readouterr().out)["controlled_publication"]
    assert _RecordingTransport.calls==sends
    diag=value["combo_diagnostics"]
    assert diag["policy"]==FLOOR_POLICY and diag["minimum_combo_leg_decimal_odds"]=="1.30"
    if sends:
        assert diag["reason"]==reason
    else:
        assert diag["rejection_counts"][reason]==3 and not _RecordingTransport.constructed
    store=ShadowEvidenceRepository(tmp_path/"var/lab_v2/shadow.db")
    try:
        saved,=store.all("publication_cycle")
        assert all(saved["controlled_publication"]["combo_diagnostics"][key]==diag[key]
                   for key in ("policy","minimum_combo_leg_decimal_odds","rejection_counts","eligible_fixture_count","prepared_count","reason"))
    finally:
        store.close()


@pytest.mark.parametrize("odds,allowed",[("1.29",False),("1.30",True)])
def test_v2_positive_value_combo_path_respects_leg_floor(ledger,monkeypatch,odds,allowed):
    import app.lab_v2_shadow.publication as publication
    from tests.test_lab_no_minimum_odds_policy import _ready_candidate
    monkeypatch.setattr(publication,"review_publication",lambda item,now:{"eligible":True,"rejection_reasons":[]})
    monkeypatch.setattr(publication,"current_quote",lambda *a,**kw:True)
    monkeypatch.setattr(publication,"publication_blocker",lambda *a,**kw:None)
    rows=[_ready_candidate(i,"1.30") for i in (1,2,3)]
    rows[0]["captured_odds"]=odds
    result=prepare_v2_publications({"candidate_markets":rows},ledger,now=NOW)
    assert bool(result["combos"]) is allowed
    if allowed:
        assert result["combos"][0]["minimum_combo_leg_decimal_odds"]=="1.30"
    else:
        assert result["publication_blockers"][rows[0]["candidate_id"]]==BELOW_FLOOR


def test_stdout_floor_counts_are_bounded_and_allowlisted():
    from app.lab_v2_shadow.operator_output import operator_cycle_summary
    report={"controlled_publication":{"combo_diagnostics":{
        "minimum_combo_leg_decimal_odds":"1.30","combo_leg_odds_policy":"LAB_COMBO_LEG_MIN_ODDS_130_V1",
        "rejection_counts":{BELOW_FLOOR:3,"INVALID_CURRENT_DECIMAL_ODDS":-4,
                            "UNTRUSTED_SECRET":"secret",**{str(i):99 for i in range(500)}}}}}
    diag=operator_cycle_summary(report)["controlled_publication"]["combo_diagnostics"]
    assert diag["rejection_counts"]=={BELOW_FLOOR:3}
    assert "secret" not in json.dumps(diag) and len(json.dumps(diag))<1000
