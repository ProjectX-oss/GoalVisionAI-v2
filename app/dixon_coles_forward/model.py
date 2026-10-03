"""Newly fitted prospective artifacts; development artifacts cannot be imported."""
from datetime import datetime
from app.dixon_coles_constrained import model as numerical
from app.dixon_coles_research import model as baseline
from app.dixon_coles_research.contracts import seal, verify, utc, POLICY
from .contracts import VERSION, verify_plan, input_guard, reserved

def fit(rows: list[dict], *, league_id: int, as_of: datetime, plan: dict,
        additional_reserved: frozenset[int] = frozenset()) -> dict:
    input_guard(plan, as_of)
    exclusions = reserved(plan, additional_reserved)
    components = numerical.fit_components(rows, league_id=league_id, as_of=as_of,
                                         plan=plan, additional_reserved=exclusions)
    old, failure = None, None
    try:
        old = baseline.fit(rows, league_id=league_id, as_of=as_of, plan=plan,
                           additional_reserved=exclusions)
    except ValueError as exc:
        failure = str(exc) if str(exc).isupper() else "BASELINE_UNAVAILABLE"
    return seal({"version": VERSION, "purpose": "PROSPECTIVE_RESEARCH_ONLY",
                 "forward_eligible": True, "plan_fingerprint": plan["fingerprint"],
                 "protocol_fingerprint": numerical.load_protocol()["fingerprint"],
                 **components, "baseline_model": old, "baseline_unavailable": failure,
                 "selection_effect": "NONE", "historical_bookmaker_odds_used": False})

def verify_artifact(artifact: dict, *, plan: dict,
                    additional_reserved: frozenset[int] = frozenset()) -> None:
    verify_plan(plan); verify(artifact); input_guard(plan, artifact["input_as_of"])
    if (artifact["version"] != VERSION or artifact["purpose"] != "PROSPECTIVE_RESEARCH_ONLY"
            or artifact["forward_eligible"] is not True
            or artifact["plan_fingerprint"] != plan["fingerprint"]
            or artifact["protocol_fingerprint"] != plan["solver_protocol_fingerprint"]
            or artifact["policy"] != POLICY or artifact["selection_effect"] != "NONE"
            or artifact["historical_bookmaker_odds_used"] is not False
            or artifact["fit"]["converged"] is not True
            or artifact["fit"]["criterion"] != "LOCAL_APPROXIMATE_KKT"):
        raise ValueError("FORWARD_ARTIFACT_CONTRACT")
    numerical.verify_components(artifact, plan=plan, additional_reserved=reserved(plan, additional_reserved))
    old = artifact["baseline_model"]
    if (old is None) == (artifact["baseline_unavailable"] is None):
        raise ValueError("BASELINE_AVAILABILITY_CONTRACT")
    if old is not None:
        verify(old)
        if any(old[k] != artifact[k] for k in ("training_matches", "input_as_of", "league_id")):
            raise ValueError("BASELINE_PAIRING_MISMATCH")

def predict(artifact: dict, *, home_team_id: int, away_team_id: int, league_id: int,
            neutral: bool, as_of: datetime, kickoff: datetime, plan: dict,
            additional_reserved: frozenset[int] = frozenset()) -> dict:
    verify_artifact(artifact, plan=plan, additional_reserved=additional_reserved)
    values = numerical.predict_components(artifact, home_team_id=home_team_id,
        away_team_id=away_team_id, league_id=league_id, neutral=neutral, as_of=as_of, kickoff=kickoff)
    return {"version": VERSION, "purpose": "PROSPECTIVE_RESEARCH_ONLY",
            "forward_eligible": True, "selection_effect": "NONE", **values}
