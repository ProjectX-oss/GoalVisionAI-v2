"""Authorized active COMBO experiment: deterministic ranking and delivery, network denied."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json

import pytest

from app.lab_v2_shadow import combo_agreement as agreement
from app.lab_v2_shadow.combo_agreement_sources import Inputs
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_v2_shadow.accuracy_combo import review_accuracy_combo
from app.lab_combo.bot_routing import cohort_statistics
from app.lab_combo.service import LabComboService
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.contracts import seal
from app.real_match_lab_analysis.fingerprint import fingerprint
from tests.test_dixon_coles_forward import artifact, item, START
from tests.test_lab_v2_shadow import bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger
from tests.test_combo_bot_routing import routed, send, RoutedTransport, TOKEN
from tests.test_lab_combo_early_loss import Provider, payload

@pytest.fixture(autouse=True)
def active(monkeypatch):
    monkeypatch.setenv(agreement.FLAG, "1")
    monkeypatch.setenv("GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130", "1")
    monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_130", "1")
    monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_150", "1")
    monkeypatch.setenv("GOALVISION_LAB_TODAY_ONLY", "1")
    monkeypatch.setenv("GOALVISION_LAB_EARLY_COMBO_LOSS", "1")

@pytest.fixture
def sources(tmp_path, artifact):
    db = tmp_path / "research.db"
    store = ResearchStore(db)
    store.append("model", artifact["fingerprint"], artifact)
    store.close()
    repo = ShadowEvidenceRepository(tmp_path / "shadow.db")
    def make(rows=None):
        inputs = [item(i) for i in range(3)] if rows is None else rows
        for source in inputs:
            document = deepcopy(source["capture"]["source_consensus"])
            document["retrieved_at_utc"] = source["capture"]["captured_at"]
            repo.append("market_consensus",
                f'{document["fixture_id"]}:{document["market_family"]}:{fingerprint(document)}',
                document, created_at=START)
        return [c for source in inputs for c in source["candidates"].values()], Inputs(repo, model_path=db)
    yield make, repo, db
    repo.close()

def prepare(ledger, sources, *, now=START, items=None):
    rows, inputs = sources[0](items)
    return prepare_v2_publications({"candidate_markets": rows}, ledger, now=now,
        label_origin=True, accuracy_combos=True, combo_inputs=inputs)

def test_real_numeric_ranking_selects_agreement_over_high_ensemble(ledger, sources):
    values = [item(i) for i in range(3)]
    alternate = values[0]["candidates"]["OVER_3_5"]
    alternate["ensemble_probability"] = ".80"
    alternate["signals"][0]["probability"] = ".80"
    alternate["edge"] = str(Decimal(".80") - 1 / Decimal(alternate["captured_odds"]))
    bind_candidate_evidence(alternate)
    original = deepcopy(values)
    result = prepare(ledger, sources, items=values)
    combo, = result["combos"]
    assert values == original
    assert all(leg["market"] == "UNDER_3_5" for leg in combo["legs"])
    assert result["single_selection_policy"].endswith("MIN_ODDS_150")
    assert next(v for v in result["singles"] if v["fixture_id"] == 9000)["market"] == "OVER_3_5"
    assert combo["policy"] == agreement.POLICY
    assert combo["statistics_cohort"] == agreement.COHORT
    assert combo["score_is_calibrated_probability"] is False
    assert combo["combined_odds"] == str(Decimal("1.30") ** 3)
    assert review_accuracy_combo(combo, now=START)["eligible"]
    assert "COMBO DC tests" in ledger.get("preview", combo["prediction_id"])["message"]

def test_exact_replay_no_refit_and_private_fake_delivery(ledger, sources, routed, monkeypatch):
    from app.dixon_coles_forward import model
    monkeypatch.setattr(model, "fit", lambda *a, **k: pytest.fail("publication must not fit"))
    first = prepare(ledger, sources)["combos"][0]
    replay = prepare(ledger, sources)["combos"][0]
    assert first == replay
    client = RoutedTransport(TOKEN)
    out = send(ledger, "combo_prediction", first["prediction_id"], routed[2], client, now=START)
    assert out["sent"] and len(client.calls) == 1
    assert client.calls[0]["chat_id"] == routed[2].chat_id
    assert not prepare(ledger, sources)["combos"]
    assert send(ledger, "combo_prediction", first["prediction_id"], routed[2], client, now=START)["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(client.calls) == 1

@pytest.mark.parametrize("case", ["missing_model", "missing_market", "stale", "unknown_team",
    "league", "floor", "tomorrow", "shared_team", "quality", "excluded", "mode", "no_inputs"])
def test_fail_closed_without_old_rank_fallback(ledger, sources, case, monkeypatch):
    values = [item(i) for i in range(3)]
    if case == "missing_model": sources[2].unlink()
    if case == "missing_market":
        rows, inputs = sources[0](values)
        inputs.repository = ShadowEvidenceRepository(sources[2].parent / "empty.db")
    if case == "unknown_team":
        for c in values[0]["candidates"].values(): c["home_team_id"] = 555
    if case == "league":
        for c in values[0]["candidates"].values(): c["league_id"] = 999
    if case == "floor": values[0] = item(0, odds="1.29999999999999999999")
    if case == "tomorrow":
        for c in values[0]["candidates"].values():
            c["kickoff_utc"] = (START + timedelta(days=1)).isoformat()
    if case == "shared_team":
        for c in values[0]["candidates"].values(): c["home_team_id"] = 3
    if case == "quality":
        for c in values[0]["candidates"].values(): c["hard_failures"].append("UNSUPPORTED_MARKET")
    if case == "excluded": values[0] = item(0, fixture_id=1602097)
    if case == "mode": monkeypatch.setenv(agreement.FLAG, "yes")
    if case not in {"missing_market"}: rows, inputs = sources[0](values)
    if case == "no_inputs": inputs = None
    now = START + timedelta(seconds=901) if case == "stale" else START
    result = prepare_v2_publications({"candidate_markets": rows}, ledger, now=now,
        label_origin=True, accuracy_combos=True, combo_inputs=inputs)
    assert not result["combos"] and not ledger.all("prediction")
    assert result["combo_diagnostics"]["policy"] == agreement.POLICY
    if case == "missing_market": inputs.repository.close()

@pytest.mark.parametrize("case", ["score", "dc", "book", "model", "candidate", "aggregate", "cohort", "future"])
def test_tampered_frozen_evidence_rejected_before_claim(ledger, sources, routed, case, monkeypatch):
    combo = prepare(ledger, sources)["combos"][0]
    changed = deepcopy(combo)
    e = changed["legs"][0]["combo_agreement"]
    if case == "score": e["ranking_score"] = ".99"
    if case == "dc": e["probabilities"]["DIXON_COLES"] = ".99"
    if case == "book": e["bookmaker_id"] = 888
    if case == "model": e["artifact"]["parameters"]["base"] += .1
    if case == "candidate": changed["legs"][0]["league_id"] = 222
    if case == "aggregate": changed["ranking_score_if_independent"] = ".99"
    if case == "cohort": changed["statistics_cohort"] = "old"
    if case == "future": e["selected_at"] = (START + timedelta(minutes=1)).isoformat()
    # Even an internally rehashed record must reproduce the actual numbers.
    e.pop("fingerprint")
    changed["legs"][0]["combo_agreement"] = seal(e)
    assert not review_accuracy_combo(changed, now=START)["eligible"]
    original_get = ledger.get
    monkeypatch.setattr(ledger, "get", lambda kind, key: changed if kind == "prediction"
                        and key == combo["prediction_id"] else original_get(kind, key))
    client = RoutedTransport(TOKEN)
    assert not send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["sent"]
    assert not client.calls and not ledger.all("claim")

def test_roll_back_blocks_new_attempts_but_keeps_cohort_reader(ledger, sources, routed, monkeypatch):
    combo = prepare(ledger, sources)["combos"][0]
    client = RoutedTransport(TOKEN)
    monkeypatch.setenv(agreement.FLAG, "0")
    result = send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)
    assert result["status"] == "COMBO_ACTIVE_SELECTION_POLICY_MISMATCH"
    assert not client.calls and not ledger.all("claim")
    monkeypatch.setenv(agreement.FLAG, "1")
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["sent"]
    monkeypatch.setenv(agreement.FLAG, "0")
    new = cohort_statistics(ledger, routed[2].route, agreement=True)
    old = cohort_statistics(ledger, routed[2].route, agreement=False)
    assert new["total_published"] == 1 and new["pending"] == 1
    assert new["selection_cohort"] == agreement.COHORT
    assert old["total_published"] == 0
    assert cohort_statistics(ledger, routed[2].route)["total_published"] == 1

def test_reader_preserves_source_bytes_and_expired_models_fail_closed(sources, monkeypatch):
    import hashlib
    before = hashlib.sha256(sources[2].read_bytes()).hexdigest()
    rows, inputs = sources[0]()
    result = inputs.score(rows[0], now=START)
    assert result["artifact"]["purpose"] == "PROSPECTIVE_RESEARCH_ONLY"
    assert result["artifact"]["selection_effect"] == "NONE"
    assert hashlib.sha256(sources[2].read_bytes()).hexdigest() == before
    with pytest.raises(ValueError):
        agreement.evidence(rows[0], result["artifact"], result["consensus"], now=START+timedelta(days=2))

def test_permutation_determinism(ledger, sources):
    rows, inputs = sources[0]()
    a = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, combo_inputs=inputs)
    b = prepare_v2_publications({"candidate_markets": list(reversed(rows))}, ledger, now=START,
        label_origin=True, accuracy_combos=True, combo_inputs=inputs)
    assert a["combos"] == b["combos"]

def test_replay_does_not_renew_frozen_evidence(ledger, sources):
    first = prepare(ledger, sources)["combos"][0]
    later = prepare(ledger, sources, now=START+timedelta(minutes=1))["combos"][0]
    assert first == later

def test_active_mode_blocks_old_prepared_selection_before_claim(ledger, sources, routed, monkeypatch):
    monkeypatch.setenv(agreement.FLAG, "0")
    old = prepare(ledger, sources)["combos"][0]
    monkeypatch.setenv(agreement.FLAG, "1")
    client = RoutedTransport(TOKEN)
    outcome = send(ledger, "combo_prediction", old["prediction_id"], routed[2], client, now=START)
    assert outcome["status"] == "COMBO_ACTIVE_SELECTION_POLICY_MISMATCH"
    assert not client.calls and not ledger.all("claim")

@pytest.mark.parametrize("photo", [False, True])
def test_early_loss_reply_and_remaining_legs_after_rollback(ledger, sources, routed, monkeypatch, tmp_path, photo):
    from tests.test_settlement_replies import transport
    from app.lab_combo.presentation import ResultImagePaths
    monkeypatch.setenv("GOALVISION_LAB_SETTLEMENT_REPLIES", "1")
    values = [item(i) for i in range(3)]
    prepared = prepare(ledger, sources, items=values)
    assert prepared["combos"], json.dumps({"diag": prepared["combo_diagnostics"], "blockers": prepared["publication_blockers"], "single": prepared["single_publication_blockers"]})
    combo = prepared["combos"][0]
    client = transport(private=True)
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["sent"]
    receipt = ledger.get("receipt", "combo_prediction:"+combo["prediction_id"])
    monkeypatch.setenv(agreement.FLAG, "0")
    later = START+timedelta(hours=2, minutes=35)
    service = LabComboService(ledger, None, clock=lambda: later, early_combo_loss=True)
    asyncio.run(service.check_results(Provider({9000: payload(9000, score=(2, 2)), 9001: payload(9001, "NS"), 9002: payload(9002, "NS")})))
    settled = ledger.get("settlement", combo["prediction_id"])
    assert settled["status"] == "LOST" and len(settled["pending_legs"]) == 2
    preview = ledger.get("settlement_preview", combo["prediction_id"])
    assert preview["statistics"]["selection_cohort"] == agreement.COHORT
    assert preview["statistics"]["LOST"] == 1
    assert cohort_statistics(ledger, routed[2].route, agreement=False)["total_settled"] == 0
    if photo:
        image = tmp_path/"lost.png"
        image.write_bytes(b"fixture-image")
        service.result_images = ResultImagePaths(image, image, image)
    outcome = asyncio.run(service.publish_experimental("combo_settlement", combo["prediction_id"], routed[2], client))
    assert outcome["sent"], outcome
    assert client.bot.calls[-1][1]["reply_parameters"].message_id == receipt["message_id"]
    assert client.bot.calls[-1][0] == ("photo" if photo else "text")
    frozen = deepcopy(settled)
    final_time = START+timedelta(hours=7)
    asyncio.run(LabComboService(ledger, None, clock=lambda: final_time, early_combo_loss=False)
        .check_results(Provider({9001: payload(9001, score=(0, 0)), 9002: payload(9002, score=(1, 0))})))
    assert ledger.get("settlement", combo["prediction_id"]) == frozen
    assert ledger.get("combo_result_detail", combo["prediction_id"]) is not None
    assert cohort_statistics(ledger, routed[2].route, agreement=True)["LOST"] == 1

def test_reader_capacity_and_sql_failure_do_not_suppress_singles(ledger, sources, monkeypatch):
    import sqlite3
    rows, inputs = sources[0]()
    for c in rows:
        if c["market"] == "UNDER_3_5":
            c["captured_odds"] = c["offered_odds"] = "1.50"
            c["edge"] = str(Decimal(c["ensemble_probability"]) - 1 / Decimal("1.50"))
            bind_candidate_evidence(c)
    monkeypatch.setattr(inputs, "score", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("offline")))
    output = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, combo_inputs=inputs)
    assert len(output["singles"]) == 3 and not output["combos"]

def test_budget_discards_partial_combo_pool(ledger, sources, monkeypatch):
    rows, inputs = sources[0]()
    original = inputs.score
    count = 0
    def bounded(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            raise ValueError("COMBO_AGREEMENT_BUDGET_EXHAUSTED")
        return original(*args, **kwargs)
    monkeypatch.setattr(inputs, "score", bounded)
    output = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, combo_inputs=inputs)
    assert not output["combos"] and not ledger.all("prediction")
    assert output["combo_diagnostics"]["reason"] == "COMBO_AGREEMENT_BUDGET_EXHAUSTED"

def test_historical_losses_stay_in_previous_cohort_and_all_time(ledger, sources, routed):
    route = routed[2].route
    old = {"prediction_id": "historic", "combined_odds": "3", "legs": [],
           "combo_selection_policy": "LAB_COMBO_ACCURACY_FROM_SINGLES_V1"}
    ledger.append("prediction", "historic", old)
    ledger.append("claim", "combo_prediction:historic", {"chat_id": route["chat_id"], "delivery_route": route})
    ledger.append("receipt", "combo_prediction:historic", {"chat_id": route["chat_id"],
        "delivery_route": route, "status": "SENT", "sent": True, "message_id": 8})
    ledger.append("settlement", "historic", {"prediction_id": "historic", "status": "LOST", "unit_result": "-1"})
    combo = prepare(ledger, sources)["combos"][0]
    client = RoutedTransport(TOKEN)
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["sent"]
    previous = cohort_statistics(ledger, route, agreement=False)
    current = cohort_statistics(ledger, route, agreement=True)
    union = cohort_statistics(ledger, route)
    assert previous["LOST"] == 1 and previous["hypothetical_profit_loss"] == "-1"
    assert current["LOST"] == 0 and current["pending"] == 1
    assert union["total_published"] == 2 and union["LOST"] == 1 and union["pending"] == 1
