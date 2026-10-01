"""Opt-in Lab triples from the existing accuracy-approved SINGLE candidate pool.

This policy permits non-positive EV exactly as the accepted SINGLE policy does.
It is disabled unless explicitly requested; it makes no profitability claim.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import combinations

from app.real_match_lab_analysis.fingerprint import fingerprint

POLICY = "LAB_COMBO_ACCURACY_FROM_SINGLES_V1"


def combo_identity(legs: list[dict]) -> str:
    binding = tuple(sorted((leg["publication_key"], leg["candidate_id"],
                            leg["quote_provenance_fingerprint"]) for leg in legs))
    return "lab-v2-combo-accuracy-" + fingerprint((POLICY, binding))


def prepare_accuracy_combos(candidates: list[dict], ledger: object, *, now: datetime,
                            label_origin: bool, football_context: object | None = None) -> tuple[list[dict], dict]:
    from .publication import (_leg, _probability_first_single_candidates, MAX_COMBOS_PER_CYCLE,
                              SINGLE_SELECTION_POLICY, MIN_PUBLISHED_DECIMAL_ODDS,
                              MIN_PUBLISHED_MARKET_PROBABILITY, v2_combo_message)
    from .origin import freeze_origin
    from app.lab_combo.service import _accuracy_delivery_review

    blockers: Counter[str] = Counter()
    ready = []
    used_fixtures = set()
    for previous in ledger.all("prediction"):
        if any(ledger.get(kind, prefix + previous["prediction_id"])
               for kind in ("claim", "receipt") for prefix in ("combo_prediction:", "prediction:")):
            used_fixtures.update(int(leg["fixture_id"]) for leg in previous["legs"])
    for candidate in _probability_first_single_candidates(candidates):
        if not label_origin:
            blockers["COMBO_SELECTION_ORIGIN_REQUIRED"] += 1
            continue
        if int(candidate["fixture_id"]) in used_fixtures:
            blockers["COMBO_FIXTURE_ALREADY_CLAIMED"] += 1
            continue
        leg = _leg(candidate, now)
        leg.update(single_selection_policy=SINGLE_SELECTION_POLICY,
                   minimum_published_probability=str(MIN_PUBLISHED_MARKET_PROBABILITY),
                   minimum_published_decimal_odds=MIN_PUBLISHED_DECIMAL_ODDS,
                   selection_origin=freeze_origin(candidate, now=now, observer=football_context))
        review = _accuracy_delivery_review(leg, now)
        if not review["eligible"]:
            blockers.update(review["rejection_reasons"])
            continue
        ready.append(leg)
    initial_count = len(ready)
    combos = []
    while len(combos) < MAX_COMBOS_PER_CYCLE:
        best = None
        for group in combinations(ready, 3):
            fixtures = {int(item["fixture_id"]) for item in group}
            teams = {str(item[key]) for item in group for key in ("home_team_id", "away_team_id")}
            if len(fixtures) != 3 or len(teams) != 6:
                continue
            probability = Decimal(1)
            for item in group:
                probability *= Decimal(item["probability"])
            rank = (-probability, tuple(sorted(item["publication_key"] for item in group)))
            if best is None or rank < best[0]:
                best = rank, group, fixtures, teams
        if best is None:
            break
        _, group, fixtures, teams = best
        legs = sorted((dict(item) for item in group), key=lambda item: item["publication_key"])
        combined, joint = Decimal(1), Decimal(1)
        for leg in legs:
            combined *= Decimal(leg["odds"])
            joint *= Decimal(leg["probability"])
        value = dict(prediction_id=combo_identity(legs), policy=POLICY,
                     combo_selection_policy=POLICY, created_at_utc=now.isoformat(),
                     legs=legs, combined_odds=str(combined),
                     estimated_probability_if_independent=str(joint),
                     estimated_ev_if_independent=str(joint * combined - 1),
                     probability_assumption="INDEPENDENCE_ASSUMED_NOT_VERIFIED",
                     accounting="LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
                     correlation_review="PASSED_DISTINCT_FIXTURES_TEAMS_AND_DISJOINT_BATCH",
                     combo_number=len(combos) + 1)
        existing = ledger.get("prediction", value["prediction_id"])
        if existing is not None:
            # Never renew a frozen review timestamp or rewrite a preview on replay.
            value = existing
        else:
            ledger.append("prediction", value["prediction_id"], value)
            ledger.append("preview", value["prediction_id"],
                          {"message": v2_combo_message(value, value["combo_number"])})
            ledger.append("v2_segmentation", value["prediction_id"],
                          {"kind": "COMBO", "combo_selection_policy": POLICY,
                           "source_candidate_ids": [leg["candidate_id"] for leg in legs]})
        combos.append(value)
        ready = [item for item in ready if int(item["fixture_id"]) not in fixtures
                 and not teams.intersection({str(item["home_team_id"]), str(item["away_team_id"])})]
    reason = ("COMBO_READY" if combos else "INSUFFICIENT_ELIGIBLE_COMBO_FIXTURES"
              if initial_count < 3 else "COMBO_NO_INDEPENDENT_NEW_TRIPLE")
    return combos, {"policy": POLICY, "eligible_fixture_count": initial_count,
                    "prepared_count": len(combos), "reason": reason,
                    "rejection_counts": dict(sorted(blockers.items()))}


def review_accuracy_combo(value: dict, *, now: datetime) -> dict:
    """Revalidate every leg, aggregate and identity before a durable send claim."""
    from app.lab_combo.service import _accuracy_delivery_review
    from .origin import is_labelled
    from .publication import SINGLE_SELECTION_POLICY, LEGACY_SINGLE_SELECTION_POLICY

    reasons = set()
    try:
        legs = value["legs"]
        if (value.get("policy") != POLICY or value.get("combo_selection_policy") != POLICY
                or len(legs) != 3 or value["prediction_id"] != combo_identity(legs)
                or value.get("accounting") != "LAB_ONLY_HYPOTHETICAL_ONE_UNIT"
                or type(value.get("combo_number")) is not int or not 1 <= value["combo_number"] <= 3):
            reasons.add("COMBO_POLICY_OR_IDENTITY_INVALID")
        fixtures = {int(leg["fixture_id"]) for leg in legs}
        teams = {str(leg[key]) for leg in legs for key in ("home_team_id", "away_team_id")}
        if len(fixtures) != 3 or len(teams) != 6:
            reasons.add("COMBO_CORRELATION_REJECTED")
        combined, joint = Decimal(1), Decimal(1)
        for leg in legs:
            reasons.update(_accuracy_delivery_review(leg, now)["rejection_reasons"])
            origin = leg.get("selection_origin") or {}
            if (not is_labelled(leg) or leg.get("single_selection_policy") not in {SINGLE_SELECTION_POLICY, LEGACY_SINGLE_SELECTION_POLICY}
                    or leg.get("candidate_lane") == "TRACKING"
                    or origin.get("selector_policy") != leg.get("policy")
                    or origin.get("model_artifact") != leg.get("model_artifact_identity")
                    or origin.get("model_generation") != leg.get("model_generation")
                    or origin.get("independent_context_model") is not None):
                reasons.add("COMBO_SELECTION_ORIGIN_INVALID")
            odds, probability = Decimal(leg["captured_odds"]), Decimal(leg["ensemble_probability"])
            if (Decimal(leg["odds"]) != odds or Decimal(leg["probability"]) != probability
                    or Decimal(leg["expected_value"]) != odds * probability - 1
                    or leg["publication_key"] != f"{leg['fixture_id']}:{leg['market']}"):
                reasons.add("COMBO_LEG_BINDING_INVALID")
            combined *= odds
            joint *= probability
        if (Decimal(value["combined_odds"]) != combined
                or Decimal(value["estimated_probability_if_independent"]) != joint
                or Decimal(value["estimated_ev_if_independent"]) != joint * combined - 1
                or value.get("probability_assumption") != "INDEPENDENCE_ASSUMED_NOT_VERIFIED"):
            reasons.add("COMBO_AGGREGATE_MISMATCH")
    except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
        reasons.add("COMBO_EVIDENCE_INVALID_OR_MISSING")
    return {"version": POLICY, "eligible": not reasons, "rejection_reasons": sorted(reasons)}
