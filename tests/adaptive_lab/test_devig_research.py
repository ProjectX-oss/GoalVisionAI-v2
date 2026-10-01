from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from math import sqrt
import pytest
from app.adaptive_lab.devig_research import devig, capture, forward_metrics
from app.lab_v2_shadow.market_consensus import current_market_consensus
from app.lab_v2_shadow.runner import _plain
from dataclasses import asdict
from .conftest import START


def document():
    source = {"response": [{"fixture": {"id": 7}, "update": START.isoformat(), "bookmakers": [
        {"id": i, "name": str(i), "bets": [{"name": "Match Winner", "values": [
            {"value": "Home", "odd": "2"}, {"value": "Draw", "odd": "3.5"},
            {"value": "Away", "odd": "4"}]}]} for i in (1, 2)]}]}
    consensus = current_market_consensus(source, fixture_id=7, retrieved_at=START, now=START)["1X2"]
    return {**_plain(asdict(consensus)), "source": "API_FOOTBALL_CURRENT_ODDS",
            "historical_bookmaker_odds_used": False}


def test_fair_symmetric_market_and_shin_binary_additive_identity():
    fair = devig({"HOME_WIN": "3", "DRAW": "3", "AWAY_WIN": "3"})
    for method in fair["methods"].values():
        assert sum(map(float, method["probabilities"].values())) == pytest.approx(1)
        assert all(float(p) == pytest.approx(1/3) for p in method["probabilities"].values())
    binary = devig({"BTTS_YES": "1.8", "BTTS_NO": "2"})
    expected = 1/1.8 - (1/1.8 + .5 - 1)/2
    assert float(binary["methods"]["SHIN"]["probabilities"]["BTTS_YES"]) == pytest.approx(expected)


def test_power_root_and_epc_equal_standard_error_reduction():
    odds = {"HOME_WIN": "2", "DRAW": "3.5", "AWAY_WIN": "4"}
    result = devig(odds)
    power = result["methods"]["POWER"]
    beta = power["parameters"]["exponent"]
    assert beta > 1
    assert sum(float(v)**(-beta) for v in odds.values()) == pytest.approx(1, abs=1e-12)
    epc = result["methods"]["OO_EPC"]
    shifts = [(1/float(o)-float(epc["probabilities"][k]))/sqrt(1-1/float(o)) for k,o in odds.items()]
    assert max(shifts)-min(shifts) < 1e-12


def test_shin_underround_is_not_claimed_and_epc_fallback_is_explicit():
    under = devig({"BTTS_YES": "2.01", "BTTS_NO": "2.01"})
    assert under["methods"]["SHIN"]["status"] == "NOT_APPLICABLE"
    longshot = devig({"HOME_WIN": "1.1", "DRAW": "6", "AWAY_WIN": "100"})
    assert longshot["methods"]["OO_EPC"]["status"] == "FALLBACK_MULTIPLICATIVE"
    assert longshot["methods"]["OO_EPC"]["probabilities"] == longshot["methods"]["MULTIPLICATIVE"]["probabilities"]


@pytest.mark.parametrize("odds", [{"HOME_WIN":"2"}, {"BTTS_YES":"NaN","BTTS_NO":"2"},
                                  {"BTTS_YES":"1","BTTS_NO":"2"}])
def test_incomplete_or_invalid_market_fails_closed(odds):
    with pytest.raises(ValueError):
        devig(odds)


def test_capture_is_current_bound_immutable_and_not_a_selection_input():
    source = document()
    before = deepcopy(source)
    result = capture(source, captured_at=START, kickoff=START+timedelta(hours=1))
    assert source == before and result["status"] == "AVAILABLE"
    assert len(result["bookmakers"]) == 2 and result["selection_effect"] == "NONE"
    bad = deepcopy(source)
    bad["quotes"][0]["decimal_odds"] = "99"
    assert capture(bad, captured_at=START, kickoff=START+timedelta(hours=1))["status"] == "BLOCKED"
    assert capture(source, captured_at=START+timedelta(hours=5),
                   kickoff=START+timedelta(hours=6))["status"] == "BLOCKED"


def test_forward_first_capture_no_duplicate_samples_no_early_result():
    c = capture(document(), captured_at=START, kickoff=START+timedelta(hours=1))
    result = {"fixture_id": 7, "status": "RESOLVED", "home_goals": 1, "away_goals": 0,
              "settled_at": (START+timedelta(hours=3)).isoformat(), "source_fingerprint":"synthetic-result-7"}
    assert forward_metrics([c], [result], now=START)["status"] == "NEEDS_MORE_EVIDENCE"
    m = forward_metrics([c, c], [result], now=START+timedelta(days=1))
    assert m["fixture_count"] == 1 and m["model_learning_observations"] == 0
    assert m["methods"]["SHIN"]["book_market_samples"] == 2
    assert m["methods"]["SHIN"]["probability_observations"] == 6


def test_forward_capture_integrity_and_result_provenance():
    c=capture(document(),captured_at=START,kickoff=START+timedelta(hours=1))
    c["bookmakers"][0]["methods"]["SHIN"]["probabilities"]["HOME_WIN"]="0.99"
    with pytest.raises(ValueError,match="RESEARCH_CAPTURE_REQUIRED"):
        forward_metrics([c],[],now=START)
