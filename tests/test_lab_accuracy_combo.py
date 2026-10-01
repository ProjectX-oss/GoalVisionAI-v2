"""Offline regressions for explicit accuracy-combo policy and immutable delivery."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.lab_combo.service import LabComboService
from app.lab_v2_shadow.accuracy_combo import POLICY, review_accuracy_combo
from app.lab_v2_shadow.publication import prepare_v2_publications
from tests.test_lab_accuracy_delivery import accuracy_candidate
from tests.test_lab_v2_shadow import NOW, bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger, config, Transport


def candidates(count=3):
    result = []
    for i in range(count):
        item = accuracy_candidate()
        item.update(candidate_id=f"accuracy-combo-{i}", fixture_id=8000+i,
                    home_team_id=9000+2*i, away_team_id=9001+2*i)
        bind_candidate_evidence(item)
        result.append(item)
    return result


def prepare(store, rows=None, **kwargs):
    return prepare_v2_publications({"candidate_markets": rows if rows is not None else candidates()},
                                  store, now=kwargs.pop("now", NOW), label_origin=True,
                                  accuracy_combos=True, **kwargs)


def test_legacy_default_and_negative_ev_diagnostics(ledger):
    result = prepare_v2_publications({"candidate_markets": candidates()}, ledger, now=NOW, label_origin=True)
    assert len(result["singles"]) == 3
    assert result["combos"] == []
    assert result["combo_diagnostics"]["accuracy_single_non_positive_ev_count"] == 3
    assert result["combo_diagnostics"]["reason"] == "INSUFFICIENT_ELIGIBLE_COMBO_FIXTURES"


def test_nine_approved_candidates_produce_three_disjoint_combos(ledger):
    rows = candidates(9)
    before = deepcopy(rows)
    result = prepare(ledger, rows)
    assert rows == before
    assert len(result["singles"]) == len(result["combos"]) == 3
    assert result["combo_diagnostics"]["eligible_fixture_count"] == 9
    fixture_ids = [leg["fixture_id"] for combo in result["combos"] for leg in combo["legs"]]
    assert len(set(fixture_ids)) == 9
    for value in result["combos"]:
        assert value["policy"] == POLICY
        assert Decimal(value["combined_odds"]) == Decimal("1.30") ** 3
        assert Decimal(value["estimated_probability_if_independent"]) == Decimal(".72") ** 3
        assert Decimal(value["estimated_ev_if_independent"]) < 0
        assert review_accuracy_combo(value, now=NOW)["eligible"]
        message = ledger.get("preview", value["prediction_id"])["message"]
        assert "negatīvu" in message and "peļņa nav garantēta" in message
        assert all(leg["decision"] == leg["stage"] == "REJECTED" for leg in value["legs"])


def test_published_singles_remain_eligible_as_combo_legs(ledger):
    rows = candidates()
    singles = prepare_v2_publications({"candidate_markets": rows}, ledger, now=NOW, label_origin=True)["singles"]
    for value in singles:
        ledger.claim_publication("single_prediction", value, {"prediction_id": value["prediction_id"]})
    result = prepare(ledger, rows)
    assert not result["singles"]
    assert len(result["combos"]) == 1


def test_replay_preserves_frozen_reviews_and_previews(ledger):
    result = prepare(ledger)
    value = result["combos"][0]
    preview = ledger.get("preview", value["prediction_id"])
    replay = prepare(ledger, now=NOW+timedelta(minutes=1))["combos"][0]
    assert replay == value
    assert ledger.get("preview", value["prediction_id"]) == preview


@pytest.mark.parametrize("failure", ["insufficient", "shared_team", "same_fixture", "stale", "other_hard_failure"])
def test_ineligible_pool_does_not_force_combo(ledger, failure):
    rows = candidates()
    if failure == "insufficient":
        rows.pop()
    if failure == "shared_team":
        rows[2]["away_team_id"] = rows[0]["home_team_id"]
        bind_candidate_evidence(rows[2])
    if failure == "same_fixture":
        rows[2]["fixture_id"] = rows[0]["fixture_id"]
        bind_candidate_evidence(rows[2])
    if failure == "stale":
        rows[2]["provider_origin_timestamp_utc"] = (NOW-timedelta(hours=6)).isoformat()
        bind_candidate_evidence(rows[2])
    if failure == "other_hard_failure":
        rows[2]["hard_failures"].append("UNSUPPORTED_MARKET")
    assert not prepare(ledger, rows)["combos"]
    assert not ledger.all("prediction") and not ledger.all("claim")


@pytest.mark.parametrize("unknown", [False, True])
def test_delivery_claim_receipt_and_no_reuse(ledger, unknown):
    value = prepare(ledger)["combos"][0]
    transport = Transport(unknown=unknown)
    service = LabComboService(ledger, None, clock=lambda: NOW)
    result = asyncio.run(service.publish_experimental("combo_prediction", value["prediction_id"], config(), transport))
    assert result["status"] == ("DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED" if unknown else "SENT")
    assert len(transport.calls) == 1
    replay = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW+timedelta(minutes=6))
                        .publish_experimental("combo_prediction", value["prediction_id"], config(), transport))
    assert replay["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(transport.calls) == 1
    assert not prepare(ledger)["combos"]


@pytest.mark.parametrize("bad", ["quote", "aggregate", "probability", "identity", "leg_alias",
                                "source", "origin", "review", "preview", "bot", "policy"])
def test_delivery_revalidates_before_claim(ledger, bad, monkeypatch):
    value = prepare(ledger)["combos"][0]
    altered = deepcopy(value)
    if bad == "quote": altered["legs"][0]["quote_provenance_fingerprint"] = "bad"
    if bad == "aggregate": altered["combined_odds"] = "10"
    if bad == "probability": altered["estimated_probability_if_independent"] = ".999"
    if bad == "identity": altered["prediction_id"] = "lab-v2-combo-accuracy-bad"
    if bad == "leg_alias": altered["legs"][0]["odds"] = "9"
    if bad == "source": altered["legs"][0]["hard_failures"].append("UNSUPPORTED_MARKET")
    if bad == "origin": altered["legs"][0]["selection_origin"]["model_artifact"] = "bad"
    if bad == "review": altered["legs"][0]["accuracy_review_completed_at_utc"] = (NOW-timedelta(hours=1)).isoformat()
    if bad == "policy": altered["combo_selection_policy"] = "unknown"
    get = ledger.get
    def corrupted(kind, identity):
        if kind == "prediction" and identity == value["prediction_id"]:
            return altered
        if bad == "preview" and kind == "preview" and identity == value["prediction_id"]:
            return {"message": "tampered"}
        return get(kind, identity)
    monkeypatch.setattr(ledger, "get", corrupted)
    transport = Transport()
    if bad == "bot": transport.bot.username = "WrongBot"
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW)
                         .publish_experimental("combo_prediction", value["prediction_id"], config(), transport))
    assert not result["sent"] and not transport.calls and not ledger.all("claim")


def test_cli_flag_requires_label_without_starting_cycle():
    from app.lab_v2_shadow.cli import main
    with pytest.raises(SystemExit) as error:
        main(["controlled-cycle", "--accuracy-combos"])
    assert error.value.code == 2


@pytest.mark.parametrize("environment_opt_in", [False, True])
def test_controlled_cycle_opt_in_sends_singles_and_combo_with_persisted_diagnostics(tmp_path, monkeypatch, capsys, environment_opt_in):
    import json
    from app.lab_v2_shadow import cli
    from app.lab_combo.repository import ComboRepository
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from tests.test_lab_v2_shadow import (_install_controlled_cycle_fakes,
        _DeterministicReadyRunner, _RecordingTransport, _controlled_cycle_arguments)
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    original = _DeterministicReadyRunner.run
    async def report(self, **kwargs):
        result = await original(self, **kwargs)
        return {**result, "ready_candidate_count": 0, "candidate_markets": candidates()}
    monkeypatch.setattr(_DeterministicReadyRunner, "run", report)
    if environment_opt_in:
        monkeypatch.setenv("GOALVISION_LAB_ACCURACY_COMBOS", "1")
    assert cli.main(_controlled_cycle_arguments(send=True) + ([] if environment_opt_in else ["--accuracy-combos"])) == 0
    summary = json.loads(capsys.readouterr().out)
    publication = summary["controlled_publication"]
    assert publication["singles_sent"] == 3 and publication["combos_sent"] == 1
    assert publication["combo_diagnostics"]["policy"] == POLICY
    assert _RecordingTransport.calls == 4
    store = ShadowEvidenceRepository(Path("var/lab_v2/shadow.db"))
    try:
        evidence, = store.all("publication_cycle")
        assert evidence["controlled_publication"]["combo_diagnostics"]["prepared_count"] == 1
    finally:
        store.close()


@pytest.mark.parametrize("outcomes,status", [
    (["WON"]*3, "WON"), (["WON","LOST","WON"], "LOST"),
    (["VOID"]*3, "VOID"), (["WON","VOID","WON"], "PARTIAL_VOID"),
])
def test_existing_settlement_accepts_new_policy(ledger, outcomes, status):
    from app.lab_combo.settlement import aggregate, statistics
    value = prepare(ledger)["combos"][0]
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW)
                         .publish_experimental("combo_prediction", value["prediction_id"], config(), Transport()))
    assert result["sent"]
    results = [{"observation_id": leg["observation_id"], "outcome": outcome}
               for leg, outcome in zip(value["legs"], outcomes)]
    settled = aggregate(value, results, NOW+timedelta(days=2))
    assert settled["status"] == status
    ledger.append("settlement", value["prediction_id"], settled)
    assert statistics(ledger, published_only=True)[status] == 1
