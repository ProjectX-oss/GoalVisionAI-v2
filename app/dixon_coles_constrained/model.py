"""Separate development artifacts; no V1 model coercion or forward registration."""
from __future__ import annotations
from collections import Counter
from datetime import datetime
import hashlib
import json
from math import exp, fsum, log, tanh
from pathlib import Path
from app.dixon_coles_research import model as baseline
from app.dixon_coles_research.contracts import (
    POLICY, normalize_results, seal, verify, utc, integer, finite)
from .geometry import evaluate, full_theta, design, Infeasible
from .solver import solve

VERSION="DIXON_COLES_CONSTRAINED_DEVELOPMENT_V1"
PROTOCOL_FINGERPRINT="2beb92ca977016a49edf9d4d67afb199cea3102794313808fc7dd1d57ddba7ce"

def load_protocol() -> dict:
    value=json.loads(Path(__file__).with_name("protocol_20261003.json").read_text())
    verify(value)
    if (value["fingerprint"]!=PROTOCOL_FINGERPRINT or value["purpose"]!="DEVELOPMENT_ONLY"
            or value["forward_enabled"] is not False
            or hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest()!=value["baseline_model_sha256"]):
        raise ValueError("CONSTRAINED_PROTOCOL_DRIFT")
    return value

def prepare(normalized: list[dict], cutoff: datetime) -> tuple[list[int],list[tuple],dict]:
    teams=sorted({r[k] for r in normalized for k in ("home_team_id","away_team_id")})
    if len(normalized)<POLICY["minimum_matches"]: raise ValueError("INSUFFICIENT_LEAGUE_RESULTS")
    if not 2<=len(teams)<=POLICY["maximum_teams"]: raise ValueError("TEAM_CAPACITY")
    index={t:i for i,t in enumerate(teams)}
    counts=Counter(t for r in normalized for t in (r["home_team_id"],r["away_team_id"]))
    rows=[(index[r["home_team_id"]],index[r["away_team_id"]],r["home_goals"],r["away_goals"],r["neutral"],
           2**(-(utc(cutoff)-utc(r["kickoff_utc"])).total_seconds()/86400/POLICY["half_life_days"]))
          for r in normalized]
    return teams,rows,{str(t):counts[t] for t in teams}

def parameters(theta: list[float], teams: list[int]) -> dict:
    n=len(teams);full=full_theta(theta,n)
    return {"base":full[0],"home_advantage":full[1],
            "attack":{str(t):full[2+i] for i,t in enumerate(teams)},
            "defense":{str(t):full[2+n+i] for i,t in enumerate(teams)},
            "rho":POLICY["rho_scale"]*tanh(full[-1])}

def fit(rows: list[dict], *, league_id: int, as_of: datetime, plan: dict,
        additional_reserved: frozenset[int]=frozenset()) -> dict:
    protocol=load_protocol()
    if plan["fingerprint"]!=protocol["baseline_plan_fingerprint"]:
        raise ValueError("BASELINE_PLAN_MISMATCH")
    normalized,excluded=normalize_results(rows,league_id=league_id,as_of=as_of,
                                          plan=plan,additional_reserved=additional_reserved)
    teams,training,counts=prepare(normalized,as_of);n=len(teams)
    mass=fsum(r[5] for r in training)
    mh=fsum(r[2]*r[5] for r in training)/mass
    ma=fsum(r[3]*r[5] for r in training)/mass
    initial=[log(max(.2,ma)),0.0 if all(r[4] for r in training) else
             log(max(.2,mh)/max(.2,ma))]+[0.0]*(2*(n-1))+[0.0]
    prepared=design(training,n)
    def function(theta,weight,*,hessian=True):
        return evaluate(theta,training,n,weight,hessian=hessian,prepared=prepared)
    initialization="SAME_WEIGHTED_MEANS_AS_BASELINE"
    try: function(initial,protocol["solver"]["barrier_weights"][0],hessian=False)
    except Infeasible:
        # Only initialization changes; predicted/fitted rates are never clipped.
        initial=[0.0]*len(initial);initialization="STRICTLY_FEASIBLE_UNIT_RATES"
    theta,diagnostics=solve(initial,function,protocol["solver"])
    return seal({"version":VERSION,"purpose":"DEVELOPMENT_ONLY","forward_eligible":False,
        "protocol_fingerprint":protocol["fingerprint"],"baseline_plan_fingerprint":plan["fingerprint"],
        "policy":dict(POLICY),"league_id":league_id,"input_as_of":utc(as_of).isoformat(),
        "training_matches":normalized,"training_counts":counts,"team_ids":teams,
        "excluded":excluded,"optimizer_theta":theta,"parameters":parameters(theta,teams),
        "initialization":initialization,"fit":diagnostics,"selection_effect":"NONE",
        "historical_bookmaker_odds_used":False})

def verify_artifact(artifact: dict, *, plan: dict,
                    additional_reserved: frozenset[int]=frozenset()) -> dict:
    protocol=load_protocol();verify(artifact)
    if (artifact["version"]!=VERSION or artifact["purpose"]!="DEVELOPMENT_ONLY"
            or artifact["forward_eligible"] is not False or artifact["selection_effect"]!="NONE"
            or artifact["protocol_fingerprint"]!=protocol["fingerprint"]
            or artifact["baseline_plan_fingerprint"]!=plan["fingerprint"]
            or plan["fingerprint"]!=protocol["baseline_plan_fingerprint"]
            or artifact["policy"]!=POLICY or artifact["fit"]["converged"] is not True
            or artifact["fit"]["criterion"]!="LOCAL_APPROXIMATE_KKT"
            or artifact["historical_bookmaker_odds_used"] is not False):
        raise ValueError("CONSTRAINED_ARTIFACT_CONTRACT")
    normalized,_=normalize_results(artifact["training_matches"],league_id=artifact["league_id"],
                as_of=utc(artifact["input_as_of"]),plan=plan,additional_reserved=additional_reserved)
    if normalized!=artifact["training_matches"]: raise ValueError("TRAINING_REFERENCE_MISMATCH")
    teams,rows,counts=prepare(normalized,utc(artifact["input_as_of"]))
    if teams!=artifact["team_ids"] or counts!=artifact["training_counts"]:
        raise ValueError("TEAM_REFERENCE_MISMATCH")
    theta=artifact["optimizer_theta"]
    for value in theta: finite(value)
    if parameters(theta,teams)!=artifact["parameters"]:
        raise ValueError("PARAMETER_REFERENCE_MISMATCH")
    _,g,_,cert=evaluate(theta,rows,len(teams),protocol["solver"]["barrier_weights"][-1],hessian=False)
    if (cert!=artifact["fit"]["certificate"]
            or max(abs(v) for v in g)>protocol["solver"]["stationarity_tolerance"]
            or cert["complementarity_inf"]>protocol["solver"]["complementarity_inf_tolerance"]):
        raise ValueError("CONSTRAINED_CERTIFICATE_MISMATCH")
    return cert

def predict(artifact: dict, *, home_team_id: int, away_team_id: int,
            league_id: int, neutral: bool, as_of: datetime, kickoff: datetime,
            plan: dict, additional_reserved: frozenset[int]=frozenset()) -> dict:
    verify_artifact(artifact,plan=plan,additional_reserved=additional_reserved)
    integer(home_team_id);integer(away_team_id)
    if (home_team_id==away_team_id or type(neutral) is not bool
            or league_id!=artifact["league_id"]
            or not utc(artifact["input_as_of"])<=utc(as_of)<utc(kickoff)):
        raise ValueError("DEVELOPMENT_PREDICTION_BOUNDARY")
    h,a=str(home_team_id),str(away_team_id);p=artifact["parameters"]
    if any(artifact["training_counts"].get(t,0)<POLICY["minimum_target_team_matches"] for t in (h,a)):
        raise ValueError("INSUFFICIENT_TARGET_TEAM_RESULTS")
    lam=exp(p["base"]+p["attack"][h]+p["defense"][a]+(0 if neutral else p["home_advantage"]))
    mu=exp(p["base"]+p["attack"][a]+p["defense"][h])
    return {"version":VERSION,"purpose":"DEVELOPMENT_ONLY","forward_eligible":False,
            "selection_effect":"NONE","dixon_coles":baseline.markets(lam,mu,p["rho"]),
            "independent_poisson_ablation":baseline.markets(lam,mu,0)}
