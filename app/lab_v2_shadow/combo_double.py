"""User-authorized two-leg model filter; quality disagreement stays diagnostic."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from itertools import combinations
import os
from zoneinfo import ZoneInfo

from app.lab_combo.cardinality import DOUBLE_POLICY as POLICY
from app.lab_combo.publication_window import publication_blocker
from .publication_policy import review_accuracy_publication

FLAG = "GOALVISION_COMBO_DOUBLE_170"
COHORT = "COMBO_DOUBLE_20261006_V1"
MIN_ODDS, MIN_P, MAX_P = Decimal("1.70"), Decimal("0.70"), Decimal("0.80")
MAX_CANDIDATES = 6000
MAX_RANKED_FIXTURES = 60
DIAGNOSTIC_FINDINGS = frozenset({
    "NON_POSITIVE_VALUE", "INSUFFICIENT_INDEPENDENT_SIGNALS", "ENSEMBLE_EDGE_BELOW_0_04",
    "WEIGHTED_AGREEMENT_BELOW_0_65", "MATERIAL_SIGNAL_DISAGREEMENT",
    "ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE", "SEVERE_MODEL_MARKET_CONTRADICTION",
    "SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION", "VALUE_BELOW_PROFILE_THRESHOLD",
})


def requested() -> bool:
    return os.environ.get(FLAG, "0") != "0"


def mode_blocker(policy: str) -> str | None:
    mode = os.environ.get(FLAG, "0")
    if policy == POLICY:
        return ("COMBO_DOUBLE_CONFIGURATION_INVALID" if mode not in {"0", "1"}
                else "COMBO_DOUBLE_DISABLED" if mode != "1" else None)
    if requested() and policy == "LAB_COMBO_MULTI_BOOK_MARKET_V1":
        return "COMBO_MARKET_REPLACED_BY_DOUBLE"
    return None


def metadata() -> dict:
    return {"statistics_cohort": COHORT, "leg_count": 2,
            "minimum_combo_leg_decimal_odds": str(MIN_ODDS),
            "minimum_leg_model_probability": str(MIN_P), "maximum_leg_model_probability": str(MAX_P),
            "score_is_calibrated_probability": False}


def review_leg(candidate: dict, *, now: datetime) -> dict:
    """Reuse exact source replay; relax only declared quality findings, not integrity."""
    from app.adaptive_lab.contracts import MARKETS
    from app.lab_combo.service import FINAL_REVIEW_REFRESH_MAX_AGE
    from .ensemble import EnsembleSignal, _independence_group
    base = review_accuracy_publication(candidate, now=now)
    findings = set(base["rejection_reasons"])
    retained = (findings | set(candidate.get("soft_findings") or ())
                | set(candidate.get("hard_failures") or ()) | set(candidate.get("rejection_reasons") or ()))
    reasons = findings - DIAGNOSTIC_FINDINGS
    try:
        odds, probability = (Decimal(str(candidate[k])) for k in ("captured_odds", "ensemble_probability"))
        if not odds.is_finite() or odds < MIN_ODDS:
            reasons.add("COMBO_DOUBLE_LEG_ODDS_BELOW_1_70")
        if not probability.is_finite() or not MIN_P <= probability <= MAX_P:
            reasons.add("COMBO_DOUBLE_PROBABILITY_OUTSIDE_70_80")
        kickoff = datetime.fromisoformat(candidate["kickoff_utc"])
        if (kickoff <= now or kickoff.astimezone(ZoneInfo("Europe/Riga")).date()
                != now.astimezone(ZoneInfo("Europe/Riga")).date()):
            reasons.add("COMBO_DOUBLE_TODAY_PREMATCH_REQUIRED")
        blocker = publication_blocker(now, [candidate["kickoff_utc"]])
        if blocker:
            reasons.add(blocker)
        if (candidate.get("decision") != "APPROVED" or candidate.get("stage") != "READY_TO_PUBLISH"
                or candidate.get("market") not in MARKETS):
            reasons.add("COMBO_DOUBLE_COMPLETED_FINAL_REVIEW_REQUIRED")
        reviewed = datetime.fromisoformat(candidate["final_review_completed_at_utc"])
        if not 0 <= (now - reviewed).total_seconds() <= FINAL_REVIEW_REFRESH_MAX_AGE.total_seconds():
            reasons.add("COMBO_DOUBLE_FINAL_REVIEW_EXPIRED")
        signals = [EnsembleSignal(**{**s, "probability": Decimal(str(s["probability"]))
                   if s["probability"] is not None else None,
                   "reliability": Decimal(str(s["reliability"]))}) for s in candidate["signals"]]
        if not any(s.probability is not None and s.provenance
                   and s.name != "CURRENT_MARKET_CONSENSUS"
                   and _independence_group(s) != "CURRENT_MARKET_CONSENSUS" for s in signals):
            reasons.add("COMBO_DOUBLE_NON_MARKET_MODEL_REQUIRED")
    except (KeyError, ValueError, TypeError, ArithmeticError, AttributeError):
        reasons.add("COMBO_DOUBLE_LEG_EVIDENCE_INVALID")
    return {"version": POLICY, "eligible": not reasons, "rejection_reasons": sorted(reasons),
            "diagnostic_quality_findings": sorted(retained & DIAGNOSTIC_FINDINGS)}


def prepare(candidates: list[dict], ledger: object, *, now: datetime, label_origin: bool,
            football_context: object | None = None, excluded_combos: tuple[dict, ...] = ()) -> tuple[list[dict], dict]:
    from .publication import _leg, _single_rank, v2_combo_message
    from .accuracy_combo import combo_identity
    from .origin import freeze_origin
    from app.lab_combo.repository import _combo_exposures
    rejected: Counter[str] = Counter()
    def result(values: list[dict], count: int, reason: str, omitted: int = 0):
        return values, {"policy": POLICY, **metadata(), "eligible_fixture_count": count,
                        "prepared_count": len(values), "reason": reason,
                        "rejection_counts": dict(sorted(rejected.items())), "rank_tail_omitted": omitted}
    blocker = mode_blocker(POLICY)
    if blocker or not label_origin or len(candidates) > MAX_CANDIDATES:
        reason = blocker or ("COMBO_SELECTION_ORIGIN_REQUIRED" if not label_origin else "COMBO_DOUBLE_CAPACITY")
        rejected[reason] += 1
        return result([], 0, reason)
    exposures = set()
    for old in [*excluded_combos, *ledger.all("prediction")]:
        if old in excluded_combos or any(ledger.get(kind, prefix + old["prediction_id"])
                for kind in ("claim", "receipt") for prefix in ("combo_prediction:", "prediction:")):
            exposures.update(_combo_exposures(old))
    best_by_fixture = {}
    for candidate in candidates:
        check = review_leg(candidate, now=now)
        if not check["eligible"]:
            rejected.update(check["rejection_reasons"])
            continue
        leg = _leg(candidate, now)
        if exposures & _combo_exposures({"legs": [leg]}):
            rejected["COMBO_DOUBLE_EXPOSURE_ALREADY_RESERVED"] += 1
            continue
        leg.update(combo_leg_selection_policy=POLICY, double_selection_review=check,
                   double_review_completed_at_utc=now.isoformat(),
                   selection_origin=freeze_origin(candidate, now=now, observer=football_context))
        fid, rank = int(leg["fixture_id"]), _single_rank(leg)
        if fid not in best_by_fixture or rank < best_by_fixture[fid][0]:
            best_by_fixture[fid] = (rank, leg)
    ranked = [item[1] for item in sorted(best_by_fixture.values(), key=lambda item: item[0])]
    count, omitted = len(ranked), max(0, len(ranked) - MAX_RANKED_FIXTURES)
    best = None
    for group in combinations(ranked[:MAX_RANKED_FIXTURES], 2):
        if len({str(leg[k]) for leg in group for k in ("home_team_id", "away_team_id")}) != 4:
            continue
        joint = Decimal(group[0]["probability"]) * Decimal(group[1]["probability"])
        rank = (-joint, tuple(sorted(leg["publication_key"] for leg in group)))
        if best is None or rank < best[0]:
            best = rank, group
    if best is None:
        return result([], count, "INSUFFICIENT_INDEPENDENT_DOUBLE_LEGS", omitted)
    legs = sorted((dict(leg) for leg in best[1]), key=lambda leg: leg["publication_key"])
    combined = Decimal(legs[0]["odds"]) * Decimal(legs[1]["odds"])
    joint = Decimal(legs[0]["probability"]) * Decimal(legs[1]["probability"])
    value = {"prediction_id": combo_identity(legs, policy=POLICY), "policy": POLICY,
             "combo_selection_policy": POLICY, "created_at_utc": now.isoformat(), "legs": legs,
             "combined_odds": str(combined), "estimated_probability_if_independent": str(joint),
             "estimated_ev_if_independent": str(joint * combined - 1),
             "probability_assumption": "INDEPENDENCE_ASSUMED_NOT_VERIFIED",
             "accounting": "LAB_ONLY_HYPOTHETICAL_ONE_UNIT", "combo_number": 1,
             "correlation_review": "PASSED_DISTINCT_FIXTURES_TEAMS_AND_DISJOINT_BATCH", **metadata()}
    existing = ledger.get("prediction", value["prediction_id"])
    if existing is not None:
        value = existing
    else:
        ledger.append("prediction", value["prediction_id"], value)
        ledger.append("preview", value["prediction_id"], {"message": v2_combo_message(value, 1)})
        ledger.append("v2_segmentation", value["prediction_id"], {
            "kind": "COMBO", "combo_selection_policy": POLICY, **metadata(),
            "source_candidate_ids": [leg["candidate_id"] for leg in legs]})
    return result([value], count, "COMBO_DOUBLE_READY", omitted)


def review(value: dict, *, now: datetime) -> dict:
    """Verify frozen two-leg evidence again before the atomic transport claim."""
    from .accuracy_combo import combo_identity
    from .origin import is_labelled
    from app.lab_combo.service import FINAL_REVIEW_REFRESH_MAX_AGE
    reasons = set()
    try:
        legs = value["legs"]
        if (not isinstance(legs, list) or len(legs) != 2 or value.get("policy") != POLICY
                or value.get("combo_selection_policy") != POLICY
                or value["prediction_id"] != combo_identity(legs, policy=POLICY)
                or value.get("accounting") != "LAB_ONLY_HYPOTHETICAL_ONE_UNIT"
                or type(value.get("combo_number")) is not int or value["combo_number"] != 1
                or any(value.get(k) != v for k, v in metadata().items())):
            reasons.add("COMBO_DOUBLE_POLICY_OR_IDENTITY_INVALID")
        if (len({int(leg["fixture_id"]) for leg in legs}) != 2
                or len({str(leg[k]) for leg in legs for k in ("home_team_id", "away_team_id")}) != 4):
            reasons.add("COMBO_CORRELATION_REJECTED")
        combined, joint = Decimal(1), Decimal(1)
        for leg in legs:
            fresh = review_leg(leg, now=now)
            reasons.update(fresh["rejection_reasons"])
            selected = datetime.fromisoformat(leg["double_review_completed_at_utc"])
            frozen = review_leg(leg, now=selected)
            if (leg.get("combo_leg_selection_policy") != POLICY or not frozen["eligible"]
                    or leg.get("double_selection_review") != frozen
                    or not 0 <= (now-selected).total_seconds() <= FINAL_REVIEW_REFRESH_MAX_AGE.total_seconds()):
                reasons.add("COMBO_DOUBLE_FROZEN_REVIEW_INVALID")
            origin = leg.get("selection_origin") or {}
            if (not is_labelled(leg) or origin.get("selector_policy") != leg.get("policy")
                    or origin.get("model_artifact") != leg.get("model_artifact_identity")
                    or origin.get("model_generation") != leg.get("model_generation")
                    or origin.get("independent_context_model") is not None):
                reasons.add("COMBO_SELECTION_ORIGIN_INVALID")
            odds, p = Decimal(leg["captured_odds"]), Decimal(leg["ensemble_probability"])
            if (Decimal(leg["odds"]) != odds or Decimal(leg["probability"]) != p
                    or Decimal(leg["expected_value"]) != odds*p-1
                    or leg["publication_key"] != f"{leg['fixture_id']}:{leg['market']}"):
                reasons.add("COMBO_LEG_BINDING_INVALID")
            combined *= odds
            joint *= p
        if (Decimal(value["combined_odds"]) != combined
                or Decimal(value["estimated_probability_if_independent"]) != joint
                or Decimal(value["estimated_ev_if_independent"]) != joint*combined-1
                or value.get("probability_assumption") != "INDEPENDENCE_ASSUMED_NOT_VERIFIED"):
            reasons.add("COMBO_AGGREGATE_MISMATCH")
    except (KeyError, ValueError, TypeError, ArithmeticError, AttributeError):
        reasons.add("COMBO_DOUBLE_EVIDENCE_INVALID_OR_MISSING")
    return {"version": POLICY, "eligible": not reasons, "rejection_reasons": sorted(reasons)}
