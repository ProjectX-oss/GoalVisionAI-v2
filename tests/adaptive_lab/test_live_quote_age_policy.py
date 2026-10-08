"""User-authorized LIVE quote age is diagnostic, with unchanged state/transport gates."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.adaptive_lab import daypart
from app.adaptive_lab.contracts import digest
from app.live_lab.engine import readiness
from app.live_lab.provider import normalize_quotes
from app.live_lab.runner import LiveRunner
from app.live_lab.service import LiveService
from app.lab_telegram.models import LabTelegramConfig
from .conftest import START
from .test_evening_live import provider_offer


def data(age=60):
    state, rates, row, catalog = provider_offer(age)
    quote = normalize_quotes({"response":[row]}, state, catalog,
                             retrieved_at=START, allow_provider_feed=True)[0][0]
    return state, quote, rates


def rehash(quote):
    quote["quote_fingerprint"] = digest({k:v for k,v in quote.items() if k != "quote_fingerprint"})
    return quote


@pytest.mark.parametrize("age", [20.001, 30, 60, 600, 86400])
def test_age_alone_is_diagnostic_and_legacy_mode_is_unchanged(repo, age):
    state, quote, rates = data(age)
    strict = LiveService(repo, clock=lambda:START, allow_provider_feed=True)
    old = strict.candidate(state, quote, rates, now=START)
    assert "STALE_LIVE_ODDS" in old["blockers"]
    service = LiveService(repo, clock=lambda:START, allow_provider_feed=True, quote_age_diagnostic=True)
    candidate = service.candidate(state, quote, rates, now=START)
    assert candidate["blockers"] == []
    assert candidate["policy"] == "LAB_LIVE_API_FEED_AGE_DIAGNOSTIC_V2"
    assert candidate["prediction_id"] != old["prediction_id"]
    assert repo.get("live_candidates", old["prediction_id"]) == old
    assert candidate["ensemble_probability"] == old["ensemble_probability"]
    assert candidate["quote"] == old["quote"]
    assert candidate["quote_age_diagnostics"]["origin_age_seconds"] == age
    assert candidate["quote_age_diagnostics"]["mode"] == "DIAGNOSTIC_ONLY"
    assert service.candidate(state, quote, rates, now=START) == candidate


@pytest.mark.parametrize("field,value", [
    ("origin_timestamp", None), ("origin_timestamp", "invalid"),
    ("origin_timestamp", (START+timedelta(seconds=1)).isoformat()),
    ("retrieved_at", None), ("retrieved_at", (START+timedelta(seconds=1)).isoformat()),
    ("retrieved_at", (START-timedelta(seconds=120)).isoformat()),
])
def test_missing_invalid_future_and_reversed_clocks_remain_blocked(field, value):
    state, quote, _ = data()
    quote[field] = value
    if field == "origin_timestamp":
        quote["provider_update_timestamp"] = value
    rehash(quote)
    reasons = readiness(state, quote, .6, uncertainty=.07, now=START,
                        allow_provider_feed=True, quote_age_diagnostic=True)
    assert "LIVE_QUOTE_TIMESTAMP_INVALID" in reasons


@pytest.mark.parametrize("field,expected", [
    ("retrieved_at","STALE_LIVE_RETRIEVED_AT"),
    ("score_retrieved_at","STALE_LIVE_SCORE_RETRIEVED_AT"),
    ("minute_retrieved_at","STALE_LIVE_MINUTE_RETRIEVED_AT"),
    ("event_retrieved_at","STALE_EVENT_STATE"),
])
def test_state_and_event_age_limits_remain_enforced(field, expected):
    state, quote, _ = data()
    state[field] = (START-timedelta(seconds=31)).isoformat()
    state["state_fingerprint"] = digest({k:v for k,v in state.items() if k != "state_fingerprint"})
    quote["state_fingerprint"] = state["state_fingerprint"]
    rehash(quote)
    assert expected in readiness(state, quote, .6, uncertainty=.07, now=START,
                                 allow_provider_feed=True, quote_age_diagnostic=True)


@pytest.mark.parametrize("final_change,expected", [
    ("none","SENT"), ("suspended","LIVE_READINESS_BLOCKED"),
    ("missing","LIVE_REFRESH_QUOTE_MISSING"), ("error","LIVE_FINAL_REFRESH_FAILED"),
    ("mismatch","LIVE_READINESS_BLOCKED"), ("negative_ev","LIVE_READINESS_BLOCKED"),
])
def test_final_refresh_and_claim_still_control_delivery(repo, final_change, expected):
    state, quote, rates = data()
    service = LiveService(repo, clock=lambda:START, allow_provider_feed=True, quote_age_diagnostic=True)
    original = service.candidate(state, quote, rates, now=START)
    calls=[]
    refreshes=[]
    class Transport:
        async def send_message_receipt(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(chat_id=kwargs["chat_id"], message_id=31)
    async def refresh(identity):
        refreshes.append(identity)
        if final_change == "error":
            raise ValueError("provider unavailable")
        q=deepcopy(quote)
        if final_change == "suspended": q["suspended"]=True
        if final_change == "mismatch": q["fixture_id"]=99
        if final_change == "negative_ev": q["decimal_odds"]="1.01"
        return state, [] if final_change == "missing" else [rehash(q)], rates
    config=LabTelegramConfig(token="fake",chat_id="-1003510920417",
                             automatic_enabled=True,official_destinations=frozenset())
    result=asyncio.run(service.publish(original["prediction_id"],config,Transport(),refresh=refresh))
    assert result["status"] == expected
    assert refreshes == [7]
    assert len(calls) == (final_change == "none")
    assert len(repo.all("live_claims")) == len(calls)
    if calls:
        again=asyncio.run(service.publish(original["prediction_id"],config,Transport(),refresh=refresh))
        assert not again["sent"] and len(calls)==1


@pytest.mark.parametrize("diagnostic,reviewed", [(False,0),(True,1)])
def test_broad_feed_age_filter_uses_same_policy_without_changing_review_cap(repo, diagnostic, reviewed):
    state, rates, row, catalog=provider_offer(60)
    service=LiveService(repo, clock=lambda:START, allow_provider_feed=True,quote_age_diagnostic=diagnostic)
    fixture={"fixture":{"id":7,"date":state["kickoff_utc"],"status":{"short":"2H","elapsed":60}},
             "goals":{"home":0,"away":0},"teams":{"home":{"id":1},"away":{"id":2}}}
    class Client:
        async def live_fixtures(self): return {"response":[fixture]}
        async def live_odds(self): return {"response":[row]}
    class Quota:
        def bind(self,*args): pass
        async def call(self,category,fn,*args): return await fn(*args)
    runner=LiveRunner(service,Client(),Quota(),clock=lambda:START)
    refreshes=[]
    async def refresh(identity):
        refreshes.append(identity)
        return state,normalize_quotes({"response":[row]},state,catalog,retrieved_at=START,
                                      allow_provider_feed=True)[0],rates
    runner.refresh=refresh
    report=asyncio.run(runner.scan())
    assert report["fixtures_reviewed"] == reviewed
    assert report["fresh_feed_fixtures"] == 0
    assert report["eligible_feed_fixtures"] == reviewed
    assert report["quote_age_diagnostic_fixtures"] == reviewed
    assert len(refreshes) == reviewed


def test_opt_in_requires_feed_and_strict_valid_boolean(repo,monkeypatch):
    monkeypatch.delenv("GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC",raising=False)
    assert daypart.quote_age_diagnostic_enabled() is False
    monkeypatch.setenv("GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC","1")
    assert daypart.quote_age_diagnostic_enabled() is True
    with pytest.raises(ValueError,match="REQUIRES_FEED_MODE"):
        LiveService(repo,clock=lambda:START,quote_age_diagnostic=True)
    monkeypatch.setenv("GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC","yes")
    with pytest.raises(ValueError,match="INVALID_LAB_DAYPART_FLAG"):
        daypart.quote_age_diagnostic_enabled()


def test_worker_wires_opt_in_without_training_or_extra_initial_requests(repo,monkeypatch):
    from .test_evening_live import test_worker_accounts_status_before_http_without_automatic_learning
    original=LiveService.__init__
    seen=[]
    def capture(self,*args,**kwargs):
        seen.append(kwargs.get("quote_age_diagnostic"))
        return original(self,*args,**kwargs)
    monkeypatch.setenv("GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC","1")
    monkeypatch.setattr(LiveService,"__init__",capture)
    test_worker_accounts_status_before_http_without_automatic_learning(repo,monkeypatch)
    assert seen==[True]
