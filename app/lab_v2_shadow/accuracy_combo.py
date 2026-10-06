"""Opt-in Lab triples from the existing accuracy-approved SINGLE candidate pool.

This policy permits non-positive EV exactly as the accepted SINGLE policy does.
It is disabled unless explicitly requested; it makes no profitability claim.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import combinations
import sqlite3

from app.real_match_lab_analysis.fingerprint import fingerprint
from app.lab_combo.odds_policy import (FLOOR_POLICY, COMBO_LEG_ODDS_FLOOR,
    minimum_combo_leg_odds, combo_leg_odds_blocker, combo_odds_blocker, floor_metadata)

POLICY = "LAB_COMBO_ACCURACY_FROM_SINGLES_V1"
from .combo_agreement import POLICY as AGREEMENT_POLICY, COHORT, requested, mode_blocker
from . import combo_market
from app.lab_combo.cardinality import DOUBLE_POLICY
SUPPORTED_POLICIES = frozenset({POLICY, FLOOR_POLICY, AGREEMENT_POLICY, combo_market.POLICY, DOUBLE_POLICY})


def active_policy() -> str:
    return AGREEMENT_POLICY if requested() else FLOOR_POLICY if minimum_combo_leg_odds() is not None else POLICY


def combo_identity(legs: list[dict], *, policy: str = POLICY) -> str:
    binding = tuple(sorted((leg["publication_key"], leg["candidate_id"],
                            leg["quote_provenance_fingerprint"]) for leg in legs))
    if policy == AGREEMENT_POLICY:
        binding = (binding, tuple(sorted((leg["publication_key"], (leg["combo_agreement"]["artifact"]["fingerprint"], fingerprint(leg["combo_agreement"]["consensus"]))) for leg in legs)))
    if policy == combo_market.POLICY:
        binding = (binding, tuple(sorted((leg["publication_key"], fingerprint(leg["combo_market"]["consensus"])) for leg in legs)))
    return "lab-v2-combo-accuracy-" + fingerprint((policy, binding))


def prepare_accuracy_combos(candidates: list[dict], ledger: object, *, now: datetime,
                            label_origin: bool, football_context: object | None = None,
                            combo_inputs: object | None = None, market_variant: bool = False,
                            excluded_combos: tuple[dict, ...] = ()) -> tuple[list[dict], dict]:
    from .publication import (_leg, _probability_first_single_candidates, MAX_COMBOS_PER_CYCLE,
                              SINGLE_SELECTION_POLICY, MIN_PUBLISHED_DECIMAL_ODDS,
                              MIN_PUBLISHED_MARKET_PROBABILITY, v2_combo_message)
    from .origin import freeze_origin
    from app.lab_combo.service import _accuracy_delivery_review

    agreement = not market_variant and requested()
    scored = agreement or market_variant
    score_key = "combo_market" if market_variant else "combo_agreement"
    prefix = "COMBO_MARKET" if market_variant else "COMBO_AGREEMENT"
    minimum = COMBO_LEG_ODDS_FLOOR if scored else minimum_combo_leg_odds()
    policy = (combo_market.POLICY if market_variant else AGREEMENT_POLICY if agreement
              else FLOOR_POLICY if minimum is not None else POLICY)
    blocker = combo_market.mode_blocker(policy) if market_variant else mode_blocker(policy)
    if scored and (blocker or combo_inputs is None):
        reason = blocker or prefix + "_INPUTS_UNAVAILABLE"
        return [], {"policy": policy, **floor_metadata(minimum), "eligible_fixture_count": 0,
                    "prepared_count": 0, "reason": reason, "rejection_counts": {reason: 1}}
    blockers: Counter[str] = Counter()
    qualified = []
    for candidate in candidates:
        blocker = combo_leg_odds_blocker(candidate.get("captured_odds"), minimum=minimum)
        if blocker:
            blockers[blocker] += 1
        else:
            qualified.append(candidate)
    ready = []
    used_fixtures = set()
    used_teams = set()
    from zoneinfo import ZoneInfo
    day = now.astimezone(ZoneInfo("Europe/Riga")).date()
    def reserve_teams(previous):
        for leg in previous["legs"]:
            if datetime.fromisoformat(leg["kickoff_utc"]).astimezone(ZoneInfo("Europe/Riga")).date() == day:
                used_teams.update(str(leg[k]) for k in ("home_team_id", "away_team_id"))
    for previous in excluded_combos:
        used_fixtures.update(int(leg["fixture_id"]) for leg in previous["legs"])
        reserve_teams(previous)
    for previous in ledger.all("prediction"):
        if any(ledger.get(kind, prefix + previous["prediction_id"])
               for kind in ("claim", "receipt") for prefix in ("combo_prediction:", "prediction:")):
            used_fixtures.update(int(leg["fixture_id"]) for leg in previous["legs"])
            if market_variant or previous.get("combo_selection_policy") in {combo_market.POLICY, DOUBLE_POLICY}:
                reserve_teams(previous)
    source_candidates = qualified if scored else _probability_first_single_candidates(qualified)
    if scored and len(source_candidates) > 600:
        return [], {"policy": policy, **floor_metadata(minimum), "eligible_fixture_count": 0,
                    "prepared_count": 0, "reason": prefix + "_CAPACITY",
                    "rejection_counts": {prefix + "_CAPACITY": 1}}
    for candidate in source_candidates:
        if not label_origin:
            blockers["COMBO_SELECTION_ORIGIN_REQUIRED"] += 1
            continue
        if int(candidate["fixture_id"]) in used_fixtures:
            blockers["COMBO_FIXTURE_ALREADY_CLAIMED"] += 1
            continue
        if used_teams.intersection(str(candidate[k]) for k in ("home_team_id", "away_team_id")):
            blockers["COMBO_TEAM_ALREADY_RESERVED"] += 1
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
        if scored:
            try:
                leg[score_key] = combo_inputs.score(candidate, now=now)
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError) as exc:
                if str(exc) == prefix + "_BUDGET_EXHAUSTED":
                    return [], {"policy": policy, **floor_metadata(minimum), "eligible_fixture_count": 0,
                                "prepared_count": 0, "reason": prefix + "_BUDGET_EXHAUSTED",
                                "rejection_counts": {prefix + "_BUDGET_EXHAUSTED": 1}}
                reason = str(exc) if market_variant and str(exc).startswith("COMBO_MARKET_") else prefix + "_INPUT_UNAVAILABLE"
                blockers[reason] += 1
                continue
        ready.append(leg)
    if scored:
        from .publication import _single_rank
        best_by_fixture = {}
        for leg in ready:
            rank = (-Decimal(leg[score_key]["ranking_score"]), *_single_rank(leg)[1:])
            previous = best_by_fixture.get(int(leg["fixture_id"]))
            if previous is None or rank < previous[0]:
                best_by_fixture[int(leg["fixture_id"])] = (rank, leg)
        ready = [v[1] for v in sorted(best_by_fixture.values(), key=lambda v: v[0])]
    initial_count = len(ready)
    if agreement and initial_count > 60:
        return [], {"policy": policy, **floor_metadata(minimum), "eligible_fixture_count": initial_count,
                    "prepared_count": 0, "reason": prefix + "_CAPACITY",
                    "rejection_counts": {prefix + "_CAPACITY": 1}}
    rank_tail_omitted = max(0, initial_count - 60) if market_variant else 0
    if market_variant:
        ready = ready[:60]
    combos = []
    while len(combos) < (combo_market.MAX_COMBOS if market_variant else MAX_COMBOS_PER_CYCLE):
        best = None
        for group in combinations(ready, 3):
            fixtures = {int(item["fixture_id"]) for item in group}
            teams = {str(item[key]) for item in group for key in ("home_team_id", "away_team_id")}
            if len(fixtures) != 3 or len(teams) != 6:
                continue
            probability = Decimal(1)
            for item in group:
                probability *= Decimal(item[score_key]["ranking_score"] if scored else item["probability"])
            rank = (-probability, tuple(sorted(item["publication_key"] for item in group)))
            if best is None or rank < best[0]:
                best = rank, group, fixtures, teams
        if best is None:
            break
        _, group, fixtures, teams = best
        legs = sorted((dict(item) for item in group), key=lambda item: item["publication_key"])
        combined, joint, ranking_joint = Decimal(1), Decimal(1), Decimal(1)
        for leg in legs:
            combined *= Decimal(leg["odds"])
            joint *= Decimal(leg["probability"])
            if scored:
                # Decimal multiplication is order-sensitive after rounding. Persist
                # the score in the same frozen leg order used by delivery review.
                ranking_joint *= Decimal(leg[score_key]["ranking_score"])
        value = dict(prediction_id=combo_identity(legs, policy=policy), policy=policy,
                     combo_selection_policy=policy, created_at_utc=now.isoformat(),
                     legs=legs, combined_odds=str(combined),
                     estimated_probability_if_independent=str(joint),
                     estimated_ev_if_independent=str(joint * combined - 1),
                     probability_assumption="INDEPENDENCE_ASSUMED_NOT_VERIFIED",
                     accounting="LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
                     correlation_review="PASSED_DISTINCT_FIXTURES_TEAMS_AND_DISJOINT_BATCH",
                     combo_number=len(combos) + 1, **floor_metadata(minimum))
        if scored:
            value.update(statistics_cohort=combo_market.COHORT if market_variant else COHORT, score_is_calibrated_probability=False,
                         ranking_score_if_independent=str(ranking_joint))
        existing = ledger.get("prediction", value["prediction_id"])
        if existing is not None:
            # Never renew a frozen review timestamp or rewrite a preview on replay.
            value = existing
        else:
            ledger.append("prediction", value["prediction_id"], value)
            ledger.append("preview", value["prediction_id"],
                          {"message": v2_combo_message(value, value["combo_number"])})
            ledger.append("v2_segmentation", value["prediction_id"],
                          {"kind": "COMBO", "combo_selection_policy": policy,
                           **floor_metadata(minimum),
                           "source_candidate_ids": [leg["candidate_id"] for leg in legs]})
        combos.append(value)
        ready = [item for item in ready if int(item["fixture_id"]) not in fixtures
                 and not teams.intersection({str(item["home_team_id"]), str(item["away_team_id"])})]
    reason = ("COMBO_READY" if combos else "INSUFFICIENT_ELIGIBLE_COMBO_FIXTURES"
              if initial_count < 3 else "COMBO_NO_INDEPENDENT_NEW_TRIPLE")
    return combos, {"policy": policy, **floor_metadata(minimum), "eligible_fixture_count": initial_count,
                    "prepared_count": len(combos), "reason": reason,
                    "rejection_counts": dict(sorted(blockers.items())),
                    **({"rank_tail_omitted": rank_tail_omitted} if market_variant else {})}


def review_accuracy_combo(value: dict, *, now: datetime) -> dict:
    """Revalidate every leg, aggregate and identity before a durable send claim."""
    if value.get("combo_selection_policy") == DOUBLE_POLICY:
        from .combo_double import review
        return review(value, now=now)
    from app.lab_combo.service import _accuracy_delivery_review
    from .origin import is_labelled
    from .publication import SINGLE_SELECTION_POLICY, LEGACY_SINGLE_SELECTION_POLICY

    reasons = set()
    try:
        legs = value["legs"]
        policy = value.get("combo_selection_policy")
        if (policy not in SUPPORTED_POLICIES or value.get("policy") != policy
                or len(legs) != 3 or value["prediction_id"] != combo_identity(legs, policy=policy)
                or value.get("accounting") != "LAB_ONLY_HYPOTHETICAL_ONE_UNIT"
                or type(value.get("combo_number")) is not int or not 1 <= value["combo_number"] <= 3):
            reasons.add("COMBO_POLICY_OR_IDENTITY_INVALID")
        if policy in {FLOOR_POLICY, AGREEMENT_POLICY, combo_market.POLICY}:
            if any(value.get(k) != v for k, v in floor_metadata(COMBO_LEG_ODDS_FLOOR).items()):
                reasons.add("COMBO_FLOOR_POLICY_INVALID")
            blocker = combo_odds_blocker(value, minimum=COMBO_LEG_ODDS_FLOOR)
            if blocker:
                reasons.add(blocker)
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
        if policy == AGREEMENT_POLICY:
            from .combo_agreement import review
            review(value, now=now)
        if policy == combo_market.POLICY:
            if value["combo_number"] > combo_market.MAX_COMBOS:
                reasons.add("COMBO_MARKET_BATCH_LIMIT")
            combo_market.review(value, now=now)
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        reasons.add("COMBO_EVIDENCE_INVALID_OR_MISSING")
    return {"version": value.get("combo_selection_policy", POLICY), "eligible": not reasons, "rejection_reasons": sorted(reasons)}
