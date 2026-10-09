"""Authorized LIVE 60–70% experiment; all transports/provider calls are fake."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from app.adaptive_lab import daypart
from app.adaptive_lab.contracts import digest
from app.live_lab.engine import readiness
from app.live_lab.service import LiveService
from app.live_lab.selection import in_probability_band, select_candidates, PROBABILITY_POLICY
from app.live_lab.presentation import prediction_message
from app.lab_telegram.models import LabTelegramConfig
from .conftest import START, repo
from .test_live_quote_age_policy import data, rehash


@pytest.mark.parametrize("p,allowed",[
    ("0.60",True),("0.70",True),(".65",True),
    ("0.5999999999999999999",False),("0.7000000000000000001",False),
    ("0",False),("1",False),("NaN",False),("Infinity",False),("-Infinity",False),
    (None,False),("",False),(True,False)])
def test_exact_unrounded_probability_band(p,allowed):
    assert in_probability_band(p) is allowed


@pytest.mark.parametrize("p,odds,band,reason",[
    (.6,"1.4",True,None),(.7,"1.4",True,None),(.625,"1.6",True,None),
    (.65,"1.4",False,"NON_POSITIVE_EV"),
    (.599999,"1.7",True,"LIVE_PROBABILITY_OUTSIDE_60_70"),
    (.700001,"1.7",True,"LIVE_PROBABILITY_OUTSIDE_60_70"),
    (.65,"10",True,"SEVERE_MODEL_MARKET_CONTRADICTION"),
    (0,"1.7",True,"PROBABILITY_OR_ODDS_CONTRACT"),
    (1,"1.7",True,"PROBABILITY_OR_ODDS_CONTRACT"),
    (float("nan"),"1.7",True,"PROBABILITY_OR_ODDS_CONTRACT")])
def test_initial_gate_removes_only_ev(p,odds,band,reason):
    state,quote,_=data(600)
    quote["decimal_odds"]=odds;rehash(quote)
    reasons=readiness(state,quote,p,uncertainty=.07,now=START,
                      allow_provider_feed=True,quote_age_diagnostic=True,probability_band=band)
    if reason is None:assert reasons==[]
    else:assert reason in reasons
    if band:assert "NON_POSITIVE_EV" not in reasons


def selection_row(identity,p,ev,blockers=(),policy=PROBABILITY_POLICY):
    return {"prediction_id":identity,"ensemble_probability":str(p),"expected_value":ev,
            "policy":policy,"blockers":list(blockers)}


def test_probability_ranking_ev_has_no_effect_and_no_forced_selection():
    rows=[selection_row("a",.65,100),selection_row("b",.69,-.2),
          selection_row("c",.8,500),selection_row("d",.7,10,["LIVE_MARKET_SUSPENDED"])]
    assert select_candidates(rows,probability_band=True)[0]["prediction_id"]=="b"
    rows[0]["expected_value"]=-999;rows[1]["expected_value"]=999
    assert select_candidates(rows,probability_band=True)[0]["prediction_id"]=="b"
    assert select_candidates([selection_row("x",.9,99)],probability_band=True)==[]
    assert select_candidates([selection_row("x",.65,99,policy="legacy")],probability_band=True)==[]
    assert select_candidates([selection_row("x","nan",99)],probability_band=True)==[]
    ties=[selection_row("z",.65,999),selection_row("a",.65,-999)]
    assert select_candidates(ties,probability_band=True)[0]["prediction_id"]=="a"
    assert select_candidates(ties)[0]["prediction_id"]=="z"


def service(repo,monkeypatch,p=.65,band=True):
    state,quote,rates=data(600)
    quote["decimal_odds"]="1.4";rehash(quote)
    monkeypatch.setattr("app.live_lab.service.remaining_goal_probabilities",
                        lambda *a,**k:{"OVER_1_5":p})
    instance=LiveService(repo,clock=lambda:START,allow_provider_feed=True,
                         quote_age_diagnostic=True,probability_band=band)
    return instance,state,quote,rates


def test_frozen_identity_prospective_cohort_and_legacy_records(repo,monkeypatch):
    live,state,quote,rates=service(repo,monkeypatch)
    legacy=LiveService(repo,clock=lambda:START,allow_provider_feed=True,quote_age_diagnostic=True)
    old=legacy.candidate(state,quote,rates,now=START)
    new=live.candidate(state,quote,rates,now=START)
    assert old["blockers"]==["NON_POSITIVE_EV"] and new["blockers"]==[]
    assert new["prediction_id"]!=old["prediction_id"]
    assert new["ensemble_probability"]==old["ensemble_probability"]
    assert new["expected_value"]<0 and new["ev_role"]=="DIAGNOSTIC_ONLY"
    assert new["statistics_cohort"]=="LIVE_P60_70_20261009_V1"
    assert repo.get("live_candidates",old["prediction_id"])==old
    assert live.candidate(state,quote,rates,now=START)==new
    message=prediction_message(new)
    assert "60–70%" in message and "EV:" not in message and "Edge:" not in message
    assert "EV:" in prediction_message(old)


@pytest.mark.parametrize("change,expected",[
    ("none","SENT"),("below","LIVE_READINESS_BLOCKED"),("above","LIVE_READINESS_BLOCKED"),
    ("suspended","LIVE_READINESS_BLOCKED"),("stale_state","LIVE_READINESS_BLOCKED"),
    ("missing","LIVE_REFRESH_QUOTE_MISSING"),("error","LIVE_FINAL_REFRESH_FAILED"),
    ("mismatch","LIVE_READINESS_BLOCKED"),("divergence","LIVE_READINESS_BLOCKED")])
def test_final_refresh_band_and_safety_before_claim(repo,monkeypatch,change,expected):
    live,state,quote,rates=service(repo,monkeypatch)
    original=live.candidate(state,quote,rates,now=START)
    sends=[]
    class Transport:
        async def send_message_receipt(self,**kwargs):
            sends.append(kwargs)
            return SimpleNamespace(chat_id=kwargs["chat_id"],message_id=11)
    async def refresh(identity):
        assert identity==7
        if change=="error":raise ValueError("synthetic")
        s,q=deepcopy(state),deepcopy(quote)
        if change in {"below","above"}:
            monkeypatch.setattr("app.live_lab.service.remaining_goal_probabilities",
                                lambda *a,**k:{"OVER_1_5":.599 if change=="below" else .701})
        if change=="suspended":q["suspended"]=True
        if change=="divergence":q["decimal_odds"]="10"
        if change=="mismatch":q["fixture_id"]=999
        if change=="stale_state":
            s["retrieved_at"]=(START-timedelta(seconds=31)).isoformat()
            s["state_fingerprint"]=digest({k:v for k,v in s.items() if k!="state_fingerprint"})
            q["state_fingerprint"]=s["state_fingerprint"]
        # Exact refresh has a new immutable quote identity even if the match minute is unchanged.
        q["origin_timestamp"]=(START-timedelta(seconds=30)).isoformat()
        q["provider_update_timestamp"]=q["origin_timestamp"]
        return s,[] if change=="missing" else [rehash(q)],rates
    config=LabTelegramConfig(token="fake",chat_id="-1003510920417",
                             automatic_enabled=True,official_destinations=frozenset())
    outcome=asyncio.run(live.publish(original["prediction_id"],config,Transport(),refresh=refresh))
    assert outcome["status"]==expected
    assert len(sends)==(change=="none")
    assert len(repo.all("live_claims"))==len(sends)
    if sends:
        repeat=asyncio.run(live.publish(original["prediction_id"],config,Transport(),refresh=refresh))
        assert not repeat["sent"] and len(sends)==1
        published=repo.all("live_publications")[0]["selection_id"]
        assert repo.get("live_candidates",published)["expected_value"]<0
        payload={"response":[{"fixture":{"id":7,"status":{"short":"FT"}},
                              "score":{"fulltime":{"home":2,"away":0}}}]}
        result=live.settle(published,payload,now=START+timedelta(hours=1))
        assert result["status"]=="WON"
        receipt=asyncio.run(live.publish_result(published,config,Transport()))
        assert receipt["sent"] and sends[-1]["reply_to_message_id"]==11
        assert repo.all("learning_observations","PREMATCH")==[]


def test_uncertainty_exposure_and_duplicate_guards_remain():
    state,quote,_=data(600);quote["decimal_odds"]="1.4";rehash(quote)
    old={"fixture_id":7,"market":quote["market"],"state":state,"captured_odds":"1.4"}
    kwargs=dict(now=START,allow_provider_feed=True,quote_age_diagnostic=True,probability_band=True)
    assert "UNCERTAINTY_TOO_HIGH" in readiness(state,quote,.65,uncertainty=.13,**kwargs)
    assert "DUPLICATE_LIVE_OPPORTUNITY" in readiness(state,quote,.65,uncertainty=.07,previous=[old],**kwargs)
    assert "LIVE_FIXTURE_SELECTION_LIMIT" in readiness(state,quote,.65,uncertainty=.07,previous=[old]*3,**kwargs)


def test_worker_wires_policy_and_preserves_initial_quota_calls(repo,monkeypatch):
    from .test_evening_live import test_worker_accounts_status_before_http_without_automatic_learning
    original=LiveService.__init__;seen=[]
    def capture(self,*args,**kwargs):
        seen.append(kwargs.get("probability_band"))
        return original(self,*args,**kwargs)
    monkeypatch.setenv("GOALVISION_LIVE_PROBABILITY_60_70","1")
    monkeypatch.setattr(LiveService,"__init__",capture)
    test_worker_accounts_status_before_http_without_automatic_learning(repo,monkeypatch)
    assert seen==[True]


def test_flag_defaults_off_and_rejects_ambiguous_values(monkeypatch):
    monkeypatch.delenv("GOALVISION_LIVE_PROBABILITY_60_70",raising=False)
    assert not daypart.probability_band_enabled()
    monkeypatch.setenv("GOALVISION_LIVE_PROBABILITY_60_70","1")
    assert daypart.probability_band_enabled()
    monkeypatch.setenv("GOALVISION_LIVE_PROBABILITY_60_70","true")
    with pytest.raises(ValueError,match="INVALID_LAB_DAYPART_FLAG"):
        daypart.probability_band_enabled()


def test_range_block_does_not_erase_preexisting_shadow_capture(repo,monkeypatch):
    live,state,quote,rates=service(repo,monkeypatch,p=.59)
    observed=[]
    monkeypatch.setattr(live.governance,"observe",lambda *a,**k:observed.append(a))
    candidate=live.candidate(state,quote,rates,now=START)
    assert "LIVE_PROBABILITY_OUTSIDE_60_70" in candidate["blockers"]
    assert len(observed)==1
