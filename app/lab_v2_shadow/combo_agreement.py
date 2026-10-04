"""Explicit Lab COMBO publication experiment; cached models, never fitting or I/O."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import os

from app.adaptive_lab.devig_research import capture
from app.dixon_coles_forward.contracts import load_plan, reserved
from app.dixon_coles_forward.model import verify_artifact
from app.dixon_coles_constrained.model import predict_components
from app.dixon_coles_research.contracts import seal, verify, utc

POLICY = "LAB_COMBO_CONSERVATIVE_AGREEMENT_V1"
COHORT = "COMBO_AGREEMENT_20261004_V1"
FLAG = "GOALVISION_COMBO_CONSERVATIVE_AGREEMENT"
MAX_MODEL_AGE = timedelta(hours=24)
BINDING = ("candidate_id", "fixture_id", "league_id", "home_team_id", "away_team_id",
           "kickoff_utc", "market", "captured_odds", "ensemble_probability",
           "quote_provenance_fingerprint", "provider_origin_timestamp_utc",
           "goalvision_retrieved_at_utc")

def requested() -> bool:
    """An invalid nonzero value blocks COMBO rather than silently reverting."""
    return os.environ.get(FLAG, "0") != "0"

def mode_blocker(policy: str) -> str | None:
    mode = os.environ.get(FLAG, "0")
    if mode not in {"0", "1"}:
        return "COMBO_AGREEMENT_CONFIGURATION_INVALID"
    if (mode == "1") != (policy == POLICY):
        return "COMBO_ACTIVE_SELECTION_POLICY_MISMATCH"
    return None

def binding(candidate: dict) -> dict:
    return {**{k: candidate[k] for k in BINDING},
            "neutral": "IS_NEUTRAL_VENUE" in candidate.get("flags", [])}

def evidence(candidate: dict, artifact: dict, consensus: dict, *, now: datetime,
             verified: bool = False) -> dict:
    """Reproduce three input scores; the minimum is a rank, not calibrated probability."""
    plan = load_plan()
    clock, kickoff = utc(now), utc(candidate["kickoff_utc"])
    model_at = utc(artifact["input_as_of"])
    if not (utc(plan["evaluation_start"]) <= clock < kickoff < utc(plan["evaluation_end"])
            or not timedelta(0) <= clock - model_at <= MAX_MODEL_AGE):
        raise ValueError("COMBO_MODEL_OR_EXPERIMENT_WINDOW_EXPIRED")
    fid = int(candidate["fixture_id"])
    if fid in reserved(plan) or any(r["fixture_id"] == fid for r in artifact["training_matches"]):
        raise ValueError("COMBO_EXCLUDED_OR_TRAINING_FIXTURE")
    if not verified:
        verify_artifact(artifact, plan=plan)
    market = candidate["market"]
    if (consensus["fixture_id"] != fid or consensus["historical_bookmaker_odds_used"] is not False
            or consensus["source"] != "API_FOOTBALL_CURRENT_ODDS"):
        raise ValueError("COMBO_CURRENT_MARKET_BINDING_INVALID")
    quotes = consensus["quotes"]
    matching = [q for q in quotes if q["provenance_fingerprint"] == candidate["quote_provenance_fingerprint"]]
    if (len(matching) != 1 or matching[0]["market"] != market
            or Decimal(str(matching[0]["decimal_odds"])) != Decimal(candidate["captured_odds"])):
        raise ValueError("COMBO_CURRENT_QUOTE_BINDING_INVALID")
    # Retrieval freshness is stricter than provider update freshness.
    if any(not timedelta(0) <= clock - utc(q["retrieved_at_utc"]) <= timedelta(seconds=900)
           for q in quotes):
        raise ValueError("COMBO_CURRENT_COMPARATOR_STALE")
    current = capture(consensus, captured_at=clock, kickoff=kickoff,
                      model_probabilities={}, policy_context={"active_combo_policy": POLICY})
    if current["status"] != "AVAILABLE":
        raise ValueError("COMBO_CURRENT_COMPARATOR_UNAVAILABLE")
    books = [b for b in current["bookmakers"] if b["status"] == "AVAILABLE"]
    book = min(books, key=lambda b: (b["bookmaker_id"] is None, b["bookmaker_id"] or 0, b["bookmaker"]))
    values = predict_components(artifact, home_team_id=int(candidate["home_team_id"]),
        away_team_id=int(candidate["away_team_id"]), league_id=int(candidate["league_id"]),
        neutral="IS_NEUTRAL_VENUE" in candidate.get("flags", []), as_of=clock, kickoff=kickoff)
    probabilities = {
        "DIXON_COLES": str(values["dixon_coles"]["probabilities"][market]),
        "EXISTING_ENSEMBLE": str(candidate["ensemble_probability"]),
        "MULTIPLICATIVE": str(book["methods"]["MULTIPLICATIVE"]["probabilities"][market]),
    }
    scores = [Decimal(v) for v in probabilities.values()]
    if any(not v.is_finite() or not Decimal(0) < v < Decimal(1) for v in scores):
        raise ValueError("COMBO_COMPARISON_PROBABILITY_INVALID")
    return seal({"policy": POLICY, "statistics_cohort": COHORT, "selected_at": clock.isoformat(),
        "candidate_binding": binding(candidate), "artifact": artifact, "consensus": consensus,
        "probabilities": probabilities, "ranking_score": str(min(scores)),
        "score_is_calibrated_probability": False, "bookmaker_id": book["bookmaker_id"],
        "bookmaker": book["bookmaker"], "plan_fingerprint": plan["fingerprint"]})

def review(value: dict, *, now: datetime) -> None:
    """Recheck complete frozen numeric evidence before a publication claim."""
    if (value.get("statistics_cohort") != COHORT or value.get("score_is_calibrated_probability") is not False):
        raise ValueError("COMBO_AGREEMENT_COHORT_INVALID")
    joint = Decimal(1)
    for leg in value["legs"]:
        frozen = leg["combo_agreement"]
        verify(frozen)
        if frozen["candidate_binding"] != binding(leg):
            raise ValueError("COMBO_AGREEMENT_CANDIDATE_CHANGED")
        selected = utc(frozen["selected_at"])
        if not selected <= utc(now):
            raise ValueError("COMBO_AGREEMENT_FUTURE_EVIDENCE")
        reproduced = evidence(leg, frozen["artifact"], frozen["consensus"], now=selected)
        if reproduced != frozen:
            raise ValueError("COMBO_AGREEMENT_REPRODUCTION_FAILED")
        # The provider/retrieval and model windows must still be valid at delivery.
        evidence(leg, frozen["artifact"], frozen["consensus"], now=now, verified=True)
        joint *= Decimal(frozen["ranking_score"])
    if Decimal(value["ranking_score_if_independent"]) != joint:
        raise ValueError("COMBO_AGREEMENT_AGGREGATE_MISMATCH")
