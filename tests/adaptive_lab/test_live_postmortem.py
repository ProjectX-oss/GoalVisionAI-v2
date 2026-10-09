"""Read-only postmortem chronology and accounting, using fictional inputs."""
from copy import deepcopy
from datetime import timedelta
import runpy
from pathlib import Path
import pytest
from app.live_lab.service import LiveService
from app.live_lab.provider import history_rates
from .test_live import live_data
from .conftest import START, repo

audit = runpy.run_path(str(Path(__file__).parents[2]/"operations/live-postmortem/audit.py"))


def fixture_tables(repo):
    s,q,_ = live_data()
    payloads=[]
    for team in (1,2):
        payloads.append({"response":[{"fixture":{"id":100+team*10+i,
            "date":(START-timedelta(days=i+2)).isoformat(),"status":{"short":"FT"}},
            "teams":{"home":{"id":team},"away":{"id":99}},
            "score":{"fulltime":{"home":2,"away":1}}, "league":{"id":39,"country":"Test"}}
            for i in range(10)]})
    rates=history_rates(s,*payloads,retrieved_at=START)
    from app.adaptive_lab.contracts import digest
    q["decimal_odds"]="5"
    q["quote_fingerprint"]=digest({k:v for k,v in q.items() if k!="quote_fingerprint"})
    p=LiveService(repo,clock=lambda:START).candidate(s,q,rates,now=START)
    identity=p["prediction_id"]
    result={"prediction_id":identity,"fixture_id":7,"market":p["market"],"captured_odds":"5",
            "status":"WON","fulltime_home":2,"fulltime_away":0,"provider_status":"FT",
            "settled_at_utc":(START+timedelta(hours=1)).isoformat()}
    return {"live_candidates":[p],"live_claims":[],
            "live_publications":[{"selection_id":identity,"status":"SENT","sent_at_utc":START.isoformat()}],
            "live_settlements":[result],
            "live_result_receipts":[{"selection_id":identity,"status":"SENT",
                "sent_at_utc":(START+timedelta(hours=1,seconds=1)).isoformat()}]}


def test_asof_does_not_use_future_settlement_or_result_receipt(repo):
    tables=fixture_tables(repo)
    rows=audit["published_rows"](tables,since=START,until=START)
    assert rows[0]["result"]=="PENDING"
    assert rows[0]["flat_pnl"] is None
    assert rows[0]["result_receipt_present"] is False
    assert audit["summary"](rows)["settled"]==0


def test_exact_replay_and_decimal_profit(repo):
    rows=audit["published_rows"](fixture_tables(repo),since=START,until=START+timedelta(hours=2))
    assert rows[0]["poisson_probability_absolute_replay_error"]==0
    assert rows[0]["rates_replay_equal"]
    assert rows[0]["flat_pnl"]=="4"
    assert rows[0]["settlement_replay"]=="PASS"
    assert audit["summary"](rows)["flat_roi"]=="4"


def test_conflicting_outcome_fails_closed(repo):
    tables=fixture_tables(repo)
    tables["live_settlements"][0]["status"]="LOST"
    with pytest.raises(ValueError,match="SETTLEMENT_REPLAY_MISMATCH"):
        audit["published_rows"](tables,since=START,until=START+timedelta(hours=2))


def test_conflicting_settlement_identity_fails_closed(repo):
    tables=fixture_tables(repo)
    tables["live_settlements"][0]["fixture_id"]=999
    with pytest.raises(ValueError,match="SETTLEMENT_PROVENANCE"):
        audit["published_rows"](tables,since=START,until=START+timedelta(hours=2))


def test_duplicate_publication_fails_closed(repo):
    tables=fixture_tables(repo)
    tables["live_publications"]*=2
    with pytest.raises(ValueError,match="DUPLICATE_PUBLICATION"):
        audit["published_rows"](tables,since=START,until=START+timedelta(hours=2))


def test_void_excluded_from_probability_metrics():
    rows=[{"probability":".8","result":"WON"},{"probability":".2","result":"VOID"},
          {"probability":".2","result":"LOST"}]
    value=audit["probability_metrics"](rows,"probability")
    assert value["n"]==2
    assert value["brier"]==pytest.approx(.04)


@pytest.mark.parametrize("probability",["0","1","nan"])
def test_invalid_probability_not_clamped(probability):
    with pytest.raises(ValueError,match="PROBABILITY_BOUNDARY"):
        audit["probability_metrics"]([{"probability":probability,"result":"LOST"}],"probability")
