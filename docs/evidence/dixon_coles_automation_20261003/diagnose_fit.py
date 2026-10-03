"""Offline forensic replay of a recorded fit failure; never stores forecasts/models."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from math import exp, fsum, isfinite, tanh
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.dixon_coles_research import model, sources
from app.dixon_coles_research.contracts import load_plan, normalize_results, utc, digest, verify, POLICY
from app.adaptive_lab.devig_research import verify_capture

def describe_state(state: dict, normalized: list[dict]) -> dict:
    if not state:
        return {"optimizer_state": "UNAVAILABLE"}
    theta, rows, n = state["x"], state["rows"], state["n"]
    attacks, defenses = theta[2:2+n], theta[2+n:2+2*n]
    am, dm = fsum(attacks)/n, fsum(defenses)/n
    rho = POLICY["rho_scale"]*tanh(theta[-1])
    rates = []
    for source, (hi,ai,h,a,neutral,w) in zip(normalized,rows):
        lam = exp(theta[0]+attacks[hi]-am+defenses[ai]-dm+(0 if neutral else theta[1]))
        mu = exp(theta[0]+attacks[ai]-am+defenses[hi]-dm)
        tau = min(model.correction(x,y,lam,mu,rho) for x,y in ((0,0),(0,1),(1,0),(1,1)))
        rates.append({"fixture_id":source["fixture_id"],"home_goal_rate":lam,
                      "away_goal_rate":mu,"minimum_low_cell_factor":tau})
    finite = lambda v: v if isinstance(v,(int,float)) and isfinite(v) else None
    result = {key:finite(state.get(key)) for key in
              ("iteration","norm","value","initial_value","step","slope","fv")}
    result.update(maximum_fitted_rate=max(max(r["home_goal_rate"],r["away_goal_rate"]) for r in rates),
                  minimum_low_cell_factor=min(r["minimum_low_cell_factor"] for r in rates),
                  rho=rho,
                  highest_rates=sorted(rates,key=lambda r:max(r["home_goal_rate"],r["away_goal_rate"]),reverse=True)[:3],
                  maximum_gradient_component=max(range(len(state["g"])),key=lambda i:abs(state["g"][i])),
                  terminated_at_iteration_limit=state["iteration"]==POLICY["maximum_iterations"],
                  line_search_attempt_index=state.get("_"))
    result["goal_rate_ceiling_margin"] = POLICY["maximum_goal_rate"]-result["maximum_fitted_rate"]
    return result

def diagnose(shadow: Path, audit: Path, research: Path, evidence: Path) -> dict:
    plan = load_plan()
    additional = sources.consumed_holdout_fixtures(audit)
    expected = json.loads(evidence.read_text())["diagnostics"]
    if not 1 <= len(expected) <= 2:
        raise ValueError("BOUNDED_DIAGNOSTIC_EVIDENCE_REQUIRED")
    rows = []
    with sources.readonly(research) as db:
        for document in expected:
            verify(document)
            if document["plan_fingerprint"] != plan["fingerprint"]:
                raise ValueError("DIAGNOSTIC_PLAN_MISMATCH")
            row = db.execute("SELECT document FROM dc_research_records WHERE kind='diagnostic' AND identity=?",
                             (document["fingerprint"],)).fetchone()
            if row is None or json.loads(row["document"]) != document:
                raise ValueError("DIAGNOSTIC_REFERENCE_INTEGRITY")
            rows.append(row)
    output = []
    for raw in rows:
        diagnostic = json.loads(raw["document"]); verify(diagnostic)
        if diagnostic["reason"] != "FIT_DID_NOT_CONVERGE":
            continue
        with sources.readonly(shadow) as db:
            capture = sources._evidence(db,"devig_research",diagnostic["capture_id"])
            verify_capture(capture)
            candidates = [sources._evidence(db,"candidate",ref["candidate_id"])
                          for ref in capture["model_probabilities"].values()]
            for candidate in candidates:
                ref=capture["model_probabilities"][candidate["market"]]
                if sources.fingerprint(candidate)!=ref["candidate_fingerprint"]:
                    raise ValueError("CANDIDATE_REFERENCE_INTEGRITY")
            candidate=candidates[0]
            history=sources._history(db,candidate["league_id"],candidate["season"],utc(capture["captured_at"]))
        normalized, excluded = normalize_results(history,league_id=candidate["league_id"],
            as_of=utc(capture["captured_at"]),plan=plan,additional_reserved=additional)
        state={}
        def observe(frame,event,arg):
            if frame.f_code is not model._optimize.__code__:
                return None
            if event=="exception" and isinstance(arg[1],ValueError) and str(arg[1])=="FIT_DID_NOT_CONVERGE":
                state.update(frame.f_locals)
            return observe
        started=time.monotonic(); old=sys.gettrace()
        sys.settrace(observe)
        failure=None; fitted=None
        try:
            fitted=model.fit(history,league_id=candidate["league_id"],as_of=utc(capture["captured_at"]),
                             plan=plan,additional_reserved=additional)
        except ValueError as exc:
            failure=str(exc)
        finally:
            sys.settrace(old)
        counts=Counter(t for row in normalized for t in (row["home_team_id"],row["away_team_id"]))
        output.append({"fixture_id":diagnostic["fixture_id"],"capture_id":diagnostic["capture_id"],
            "family":capture["market_family"],"league_id":candidate["league_id"],"season":candidate["season"],
            "captured_at":capture["captured_at"],"kickoff_utc":capture["kickoff_utc"],
            "training_matches":len(normalized),"training_teams":len(counts),"excluded":excluded,
            "input_hash":digest(normalized),"training_source_fingerprints":sorted({r["source_fingerprint"] for r in normalized}),
            "target_team_match_counts":{str(t):counts[t] for t in (candidate["home_team_id"],candidate["away_team_id"])},
            "training_score_maximum":max(max(r["home_goals"],r["away_goals"]) for r in normalized),
            "reproduced_failure":failure,"converged":fitted is not None,
            "elapsed_seconds":time.monotonic()-started,
            "optimizer":describe_state(state,normalized)})
    return {"version":"DIXON_COLES_OFFLINE_FIT_DIAGNOSTIC_V1","observed_at":datetime.now(timezone.utc).isoformat(),
            "plan_fingerprint":plan["fingerprint"],"policy":dict(POLICY),"replays":output,
            "cycle_evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "provider_calls":0,"telegram_requests":0,"forecast_writes":0,"model_writes":0,
            "research_database_writes":0,"parameter_changes":False,"quality_claim":False,
            "historical_bookmaker_odds_used":False}

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow",type=Path,required=True)
    parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--research",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--cycle-evidence",type=Path,default=Path(__file__).with_name("first_natural_cycle.json"))
    args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU,(12,12))
    report=diagnose(args.shadow,args.audit,args.research,args.cycle_evidence)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report,sort_keys=True,allow_nan=False))

if __name__=="__main__":
    main()
