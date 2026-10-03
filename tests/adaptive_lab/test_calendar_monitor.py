"""Offline calendar readiness progress and observer isolation; no operational cycles."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import builtins
import json

import pytest

from app.adaptive_lab import calendar_monitor as monitor
from app.adaptive_lab.calendar_audit import read_snapshot, PROTECTED_TABLES
from app.adaptive_lab.contracts import canonical, digest
from app.adaptive_lab.observer import observe
from .conftest import START, frozen
from .test_calendar_research import plan, populated, row, resign, NOW
from .test_lab_product_schedule import Ledger


def forecast(i, created, **changes):
    value = frozen(i)[0]
    value.update(prepared_at_utc=created.isoformat(),
                 kickoff_utc=(created+timedelta(hours=1)).isoformat(), **changes)
    return value


def snapshot(rows=(), forecasts=(), results=(), consumed=()):
    return {"rows": list(rows), "canonical_opportunities": list(forecasts),
            "canonical_results": list(results), "consumed_fixtures": set(consumed),
            "snapshot_fingerprint": digest(list(rows))}


def result(prediction, at):
    return {"fixture_id": prediction["fixture_id"], "market": prediction["market"],
            "retrieved_at_utc": at.isoformat()}


def single(ledger, pred, *, accepted=True, settled=None):
    pid = pred["prediction_id"]
    ledger.append("single_prediction", pid, pred)
    ledger.append("receipt", "single_prediction:"+pid,
        {"status": "SENT" if accepted else "UNKNOWN", "sent_at_utc": pred["prepared_at_utc"]})
    if settled:
        ledger.append("single_settlement", pid, {"settled_at_utc": settled.isoformat()})


def test_progress_lifecycle_and_readiness_are_distinct_and_deterministic():
    p = plan()
    fit = p.windows()["CALIBRATION_FIT"][0]
    now = fit+timedelta(hours=6)
    forecasts = [forecast(0, fit+timedelta(hours=7)), forecast(1, fit+timedelta(hours=5,minutes=30)),
                 forecast(2,fit), forecast(3,fit), forecast(4,fit)]
    rows = [row(4, fit)]
    data = snapshot(rows, forecasts, [result(forecasts[3],now)])
    before = deepcopy(data)
    value = monitor.build_report(data, Ledger(), p, now=now)
    phase = value["windows"]["CALIBRATION_FIT"]
    assert phase["progress"] == {"observed_fixtures":4,"observed_opportunities":4,
        "completed_fixtures":1,"pending_fixtures":2,"upcoming_fixtures":1,
        "awaiting_result_fixtures":1,"result_awaiting_linkage_fixtures":1,"excluded_fixtures":0}
    assert phase["eligible_resolved_observations"] == phase["eligible_resolved_fixtures"] == 1
    assert phase["missing_independent_fixtures"] == phase["missing_observations"] == 299
    assert phase["window_state"] == "OPEN"
    assert value["status"] == "BLOCKED"
    assert data == before
    data["canonical_opportunities"].reverse()
    assert monitor.build_report(data, Ledger(), p, now=now) == value
    assert len(canonical(value).encode()) < monitor.MAX_OUTPUT_BYTES


def test_economic_dedup_receipts_streams_and_combo_never_inflate():
    p, l = plan(), Ledger()
    t = p.windows()["CALIBRATION_FIT"][0]
    pred = forecast(1,t)
    single(l,pred)
    duplicate = dict(pred,prediction_id="z-duplicate",prepared_at_utc=(t+timedelta(minutes=1)).isoformat())
    single(l,duplicate)
    single(l,forecast(2,t),accepted=False)
    single(l,forecast(3,t,stream="LIVE"))
    single(l,forecast(4,t,stream="OFFICIAL"))
    l.append("prediction","combo",{"legs":[pred]*20})
    value = monitor.build_report(snapshot(forecasts=[pred]),l,p,now=t+timedelta(hours=3))
    assert value["windows"]["CALIBRATION_FIT"]["progress"]["observed_opportunities"] == 1
    assert value["windows"]["CALIBRATION_FIT"]["eligible_resolved_observations"] == 0
    # Exact accepted audit evidence wins over pending raw copies.
    value = monitor.build_report(snapshot([row(1,t)], [pred]),l,p,now=t+timedelta(hours=4))
    assert value["windows"]["CALIBRATION_FIT"]["progress"]["completed_fixtures"] == 1


def test_single_result_is_visible_without_manufacturing_learning():
    p, l = plan(), Ledger()
    t = p.windows()["CALIBRATION_FIT"][0]
    single(l,forecast(1,t),settled=t+timedelta(hours=3))
    value = monitor.build_report(snapshot(),l,p,now=t+timedelta(hours=4))
    phase = value["windows"]["CALIBRATION_FIT"]
    assert phase["progress"]["result_awaiting_linkage_fixtures"] == 1
    assert phase["eligible_resolved_observations"] == 0


@pytest.mark.parametrize("reason",["cohort","reserved","consumed","void","mixed_window","late"])
def test_excluded_fixture_never_counts_as_pending_or_ready(reason):
    t = plan().windows()["CALIBRATION_FIT"][0]
    pred, rows, consumed = forecast(1,t), [], ()
    p = plan(reserved_holdout_fixtures=("2",)) if reason=="reserved" else plan()
    forecasts = [pred]
    if reason=="cohort":
        forecasts.append(forecast(2,t,fixture_id=2,market="AWAY_WIN",model_generation="other"))
    elif reason=="consumed":
        consumed=("2",)
    elif reason=="void":
        rows=[row(1,t,outcome="VOID",target=None)]
    elif reason=="late":
        rows=[resign(dict(row(1,t),settled_at=p.windows()["CALIBRATION_FIT"][1].isoformat()))]
    elif reason=="mixed_window":
        forecasts.append(forecast(2,START,fixture_id=2,market="AWAY_WIN"))
    value = monitor.build_report(snapshot(rows,forecasts,consumed=consumed),Ledger(),p,now=NOW)
    phase = value["windows"]["CALIBRATION_FIT"]
    assert phase["eligible_resolved_observations"] == 0
    assert phase["progress"]["pending_fixtures"] == 0
    assert phase["progress"]["completed_fixtures"] == 0
    assert sum(value["excluded_forecast_fixture_reasons"].values()) == 1


def test_future_result_and_unsettled_audit_are_not_completed():
    p = plan()
    t = p.windows()["CALIBRATION_FIT"][0]
    pred = forecast(1,t)
    pending = resign(dict(row(1,t),outcome="PENDING",target=None,settled_at=None))
    value = monitor.build_report(snapshot([pending],[pred],[result(pred,NOW)]),
                                 Ledger(),p,now=t+timedelta(hours=2))
    assert value["windows"]["CALIBRATION_FIT"]["progress"]["pending_fixtures"] == 1
    assert value["windows"]["CALIBRATION_FIT"]["eligible_resolved_observations"] == 0


def test_ready_is_offline_review_only_and_source_order_is_stable():
    data = snapshot(populated())
    value = monitor.build_report(data,Ledger(),plan(),now=NOW)
    assert value["status"] == "READY_FOR_OFFLINE_REVIEW"
    assert value["training_invoked"] is value["holdout_evaluated"] is value["promotion_allowed"] is False
    assert value["selection_effect"] == "NONE"
    data["rows"].reverse()
    assert monitor.build_report(data,Ledger(),plan(),now=NOW) == value
    assert [v["required_observations_and_fixtures"] for v in value["windows"].values()] == [1,300,30,100]


def test_runtime_plan_is_exact_predeclared_document_and_rejects_rebase(tmp_path,monkeypatch):
    original = monitor.load_plan().document()
    assert original["plan_fingerprint"] == monitor.PLAN_FINGERPRINT
    assert original == json.loads((monitor.PLAN_PATH.parents[2]/"docs/evidence/calibration_calendar_20261002/plan.json").read_text())
    path = tmp_path/"plan.json"
    path.write_text(json.dumps(plan().document()))
    monkeypatch.setattr(monitor,"PLAN_PATH",path)
    with pytest.raises(ValueError,match="NOT_REVIEWED"):
        monitor.load_plan()
    path.unlink()
    path.symlink_to(tmp_path/"absent")
    with pytest.raises(ValueError,match="PLAN_INVALID"):
        monitor.load_plan()


@pytest.mark.parametrize("source", ["canonical_opportunities","canonical_results","ledger"])
def test_forecast_bounds(source,monkeypatch):
    monkeypatch.setattr(monitor,"POLICY",replace(monitor.POLICY,training_rows_limit=1))
    data, l = snapshot(), Ledger()
    if source=="ledger":
        single(l,forecast(0,START));single(l,forecast(1,START))
    elif source=="canonical_results":
        data[source]=[result(forecast(i,START),START) for i in range(2)]
    else:
        data[source]=[forecast(i,START) for i in range(2)]
    with pytest.raises(ValueError,match="BOUND"):
        monitor.build_report(data,l,plan(),now=NOW)


def test_optional_forecast_snapshot_is_query_only_bounded_and_scope_correct(repo,monkeypatch):
    pred=forecast(0,START)
    repo.append("canonical_opportunities","p","PREMATCH",pred,START.isoformat())
    repo.append("canonical_opportunities","live","LIVE",pred,START.isoformat())
    path=repo.connection.execute("PRAGMA database_list").fetchone()[2]
    before={t:repo.revision(t) for t in PROTECTED_TABLES}
    assert "canonical_opportunities" not in read_snapshot(path)
    data=read_snapshot(path,include_forecasts=True)
    assert data["canonical_opportunities"]==[pred] and data["canonical_results"]==[]
    def forbidden(*a,**kw):
        pytest.fail("Readiness must not write or fit")
    monkeypatch.setattr("app.adaptive_lab.repository.AuditRepository.append",forbidden)
    monkeypatch.setattr("app.adaptive_lab.automl.train",forbidden)
    monkeypatch.setattr("app.adaptive_lab.calibration_research.research",forbidden)
    monkeypatch.setattr(monitor,"load_plan",plan)
    value=monitor.observed_readiness(repo,Ledger(),now=NOW)
    assert value["windows"]["TRAIN"]["progress"]["awaiting_result_fixtures"]==1
    assert before=={t:repo.revision(t) for t in PROTECTED_TABLES}
    from app.adaptive_lab import calendar_audit
    monkeypatch.setattr(calendar_audit,"POLICY",replace(calendar_audit.POLICY,training_rows_limit=0))
    with pytest.raises(ValueError,match="FORECAST_BOUND"):
        read_snapshot(path,include_forecasts=True)


def test_observer_flag_adds_only_compact_health_and_preserves_core(repo,monkeypatch):
    l=Ledger()
    monkeypatch.delenv(monitor.ENVIRONMENT_FLAG,raising=False)
    monkeypatch.delenv("GOALVISION_LAB_DEVIG_RESEARCH",raising=False)
    before=observe(repo,l,now=NOW)
    assert "CALIBRATION_READINESS" not in before
    protected={t:repo.revision(t) for t in PROTECTED_TABLES}
    monkeypatch.setenv(monitor.ENVIRONMENT_FLAG,"1")
    monkeypatch.setattr(monitor,"load_plan",plan)
    def forbidden(*a,**kw):
        pytest.fail("Observer must not train")
    monkeypatch.setattr("app.adaptive_lab.automl.train",forbidden)
    monkeypatch.setattr("app.adaptive_lab.calibration_research.research",forbidden)
    after=observe(repo,l,now=NOW)
    report=after.pop("CALIBRATION_READINESS")
    assert after==before
    assert report["status"]=="BLOCKED"
    assert repo.all("observer_runs","PREMATCH")[-1]["CALIBRATION_READINESS"]==report
    assert protected=={t:repo.revision(t) for t in PROTECTED_TABLES}
    assert after["api_calls"]==after["telegram_sends"]==0 and after["LIVE"]=="DISABLED"


@pytest.mark.parametrize("failure",["snapshot","import"])
def test_optional_failure_is_sanitized_and_observer_persists(repo,monkeypatch,failure):
    monkeypatch.setenv(monitor.ENVIRONMENT_FLAG,"1")
    if failure=="snapshot":
        def broken(*a,**kw):
            raise ValueError("secret-token-should-not-escape")
        monkeypatch.setattr(monitor,"observed_readiness",broken)
    else:
        original=builtins.__import__
        def broken(name,*args,**kwargs):
            if name=="calendar_monitor":
                raise ImportError("secret-token-should-not-escape")
            return original(name,*args,**kwargs)
        monkeypatch.setattr(builtins,"__import__",broken)
    value=observe(repo,Ledger(),now=NOW)
    assert value["CALIBRATION_READINESS"]["status"]=="UNAVAILABLE"
    assert "secret-token" not in canonical(value)
    assert repo.all("observer_runs","PREMATCH")
