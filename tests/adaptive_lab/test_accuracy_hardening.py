"""Research chronology, evidence boundaries and exact scenarios; no transports."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import runpy

import pytest
from app.adaptive_lab.contracts import digest
from app.live_lab.context_research import forecast, context_reasons
from app.live_lab.policy_research import compare_pool, market_evidence
from app.adaptive_lab.joint_scenarios import scenario_probability
from .conftest import START
from .test_live_quote_age_policy import data, rehash


def seal_state(candidate):
    s = candidate["state"]
    s["state_fingerprint"] = digest({k:v for k,v in s.items() if k != "state_fingerprint"})
    candidate["quote"]["state_fingerprint"] = s["state_fingerprint"]
    rehash(candidate["quote"])
    return candidate


def candidate(identity="a", p=".65", odds="1.7"):
    state, quote, _ = data(20)
    state.update(home_score=0, away_score=0, red_cards_home=0, red_cards_away=0,
                 events=[], minute=40, league_id=9)
    payloads = []
    for index, side in enumerate(("home", "away")):
        rows = []
        for i in range(5):
            rows.append({"fixture": {"id": 100+index*10+i,
                "date": (START-timedelta(days=i+2)).isoformat(), "status": {"short": "FT"}},
                "league": {"id": 9}, "teams": {side:{"id": state[side+"_team_id"]},
                    ("away" if side=="home" else "home"): {"id": 1000+i}},
                "score": {"fulltime": {"home": 2, "away": 1}}})
        payloads.append({"response": rows})
    rates = {"frozen_history_payloads": payloads, "source_fingerprint": digest(payloads),
             "available_at": START.isoformat(), "home_goal_rate": 2., "away_goal_rate": 1.,
             "home_sample": 5, "away_sample": 5}
    quote["decimal_odds"] = odds
    return seal_state({"prediction_id": identity, "fixture_id": state["fixture_id"],
        "state": state, "quote": quote, "rates": rates, "market": quote["market"],
        "ensemble_probability": p, "captured_odds": odds,
        "prepared_at_utc": START.isoformat(), "uncertainty_penalty": .07})


def test_venue_model_is_reproducible_and_does_not_mutate_input():
    p = candidate(); original = deepcopy(p)
    a = forecast(p, at=START)
    assert a["status"] == "RESEARCH_FORECAST"
    assert a["rates"]["home_goal_rate"] == 2 and a["rates"]["away_goal_rate"] == 1
    assert a == forecast(p, at=START) and p == original
    assert all(0 <= v <= 1 for v in a["probabilities"].values())
    assert not a["calibrated"] and a["optional_features_used"] == []


@pytest.mark.parametrize("cards", [1, 2, 3])
def test_no_invented_red_card_coefficient(cards):
    p = candidate(); s = p["state"]
    s["red_cards_away"] = cards
    s["events"] = [{"type": "Card", "detail": "Red Card", "time": {"elapsed": i+1},
                    "team": {"id": s["away_team_id"]}} for i in range(cards)]
    seal_state(p)
    r = forecast(p, at=START)
    assert "RED_CARD_EFFECT_NOT_ESTIMATED" in r["blockers"]
    assert r["probabilities"] is None


@pytest.mark.parametrize("kind,reason", [
    ("event_future", "EVENT_MINUTE_CONFLICT"), ("score", "GOAL_EVENT_SCORE_MISMATCH"),
    ("card_count", "RED_CARD_EVENT_COUNT_MISMATCH"), ("old_state", "CONTEXT_CLOCK_INVALID"),
    ("future_state", "CONTEXT_CLOCK_INVALID"), ("minute90", "REMAINING_REGULATION_TIME_UNSUPPORTED"),
    ("own_goal", "GOAL_EVENT_SEMANTICS_UNSUPPORTED"), ("missing_events", "EVENTS_UNAVAILABLE"),
    ("label", "LABEL_IN_MODEL_INPUT"), ("history_hash", "HISTORY_INTEGRITY_FAILURE"),
    ("future_history", "FUTURE_HISTORY"), ("target_history", "VENUE_COMPETITION_HISTORY_INSUFFICIENT"),
    ("duplicate_history", "DUPLICATE_OR_INVALID_HISTORY_ID"),
    ("thin_venue", "VENUE_COMPETITION_HISTORY_INSUFFICIENT")])
def test_context_fails_closed(kind, reason):
    p = candidate(); s, rates = p["state"], p["rates"]
    if kind in {"event_future", "own_goal"}:
        s["events"] = [{"type": "Goal", "detail": "Own Goal" if kind=="own_goal" else "Normal Goal",
                        "time": {"elapsed": 41 if kind=="event_future" else 20},
                        "team": {"id": s["home_team_id"]}}]
    if kind=="score": s["home_score"] = 1
    if kind=="card_count": s["red_cards_home"] = 1
    if kind=="old_state": s["retrieved_at"] = (START-timedelta(seconds=31)).isoformat()
    if kind=="future_state": s["retrieved_at"] = (START+timedelta(seconds=1)).isoformat()
    if kind=="minute90": s["minute"] = 90
    if kind=="missing_events": s["events"] = None
    if kind=="label": p["outcome"] = "WON"
    if kind=="future_history": rates["available_at"] = (START+timedelta(seconds=1)).isoformat()
    rows = rates["frozen_history_payloads"][0]["response"]
    if kind=="target_history": rows[0]["fixture"]["id"] = s["fixture_id"]
    if kind=="duplicate_history": rows.append(deepcopy(rows[0]))
    if kind=="thin_venue": rows.pop()
    rates["source_fingerprint"] = "wrong" if kind=="history_hash" else digest(rates["frozen_history_payloads"])
    seal_state(p)
    r = forecast(p, at=START)
    assert reason in r["blockers"] and r["probabilities"] is None


def test_excluded_upcoming_history_cannot_change_forecast():
    p = candidate(); before = forecast(p,at=START)
    future = deepcopy(p["rates"]["frozen_history_payloads"][0]["response"][0])
    future["fixture"]["id"] = 9999
    future["fixture"]["date"] = (START+timedelta(days=1)).isoformat()
    future["score"]["fulltime"] = {"home":30,"away":30}
    p["rates"]["frozen_history_payloads"][0]["response"].append(future)
    p["rates"]["source_fingerprint"] = digest(p["rates"]["frozen_history_payloads"])
    after = forecast(p,at=START)
    assert before["probabilities"] == after["probabilities"]
    assert after["history_excluded_counts"] == {"FUTURE_OR_TARGET_HISTORY":1}


def paired_market(p):
    opposite = deepcopy(p); opposite["prediction_id"] += "-opposite"
    opposite["market"] = "UNDER_1_5"
    opposite["quote"]["market"] = opposite["market"]
    opposite["quote"]["decimal_odds"] = "2.2"; opposite["captured_odds"] = "2.2"
    opposite["ensemble_probability"] = ".35"
    rehash(opposite["quote"])
    return [p, opposite]


def test_policy_a_negative_ev_and_b_value_filter_and_c_missing_calibration():
    pool = paired_market(candidate(odds="1.4"))
    r = compare_pool(pool, at=START)
    assert r["policies"]["A_CURRENT_60_70"]["nomination"] == "a"
    assert r["policies"]["B_VALUE_CONTROL"]["nomination"] is None
    assert r["policies"]["C_CONTEXT_CONFIDENCE"]["nomination"] is None
    assert "RESEARCH_NON_POSITIVE_EV" in r["policies"]["B_VALUE_CONTROL"]["blocker_counts"]
    assert not r["policies"]["A_CURRENT_60_70"]["final_refresh_verified"]
    assert compare_pool(list(reversed(pool)), at=START) == r


def test_policy_b_complete_market_and_no_future_fair_probability():
    pool = paired_market(candidate())
    r = compare_pool(pool, at=START)
    assert r["policies"]["B_VALUE_CONTROL"]["nomination"] == "a"
    assert market_evidence(pool[0], pool)["status"] == "AVAILABLE"
    other = deepcopy(pool[1]); other["quote"]["origin_timestamp"] = (START-timedelta(seconds=1)).isoformat()
    assert market_evidence(pool[0], [pool[0], other])["status"] == "COMPLETE_AS_OF_MARKET_UNAVAILABLE"
    assert compare_pool([pool[0]], at=START)["policies"]["B_VALUE_CONTROL"]["nomination"] is None


@pytest.mark.parametrize("p,eligible", [(".60",True),(".70",True),(".59999999999999999",False),(".70000000000000001",False)])
def test_exact_policy_boundary(p, eligible):
    r = compare_pool([candidate(p=p)], at=START)
    assert bool(r["policies"]["A_CURRENT_60_70"]["nomination"]) is eligible


def test_selection_rejects_future_labels_duplicates_and_respects_exposure():
    p = candidate()
    for mutation, reason in [(dict(outcome="WON"),"LABEL"),
        (dict(prepared_at_utc=(START+timedelta(seconds=1)).isoformat()),"FUTURE")]:
        with pytest.raises(ValueError, match=reason): compare_pool([{**p, **mutation}], at=START)
    with pytest.raises(ValueError, match="DUPLICATE"): compare_pool([p,p], at=START)
    previous = {**p, "known_at": (START-timedelta(seconds=1)).isoformat()}
    assert compare_pool([p],at=START,exposures=[previous])["policies"]["A_CURRENT_60_70"]["nomination"] is None


def scenario():
    legs = [{"fixture_id": 1, "market": "HOME_WIN", "model_probability": ".6",
             "kickoff_utc": (START+timedelta(hours=1)).isoformat()},
            {"fixture_id": 2, "market": "HOME_WIN", "model_probability": ".6",
             "kickoff_utc": (START+timedelta(hours=2)).isoformat()}]
    artifact = {"version": "FROZEN_JOINT_SCORE_SCENARIOS_V1", "scope": "RESEARCH_ONLY",
                "inputs_available_at": START.isoformat(), "created_at": START.isoformat(),
                "source_fingerprint": "synthetic-source", "model_generation": "synthetic-test",
                "fixture_ids": [1,2], "scenarios": [
                    {"probability": ".6", "scores": {"1": [1,0], "2": [1,0]}},
                    {"probability": ".4", "scores": {"1": [0,1], "2": [0,1]}}]}
    return legs, artifact


def test_scenario_joint_is_not_product_or_empirical_proof():
    legs, a = scenario()
    r = scenario_probability(legs,a,at=START,expected_fingerprint=digest(a))
    assert Decimal(r["scenario_probability"]) == Decimal(".6")
    assert Decimal(r["naive_joint_probability"]) == Decimal(".36")
    assert not r["positive_ev_proven"] and not r["production_eligible"]
    assert r == scenario_probability(legs,a,at=START,expected_fingerprint=digest(a))


def test_scenario_does_not_round_a_mass_error_away():
    legs, a = scenario()
    a["scenarios"][0]["probability"] = "0.60000000000000000000000000000000000000001"
    r = scenario_probability(legs,a,at=START,expected_fingerprint=digest(a))
    assert r["scenario_probability"] is None
    assert "SCENARIO_MASS_NOT_ONE" in r["blockers"]


@pytest.mark.parametrize("kind,reason", [
    ("missing", "VERIFIED_AS_OF_JOINT_SCENARIOS_UNAVAILABLE"),
    ("hash", "SCENARIO_ARTIFACT_INTEGRITY_FAILURE"),
    ("future", "FUTURE_SCENARIO_ARTIFACT"), ("mass", "SCENARIO_MASS_NOT_ONE"),
    ("negative", "SCENARIO_MASS_INVALID"), ("nan", "SCENARIO_MASS_INVALID"),
    ("duplicate", "DUPLICATE_SCENARIO"), ("score", "SCENARIO_SCORE_INVALID"),
    ("fixtures", "SCENARIO_FIXTURE_MISMATCH"), ("label", "LABEL_IN_SCENARIO_INPUT")])
def test_joint_fail_closed(kind, reason):
    legs, a = scenario()
    if kind=="future": a["created_at"] = (START+timedelta(seconds=1)).isoformat()
    if kind=="mass": a["scenarios"][0]["probability"] = ".5"
    if kind=="negative": a["scenarios"][0]["probability"] = "-.1"
    if kind=="nan": a["scenarios"][0]["probability"] = "NaN"
    if kind=="duplicate": a["scenarios"].append(deepcopy(a["scenarios"][0]))
    if kind=="score": a["scenarios"][0]["scores"]["1"] = [True,0]
    if kind=="fixtures": a["fixture_ids"] = [1,3]
    if kind=="label": a["target"] = "WON"
    r = scenario_probability(legs,None if kind=="missing" else a,at=START,
                             expected_fingerprint="wrong" if kind=="hash" else digest(a))
    assert reason in r["blockers"] and r["scenario_probability"] is None


def test_frozen_replay_reads_are_closed_before_any_selector(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module = runpy.run_path(str(root/"operations/live-combo-research/audit.py"))
    class DB:
        closed = False
        def execute(self,*args):
            assert not self.closed
            return []
        def close(self): self.closed = True
    db = DB()
    fn = module["read_replay_inputs"]
    monkeypatch.setitem(fn.__globals__,"readonly",lambda p:db)
    assert fn(Path("fake"),now=START,limit=1) == ([],{}, {})
    assert db.closed
    # This separation is the regression: selectors cannot hold the production
    # read transaction or exhaust its wall-clock progress deadline.
    import inspect
    body = inspect.getsource(module["frozen_replay"])
    assert "db.execute" not in body and "read_replay_inputs" in body
