"""COMBO joint outcome research: exact finite scenario integration, no fit.

A correlation screen is not a joint model. Inputs must be an externally pinned
as-of distribution over ALL included fixtures; we never synthesize cross-match
correlations from separate Poisson/DC marginals. This module has no DB/transport.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from .contracts import MARKETS, digest, utc
from .performance import finite
from .combo_research import joint_diagnostics

VERSION = "COMBO_JOINT_PROBABILITY_RESEARCH_V1"


def _exact_decimal(value: Fraction) -> str:
    # Input masses have at most 100 decimal places; sums remain terminating.
    with localcontext() as context:
        context.prec = 220
        return str(Decimal(value.numerator)/Decimal(value.denominator))


def scenario_probability(legs: list[dict], artifact: dict | None, *, at: datetime,
                         expected_fingerprint: str | None = None) -> dict:
    """Evaluate a pinned finite joint distribution; do not assert calibration."""
    value = {**joint_diagnostics(legs), "scenario_probability": None,
             "scenario_marginals": None, "scenario_artifact_fingerprint": None,
             "positive_ev_proven": False, "production_eligible": False,
             "as_of": utc(at).isoformat(), "source_legs_fingerprint": digest(legs)}
    reasons = set()
    if not 2 <= len(legs) <= 3:
        reasons.add("UNSUPPORTED_LEG_COUNT")
    if artifact is None or expected_fingerprint is None:
        reasons.add("VERIFIED_AS_OF_JOINT_SCENARIOS_UNAVAILABLE")
    else:
        try:
            if digest(artifact) != expected_fingerprint:
                reasons.add("SCENARIO_ARTIFACT_INTEGRITY_FAILURE")
            if (artifact["version"] != "FROZEN_JOINT_SCORE_SCENARIOS_V1"
                    or artifact["scope"] != "RESEARCH_ONLY"
                    or not artifact["source_fingerprint"] or not artifact["model_generation"]):
                reasons.add("SCENARIO_PROVENANCE_INVALID")
            if not utc(artifact["inputs_available_at"]) <= utc(artifact["created_at"]) <= utc(at):
                reasons.add("FUTURE_SCENARIO_ARTIFACT")
            if any(k in artifact for k in ("target", "settlement", "result_label")):
                reasons.add("LABEL_IN_SCENARIO_INPUT")
            fixture_ids = {str(l["fixture_id"]) for l in legs}
            if set(map(str, artifact["fixture_ids"])) != fixture_ids:
                reasons.add("SCENARIO_FIXTURE_MISMATCH")
            if any(l["market"] not in MARKETS for l in legs):
                reasons.add("UNSUPPORTED_MARKET")
            if len({(str(l["fixture_id"]), l["market"]) for l in legs}) != len(legs):
                reasons.add("DUPLICATE_LEG")
            if any(utc(l["kickoff_utc"]) <= utc(at) for l in legs):
                reasons.add("COMBO_KICKOFF_NOT_FUTURE")
            rows = artifact["scenarios"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 100000:
                reasons.add("SCENARIO_BOUND")
            total, joint = Fraction(0), Fraction(0)
            marginals, seen = [Fraction(0) for _ in legs], set()
            if not reasons:
                from app.current_odds_forward_test.service import _won
                for row in rows:
                    mass = finite(row["probability"])
                    if (mass is None or not 0 <= mass <= 1 or len(str(mass)) > 128
                            or mass.as_tuple().exponent < -100):
                        raise ValueError("SCENARIO_MASS_INVALID")
                    mass = Fraction(mass)
                    scores = row["scores"]
                    if set(scores) != fixture_ids or any(
                        not isinstance(s, list) or len(s) != 2 or
                        any(type(g) is not int or not 0 <= g <= 60 for g in s) for s in scores.values()
                    ):
                        raise ValueError("SCENARIO_SCORE_INVALID")
                    identity = digest(scores)
                    if identity in seen:
                        raise ValueError("DUPLICATE_SCENARIO")
                    seen.add(identity)
                    wins = [_won(l["market"], *scores[str(l["fixture_id"])] ) for l in legs]
                    total += mass
                    if all(wins):
                        joint += mass
                    for i, win in enumerate(wins):
                        if win:
                            marginals[i] += mass
                # Do not renormalize truncated Poisson tails or invalid distributions.
                if total != 1:
                    reasons.add("SCENARIO_MASS_NOT_ONE")
                else:
                    value.update(scenario_probability=_exact_decimal(joint),
                                 scenario_marginals=list(map(_exact_decimal, marginals)),
                                 scenario_artifact_fingerprint=expected_fingerprint,
                                 calibration_status="UNVALIDATED_RESEARCH_DISTRIBUTION")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            reasons.add(str(exc) if str(exc).startswith(("SCENARIO_", "DUPLICATE_")) else "INVALID_SCENARIO_INPUT")
    value.update(status="INSUFFICIENT_EVIDENCE" if reasons else "CONDITIONAL_SCENARIO_ESTIMATE",
                 blockers=sorted(reasons), empirical_joint_fit_invoked=False,
                 risk_screen_is_joint_model=False, model_learning_observations=0)
    value["fingerprint"] = digest(value)
    return value
