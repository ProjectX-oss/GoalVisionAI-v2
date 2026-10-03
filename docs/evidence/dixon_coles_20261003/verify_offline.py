"""Reproducible offline evidence; sources query-only, fitting in isolated memory."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import random
import time
from app.dixon_coles_research.contracts import load_plan,digest,seal,utc
from app.dixon_coles_research.model import fit
from app.dixon_coles_research.service import forecast
from app.dixon_coles_research.metrics import evaluate
from app.dixon_coles_research.sources import readonly,_history,consumed_holdout_fixtures
from app.adaptive_lab.devig_research import capture
from app.real_match_lab_analysis.fingerprint import fingerprint
from tests.test_dixon_coles_research import history,item,START

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"docs/evidence/dixon_coles_20261003"
SHADOW=Path("/home/arvis/GoalVisionAI/var/lab_v2/shadow.db")
AUDIT=Path("/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db")

def write(name,document):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(document,sort_keys=True,indent=2,allow_nan=False)+"\n")

def main():
    current=os.getpriority(os.PRIO_PROCESS,0)
    if current<10: os.nice(10-current)
    plan=load_plan()
    # Synthetic result-only TRAIN; held-out fixture goals are never passed to fit.
    artifact=fit(history(),league_id=71,as_of=START,plan=plan)
    forecasts=[];results=[];rng=random.Random(30103)
    for i in range(30):
        source=item();fid=9000+i;kickoff=START+timedelta(hours=2+i)
        old=source["capture"];consensus=deepcopy(old["source_consensus"]);consensus["fixture_id"]=fid
        for quote in consensus["quotes"]:
            quote["fixture_id"]=fid
            from decimal import Decimal
            quote["provenance_fingerprint"]=fingerprint(dict(provider="API_FOOTBALL",fixture_id=fid,
                bookmaker_id=quote["bookmaker_id"],bookmaker=quote["bookmaker_name"],market=quote["market"],
                odds=Decimal(quote["decimal_odds"]),provider_updated=utc(quote["provider_origin_timestamp_utc"]),
                retrieved_at=utc(quote["retrieved_at_utc"])))
        candidates=deepcopy(source["candidates"])
        for m,c in candidates.items():
            c.update(fixture_id=fid,candidate_id=f"fictional-{fid}-{m}",kickoff_utc=kickoff.isoformat(),
                     home_team_id=i%6+1,away_team_id=(i%6+1)%6+1,
                     quote_provenance_fingerprint=next(q["provenance_fingerprint"] for q in consensus["quotes"] if q["market"]==m))
        refs={m:{"probability":c["ensemble_probability"],"candidate_id":c["candidate_id"],
                 "candidate_fingerprint":fingerprint(c)} for m,c in candidates.items()}
        source["candidates"]=candidates
        source["capture"]=capture(consensus,captured_at=START,kickoff=kickoff,model_probabilities=refs,
                                  policy_context=old["policy_context"])
        forecasts.append(forecast(source,artifact=artifact,plan=plan,now=START))
        results.append({"fixture_id":fid,"status":"RESOLVED","home_goals":rng.randrange(4),
                        "away_goals":rng.randrange(3),"settled_at":(kickoff+timedelta(hours=3)).isoformat(),
                        "source_fingerprint":digest(["fictional",fid]),"source_product":"SHADOW"})
    after=START+timedelta(days=3)
    metrics=evaluate(forecasts,{artifact["fingerprint"]:artifact},results,plan=plan,now=after)
    replay=evaluate(list(reversed(forecasts)),{artifact["fingerprint"]:artifact},list(reversed(results)),plan=plan,now=after)
    assert replay==metrics
    write("controlled_replay.json",seal({"source_mode":"CONTROLLED_SYNTHETIC_RESEARCH_ONLY",
        "real_world_quality_evidence":False,"train_matches":len(history()),"held_out_fixtures":30,
        "train_evaluation_fixture_overlap":0,"model_fingerprint":artifact["fingerprint"],
        "fit":artifact["fit"],"replay_identical":True,
        "metrics_fingerprint":metrics["fingerprint"],"overall_metrics":metrics["overall"],
        "lifecycle":metrics["lifecycle"],"segment_counts":{k:len(v) for k,v in metrics["segments"].items()},
        "production_training_registration":False,"telegram_calls":0}))
    now=datetime.now(timezone.utc);reserved=consumed_holdout_fixtures(AUDIT);prepared=[];seen=set()
    with readonly(SHADOW) as connection:
        rows=connection.execute("SELECT query_json,retrieved_at_utc FROM lab_v2_provider_cache WHERE endpoint='/fixtures(results)' ORDER BY rowid DESC LIMIT 30").fetchall()
        for row in rows:
            q=json.loads(row["query_json"]);key=(q["league"],q["season"])
            if key in seen: continue
            seen.add(key)
            prepared.append((key,_history(connection,*key,now)))
            if len(prepared)>=3: break
    diagnostics=[]
    for (league,season),rows in prepared:
        start=time.monotonic()
        try:
            model=fit(rows,league_id=league,as_of=now,plan=plan,additional_reserved=reserved)
            diagnostics.append({"league_id":league,"season":season,"status":"FITTED",
                "input_results":len(rows),"retained_results":len(model["training_matches"]),
                "excluded":model["excluded"],"model_fingerprint":model["fingerprint"],
                "fit":model["fit"],"training_data_fingerprint":digest(model["training_matches"]),
                "duration_seconds":round(time.monotonic()-start,4)})
        except ValueError as exc:
            diagnostics.append({"league_id":league,"season":season,"status":"UNAVAILABLE",
                                "reason":str(exc),"input_results":len(rows)})
    write("cached_result_fit_check.json",seal({"as_of":now.isoformat(),
        "source_mode":"EXISTING_CACHED_REGULATION_RESULTS_QUERY_ONLY",
        "sampling":"LATEST_THREE_DISTINCT_LEAGUE_SEASONS_WITHIN_30_CACHE_ROWS",
        "plan_fingerprint":plan["fingerprint"],"fits":diagnostics,
        "predictive_quality_verdict":"NOT_EVALUATED; FITTING_IS_NOT_FORWARD_PERFORMANCE",
        "production_model_registry_changed":False,"provider_calls":0,"telegram_calls":0}))
    print(json.dumps({"synthetic_held_out_fixtures":30,"synthetic_replay":"PASS","cached_fit_checks":diagnostics}))

if __name__=="__main__": main()
