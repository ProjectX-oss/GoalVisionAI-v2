"""Exactly paired prospective probability scores; never evaluates a bet policy."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime
from .contracts import seal,verify,verify_plan,utc,integer,VERSION
from .service import forecast
from app.adaptive_lab.performance import probability_metrics,band

COMPARATORS=("DIXON_COLES","POISSON_SAME_RATES","EXISTING_ENSEMBLE",
             "MULTIPLICATIVE","SHIN","POWER","OO_EPC")

def won(market: str,h: int,a: int) -> int:
    if market=="HOME_WIN": return int(h>a)
    if market=="AWAY_WIN": return int(h<a)
    if market=="DRAW": return int(h==a)
    if market=="BTTS_YES": return int(h>0 and a>0)
    if market=="BTTS_NO": return int(not(h>0 and a>0))
    direction,line,_=market.split("_")
    return int(h+a>int(line)) if direction=="OVER" else int(h+a<=int(line))

def _summary(rows: list[dict]) -> dict:
    paired={}
    for name in COMPARATORS:
        subset=[r for r in rows if name in r["p"]]
        paired[name]={"method":probability_metrics([(r["p"][name],r["y"]) for r in subset]),
                      "paired_dixon_coles":probability_metrics([(r["p"]["DIXON_COLES"],r["y"]) for r in subset]),
                      "fixtures":len({r["fixture_id"] for r in subset}),
                      "missing_market_rows":len(rows)-len(subset)}
    common=[r for r in rows if all(k in r["p"] for k in COMPARATORS)]
    return {"market_rows":len(rows),"fixtures":len({r["fixture_id"] for r in rows}),
            "kickoff_dates":len({r["date"] for r in rows}),
            "paired":paired,"common_market_rows":len(common),
            "common":{k:probability_metrics([(r["p"][k],r["y"]) for r in common]) for k in COMPARATORS}}

def evaluate(forecasts: list[dict],models: dict[str,dict],results: list[dict],*,
             plan: dict,now: datetime,additional_reserved: frozenset[int]=frozenset()) -> dict:
    verify_plan(plan); cutoff=utc(now); outcomes={}; counts=Counter()
    reserved={int(v) for v in plan["protected_calendar"]["reserved_holdout_fixtures"]}|set(additional_reserved)
    for result in results:
        if result.get("source_product") not in {"SINGLE","SHADOW"}: counts["excluded_non_independent_result"]+=1; continue
        if utc(result["settled_at"])>cutoff: counts["future_result"]+=1; continue
        fid=integer(result["fixture_id"])
        if fid in reserved: counts["reserved_result"]+=1; continue
        if result.get("status") not in {"RESOLVED","VOID"}: counts["unresolved_result"]+=1; continue
        if not result.get("source_fingerprint"): raise ValueError("RESULT_PROVENANCE")
        if result["status"]=="RESOLVED":
            integer(result["home_goals"],low=0,high=30); integer(result["away_goals"],low=0,high=30)
        previous=outcomes.get(fid)
        if previous:
            if any(previous.get(k)!=result.get(k) for k in ("status","home_goals","away_goals")):
                raise ValueError("CONFLICTING_FORWARD_RESULT")
            counts["duplicate_result"]+=1
            if utc(previous["settled_at"])<=utc(result["settled_at"]): continue
        outcomes[fid]=result
    rows=[]; seen=set(); lifecycle=defaultdict(set)
    for record in sorted(forecasts,key=lambda r:(r["forecast_at"],r["fingerprint"])):
        verify(record)
        if utc(record["forecast_at"])>cutoff: counts["future_forecast"]+=1; continue
        if record["plan_fingerprint"]!=plan["fingerprint"]: raise ValueError("PLAN_MIXING")
        fid=record["fixture_id"]; key=(fid,record["market_family"])
        if key in seen: raise ValueError("DUPLICATE_RESEARCH_FAMILY")
        seen.add(key)
        if fid in reserved: counts["reserved_forecast"]+=1; continue
        artifact=models.get(record["model_fingerprint"])
        if artifact is None: raise ValueError("MODEL_REFERENCE_MISSING")
        reproduced=forecast({"capture":record["capture"],"candidates":record["candidate_references"]},
                            artifact=artifact,plan=plan,now=utc(record["forecast_at"]))
        if reproduced!=record: raise ValueError("FORECAST_REPRODUCTION_FAILED")
        result=outcomes.get(fid)
        counts["forecast_families"]+=1
        if result is None: lifecycle["PENDING"].add(fid); continue
        if utc(result["settled_at"])<=utc(record["kickoff_utc"]):
            raise ValueError("RESULT_BEFORE_KICKOFF")
        if result["status"]=="VOID": lifecycle["VOID"].add(fid); continue
        lifecycle["RESOLVED"].add(fid)
        lead=(utc(record["kickoff_utc"])-utc(record["forecast_at"])).total_seconds()/60
        for market,probs in record["comparisons"].items():
            rows.append({"fixture_id":fid,"date":record["kickoff_utc"][:10],
                         "league":str(record["league_id"]),"market":market,
                         "family":record["market_family"],"lead":band(lead,(10,25,45,90)),
                         "odds":band(record["comparison_odds"][market],(1.5,2,3,5,10)),
                         "p":probs,"y":won(market,result["home_goals"],result["away_goals"])})
    segments={}
    for dimension in ("league","market","family","lead","odds"):
        groups=defaultdict(list)
        for row in rows: groups[row[dimension]].append(row)
        segments[dimension]={k:_summary(v) for k,v in sorted(groups.items())}
    return seal({"version":VERSION,"plan_fingerprint":plan["fingerprint"],"as_of":cutoff.isoformat(),
                 "counts":dict(counts),"lifecycle":{k:len(lifecycle[k]) for k in ("PENDING","VOID","RESOLVED")},
                 "overall":_summary(rows),"segments":segments,
                 "quality_verdict":"NEEDS_MORE_EVIDENCE",
                 "unit_of_independence":"FIXTURE_AND_KICKOFF_DATE; COMPLEMENTS_ARE_CORRELATED",
                 "betting_metrics":"NOT_APPLICABLE_NO_RESEARCH_BET_SELECTION",
                 "selection_effect":"NONE","automatic_promotion":False})
