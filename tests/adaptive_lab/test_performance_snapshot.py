from datetime import timedelta
from decimal import Decimal
import pytest
from app.adaptive_lab.performance import performance_snapshot, timing, candidate_timing_diagnostics
from app.adaptive_lab.health import persist_health
from .conftest import START


class Ledger:
    def __init__(self):
        self.rows = {}
    def add(self, kind, key, value):
        self.rows[(kind, key)] = value
    def all(self, kind):
        return [v for (k, _), v in self.rows.items() if k == kind]
    def get(self, kind, key):
        return self.rows.get((kind, key))


def single(ledger, key, status, odds="1.5", probability=".6"):
    p = {"prediction_id": key, "captured_odds": odds, "ensemble_probability": probability,
         "prepared_at_utc": START.isoformat(), "kickoff_utc": (START+timedelta(minutes=25)).isoformat(),
         "provider_origin_timestamp_utc": (START-timedelta(minutes=5)).isoformat(),
         "market": "HOME_WIN", "league_id": 7, "confidence": "HIGH", "market_fair_probability": ".55"}
    ledger.add("single_prediction", key, p)
    ledger.add("receipt", "single_prediction:"+key, {"status": "SENT", "sent_at_utc": START.isoformat()})
    if status:
        pnl = Decimal(odds)-1 if status == "WON" else -1 if status == "LOST" else 0
        ledger.add("single_settlement", key, {"status": status, "unit_result": str(pnl),
                   "settled_at_utc": (START+timedelta(hours=3)).isoformat()})
    return p


def test_published_ticket_denominators_pending_void_segments_and_negative_ev():
    ledger = Ledger()
    for key, status in enumerate(("WON", "WON", "LOST", "VOID", None)):
        single(ledger, str(key), status)
    single(ledger, "not-sent", "WON")
    ledger.add("receipt", "single_prediction:not-sent", {"status": "FAILED"})
    snapshot = performance_snapshot(ledger, now=START+timedelta(days=1))
    s = snapshot["SINGLE"]
    assert (s["total_published"], s["total_settled"], s["pending"]) == (5, 4, 1)
    assert (s["WON"], s["LOST"], s["VOID"]) == (2, 1, 1)
    assert s["hit_rate"] == pytest.approx(2/3)
    assert Decimal(s["flat_unit_pnl"]) == 0 and s["flat_roi"] == 0
    assert Decimal(s["average_odds"]) == Decimal(s["median_odds"]) == Decimal("1.5")
    assert s["brier"] == pytest.approx((.16+.16+.36)/3)
    assert snapshot["negative_ev"]["SINGLE"] == s
    segment = next(v for v in snapshot["segments"]["SINGLE"] if v["dimension"] == "lead_time_bucket")
    assert segment["value"] == "[25,45)" and segment["pending"] == 1
    assert snapshot["COMBO"]["predictive_calibration_observations"] == 0


def test_partial_void_combo_retains_flat_pnl_but_no_model_targets():
    ledger = Ledger()
    ledger.add("prediction", "c", {"prediction_id": "c", "combined_odds": "8",
        "estimated_probability_if_independent": ".1", "legs": []})
    ledger.add("receipt", "combo_prediction:c", {"status": "SENT", "sent_at_utc": START.isoformat()})
    ledger.add("settlement", "c", {"status": "PARTIAL_VOID", "partial_void": True, "unit_result": "3",
        "settled_at_utc": (START+timedelta(hours=3)).isoformat()})
    s = performance_snapshot(ledger, now=START+timedelta(days=1))
    assert s["COMBO"]["PARTIAL_VOID"] == s["COMBO"]["partial_void_count"] == 1
    assert s["COMBO"]["flat_roi"] == 3
    assert s["COMBO"]["brier"] is None
    assert s["negative_ev"]["COMBO"]["total_settled"] == 1


def test_asof_does_not_use_future_results_or_publications():
    ledger = Ledger()
    single(ledger, "future-result", "WON")
    single(ledger, "future-send", None)
    ledger.add("receipt", "single_prediction:future-send",
               {"status": "SENT", "sent_at_utc": (START+timedelta(hours=2)).isoformat()})
    result = performance_snapshot(ledger, now=START+timedelta(hours=1))
    assert result["SINGLE"]["total_published"] == result["SINGLE"]["pending"] == 1
    assert result["SINGLE"]["total_settled"] == 0
    assert result["status"] == "PARTIAL"


@pytest.mark.parametrize("lead,expected", [(0,"[0,10)"),(10,"[10,25)"),(25,"[25,45)"),
                                          (45,"[45,90)"),(90,"[90,inf)")])
def test_lead_boundaries_and_original_odds_age(lead, expected):
    p = {"prepared_at_utc": START.isoformat(), "kickoff_utc": (START+timedelta(minutes=lead)).isoformat(),
         "provider_origin_timestamp_utc": (START-timedelta(seconds=300)).isoformat()}
    value = timing(p)
    assert value["prematch_lead_minutes_bucket"] == expected
    assert value["odds_age_seconds"] == 300
    assert value["odds_age_seconds_bucket"] == "[300,900)"


def test_no_pick_diagnostics_use_candidate_denominator():
    ledger = Ledger()
    p = single(ledger, "1", None)
    rows = [{**p, "rejection_reasons": ["INVALID_MODEL_PROBABILITY"]}, p]
    result = candidate_timing_diagnostics(rows, selected_at=START)
    for g in result["groups"]:
        assert g["candidate_count"] == 2 and g["invalid_or_stale_rate"] == .5
        assert g["no_pick_reasons"] == {"INVALID_MODEL_PROBABILITY": 1}
    assert result["publication_policy_changed"] is False


def test_persisted_health_has_explicit_snapshot_availability(repo, tmp_path):
    value = persist_health(repo, {}, started=START, completed=START,
                           ledger_path=tmp_path/"absent.db")
    assert value["PERFORMANCE"]["status"] == "UNAVAILABLE"
    assert value["timing_diagnostics"]["groups"] == []
