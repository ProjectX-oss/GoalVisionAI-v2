"""Frozen current-context research comparators; never publication or learning rows."""
from __future__ import annotations
from collections import defaultdict
from math import exp, log, sqrt
from statistics import mean
from .contracts import digest, number, utc
from .performance import probability_metrics

VERSION = "PREMATCH_CONTEXT_SHADOW_V1"
XG_VERSION = "CURRENT_XG_CONTEXT_V1"
MAX_CONTEXT_AGE = 21600
MIN_XG_MATCHES = 3


def goal_distribution(home_rate, away_rate):
    """Independent Poisson baseline with explicit, bounded truncation error."""
    rates = [number(v, low=.05, high=8) for v in (home_rate, away_rate)]
    distributions = []
    for rate in rates:
        values = [exp(-rate)]
        for k in range(1, 61):
            values.append(values[-1]*rate/k)
            if 1-sum(values) < 1e-13:
                break
        distributions.append(values)
    h,a = distributions
    mass = sum(h)*sum(a)
    residual = max(0., 1-mass)
    if residual > 1e-10:
        raise ValueError("POISSON_TAIL_NOT_BOUNDED")
    out = {"HOME_WIN": 0., "DRAW": 0., "AWAY_WIN": 0.}
    for i,ph in enumerate(h):
        for j,pa in enumerate(a):
            out["HOME_WIN" if i>j else "DRAW" if i==j else "AWAY_WIN"] += ph*pa/mass
    for line in (1,2,3):
        total = exp(-sum(rates))
        term = total
        for k in range(1,line+1):
            term *= sum(rates)/k
            total += term
        out[f"UNDER_{line}_5"] = total
        out[f"OVER_{line}_5"] = 1-total
    out["BTTS_YES"] = (1-exp(-rates[0]))*(1-exp(-rates[1]))
    out["BTTS_NO"] = 1-out["BTTS_YES"]
    return {"probabilities": out, "home_goal_rate": rates[0], "away_goal_rate": rates[1],
            "discarded_tail_mass": residual, "model": "INDEPENDENT_POISSON_RESEARCH_V1"}


def fixture_identity(context, now):
    required = ("fixture_id","league_id","home_team_id","away_team_id","kickoff_utc","captured_at")
    if any(context.get(k) is None for k in required):
        raise ValueError("SHADOW_IDENTITY_MISSING")
    if context["home_team_id"] == context["away_team_id"]:
        raise ValueError("SHADOW_TEAM_IDENTITY_CONFLICT")
    if not utc(context["captured_at"]) <= utc(now) < utc(context["kickoff_utc"]):
        raise ValueError("SHADOW_CAPTURE_NOT_PREMATCH")
    if (utc(now)-utc(context["captured_at"])).total_seconds() > MAX_CONTEXT_AGE:
        raise ValueError("SHADOW_CONTEXT_STALE")
    return {k: context[k] for k in required}


def record(method, context, output, *, now, references=None):
    identity = fixture_identity(context, now)
    material = {"version": VERSION, "method": method, **identity,
                "created_at": utc(now).isoformat(), "source_fingerprint": digest(context),
                "source_context": context, "output": output, "references": references or {},
                "scope": "PREMATCH_LAB_SHADOW_ONLY", "publication_eligible": False,
                "calibration_status": "UNCALIBRATED_RESEARCH",
                "historical_bookmaker_odds_used": False, "learning_observation": False}
    material["capture_id"] = "context-shadow-"+digest(material)
    return material


def xg(context, *, now, references=None):
    """Require genuine, venue-specific xG and opponent xG; never goal bounds."""
    fixture_identity(context, now)
    if context.get("version") != XG_VERSION:
        raise ValueError("GENUINE_CURRENT_XG_CONTEXT_REQUIRED")
    stats, manifests = {}, {}
    for side,venue in (("home","HOME"),("away","AWAY")):
        samples = context.get(side+"_samples", [])
        accepted, seen = [], set()
        for row in samples:
            if (row.get("source_metric") != "expected_goals"
                    or row.get("source_endpoint") != "/fixtures/statistics"
                    or not row.get("source_fingerprint")
                    or row.get("team_id") != context[side+"_team_id"]
                    or row.get("league_id") != context["league_id"]
                    or row.get("fixture_id") == context["fixture_id"]
                    or row.get("status") != "RESOLVED"):
                raise ValueError("XG_SOURCE_PROVENANCE_INVALID")
            if row["fixture_id"] in seen:
                raise ValueError("XG_DUPLICATE_FIXTURE")
            seen.add(row["fixture_id"])
            played, available = utc(row["played_at"]), utc(row["available_at"])
            if not played < available <= utc(context["captured_at"]):
                raise ValueError("XG_FUTURE_OR_UNAVAILABLE_SOURCE")
            if (utc(context["captured_at"])-played).total_seconds() > 180*86400:
                continue
            if row.get("venue") != venue:
                continue
            accepted.append((number(row["xg_for"],low=0,high=15),
                             number(row["xg_against"],low=0,high=15)))
        if len(accepted) < MIN_XG_MATCHES:
            raise ValueError("XG_VENUE_SAMPLE_INSUFFICIENT_"+side.upper())
        stats[side] = {"attack": mean(v[0] for v in accepted),
                       "defence_conceded": mean(v[1] for v in accepted), "n": len(accepted)}
        manifests[side] = sorted(str(v) for v in seen)
    home_rate = sqrt(stats["home"]["attack"]*stats["away"]["defence_conceded"])
    away_rate = sqrt(stats["away"]["attack"]*stats["home"]["defence_conceded"])
    output = goal_distribution(home_rate, away_rate)
    output.update(venue_context=stats, input_fixture_ids=manifests,
                  rate_policy="GEOMETRIC_ATTACK_OPPONENT_DEFENCE_V1",
                  independence_group="EXPECTED_GOALS_CONTEXT",
                  possible_overlap=["CURRENT_MATCH_INTELLIGENCE"], independence_proven=False)
    return record("XG_POISSON",context,output,now=now,references=references)


def validate_capture(value):
    if (value.get("version") != VERSION or value.get("publication_eligible") is not False
            or value.get("learning_observation") is not False
            or value.get("historical_bookmaker_odds_used") is not False
            or value.get("capture_id") != "context-shadow-"+digest({k:v for k,v in value.items() if k!="capture_id"})
            or value.get("source_fingerprint") != digest(value.get("source_context"))):
        raise ValueError("SHADOW_CAPTURE_INTEGRITY_FAILURE")
    fixture_identity(value, utc(value["created_at"]))
    probs = value["output"]["probabilities"]
    if any(not 0 < number(p,low=0,high=1) < 1 for p in probs.values()):
        raise ValueError("SHADOW_PROBABILITY_INVALID")
    if abs(sum(probs[k] for k in ("HOME_WIN","DRAW","AWAY_WIN"))-1)>1e-9:
        raise ValueError("SHADOW_DISTRIBUTION_INVALID")


def forward_metrics(captures, results, *, now):
    """First pre-kickoff capture per model/fixture; matched market comparisons."""
    by_result = {}
    for row in results:
        if (row.get("status") != "RESOLVED" or not row.get("source_fingerprint")
                or utc(row["available_at"]) > utc(now)):
            continue
        key = str(row["fixture_id"])
        if key in by_result and digest(row) != digest(by_result[key]):
            raise ValueError("CONFLICTING_SHADOW_RESULTS")
        by_result[key] = row
    grouped, paired, seen, pending = defaultdict(list), defaultdict(list), set(), 0
    for value in sorted(captures,key=lambda r:(utc(r["created_at"]),r["capture_id"])):
        validate_capture(value)
        if utc(value["created_at"]) > utc(now):
            continue
        key = (value["method"],str(value["fixture_id"]))
        if key in seen:
            continue
        seen.add(key)
        result = by_result.get(key[1])
        if result is None:
            pending += 1
            continue
        if not utc(value["kickoff_utc"]) < utc(result["available_at"]):
            raise ValueError("SHADOW_RESULT_CHRONOLOGY_INVALID")
        h,a = result["home_goals"],result["away_goals"]
        if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=30 for v in (h,a)):
            raise ValueError("SHADOW_SCORE_INVALID")
        targets = {"HOME_WIN":int(h>a),"DRAW":int(h==a),"AWAY_WIN":int(h<a),
                   "BTTS_YES":int(h>0 and a>0),"BTTS_NO":int(h==0 or a==0)}
        for line in (1,2,3):
            targets.update({f"OVER_{line}_5":int(h+a>line),f"UNDER_{line}_5":int(h+a<=line)})
        for market,p in value["output"]["probabilities"].items():
            y = targets[market]
            grouped[(key[0],market)].append((p,y))
            for name,reference in value["references"].items():
                q = reference.get("probabilities",{}).get(market)
                if (q is None or not reference.get("source_fingerprint")
                        or not reference.get("captured_at")
                        or utc(reference["captured_at"]) > utc(value["created_at"])):
                    continue
                q = number(q,low=0,high=1)
                if not 0<q<1:
                    continue
                paired[(key[0],name,market)].append((p,q,y))
    comparisons = []
    for (method,reference,market),rows in sorted(paired.items()):
        ps,qs = [(p,y) for p,q,y in rows],[(q,y) for p,q,y in rows]
        pm,qm = probability_metrics(ps),probability_metrics(qs)
        comparisons.append({"method":method,"reference":reference,"market":market,"n":len(rows),
            "shadow":pm,"reference_metrics":qm,
            "brier_delta":pm["brier"]-qm["brier"],"log_loss_delta":pm["log_loss"]-qm["log_loss"],
            "mean_absolute_disagreement":mean(abs(p-q) for p,q,y in rows),
            "incremental_information_status":"NEEDS_MORE_EVIDENCE"})
    return {"version":VERSION,"status":"RESEARCH_ONLY","pending":pending,
            "unique_model_fixtures":len(seen),
            "metrics":[{"method":m,"market":k,**probability_metrics(v)} for (m,k),v in sorted(grouped.items())],
            "paired_comparisons":comparisons,"promotion_eligible":False}
