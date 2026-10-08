"""Offline isolation, chronology and statistical-contract tests."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import importlib.util
import os
from pathlib import Path
import sqlite3
import pytest

from app.adaptive_lab.combo_evidence import coupon_report
from app.adaptive_lab.combo_research import (
    joint_diagnostics, clustered_interval, replay, score_replay,
    MemoryLedger, performance_comparison, quality_value_screen,
)
from app.adaptive_lab.contracts import digest, learning_source
from app.live_lab.research import candidate_diagnostic, report as live_report, age_bucket
from tests.test_prematch_quality_evidence import Ledger, prediction, result, NOW as REPORT_NOW
from tests.test_private_single_170 import candidate
from tests.test_lab_v2_shadow import NOW

spec=importlib.util.spec_from_file_location("live_combo_audit",
    Path(__file__).parents[1]/"operations/live-combo-research/audit.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def live_candidate(age=25, blockers=("STALE_LIVE_ODDS",)):
    return {"candidate_id":"test","fixture_id":1,"market":"HOME_WIN",
            "prepared_at_utc":NOW.isoformat(),"captured_odds":"2","ensemble_probability":".6",
            "quote":{"origin_timestamp":(NOW-timedelta(seconds=age)).isoformat(),
                     "retrieved_at":NOW.isoformat()},
            "blockers":list(blockers)}


@pytest.mark.parametrize("age,expected",[(0,"0-10"),(10,"0-10"),(10.01,"10-20"),
    (20,"10-20"),(30,"20-30"),(45,"30-45"),(60,"45-60"),(61,">60"),(-1,"INVALID_FUTURE"),(None,"MISSING")])
def test_exact_bucket_boundaries(age, expected):
    assert age_bucket(age)==expected


def test_counterfactual_retains_ev_and_invalid_provenance():
    one=candidate_diagnostic(live_candidate())
    assert one["counterfactual_initial_ready"]=={"20":False,"30":True,"45":True}
    blocked=candidate_diagnostic(live_candidate(blockers=("STALE_LIVE_ODDS","NON_POSITIVE_EV")))
    assert not any(blocked["counterfactual_initial_ready"].values())
    assert not blocked["age_only_rejected"]
    assert not any(candidate_diagnostic(live_candidate(-1))["counterfactual_initial_ready"].values())
    row=live_candidate();row["quote"]["origin_timestamp"]=None
    assert not any(candidate_diagnostic(row)["counterfactual_initial_ready"].values())


def test_live_receipts_results_and_no_fabricated_http_latency():
    row=live_candidate()
    receipt={"selection_id":"test","status":"SENT","sent_at_utc":NOW.isoformat()}
    claim={"selection_id":"test","created_at":NOW.isoformat()}
    future={"prediction_id":"test","status":"WON","settled_at_utc":(NOW+timedelta(hours=1)).isoformat()}
    r=live_report([row],[],[],[receipt],[claim],[future],as_of=NOW,since=NOW-timedelta(days=1))
    assert r["confirmed_publications"]==1 and r["claims_without_receipt"]==0
    assert r["result_counts"]=={"PENDING":1}
    assert r["http_latency_seconds"] is None
    assert r["provider_calls_initiated"]==r["telegram_sends_initiated"]==0


def test_joint_bounds_are_not_an_estimated_correlation():
    legs=[{"fixture_id":1,"home_team_id":1,"away_team_id":2,"model_probability":".7","market":"OVER_2_5","league_id":1},
          {"fixture_id":2,"home_team_id":3,"away_team_id":4,"model_probability":".8","market":"UNDER_3_5","league_id":1}]
    r=joint_diagnostics(legs)
    assert Decimal(r["naive_joint_probability"])==Decimal(".56")
    assert Decimal(r["frechet_lower_bound"])==Decimal(".5")
    assert Decimal(r["frechet_upper_bound"])==Decimal(".7")
    assert r["correlation_adjusted_probability"] is None
    assert not r["risk_screen_is_joint_model"]
    assert "SHARED_LEAGUE" in r["risk_flags"] and "SHARED_MARKET_FAMILY" in r["risk_flags"]
    legs[1]["home_team_id"]=2
    assert "SHARED_TEAM" in joint_diagnostics(legs)["risk_flags"]
    legs[1]["model_probability"]="0"
    assert joint_diagnostics(legs)["naive_joint_probability"] is None


def test_coupon_failure_detail_unknown_is_not_a_loss():
    p=prediction();p["legs"][0].update(market="OVER_2_5",observation_id="leg1")
    p["legs"][1].update(market="BTTS_YES",observation_id="leg2")
    r=result("LOST","-1",legs=[{"observation_id":"leg1","fixture_id":1,"market":"OVER_2_5",
                              "outcome":"LOST","retrieved_at_utc":"2026-10-07T13:00:00+00:00"}])
    ledger=Ledger([p],{"one":r})
    output=performance_comparison(ledger,now=REPORT_NOW)
    row=output["rows"][0]
    assert row["losing_leg_count_known"]==1
    assert row["unknown_leg_count"]==1
    assert output["overall"]["median_combined_odds"]=="3.06"
    assert output["overall"]["maximum_known_losing_streak_publication_order"]==1
    assert not learning_source(row)
    assert output["paired_strategy_score_delta"] is None


def test_future_leg_result_excluded_and_input_not_mutated():
    p=prediction();p["legs"][0].update(market="OVER_2_5",observation_id="leg1")
    results={"one":result("LOST","-1"),"leg1":{"fixture_id":1,"market":"OVER_2_5","outcome":"LOST",
             "retrieved_at_utc":"2026-10-08T13:00:00+00:00"}}
    ledger=Ledger([p],results);before=deepcopy(ledger.__dict__)
    r=coupon_report(ledger,now=REPORT_NOW)
    assert r["rows"][0]["legs"][0]["outcome"]=="UNKNOWN"
    assert ledger.__dict__==before


def test_cluster_gate_counts_dependencies_not_coupon_volume():
    rows=[]
    for i in range(40):
        rows.append({"status":"LOST","flat_unit_pnl":"-1","published_at":(NOW+timedelta(days=i)).isoformat(),
                     "legs":[{"fixture_id":1}]})
    r=clustered_interval(rows)
    assert r["clusters"]==1
    assert r["roi_95_interval"] is None and not r["ranking_eligible"]
    for i,row in enumerate(rows):row["legs"][0]["fixture_id"]=i
    r=clustered_interval(rows)
    assert r["roi_95_interval"]==[-1.,-1.]
    assert r==clustered_interval(rows)
    assert not r["ranking_eligible"]


def test_memory_ledger_cannot_mutate_inputs_or_rewrite():
    original={"prediction_id":"x","legs":[]}
    ledger=MemoryLedger([original]);original["legs"].append("changed")
    assert ledger.get("prediction","x")["legs"]==[]
    read=ledger.get("prediction","x");read["legs"].append("changed")
    assert ledger.get("prediction","x")["legs"]==[]
    with pytest.raises(ValueError,match="IMMUTABLE"):
        ledger.append("prediction","x",original)


def test_production_double_replay_and_independent_variants(monkeypatch):
    rows=[candidate(i,"1.70",".75") for i in range(3)]
    before=deepcopy(rows)
    monkeypatch.setenv("GOALVISION_COMBO_DOUBLE_170","sentinel")
    result=replay(rows,[],at=NOW)
    assert os.environ["GOALVISION_COMBO_DOUBLE_170"]=="sentinel"
    assert rows==before and result["source_pool_fingerprint"]==digest(rows)
    a=result["A_CURRENT_DOUBLE"]["selected"]
    assert len(a)==1 and len(a[0]["legs"])==2
    assert Decimal(a[0]["combined_odds"])==Decimal("2.89")
    assert result["C_QUALITY_VALUE_FIRST"]["selected"]==[]
    assert not result["C_QUALITY_VALUE_FIRST"]["ranking_implemented"]
    again=replay(rows,a,at=NOW)
    assert not again["A_CURRENT_DOUBLE"]["selected"]


@pytest.mark.parametrize("field,value",[
    ("outcome","WON"),("target",1),
    ("goalvision_retrieved_at_utc",(NOW+timedelta(seconds=1)).isoformat()),
    ("final_review_completed_at_utc",(NOW+timedelta(seconds=1)).isoformat()),
])
def test_replay_rejects_future_and_label_inputs(field,value):
    rows=[candidate(i) for i in range(2)];rows[0][field]=value
    with pytest.raises(ValueError,match="RESEARCH_(FUTURE_INPUT|LABEL_IN_SELECTION)"):
        replay(rows,[],at=NOW)


def test_quality_raw_and_self_declared_calibration_cannot_pass():
    row=candidate(0);row["calibration_status"]="CALIBRATED"
    result=quality_value_screen([row],at=NOW)
    assert not result["selected"]
    assert result["candidate_diagnostics"][0]["calibrated_probability"] is None
    assert result["rejection_counts"]["VALIDATED_JOINT_PROBABILITY_UNAVAILABLE"]==1


def coupon():
    legs=[{"fixture_id":i+1,"market":"OVER_2_5","captured_odds":o,"ensemble_probability":".75"}
          for i,o in enumerate(("1.70","1.80"))]
    return {"prediction_id":"test","created_at_utc":NOW.isoformat(),"legs":legs,
            "combined_odds":"3.0600","estimated_probability_if_independent":".5625"}


def fact(fid,outcome="WON",hours=2):
    return {"fixture_id":fid,"outcome":outcome,"provider_status":"FT",
            "fulltime_home":3 if outcome=="WON" else 0,"fulltime_away":0,
            "retrieved_at_utc":(NOW+timedelta(hours=hours)).isoformat()}


@pytest.mark.parametrize("outcomes,status,pnl",[
    (("WON","WON"),"WON","2.06"),(("WON","LOST"),"LOST","-1"),
    (("VOID","VOID"),"VOID","0"),(("VOID","WON"),"PARTIAL_VOID","0.80"),
    (("LOST",None),"LOST","-1"),(("WON",None),"PENDING",None),
])
def test_replay_settlement_void_partial_early_loss(outcomes,status,pnl):
    facts={str(i+1):fact(i+1,o) for i,o in enumerate(outcomes) if o is not None}
    row=score_replay([coupon()],facts,cutoff=NOW+timedelta(hours=3))[0]
    assert row["status"]==status
    assert row["flat_unit_pnl"] is None if pnl is None else Decimal(row["flat_unit_pnl"])==Decimal(pnl)


def test_future_results_cannot_score_replay():
    assert score_replay([coupon()],{"1":fact(1,"LOST",hours=4)},cutoff=NOW+timedelta(hours=3))[0]["status"]=="PENDING"


def test_readonly_sqlite_and_immutable_output(tmp_path):
    path=tmp_path/"data.db"
    db=sqlite3.connect(path);db.execute("CREATE TABLE evidence(x)");db.commit();db.close()
    before=path.read_bytes()
    db=audit.readonly(path)
    try:
        with pytest.raises(sqlite3.OperationalError):db.execute("INSERT INTO evidence VALUES (1)")
    finally:db.close()
    assert path.read_bytes()==before
    output=tmp_path/"report.json";audit.write(output,{"n":1});audit.write(output,{"n":1})
    with pytest.raises(ValueError,match="ALREADY_EXISTS"):audit.write(output,{"n":2})

def test_source_hash_tampering_fails_closed():
    import json
    value={"fixture_id":1}
    assert audit.verified(json.dumps(value),digest(value),live=True)==value
    with pytest.raises(ValueError,match="SOURCE_INTEGRITY"):
        audit.verified(json.dumps(value),"0"*64)

@pytest.mark.parametrize("sink_mode",["none","capture","broken"])
def test_opt_in_observer_preserves_request_count_and_result(sink_mode):
    import asyncio
    from types import SimpleNamespace
    from app.live_lab.runner import LiveRunner
    calls=[];events=[]
    class Quota:
        def bind(self,*args): pass
        async def call(self,category,fn,*args,**kwargs):
            calls.append(category)
            return await fn(*args,**kwargs)
    async def operation():
        return {"response":[{"fixture":{"id":1},"update":NOW.isoformat()}],"private":"secret-not-exported"}
    def broken(value): raise RuntimeError("observer down")
    runner=LiveRunner(SimpleNamespace(),None,Quota(),clock=lambda:NOW,
                      diagnostic_sink=None if sink_mode=="none" else events.append if sink_mode=="capture" else broken)
    result=asyncio.run(runner._call("LIVE_REFRESH",operation))
    assert result["private"]=="secret-not-exported"
    assert calls==["LIVE_REFRESH"]
    if events:
        assert "secret-not-exported" not in str(events)
        assert events[0]["client_call_elapsed_seconds"]>=0
        assert events[0]["evidence"]["http_latency_seconds"] is None
    assert runner.diagnostic_sink_failures==(sink_mode=="broken")


def test_diagnostic_exception_type_only_and_original_failure_preserved():
    import asyncio
    from types import SimpleNamespace
    from app.live_lab.runner import LiveRunner
    class Quota:
        def bind(self,*args): pass
        async def call(self,category,fn,*args):return await fn(*args)
    async def failing():raise ValueError("secret-not-exported")
    events=[]
    runner=LiveRunner(SimpleNamespace(),None,Quota(),clock=lambda:NOW,diagnostic_sink=events.append)
    with pytest.raises(ValueError,match="secret-not-exported"):
        asyncio.run(runner._call("LIVE_REFRESH",failing))
    assert events[0]["error_type"]=="ValueError"
    assert "secret-not-exported" not in str(events)


def test_provider_alignment_separates_minute_from_score():
    from app.live_lab.research import provider_evidence
    state={"fixture_id":1,"minute":60,"home_score":1,"away_score":0}
    raw={"response":[{"fixture":{"id":1,"status":{"elapsed":59}},
                     "teams":{"home":{"goals":1},"away":{"goals":0}},"update":NOW.isoformat(),
                     "token":"do-not-copy"}]}
    row=provider_evidence(raw,state=state)["rows"][0]
    assert row["score_matches"] and not row["minute_matches"]
    assert "token" not in str(row)

def test_future_append_does_not_change_fixed_cutoff_coupon_report():
    p=prediction();p["legs"][0].update(market="OVER_2_5",observation_id="leg1")
    before=coupon_report(Ledger([p]),now=REPORT_NOW)
    future={"leg1":{"fixture_id":1,"market":"OVER_2_5","outcome":"LOST",
                    "retrieved_at_utc":"2026-10-08T13:00:00+00:00"}}
    after=coupon_report(Ledger([p],future),now=REPORT_NOW)
    assert before==after


def test_mismatched_fixture_result_cannot_score():
    assert score_replay([coupon()],{"1":fact(99,"LOST")},cutoff=NOW+timedelta(hours=3))[0]["status"]=="PENDING"

def movement_candidate(at, odds="2", suffix="a"):
    row=live_candidate(5, ())
    row.update(candidate_id=suffix, prepared_at_utc=at.isoformat(),
               captured_odds=odds, quote_provenance_fingerprint="quote-"+suffix,
               live_match_state_fingerprint="snapshot-"+suffix,
               state={"fixture_id":1,"status":"2H","minute":60,"added_time":None,
                      "home_score":1,"away_score":0,"red_cards_home":0,"red_cards_away":0,
                      "events":[],"retrieved_at":at.isoformat(),"state_fingerprint":"snapshot-"+suffix})
    row["quote"].update(origin_timestamp=(at-timedelta(seconds=5)).isoformat(),
                        retrieved_at=at.isoformat(),source_identity="API_FOOTBALL:/odds/live",
                        provider_type="API_FOOTBALL_LIVE_ODDS",bookmaker_id=None,bookmaker=None,
                        live_market_id=1,market_identity="live:1:Home",
                        blocked=False,stopped=False,finished=False,suspended=False)
    return row


def movement_report(a, b):
    return live_report([a,b],[],[],[],[],[],as_of=NOW+timedelta(seconds=30),
                       since=NOW-timedelta(minutes=1))


def test_equal_state_price_movement_survives_distinct_capture_fingerprints():
    a=movement_candidate(NOW)
    b=movement_candidate(NOW+timedelta(seconds=10),"2.10","b")
    output=movement_report(a,b)
    assert output["same_state_odds_movement"]["n"]==1
    assert output["same_state_odds_movement"]["mean"]==pytest.approx(.05)
    assert output["same_state_quote_pairs"][0]["elapsed_seconds"]==10
    assert a["live_match_state_fingerprint"]!=b["live_match_state_fingerprint"]


@pytest.mark.parametrize("scope,key,value",[
    ("state","minute",61),("state","home_score",2),("state","red_cards_away",1),
    ("state","events",[{"type":"Card"}]),("quote","bookmaker_id",999),
    ("quote","market_identity","live:1:Away"),("quote","source_identity","ANOTHER_FEED"),
    ("quote","suspended",True),("quote","blocked",None),
])
def test_price_movement_never_pairs_different_state_source_or_activity(scope,key,value):
    a=movement_candidate(NOW);b=movement_candidate(NOW+timedelta(seconds=10),"2.10","b")
    b[scope][key]=value
    assert movement_report(a,b)["same_state_odds_movement"]["n"]==0


def test_missing_state_cannot_create_a_synthetic_price_pair():
    a=movement_candidate(NOW);b=movement_candidate(NOW+timedelta(seconds=10),"2.10","b")
    del b["state"]["events"]
    output=movement_report(a,b)
    assert output["same_state_odds_movement"]["n"]==0
    assert output["quote_movement_exclusions"]=={"STATE_EVIDENCE_INCOMPLETE":1}


def test_fixture_response_diagnostics_use_fixture_goals():
    from app.live_lab.research import provider_evidence
    state={"fixture_id":1,"minute":60,"home_score":1,"away_score":0}
    payload={"response":[{"fixture":{"id":1,"status":{"elapsed":60}},
                         "goals":{"home":1,"away":0},"teams":{"home":{"id":1},"away":{"id":2}}}]}
    row=provider_evidence(payload,state=state)["rows"][0]
    assert row["provider_score"]==[1,0]
    assert row["score_matches"] and row["minute_matches"]
    assert row["score_source"]=="FIXTURE_GOALS"


def test_missing_provider_values_are_not_reported_as_observed_mismatches():
    from app.live_lab.research import provider_evidence
    state={"fixture_id":1,"minute":60,"home_score":1,"away_score":0}
    row=provider_evidence({"response":[{"fixture":{"id":1},"teams":{}}]},state=state)["rows"][0]
    assert row["score_matches"] is None and row["minute_matches"] is None
    assert not row["score_available"] and not row["minute_available"]
