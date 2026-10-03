"""Live Lab SINGLE >=1.50 policy and immutable cohorts, with network denied."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest

from app.lab_combo.service import LabComboService
from app.lab_combo.presentation import ResultImagePaths
from app.lab_v2_shadow.publication import v2_single_message
from app.lab_v2_shadow.single_odds_policy import (
    ENVIRONMENT_FLAG, ENVIRONMENT_FLAG_150, FLOOR_SELECTION_POLICY,
    TEST_SELECTION_POLICY, minimum_single_odds,
)
from app.lab_v2_shadow.statistics import public_single_snapshot, single_cohorts
from tests.test_lab_accuracy_combo import candidates, prepare
from tests.test_prematch_single_odds_floor import quote
from tests.test_prematch_v2_enablement import ledger, config, Transport
from tests.test_combo_bot_routing import routed, send
from tests.test_settlement_replies import transport
from tests.test_lab_v2_shadow import NOW
from tests.test_lab_combo_early_loss import Provider, payload


@pytest.fixture(autouse=True)
def floor_150(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG, "1")
    monkeypatch.setenv(ENVIRONMENT_FLAG_150, "1")
    monkeypatch.setenv("GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130", "1")
    monkeypatch.setenv("GOALVISION_LAB_TODAY_ONLY", "1")
    monkeypatch.setenv("GOALVISION_LAB_SETTLEMENT_REPLIES", "1")


@pytest.mark.parametrize("odds,allowed", [
    ("1.30", False), ("1.49", False), ("1.49999999999999999999999", False),
    ("1.50", True), ("1.5000", True), ("1.51", True)])
def test_exact_boundary_and_real_publication_path_to_existing_lab(ledger,odds,allowed):
    result = prepare(ledger,[quote(candidates(1)[0],odds)])
    assert result["single_selection_policy"] == TEST_SELECTION_POLICY
    assert result["minimum_published_decimal_odds"] == "1.50"
    assert bool(result["singles"]) is allowed
    if not allowed:
        assert set(result["single_publication_blockers"].values()) == {"LAB_SINGLE_ODDS_BELOW_1_50"}
        assert not ledger.all("single_prediction")
        return
    single, = result["singles"]
    assert "koef. ≥1.50" in v2_single_message(single)
    assert "SINGLE 1.50 testa statistika" in v2_single_message(single)
    client = transport()
    result = send(ledger,"single_prediction",single["prediction_id"],config(),client)
    assert result["sent"] and len(client.bot.calls) == 1
    assert client.bot.calls[0][1]["chat_id"] == "-1003510920417"
    assert "reply_parameters" not in client.bot.calls[0][1]


def test_filter_precedes_ranking_and_combo_keeps_its_own_130_pool(ledger):
    rows = [quote(r,"1.40") for r in candidates()]
    alternative = deepcopy(rows[0])
    alternative.update(candidate_id="qualifying-150",market="UNDER_2_5",ensemble_probability=".70")
    alternative["signals"][0].update(market="UNDER_2_5",selection="UNDER_2_5",probability=".70")
    quote(alternative,"1.50")
    result = prepare(ledger,[*rows,alternative])
    single, = result["singles"]
    assert single["candidate_id"] == "qualifying-150"
    combo, = result["combos"]
    assert {leg["candidate_id"] for leg in combo["legs"]} == {r["candidate_id"] for r in rows}
    assert all(Decimal(leg["captured_odds"]) == Decimal("1.40") for leg in combo["legs"])


def test_no_single_still_allows_130_combo_on_private_bot(ledger,routed):
    _,_,cfg = routed
    result = prepare(ledger)
    assert not result["singles"]
    combo, = result["combos"]
    client = transport(private=True)
    assert send(ledger,"combo_prediction",combo["prediction_id"],cfg,client)["sent"]
    assert client.bot.calls[0][1]["chat_id"] == cfg.chat_id
    assert all(Decimal(l["captured_odds"]) == Decimal("1.30") for l in combo["legs"])
    assert "Katras likmes koef. ≥1.30." in client.bot.calls[0][1]["text"]


@pytest.mark.parametrize("previous_flag", ["0","1"])
def test_prepared_low_odds_cannot_escape_preclaim_floor(ledger,monkeypatch,previous_flag):
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"0")
    monkeypatch.setenv(ENVIRONMENT_FLAG,previous_flag)
    single, = prepare(ledger,[quote(candidates(1)[0],"1.40")])["singles"]
    frozen = deepcopy(ledger.get("single_preview",single["prediction_id"]))
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"1")
    client = Transport()
    outcome = send(ledger,"single_prediction",single["prediction_id"],config(),client)
    assert outcome["status"] == "LAB_SINGLE_ODDS_BELOW_1_50"
    assert not outcome["transport_attempted"] and not outcome["claim_persisted"]
    assert not client.calls and not ledger.all("claim")
    assert ledger.get("single_preview",single["prediction_id"]) == frozen


def test_policy_identity_is_new_but_economic_claim_is_shared(ledger,monkeypatch):
    rows = [quote(candidates(1)[0],"1.60")]
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"0")
    old, = prepare(ledger,rows)["singles"]
    frozen = deepcopy(ledger.get("single_preview",old["prediction_id"]))
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"1")
    new, = prepare(ledger,rows)["singles"]
    assert old["prediction_id"] != new["prediction_id"]
    assert new["single_selection_policy"] == TEST_SELECTION_POLICY
    assert prepare(ledger,rows)["singles"] == [new]
    assert send(ledger,"single_prediction",old["prediction_id"],config(),Transport())["sent"]
    client = Transport()
    assert send(ledger,"single_prediction",new["prediction_id"],config(),client)["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert not client.calls and not prepare(ledger,rows)["singles"]
    assert ledger.get("single_preview",old["prediction_id"]) == frozen


@pytest.mark.parametrize("minimum", ["1.30",None,"1.500"])
def test_forged_frozen_150_contract_fails_before_claim(ledger,minimum):
    single, = prepare(ledger,[quote(candidates(1)[0],"1.60")])["singles"]
    forged = deepcopy(single)
    forged["prediction_id"] += "-forged"
    forged["minimum_published_decimal_odds"] = minimum
    ledger.append("single_prediction",forged["prediction_id"],forged)
    ledger.append("single_preview",forged["prediction_id"],{"message":v2_single_message(forged)})
    client = Transport()
    result = send(ledger,"single_prediction",forged["prediction_id"],config(),client)
    assert not result["sent"] and not client.calls and not ledger.all("claim")


@pytest.mark.parametrize("bad_flag", [ENVIRONMENT_FLAG,ENVIRONMENT_FLAG_150])
@pytest.mark.parametrize("bad", ["true","yes","2",""])
def test_invalid_flags_never_silently_change_policy(monkeypatch,bad_flag,bad):
    monkeypatch.setenv(bad_flag,bad)
    with pytest.raises(ValueError,match="INVALID_LAB_SINGLE"):
        minimum_single_odds()


@pytest.mark.parametrize("photo", [False,True])
@pytest.mark.parametrize("outcome", ["WON","LOST","VOID"])
def test_new_cohort_result_reply_and_old_bet_history_survive_rollback(
        ledger,monkeypatch,tmp_path,photo,outcome):
    rows = candidates(2)
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"0")
    old, = prepare(ledger,[quote(rows[0],"1.40")])["singles"]
    old_preview = deepcopy(ledger.get("single_preview",old["prediction_id"]))
    client = transport()
    assert send(ledger,"single_prediction",old["prediction_id"],config(),client)["sent"]
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"1")
    new, = prepare(ledger,[quote(rows[1],"1.50")])["singles"]
    assert new["public_presentation"]["statistics"]["totals"]["published"] == 0
    published = send(ledger,"single_prediction",new["prediction_id"],config(),client)
    assert published["sent"]
    # The prepared/confirmed 1.50 cohort persists after a compatible 1.30 rollback.
    monkeypatch.setenv(ENVIRONMENT_FLAG_150,"0")
    assert minimum_single_odds() == Decimal("1.30")
    image = tmp_path/"result.png";image.write_bytes(b"fixture-image")
    images = ResultImagePaths(image,image,image) if photo else ResultImagePaths()
    later = NOW+timedelta(hours=12)
    service = LabComboService(ledger,None,clock=lambda:later,result_images=images)
    responses = {old["fixture_id"]:payload(old["fixture_id"],score=(0,0)),
                 new["fixture_id"]:payload(new["fixture_id"],
                     "CANC" if outcome=="VOID" else "FT",
                     (None,None) if outcome=="VOID" else (2,2) if outcome=="WON" else (0,0))}
    asyncio.run(service.check_results(Provider(responses)))
    settled = deepcopy(ledger.get("single_settlement",new["prediction_id"]))
    assert settled["status"] == outcome
    snapshot = ledger.get("single_settlement_preview",new["prediction_id"])["statistics"]
    assert snapshot["selection_policy"] == TEST_SELECTION_POLICY
    assert snapshot["totals"]["published"] == snapshot["totals"]["settled"] == 1
    assert snapshot["totals"][outcome] == 1
    assert Decimal(snapshot["totals"]["flat_unit_pnl"]) == {"WON":Decimal(".50"),"LOST":Decimal("-1"),"VOID":Decimal(0)}[outcome]
    assert snapshot["totals"]["roi_denominator_units"] == 1
    result = asyncio.run(service.publish_experimental("single_settlement",new["prediction_id"],config(),client))
    assert result["sent"] and result["reply_status"] == "CONFIRMED"
    assert result["reply_to"]["message_id"] == published["message_id"]
    assert client.bot.calls[-1][0] == ("photo" if photo else "text")
    assert "SINGLE 1.50 testa statistika" in ledger.get("single_settlement_preview",new["prediction_id"])["message"]
    assert asyncio.run(service.publish_experimental("single_settlement",old["prediction_id"],config(),client))["sent"]
    assert ledger.get("single_preview",old["prediction_id"]) == old_preview
    cohort = single_cohorts(ledger,start=NOW-timedelta(days=1),end=later+timedelta(days=1),as_of=later)
    assert cohort["forward_union"]["published"] == 2
    assert cohort["selection_policy_exclusive"][FLOOR_SELECTION_POLICY]["published"] == 1
    assert cohort["selection_policy_exclusive"][TEST_SELECTION_POLICY]["published"] == 1
    assert public_single_snapshot(ledger,as_of=NOW,selection_policy=TEST_SELECTION_POLICY)["totals"]["pending"] == 1
    before = len(client.bot.calls)
    assert asyncio.run(service.publish_experimental("single_settlement",new["prediction_id"],config(),client))["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(client.bot.calls)==before and ledger.get("single_settlement",new["prediction_id"])==settled


def test_devig_capture_records_actual_150_policy_without_provider_calls(tmp_path):
    from app.adaptive_lab import devig_integration as integration
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from app.lab_v2_shadow.market_consensus import current_market_consensus
    from tests.test_lab_v2_shadow import odds_payload
    source = odds_payload(fixture_id=7)
    families = current_market_consensus(source,fixture_id=7,retrieved_at=NOW,now=NOW)
    repo = ShadowEvidenceRepository(tmp_path/"shadow.db")
    try:
        result = integration.capture_cycle(repo,{7:(source,NOW,families)},
            {7:{"kickoff_utc":NOW+timedelta(hours=1)}},[],
            clock=NOW,runtime_clock=None,today_only=True)
        assert result["additional_provider_calls"] == 0
        captures = repo.all("devig_research")
        assert captures
        for capture in captures:
            assert capture["policy_context"]["single_policy"] == TEST_SELECTION_POLICY
            assert capture["policy_context"]["single_minimum"] == "1.50"
    finally:
        repo.close()


def test_controlled_cycle_sends_150_singles_and_keeps_policy_in_evidence(tmp_path,monkeypatch,capsys):
    import json
    from pathlib import Path
    from app.lab_v2_shadow import cli
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from tests.test_lab_v2_shadow import (
        _controlled_cycle_arguments, _install_controlled_cycle_fakes,
        _DeterministicReadyRunner, _RecordingTransport,
    )
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    original = _DeterministicReadyRunner.run
    rows = [quote(r,"1.50") for r in candidates()]
    async def report(self,**kwargs):
        assert kwargs.pop("today_only") is True
        result = await original(self,**kwargs)
        return {**result,"candidate_markets":rows,"ready_candidate_count":0}
    monkeypatch.setattr(_DeterministicReadyRunner,"run",report)
    assert cli.main([*_controlled_cycle_arguments(send=True),"--accuracy-combos"]) == 0
    output = json.loads(capsys.readouterr().out)["controlled_publication"]
    assert output["singles_sent"] == 3 and output["combos_sent"] == 1
    assert _RecordingTransport.calls == 4
    repo = ShadowEvidenceRepository(Path("var/lab_v2/shadow.db"))
    try:
        cycle, = repo.all("publication_cycle")
        assert cycle["controlled_publication"]["single_selection_policy"] == TEST_SELECTION_POLICY
        assert cycle["controlled_publication"]["minimum_published_decimal_odds"] == "1.50"
    finally:
        repo.close()
