"""Bounded offline candidate comparison; existing stores are query-only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from app.dixon_coles_constrained import model as candidate
from app.dixon_coles_research import model as baseline, sources
from app.dixon_coles_research.contracts import load_plan, utc, verify, digest
from app.adaptive_lab.devig_research import verify_capture

def run(shadow: Path,audit: Path,research: Path) -> dict:
    plan=load_plan();protocol=candidate.load_protocol()
    reserved=sources.consumed_holdout_fixtures(audit)
    evidence=Path(__file__).parents[1]/"dixon_coles_automation_20261003"/"first_natural_cycle.json"
    diagnostics=json.loads(evidence.read_text())["diagnostics"]
    cases=[]
    with sources.readonly(shadow) as db:
        for diagnostic in diagnostics:
            verify(diagnostic)
            cap=sources._evidence(db,"devig_research",diagnostic["capture_id"]);verify_capture(cap)
            reference=next(iter(cap["model_probabilities"].values()))
            row=sources._evidence(db,"candidate",reference["candidate_id"])
            if sources.fingerprint(row)!=reference["candidate_fingerprint"]:
                raise ValueError("CANDIDATE_REFERENCE")
            history=sources._history(db,row["league_id"],row["season"],utc(cap["captured_at"]))
            cases.append({"role":"KNOWN_DEVELOPMENT_FAILURE","fixture_id":row["fixture_id"],
                "league_id":row["league_id"],"home":row["home_team_id"],"away":row["away_team_id"],
                "as_of":cap["captured_at"],"kickoff":cap["kickoff_utc"],"family":cap["market_family"],
                "rows":history,"baseline_artifact":None})
    with sources.readonly(research) as db:
        rows=db.execute("SELECT document FROM dc_research_records WHERE kind='forecast' ORDER BY identity LIMIT 100").fetchall()
        seen=set()
        for raw in rows:
            forecast=json.loads(raw["document"]);verify(forecast)
            if forecast["fixture_id"] not in {1641278,1498855} or forecast["fixture_id"] in seen:
                continue
            seen.add(forecast["fixture_id"])
            raw_model=db.execute("SELECT document FROM dc_research_records WHERE kind='model' AND identity=?",
                                 (forecast["model_fingerprint"],)).fetchone()
            if raw_model is None: raise ValueError("MODEL_REFERENCE_MISSING")
            model=json.loads(raw_model["document"]);verify(model)
            row=next(iter(forecast["candidate_references"].values()))
            cases.append({"role":"KNOWN_DEVELOPMENT_INTERIOR","fixture_id":row["fixture_id"],
                "league_id":row["league_id"],"home":row["home_team_id"],"away":row["away_team_id"],
                "as_of":model["input_as_of"],"kickoff":forecast["kickoff_utc"],
                "family":forecast["market_family"],"rows":model["training_matches"],
                "baseline_artifact":model})
    reports=[];artifacts=[]
    for case in cases:
        started=time.process_time();prior=case["baseline_artifact"];error=None
        if prior is None:
            try: prior=baseline.fit(case["rows"],league_id=case["league_id"],as_of=utc(case["as_of"]),
                                    plan=plan,additional_reserved=reserved)
            except ValueError as exc: error=str(exc)
        before=digest(case["rows"])
        try:
            fitted=candidate.fit(case["rows"],league_id=case["league_id"],as_of=utc(case["as_of"]),
                                 plan=plan,additional_reserved=reserved)
            cert=candidate.verify_artifact(fitted,plan=plan,additional_reserved=reserved)
        except ValueError as exc:
            reports.append({"fixture_id":case["fixture_id"],"family":case["family"],
                "candidate_status":"UNAVAILABLE","reason":str(exc),"baseline_error":error})
            continue
        assert before==digest(case["rows"])
        args=dict(home_team_id=case["home"],away_team_id=case["away"],league_id=case["league_id"],
                  as_of=utc(case["as_of"]),kickoff=utc(case["kickoff"]),neutral=False,plan=plan)
        predicted=candidate.predict(fitted,**args,additional_reserved=reserved)
        prior_prediction=baseline.predict(prior,**args) if prior is not None else None
        delta=max(abs(v-prior_prediction["dixon_coles"]["probabilities"][k])
                  for k,v in predicted["dixon_coles"]["probabilities"].items()) if prior_prediction else None
        item={"role":case["role"],"fixture_id":case["fixture_id"],"family":case["family"],
            "league_id":case["league_id"],"input_as_of":case["as_of"],"training_matches":len(fitted["training_matches"]),
            "training_teams":len(fitted["team_ids"]),"input_fingerprint":digest(fitted["training_matches"]),
            "baseline_status":"AVAILABLE" if prior else "UNAVAILABLE","baseline_error":error,
            "baseline_objective":prior["fit"]["objective"] if prior else None,
            "candidate_status":"AVAILABLE_DEVELOPMENT_ONLY","candidate_fingerprint":fitted["fingerprint"],
            "candidate_fit":fitted["fit"],"maximum_probability_delta_vs_baseline":delta,
            "objective_delta_vs_baseline":cert["objective"]-prior["fit"]["objective"] if prior else None,
            "cpu_seconds":time.process_time()-started,"predictions_are_development_only":True}
        if case["role"]=="KNOWN_DEVELOPMENT_INTERIOR":
            assert delta<=protocol["acceptance"]["interior_probability_absolute_tolerance"]
            assert abs(item["objective_delta_vs_baseline"])<=protocol["acceptance"]["interior_objective_absolute_tolerance"]
        reports.append(item);artifacts.append(fitted)
        print(json.dumps({k:item[k] for k in ("fixture_id","family","candidate_status","cpu_seconds")}),flush=True)
    # Exactly reproducible ordering, without adding any forecast to an existing store.
    if artifacts:
        original=artifacts[0]
        reverse=candidate.fit(list(reversed(original["training_matches"])),league_id=original["league_id"],
                 as_of=utc(original["input_as_of"]),plan=plan,additional_reserved=reserved)
        assert original==reverse
    return {"version":"DC_CONSTRAINED_DEVELOPMENT_COMPARISON_V1","observed_at":datetime.now(timezone.utc).isoformat(),
            "protocol_fingerprint":protocol["fingerprint"],"baseline_plan_fingerprint":plan["fingerprint"],
            "cases":reports,"reversed_order_replay_exact":bool(artifacts),
            "quality_verdict":"NOT_EVALUATED_DEVELOPMENT_ONLY","no_global_optimum_claim":True,
            "forecast_writes":0,"model_store_writes":0,"research_database_writes":0,
            "provider_calls":0,"telegram_requests":0,"historical_bookmaker_odds_used":False,
            "no_backfill":True,"no_deployment":True,"priority":"NORMAL"}


def controlled_checks() -> dict:
    """Synthetic hold-out compatibility and a declared maximum-size budget check."""
    from datetime import timedelta
    from math import exp
    import random
    from app.adaptive_lab.performance import probability_metrics
    from tests.test_dixon_coles_research import history, PLAN, START
    rows=history()
    old=baseline.fit(rows,league_id=71,as_of=START,plan=PLAN)
    new=candidate.fit(rows,league_id=71,as_of=START,plan=PLAN)
    rng=random.Random(731956)
    def poisson(rate):
        count=0;product=1.0
        while product>exp(-rate):
            count+=1;product*=rng.random()
        return count-1
    prior_pairs=[];new_pairs=[];maximum_delta=0.0
    for i in range(30):
        home=i%6+1;away=(home+i//6)%6+1
        if away==home: away=home%6+1
        args=dict(home_team_id=home,away_team_id=away,league_id=71,neutral=False,
                  as_of=START,kickoff=START+timedelta(days=i//10,hours=1),plan=PLAN)
        p=baseline.predict(old,**args)["dixon_coles"]["probabilities"]
        q=candidate.predict(new,**args)["dixon_coles"]["probabilities"]
        h,a=poisson(1.6),poisson(1.1)
        for market,label in (("HOME_WIN",int(h>a)),("DRAW",int(h==a)),("AWAY_WIN",int(h<a))):
            prior_pairs.append((p[market],label));new_pairs.append((q[market],label))
            maximum_delta=max(maximum_delta,abs(p[market]-q[market]))
    assert maximum_delta<=candidate.load_protocol()["acceptance"]["interior_probability_absolute_tolerance"]
    stress=[]
    for i in range(500):
        home=i%64+1;away=(home+1+i//64)%64+1
        kickoff=utc(PLAN["train_end"])-timedelta(days=501-i)
        stress.append({"fixture_id":3000000+i,"league_id":71,
            "home_team_id":home,"away_team_id":away,"home_goals":poisson(1.4),"away_goals":poisson(1.0),
            "kickoff_utc":kickoff.isoformat(),"observed_at_utc":(kickoff+timedelta(hours=3)).isoformat(),
            "neutral":False,"status":"FT","source_fingerprint":"SYNTHETIC_CAPACITY_"+str(i)})
    started=time.process_time()
    try:
        large=candidate.fit(stress,league_id=71,as_of=START,plan=PLAN)
        candidate.verify_artifact(large,plan=PLAN)
        capacity={"status":"AVAILABLE_DEVELOPMENT_ONLY","training_matches":len(large["training_matches"]),
                  "teams":len(large["team_ids"]),"fit":large["fit"]}
    except ValueError as exc:
        capacity={"status":"EXPLICITLY_UNAVAILABLE","reason":str(exc)}
    capacity["cpu_seconds"]=time.process_time()-started
    print(json.dumps({"synthetic_capacity_status":capacity["status"],"cpu_seconds":capacity["cpu_seconds"]}),flush=True)
    return {"synthetic_only":True,"not_real_predictive_quality_evidence":True,
            "independent_synthetic_fixtures":30,"market_rows":90,"kickoff_dates":3,
            "baseline":probability_metrics(prior_pairs),"candidate":probability_metrics(new_pairs),
            "maximum_probability_delta":maximum_delta,"maximum_capacity_case":capacity}

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("shadow","audit","research","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args();resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    report=run(args.shadow,args.audit,args.research)
    report["controlled_checks"]=controlled_checks()
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"complete":True,"cases":len(report["cases"])}))

if __name__=="__main__":
    main()
