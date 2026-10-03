"""Prospective-only model, paired COMBO selection and bounded integration."""
from argparse import Namespace
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import pytest
from app.dixon_coles_forward import model, service, combo, worker, cli
from app.dixon_coles_forward.contracts import load_plan, VERSION
from app.dixon_coles_research.contracts import utc, seal, digest, canonical
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_constrained import model as development
from app.adaptive_lab.devig_research import capture
from app.lab_v2_shadow.market_consensus import current_market_consensus
from app.lab_v2_shadow.runner import _plain
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.real_match_lab_analysis.fingerprint import fingerprint
from tests.test_dixon_coles_research import history, PLAN as OLD_PLAN
from tests.test_lab_accuracy_delivery import accuracy_candidate
from tests.test_lab_v2_shadow import bind_candidate_evidence

PLAN = load_plan()
START = utc(PLAN["declared_at"]) + timedelta(minutes=1)

def item(index=0, *, now=START, odds="1.30", fixture_id=None):
    fid = fixture_id or 9000+index
    payload = {"response":[{"fixture":{"id":fid},"update":now.isoformat(),
        "bookmakers":[{"id":8,"name":"Test Book","bets":[{"name":"Goals Over/Under","values":[
            {"value":"Under 3.5","odd":odds},{"value":"Over 3.5","odd":"3.50"}]}]}]}]}
    consensus = current_market_consensus(payload,fixture_id=fid,retrieved_at=now,now=now)["TOTAL_3_5"]
    source = {**_plain(asdict(consensus)),"source":"API_FOOTBALL_CURRENT_ODDS","historical_bookmaker_odds_used":False}
    candidates = {}
    for market,p,price in (("UNDER_3_5",".72",odds),("OVER_3_5",".28","3.50")):
        c = accuracy_candidate(market)
        c.update(fixture_id=fid,candidate_id=f"forward-{fid}-{market}",league_id=71,season=2026,
            home_team_id=1+2*index,away_team_id=2+2*index,competition_profile="SENIOR_MEN",
            kickoff_utc=(now+timedelta(hours=1)).isoformat(),captured_odds=price,offered_odds=price,
            ensemble_probability=p,edge=str(Decimal(p)-1/Decimal(price)),
            provider_origin_timestamp_utc=now.isoformat(),goalvision_retrieved_at_utc=now.isoformat(),
            flags=[])
        c["signals"][0]["probability"] = p
        bind_candidate_evidence(c)
        candidates[market] = c
    refs = {m:{"probability":c["ensemble_probability"],"candidate_id":c["candidate_id"],
               "candidate_fingerprint":fingerprint(c)} for m,c in candidates.items()}
    cap = capture(source,captured_at=now,kickoff=now+timedelta(hours=1),
                  model_probabilities=refs,policy_context={"single_minimum":"1.50"})
    return {"capture":cap,"candidates":candidates,"training_results":history()}

@pytest.fixture(scope="module")
def artifact():
    return model.fit(history(),league_id=71,as_of=START,plan=PLAN)

@pytest.fixture(scope="module")
def forecasts(artifact):
    return [service.forecast(item(i),artifact=artifact,plan=PLAN,now=START) for i in range(3)]

def fact(index=0, *, score=(1,0), status="RESOLVED", **changes):
    return {"fixture_id":9000+index,"status":status,"home_goals":score[0],"away_goals":score[1],
        "settled_at":(START+timedelta(hours=3)).isoformat(),"source_product":"SINGLE",
        "source_fingerprint":f"fictional-result-{index}",**changes}

def reseal(value):
    value = deepcopy(value); value.pop("fingerprint"); return seal(value)

def test_new_plan_and_no_development_coercion(artifact):
    assert PLAN["fingerprint"] != OLD_PLAN["fingerprint"]
    assert PLAN["protected_calendar"] == OLD_PLAN["protected_calendar"]
    assert PLAN["train_end"] == OLD_PLAN["train_end"]
    assert artifact["forward_eligible"] and artifact["selection_effect"] == "NONE"
    model.verify_artifact(artifact,plan=PLAN)
    old = development.fit(history(),league_id=71,as_of=START,plan=OLD_PLAN)
    with pytest.raises((ValueError,KeyError)):
        model.verify_artifact(old,plan=PLAN)
    with pytest.raises((ValueError,KeyError)):
        development.verify_artifact(artifact,plan=OLD_PLAN)

@pytest.mark.parametrize("bad",["before","development","policy","certificate","training","baseline"])
def test_model_plan_and_artifact_fail_closed(artifact,bad):
    if bad == "before":
        with pytest.raises(ValueError,match="DECLARATION"):
            model.fit(history(),league_id=71,as_of=utc(PLAN["declared_at"])-timedelta(seconds=1),plan=PLAN)
        return
    changed=deepcopy(artifact)
    if bad=="development": changed["version"]=development.VERSION
    if bad=="policy": changed["policy"]["ridge"]=.9
    if bad=="certificate": changed["fit"]["certificate"]["stationarity_inf"]=0
    if bad=="training": changed["training_matches"][0]["fixture_id"]=1602097
    if bad=="baseline": changed["baseline_model"]["league_id"]=9
    with pytest.raises((ValueError,KeyError)):
        model.verify_artifact(reseal(changed),plan=PLAN)

def test_actual_completion_freshness_and_known_development_exclusion(artifact):
    with pytest.raises(ValueError):
        service.forecast(item(),artifact=artifact,plan=PLAN,now=START+timedelta(seconds=901))
    source=item();source["capture"]["fixture_id"]=1602097
    with pytest.raises(ValueError,match="EXCLUDED"):
        service.forecast(source,artifact=artifact,plan=PLAN,now=START)
    with pytest.raises(ValueError):
        service.forecast(item(),artifact=artifact,plan=PLAN,now=START+timedelta(hours=1))

def test_baseline_unavailable_remains_candidate_forecast(monkeypatch):
    monkeypatch.setattr(model.baseline,"fit",lambda *a,**k:(_ for _ in ()).throw(ValueError("FIT_DID_NOT_CONVERGE")))
    a=model.fit(history(),league_id=71,as_of=START,plan=PLAN)
    f=service.forecast(item(),artifact=a,plan=PLAN,now=START)
    assert f["missing_comparators"]["DIXON_COLES_V1:FIT_DID_NOT_CONVERGE"]==2
    score=service.evaluate([f],{a["fingerprint"]:a},[fact()],plan=PLAN,now=START+timedelta(days=1))
    pair=score["overall"]["paired"]["DIXON_COLES_V1"]
    assert pair["missing_market_rows"]==2 and score["overall"]["common_market_rows"]==0

def test_paired_metrics_and_forged_forecast_reproduction(artifact,forecasts):
    metrics=service.evaluate(forecasts,{artifact["fingerprint"]:artifact},
        [fact(i) for i in range(3)],plan=PLAN,now=START+timedelta(days=1))
    assert metrics["overall"]["fixtures"]==3
    assert metrics["overall"]["common_market_rows"]==6
    assert metrics["quality_verdict"]=="NEEDS_MORE_EVIDENCE"
    altered=deepcopy(forecasts[0]);altered["comparisons"]["UNDER_3_5"]["DIXON_COLES"]=.999
    with pytest.raises(ValueError,match="REPRODUCTION"):
        service.evaluate([reseal(altered)],{artifact["fingerprint"]:artifact},[],plan=PLAN,now=START)

def test_combo_full_candidate_quality_and_deterministic_batch(forecasts):
    a=combo.build_batch(forecasts,plan=PLAN,now=START)
    b=combo.build_batch(list(reversed(forecasts)),plan=PLAN,now=START)
    assert a==b and a["eligible_fixtures"]==3
    assert all(len(v)==1 for v in a["selections"].values())
    assert a["score_is_calibrated_probability"] is False
    for triples in a["selections"].values():
        assert Decimal(triples[0]["combined_odds"])==Decimal("1.30")**3
        assert len({leg["fixture_id"] for leg in triples[0]["legs"]})==3
        assert all(leg["market"]=="UNDER_3_5" for leg in triples[0]["legs"])

@pytest.mark.parametrize("mode",["stale","today","floor","quality","tracking","used_fixture","used_team","shared_team"])
def test_combo_never_forces_ineligible_triple(forecasts,mode):
    values=deepcopy(forecasts); now=START; kwargs={}
    if mode=="stale": now+=timedelta(seconds=901)
    elif mode=="today":
        for f in values: f["kickoff_utc"]=(START+timedelta(days=1)).isoformat()
    elif mode=="used_fixture": kwargs["used_fixtures"]=frozenset({9000})
    elif mode=="used_team": kwargs["used_teams"]=frozenset({"1"})
    else:
        for c in values[0]["candidate_references"].values():
            if mode=="floor": c["captured_odds"]="1.29999"
            if mode=="quality": c["hard_failures"].append("UNSUPPORTED_MARKET")
            if mode=="tracking": c["candidate_lane"]="TRACKING"
            if mode=="shared_team": c["home_team_id"]=values[1]["candidate_references"]["UNDER_3_5"]["home_team_id"]
            bind_candidate_evidence(c)
    values=[reseal(v) for v in values]
    output=combo.build_batch(values,plan=PLAN,now=now,**kwargs)
    assert not any(output["selections"].values())

def test_shadow_rank_can_choose_other_market_without_inventing_probability(forecasts):
    pool=combo.build_batch(forecasts,plan=PLAN,now=START)["pool"]
    first=deepcopy(pool[0]); first.update(market="OVER_2_5",selection_key="9000:OVER_2_5",
        ensemble_probability=".80",dc_probability=".30",ranking_score=".30")
    pool.append(first)
    baseline=combo.select(pool,combo.POLICIES[0])[0]["legs"]
    candidate=combo.select(pool,combo.POLICIES[1])[0]["legs"]
    assert next(v["market"] for v in baseline if v["fixture_id"]==9000)=="OVER_2_5"
    assert next(v["market"] for v in candidate if v["fixture_id"]==9000)=="UNDER_3_5"

def test_combo_replay_union_exposure_and_immutable_history(tmp_path,forecasts):
    store=ResearchStore(tmp_path/"own.db")
    first=combo.capture(forecasts,store,plan=PLAN,now=START)
    second=combo.capture(forecasts,store,plan=PLAN,now=START+timedelta(seconds=1))
    assert all(first["selections"].values()) and not any(second["selections"].values())
    assert store.all("combo_batch")
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute("DELETE FROM dc_research_records")
    store.close()

@pytest.mark.parametrize("facts,status,remaining,profit",[
    ([], "PENDING",3,None),
    ([fact(0,score=(3,2))],"LOST",2,"-1"),
    ([fact(i) for i in range(3)],"WON",0,"1.197"),
    ([fact(i,status="VOID",score=(None,None)) for i in range(3)],"VOID",0,"0"),
    ([fact(0,status="VOID",score=(None,None)),fact(1),fact(2)],"PARTIAL_VOID",0,"0.6900")])
def test_shadow_settlement_pending_early_loss_void_and_profit(forecasts,facts,status,remaining,profit):
    batch=combo.build_batch(forecasts,plan=PLAN,now=START)
    output=combo.evaluate([batch],forecasts,facts,plan=PLAN,now=START+timedelta(days=1))
    for summary in output["policies"].values():
        row=summary["rows"][0]
        assert row["status"]==status and len(row["remaining_fixtures"])==remaining
        assert (Decimal(row["profit_units"]) if row["profit_units"] is not None else None)==(Decimal(profit) if profit is not None else None)

def test_combo_bad_result_and_batch_cannot_change_history(forecasts):
    batch=combo.build_batch(forecasts,plan=PLAN,now=START)
    bad=deepcopy(batch);bad["selections"][combo.POLICIES[0]][0]["combined_odds"]="10"
    with pytest.raises(ValueError,match="REPRODUCTION"):
        combo.evaluate([reseal(bad)],forecasts,[],plan=PLAN,now=START)
    with pytest.raises(ValueError,match="CONFLICTING"):
        combo.evaluate([batch],forecasts,[fact(),fact(score=(2,2))],plan=PLAN,now=START+timedelta(days=1))
    output=combo.evaluate([batch],forecasts,[fact(source_product="COMBO_LEG")],plan=PLAN,now=START+timedelta(days=1))
    assert all(v["lifecycle"]=={"PENDING":1} for v in output["policies"].values())

def databases(tmp_path):
    shadow=tmp_path/"shadow.db";audit=tmp_path/"audit.db";ledger=tmp_path/"ledger.db"
    repo=ShadowEvidenceRepository(shadow)
    for i in range(3):
        source=item(i)
        for c in source["candidates"].values(): repo.append("candidate",c["candidate_id"],c,created_at=START)
        cap=source["capture"];repo.append("devig_research",cap["capture_id"],cap,created_at=START)
    payload={"response":[{"fixture":{"id":r["fixture_id"],"date":r["kickoff_utc"],"status":{"short":"FT"}},
        "league":{"id":71},"teams":{"home":{"id":r["home_team_id"]},"away":{"id":r["away_team_id"]}},
        "score":{"fulltime":{"home":r["home_goals"],"away":r["away_goals"]}}} for r in history()[-99:]]}
    repo.append_cache("/fixtures(results)",{"league":71,"season":2026,"status":"FT","last":99},
                      payload,retrieved_at=START-timedelta(minutes=1),ttl=timedelta(hours=6));repo.close()
    with sqlite3.connect(audit) as db:
        db.execute("CREATE TABLE holdout_results(id TEXT,stream TEXT,fingerprint TEXT,document TEXT)")
        db.execute("CREATE TABLE learning_observations(id TEXT,stream TEXT,fingerprint TEXT,document TEXT)")
        db.execute("CREATE TABLE canonical_results(id TEXT,stream TEXT,created_at TEXT,fingerprint TEXT,document TEXT)")
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE evidence(kind TEXT,identity TEXT,fingerprint TEXT,document TEXT)")
    return Namespace(shadow_database=shadow,audit_database=audit,ledger_database=ledger,
                     research_database=tmp_path/"forward.db",limit=12)

def test_source_to_model_combo_and_metrics_query_only(tmp_path,monkeypatch):
    args=databases(tmp_path);before={p:p.read_bytes() for p in (args.shadow_database,args.audit_database,args.ledger_database)}
    monkeypatch.setattr(worker,"in_slot",lambda _:True)
    output=worker.cycle(args,now=lambda:START,idle=lambda:True)
    assert output["status"]=="COMPLETED"
    assert output["capture"]["counts"]=={"forecast":3}
    assert output["capture"]["combo_shadow"]["selections"]==dict.fromkeys(combo.POLICIES,1)
    assert output["evaluation"]["lifecycle"]["PENDING"]==3
    assert output["evaluation"]["combo_shadow"]["policies"][combo.POLICIES[0]]["bets"]==1
    replay=worker.cycle(args,now=lambda:START+timedelta(seconds=1),idle=lambda:True)
    assert replay["capture"]["counts"]=={"already_forecast":3}
    assert all(p.read_bytes()==v for p,v in before.items())
    store=ResearchStore(args.research_database,readonly=True)
    assert len(store.all("model"))==1 and len(store.all("forecast"))==3
    assert not store.all("claim") and not store.all("receipt")
    store.close()
    later=worker.cycle(args,now=lambda:utc(PLAN["evaluation_end"])+timedelta(days=1),idle=lambda:True)
    assert later["capture"]["reason"]=="OUTSIDE_FROZEN_CAPTURE_WINDOW"

@pytest.mark.parametrize("minute,second,expected",[(12,30,True),(42,59,True),(12,29,False),(13,0,False),(10,30,False),(40,30,False)])
def test_separate_no_catchup_timer(minute,second,expected):
    assert worker.in_slot(START.replace(minute=minute,second=second)) is expected

def test_original_cohort_protected_even_on_capture_failure_or_hardlink(tmp_path,monkeypatch):
    old=tmp_path/"original.db"; store=ResearchStore(old);store.append("plan",OLD_PLAN["fingerprint"],OLD_PLAN);store.close()
    alias=tmp_path/"alias.db";os.link(old,alias);before=old.read_bytes()
    monkeypatch.setattr(cli,"ORIGINAL_RESEARCH",old)
    for path in (old,alias):
        with pytest.raises(ValueError,match="ORIGINAL"):
            worker.cycle(Namespace(research_database=path),now=lambda:START,idle=lambda:True)
    assert old.read_bytes()==before

def test_busy_original_blocks_without_source_reads(tmp_path):
    args=Namespace(research_database=tmp_path/"never.db")
    output=worker.cycle(args,now=lambda:START.replace(minute=12,second=30),idle=lambda:False,
                        execute=lambda *a:pytest.fail("unexpected execution"))
    assert output["reason"]=="PRODUCTION_BUSY_OR_UNKNOWN"
    assert not args.research_database.exists()
    assert "goalvision-dixon-coles-research.service" in worker.SERVICES


def test_duplicate_economic_exposure_cannot_inflate_shadow_statistics(forecasts):
    first=combo.build_batch(forecasts,plan=PLAN,now=START)
    second=combo.build_batch(forecasts,plan=PLAN,now=START+timedelta(seconds=1))
    with pytest.raises(ValueError,match="EXPOSURE"):
        combo.evaluate([first,second],forecasts,[],plan=PLAN,now=START+timedelta(minutes=1))
