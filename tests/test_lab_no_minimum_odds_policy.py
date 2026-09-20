"""LAB odds-floor regressions; all persistence uses disposable databases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.lab_combo.engine import select_combo
from app.lab_combo.repository import ComboRepository
from app.lab_v2_shadow.ensemble import EnsembleSignal, evaluate_ensemble
from app.lab_v2_shadow.market_consensus import current_market_consensus
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.official_prediction_pipeline import DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY
from app.official_prediction_selection import DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY
from app.quality_gate import DEFAULT_OFFICIAL_QUALITY_GATE_POLICY


NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def _signals(*probabilities: str) -> list[EnsembleSignal]:
    names = (
        "CURRENT_MARKET_CONSENSUS",
        "PI_RATINGS",
        "API_FOOTBALL_PREDICTION",
        "CURRENT_MATCH_INTELLIGENCE",
    )
    return [
        EnsembleSignal(
            name=name,
            market="HOME_WIN",
            probability=Decimal(probability),
            selection="HOME_WIN",
            reliability=Decimal("0.90"),
            availability="AVAILABLE",
            provenance=f"current-{name.lower()}",
        )
        for name, probability in zip(names, probabilities, strict=True)
    ]


def _ready_candidate(fixture_id: int, odds: str) -> dict[str, object]:
    return {
        "candidate_id": f"candidate-{fixture_id}",
        "policy": "LAB_V2_BROAD_COVERAGE_ENSEMBLE_V3",
        "fixture_id": fixture_id,
        "market": "HOME_WIN",
        "decision": "APPROVED",
        "stage": "READY_TO_PUBLISH",
        "home_team": f"Home {fixture_id}",
        "away_team": f"Away {fixture_id}",
        "home_team_id": fixture_id * 10,
        "away_team_id": fixture_id * 10 + 1,
        "kickoff_utc": (NOW + timedelta(minutes=30)).isoformat(),
        "captured_odds": odds,
        "offered_odds": odds,
        "quote_provenance_fingerprint": f"current-quote-{fixture_id}",
        "edge": "0.06",
        "ensemble_probability": str(Decimal(1) / Decimal(odds) + Decimal("0.06")),
        "confidence": "MEDIUM",
        "experimental_confidence": "MEDIUM",
        "provider_type": "API_FOOTBALL_CURRENT_ODDS",
        "provider_origin_timestamp_utc": NOW.isoformat(),
        "goalvision_retrieved_at_utc": NOW.isoformat(),
        "final_review_completed_at_utc": NOW.isoformat(),
        "league": f"League {fixture_id}",
        "capability_tier": "TIER_C_BASIC",
        "odds_band": "BELOW_1.70",
        "pi_available": "AVAILABLE",
        "pi_agreement": "AGREEMENT",
        "api_prediction_relation": "AGREEMENT",
        "market_consensus_relation": "AGREEMENT",
        "lineup_confirmed": "NOT_SUPPORTED",
        "ensemble_decision_class": "APPROVED",
    }


def _combo_legs() -> list[dict[str, object]]:
    result = []
    for fixture_id, odds in zip((1, 2, 3), ("1.10", "1.15", "1.20"), strict=True):
        result.append({
            "observation_id": f"observation-{fixture_id}",
            "fixture_id": str(fixture_id),
            "home_team_id": str(fixture_id * 10),
            "away_team_id": str(fixture_id * 10 + 1),
            "competition_id": str(fixture_id),
            "odds": odds,
            "probability": "0.96",
            "expected_value": "0.06",
            "quote": {"bookmaker_name": "Current Book"},
        })
    return result


def test_lab_single_at_1_25_can_pass_all_non_odds_quality_gates() -> None:
    decision = evaluate_ensemble(
        "HOME_WIN",
        Decimal("1.25"),
        _signals("0.85", "0.86", "0.87", "0.86"),
    )
    assert decision.decision == "APPROVED"
    assert decision.edge is not None and decision.edge > Decimal("0.04")
    assert "SINGLE_ODDS_BELOW_1_70" not in decision.rejection_reasons


def test_lab_single_at_1_25_still_fails_insufficient_edge() -> None:
    decision = evaluate_ensemble(
        "HOME_WIN",
        Decimal("1.25"),
        _signals("0.81", "0.82", "0.83", "0.82"),
    )
    assert decision.decision == "REJECTED"
    assert "ENSEMBLE_EDGE_BELOW_0_04" in decision.rejection_reasons
    assert "SINGLE_ODDS_BELOW_1_70" not in decision.rejection_reasons


def test_three_low_odds_legs_form_combo_below_two(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ledger_path = tmp_path / "var" / "lab_combo" / "ledger.db"
    ledger_path.parent.mkdir(parents=True)
    ledger = ComboRepository(ledger_path)
    try:
        report = {"candidate_markets": [
            _ready_candidate(1, "1.10"),
            _ready_candidate(2, "1.15"),
            _ready_candidate(3, "1.20"),
        ]}
        prepared = prepare_v2_publications(report, ledger, now=NOW)
        assert len(prepared["combos"]) == 1
        combo = prepared["combos"][0]
        assert len(combo["legs"]) == 3
        assert all(Decimal(leg["captured_odds"]) < Decimal("1.70") for leg in combo["legs"])
        assert Decimal(combo["combined_odds"]) == Decimal("1.518000")
        assert Decimal(combo["combined_odds"]) < Decimal("2.00")
    finally:
        ledger.close()


def test_low_odds_still_fail_signal_disagreement_edge_freshness_and_correlation() -> None:
    insufficient = evaluate_ensemble(
        "HOME_WIN", Decimal("1.25"), _signals("0.86", "0.86", "0.86", "0.86")[:2]
    )
    assert "INSUFFICIENT_INDEPENDENT_SIGNALS" in insufficient.rejection_reasons

    disagreement_signals = _signals("0.94", "0.55", "0.56", "0.93")
    disagreement_signals[1] = EnsembleSignal(
        "PI_RATINGS", "HOME_WIN", Decimal("0.55"), "AWAY_WIN",
        Decimal("0.90"), "AVAILABLE", "current-pi",
    )
    disagreement = evaluate_ensemble("HOME_WIN", Decimal("1.25"), disagreement_signals)
    assert "MATERIAL_SIGNAL_DISAGREEMENT" in disagreement.rejection_reasons

    stale_payload = {"response": [{
        "fixture": {"id": 7},
        "update": (NOW - timedelta(hours=4)).isoformat(),
        "bookmakers": [{
            "id": bookmaker_id,
            "name": bookmaker,
            "bets": [{"name": "Match Winner", "values": [
                {"value": "Home", "odd": "1.25"},
                {"value": "Draw", "odd": "5.00"},
                {"value": "Away", "odd": "10.00"},
            ]}],
        } for bookmaker_id, bookmaker in ((3, "Betfair"), (4, "Pinnacle"))],
    }]}
    stale = current_market_consensus(
        stale_payload, fixture_id=7, retrieved_at=NOW, now=NOW,
    )["1X2"]
    assert stale.status == "STALE_CURRENT_ODDS"

    correlated = _combo_legs()
    correlated[1]["home_team_id"] = correlated[0]["home_team_id"]
    combo, blockers = select_combo(correlated, NOW)
    assert combo is None
    assert blockers == ["CORRELATION_OR_BOOKMAKER_CONFLICT"]


def test_official_odds_policy_is_unchanged() -> None:
    assert DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.minimum_decimal_odds == Decimal("1.60")
    assert DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY.minimum_odds == Decimal("1.60")
    assert DEFAULT_OFFICIAL_QUALITY_GATE_POLICY.minimum_single_odds == Decimal("1.60")
    assert DEFAULT_OFFICIAL_QUALITY_GATE_POLICY.minimum_combo_odds == Decimal("2.00")
