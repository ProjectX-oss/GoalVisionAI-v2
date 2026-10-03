"""Manual isolated research intake; fitting never runs in production timers."""
from __future__ import annotations
from collections import Counter
from datetime import datetime
from math import isfinite
from typing import Callable
from .contracts import seal,verify,verify_plan,utc,finite,VERSION
from .model import fit,predict
from .repository import ResearchStore
from app.adaptive_lab.devig_research import verify_capture, capture as recapture
from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS, RETRIEVAL_MAX_AGE_SECONDS

def forecast(item: dict, *, artifact: dict, plan: dict, now: datetime, predictor: Callable | None = None,
             record_version: str = VERSION) -> dict:
    """Freeze DC, a same-rate Poisson ablation, and exact paired current references."""
    verify_plan(plan); verify(artifact)
    capture=item["capture"]; verify_capture(capture); cutoff=utc(now)
    if not utc(plan["evaluation_start"])<=cutoff<utc(capture["kickoff_utc"])<utc(plan["evaluation_end"]):
        raise ValueError("OUTSIDE_PROSPECTIVE_WINDOW")
    if not utc(plan["declared_at"])<=utc(capture["captured_at"])<=cutoff:
        raise ValueError("PREDECLARATION_OR_FUTURE_CAPTURE")
    if (cutoff-utc(capture["captured_at"])).total_seconds()>RETRIEVAL_MAX_AGE_SECONDS:
        raise ValueError("STALE_COMPARISON_INPUT")
    if any((cutoff-utc(q["retrieved_at_utc"])).total_seconds()>RETRIEVAL_MAX_AGE_SECONDS for q in capture["source_consensus"]["quotes"]):
        raise ValueError("STALE_COMPARISON_RETRIEVAL")
    # Re-validate original quote clocks at actual completion, not just cycle start.
    current=recapture(capture["source_consensus"],captured_at=cutoff,kickoff=capture["kickoff_utc"],
                      model_probabilities=capture["model_probabilities"],policy_context=capture["policy_context"],
                      source_issues=capture["source_issues"])
    if capture["status"]!="AVAILABLE" or current["status"]!="AVAILABLE":
        raise ValueError("CURRENT_COMPARATOR_UNAVAILABLE")
    candidates=item["candidates"]; first=next(iter(candidates.values()))
    from app.real_match_lab_analysis.fingerprint import fingerprint
    quote_fingerprints={q["provenance_fingerprint"] for q in capture["source_consensus"]["quotes"]}
    for market,candidate in candidates.items():
        ref=capture["model_probabilities"].get(market,{})
        if (fingerprint(candidate)!=ref.get("candidate_fingerprint")
                or candidate.get("candidate_id")!=ref.get("candidate_id")
                or candidate.get("fixture_id")!=capture["fixture_id"]
                or str(candidate.get("ensemble_probability"))!=str(ref.get("probability"))
                or candidate.get("quote_provenance_fingerprint") not in quote_fingerprints
                or candidate.get("market")!=market
                or candidate.get("kickoff_utc")!=capture["kickoff_utc"]):
            raise ValueError("MODEL_REFERENCE_INTEGRITY")
    if utc(artifact["input_as_of"])!=utc(capture["captured_at"]):
        raise ValueError("MODEL_INPUT_CLOCK_MISMATCH")
    if any(r["fixture_id"]==capture["fixture_id"] for r in artifact["training_matches"]):
        raise ValueError("TARGET_IN_TRAINING")
    if artifact["league_id"]!=first["league_id"]: raise ValueError("LEAGUE_MISMATCH")
    values=(predictor or predict)(artifact,home_team_id=first["home_team_id"],away_team_id=first["away_team_id"],
                   league_id=first["league_id"],neutral="IS_NEUTRAL_VENUE" in first.get("flags",[]),
                   as_of=cutoff,kickoff=utc(capture["kickoff_utc"]),plan=plan)
    books=[b for b in current["bookmakers"] if b["status"]=="AVAILABLE"]
    # One prospectively defined bookmaker per family; no pseudo-replication.
    book=min(books,key=lambda b:(b["bookmaker_id"] is None,b["bookmaker_id"] or 0,b["bookmaker"]))
    comparisons={}; missing=Counter()
    for market in sorted(book["methods"]["MULTIPLICATIVE"]["probabilities"]):
        candidate=candidates.get(market)
        ref=capture["model_probabilities"].get(market,{})
        if candidate is None or ref.get("probability") is None:
            missing["existing_model_missing"]+=1; continue
        try: probability=finite(ref["probability"],low=1e-15,high=1-1e-15)
        except (ValueError,TypeError): missing["existing_model_invalid"]+=1; continue
        methods={"DIXON_COLES":values["dixon_coles"]["probabilities"][market],
                 "POISSON_SAME_RATES":values["independent_poisson_ablation"]["probabilities"][market],
                 "EXISTING_ENSEMBLE":probability}
        for name,method in book["methods"].items():
            if method["status"] in {"AVAILABLE","FALLBACK_MULTIPLICATIVE"}:
                methods[name]=finite(method["probabilities"][market],low=1e-15,high=1-1e-15)
            else: missing[name+":"+method["status"]]+=1
        comparisons[market]=methods
    if not comparisons: raise ValueError("NO_PAIRED_MODEL_MARKETS")
    return seal({"version":record_version,"plan_fingerprint":plan["fingerprint"],
        "fixture_id":capture["fixture_id"],"league_id":first["league_id"],
        "market_family":capture["market_family"],"competition_profile":first["competition_profile"],
        "kickoff_utc":capture["kickoff_utc"],"forecast_at":cutoff.isoformat(),
        "input_as_of":capture["captured_at"],"model_fingerprint":artifact["fingerprint"],
        "capture":capture,"candidate_references":candidates,
        "comparison_odds":{q["market"]:str(q["decimal_odds"]) for q in capture["source_consensus"]["quotes"]
            if q["bookmaker_id"]==book["bookmaker_id"] and q["bookmaker_name"]==book["bookmaker"]},
        "comparisons":comparisons,"missing_comparators":dict(missing),
        "bookmaker_id":book["bookmaker_id"],"bookmaker":book["bookmaker"],
        "bookmaker_method_statuses":{k:v["status"] for k,v in book["methods"].items()},
        "goal_distribution":values,"selection_effect":"NONE","telegram_publication":False,
        "historical_bookmaker_odds_used":False})

def intake(snapshot: dict, store: ResearchStore, *, plan: dict,
           clock: Callable[[],datetime], fit_model: Callable | None = None,
           make_forecast: Callable | None = None, record_version: str = VERSION) -> dict:
    verify_plan(plan)
    store.append("plan",plan["fingerprint"],plan)
    counts=Counter(); details=[]
    models={}
    reserved=frozenset(snapshot["additional_reserved"])
    for item in sorted(snapshot["items"],key=lambda i:(i["capture"]["captured_at"],i["capture"]["capture_id"])):
        capture=item["capture"]; fid=capture["fixture_id"]
        key=f'{plan["fingerprint"]}:{fid}:{capture["market_family"]}'
        if store.get("forecast",key) is not None:
            counts["already_forecast"]+=1; continue
        if fid in reserved or str(fid) in plan["protected_calendar"]["reserved_holdout_fixtures"]:
            counts["reserved_holdout"]+=1; continue
        try:
            first=next(iter(item["candidates"].values())); league=first["league_id"]
            cache_key=(league,capture["captured_at"])
            artifact=models.get(cache_key)
            if artifact is None:
                artifact=(fit_model or fit)(item["training_results"],league_id=league,as_of=utc(capture["captured_at"]),
                             plan=plan,additional_reserved=reserved)
                models[cache_key]=artifact
                store.append("model",artifact["fingerprint"],artifact)
            result=(make_forecast or forecast)(item,artifact=artifact,plan=plan,now=clock())
            if store.append("forecast",key,result): counts["forecast"]+=1
            else: counts["already_forecast"]+=1
        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
            reason=str(exc) if isinstance(exc,ValueError) and str(exc).isupper() else "RESEARCH_INPUT_UNAVAILABLE"
            counts["unavailable"]+=1
            diagnostic=seal({"version":record_version,"fixture_id":fid,"capture_id":capture["capture_id"],
                             "plan_fingerprint":plan["fingerprint"],"reason":reason,
                             "observed_at":utc(clock()).isoformat()})
            store.append("diagnostic",diagnostic["fingerprint"],diagnostic)
            details.append({"fixture_id":fid,"reason":reason})
    return seal({"version":record_version,"status":"COMPLETED","counts":dict(counts),
                 "source_diagnostics":snapshot["diagnostics"],"details":details,
                 "selection_effect":"NONE","provider_calls":0,"telegram_sends":0,
                 "priority":"NORMAL","automatic_promotion":False})
