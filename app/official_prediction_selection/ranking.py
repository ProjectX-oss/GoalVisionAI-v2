"""Decimal-safe logical-market deduplication and deterministic ranking."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.market_value_assessment import MarketValueAssessment

from .eligibility import ordered_reasons
from .fingerprint import evaluation_fingerprint
from .models import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    SelectionReason,
)
from .policy import (
    OfficialPredictionRankingPolicy,
    OfficialPredictionSelectionPolicy,
)


RankedAssessment = tuple[AssessmentEligibilityEvaluation, MarketValueAssessment]


def ranking_values(
    evaluation: AssessmentEligibilityEvaluation,
    assessment: MarketValueAssessment,
) -> tuple[object, ...]:
    return (
        assessment.expected_value,
        assessment.fair_probability,
        assessment.absolute_probability_edge,
        assessment.bookmaker_decimal_odds,
        evaluation.freshness.overall_freshness.value,
        evaluation.freshness.odds_effective_timestamp,
        assessment.market_type.value,
        assessment.selection.value,
        assessment.market_line,
        assessment.bookmaker_id,
        assessment.value_assessment_id,
        assessment.assessment_fingerprint,
    )


def rank_key(
    item: RankedAssessment,
    policy: OfficialPredictionRankingPolicy,
) -> tuple[object, ...]:
    evaluation, assessment = item
    line_index = policy.line_priority.index(assessment.market_line)
    return (
        -assessment.expected_value,
        -assessment.fair_probability,
        -assessment.absolute_probability_edge,
        -assessment.bookmaker_decimal_odds,
        policy.freshness_priority.index(assessment.overall_freshness),
        -_utc_microseconds(evaluation.freshness.odds_effective_timestamp),
        policy.market_priority.index(assessment.market_type),
        policy.selection_priority.index(assessment.selection),
        line_index,
        assessment.bookmaker_id,
        assessment.value_assessment_id,
        assessment.assessment_fingerprint,
    )


def deduplicate_and_rank(
    evaluations: tuple[AssessmentEligibilityEvaluation, ...],
    assessments: tuple[MarketValueAssessment, ...],
    selection_policy: OfficialPredictionSelectionPolicy,
    ranking_policy: OfficialPredictionRankingPolicy,
) -> tuple[
    tuple[AssessmentEligibilityEvaluation, ...],
    tuple[RankedAssessment, ...],
]:
    by_id = {item.value_assessment_id: item for item in assessments}
    eligible = tuple(
        (evaluation, by_id[evaluation.value_assessment_id])
        for evaluation in evaluations
        if evaluation.eligibility_status is AssessmentEligibilityStatus.ELIGIBLE
    )
    logical_groups: dict[str, list[RankedAssessment]] = {}
    for item in eligible:
        logical_groups.setdefault(item[0].logical_market_identity, []).append(item)

    retained: list[RankedAssessment] = []
    replacements: dict[str, AssessmentEligibilityEvaluation] = {}
    for identity in sorted(logical_groups):
        ordered = sorted(
            logical_groups[identity],
            key=lambda item: rank_key(item, ranking_policy),
        )
        retained.append(ordered[0])
        for evaluation, _ in ordered[1:]:
            reasons = ordered_reasons(
                evaluation.ordered_rejection_reasons
                + (SelectionReason.DUPLICATE_LOGICAL_MARKET,)
            )
            status = AssessmentEligibilityStatus.DEDUPLICATED
            fingerprint = evaluation_fingerprint(
                assessment_fingerprint=evaluation.assessment_fingerprint,
                eligibility_status=status,
                ordered_rejection_reasons=reasons,
                logical_identity=evaluation.logical_market_identity,
                verified_odds=evaluation.verified_odds,
                verified_fair_probability=evaluation.verified_fair_probability,
                verified_expected_value=evaluation.verified_expected_value,
                freshness=evaluation.freshness,
                policy_version=selection_policy.version,
            )
            replacements[evaluation.evaluation_id] = replace(
                evaluation,
                eligibility_status=status,
                ordered_rejection_reasons=reasons,
                evaluation_fingerprint=fingerprint,
            )

    updated = tuple(
        replacements.get(item.evaluation_id, item) for item in evaluations
    )
    ranked = tuple(
        sorted(retained, key=lambda item: rank_key(item, ranking_policy))
    )
    return updated, ranked


def _utc_microseconds(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = value.astimezone(timezone.utc) - epoch
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
