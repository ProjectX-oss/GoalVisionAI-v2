"""Official-aligned single-market deduplication and deterministic ranking."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .fingerprint import sha256_fingerprint
from .models import BacktestExclusion


def select_assessments(predictions, assessments, policy, *, run_namespace=""):
    by_prediction = defaultdict(list)
    for assessment in assessments:
        by_prediction[assessment.prediction_row_id].append(assessment)
    updated = []
    selected = []
    exclusions = []
    prediction_by_id = {item.prediction_row_id: item for item in predictions}
    for prediction in predictions:
        rows = by_prediction[prediction.prediction_row_id]
        eligible = [item for item in rows if item.eligible]
        by_market = defaultdict(list)
        for item in eligible:
            by_market[item.market_identity].append(item)
        retained = []
        deduplicated = set()
        for market in sorted(by_market, key=lambda item: tuple(type(item)).index(item)):
            ranked = sorted(by_market[market], key=_rank_key)
            retained.append(ranked[0])
            deduplicated.update(item.assessment_id for item in ranked[1:])
        ranked = sorted(retained, key=_rank_key)
        winner = ranked[0] if ranked else None
        for item in rows:
            reasons = item.rejection_reasons
            if item.assessment_id in deduplicated:
                reasons += ("SELECTION_DEDUPLICATION",)
            elif item.eligible and (winner is None or item.assessment_id != winner.assessment_id):
                reasons += ("HIGHER_RANKED_MARKET_SELECTED",)
            new = item if reasons == item.rejection_reasons else _replace_reasons(item, reasons, policy)
            updated.append(new)
            if reasons:
                exclusions.append(
                    BacktestExclusion(
                        exclusion_id=f"historical-backtest-exclusion-{sha256_fingerprint((run_namespace, new.assessment_fingerprint, reasons))}",
                        historical_match_id=prediction.historical_match_id,
                        training_example_id=prediction.training_example_id,
                        market_identity=item.market_identity, stage="VALUE_OR_SELECTION",
                        reason=reasons[0], detail_snapshot="{}",
                        deterministic_order=len(exclusions),
                    )
                )
        if winner is not None:
            selected.append(winner)
    return tuple(updated), tuple(selected), tuple(exclusions)


def selection_fingerprint(match_assessments, selected, policy):
    return sha256_fingerprint(
        {
            "ordered_assessment_fingerprints": tuple(
                item.assessment_fingerprint for item in sorted(match_assessments, key=_rank_key)
            ),
            "selected_market": selected.market_identity,
            "selected_assessment": selected.assessment_fingerprint,
            "rank_values": _rank_key(selected),
            "policy_version": policy.selection_policy_version,
            "ranking_policy_version": policy.ranking_policy_version,
        }
    )


def verify_selection_policy_alignment(selections, assessments) -> tuple[str, ...]:
    failures = []
    by_match = defaultdict(list)
    for item in selections:
        by_match[item.historical_match_id].append(item)
    for match, rows in by_match.items():
        if len(rows) > 1:
            failures.append(f"{match}:MULTIPLE_OFFICIAL_SELECTIONS")
    valid = {item.assessment_id for item in assessments if item.eligible}
    failures.extend(f"{item.selection_id}:INELIGIBLE_ASSESSMENT" for item in selections if item.selected_assessment_id not in valid)
    return tuple(failures)


def _rank_key(item):
    return (
        item.expected_value is None,
        -item.expected_value if item.expected_value is not None else 0,
        item.calibrated_probability is None,
        -item.calibrated_probability
        if item.calibrated_probability is not None
        else 0,
        item.edge is None,
        -item.edge if item.edge is not None else 0,
        item.decimal_odds is None,
        -item.decimal_odds if item.decimal_odds is not None else 0,
        item.odds_age_seconds is None,
        item.odds_age_seconds if item.odds_age_seconds is not None else 0,
        tuple(type(item.market_identity)).index(item.market_identity),
        item.odds_row_id or "", item.assessment_id, item.assessment_fingerprint,
    )


def _replace_reasons(item, reasons, policy):
    fingerprint = sha256_fingerprint(
        {
            "base_assessment_fingerprint": item.assessment_fingerprint,
            "eligibility": False, "rejection_reasons": reasons,
            "selection_policy_version": policy.selection_policy_version,
        }
    )
    return replace(item, eligible=False, rejection_reasons=reasons, assessment_fingerprint=fingerprint)
