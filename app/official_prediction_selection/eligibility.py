"""Deterministic per-assessment Official eligibility evaluation."""

from __future__ import annotations

from datetime import timedelta, timezone

from app.market_value_assessment import (
    ActionabilityStatus,
    FreshnessState,
    MarketType,
    MarketValueAssessment,
)
from app.market_value_assessment.exceptions import IncompatibleMarketError
from app.market_value_assessment.market_mapping import MarketMappingRegistry

from .fingerprint import (
    evaluation_fingerprint,
    logical_market_identity,
    logical_prediction_identity,
    selection_evaluation_id,
)
from .models import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    AssessmentFreshnessSummary,
    OfficialPredictionSelectionCommand,
    PublicationProtectionState,
    SelectionReason,
)
from .policy import OfficialPredictionSelectionPolicy
from .ports import PublicationStateProtection


_REASON_PRIORITY = {reason: index for index, reason in enumerate(SelectionReason)}


def ordered_reasons(
    reasons: set[SelectionReason] | tuple[SelectionReason, ...],
) -> tuple[SelectionReason, ...]:
    return tuple(sorted(set(reasons), key=_REASON_PRIORITY.__getitem__))


def evaluate_assessment(
    assessment: MarketValueAssessment,
    *,
    deterministic_input_order: int,
    request: OfficialPredictionSelectionCommand,
    request_identity_fingerprint: str,
    policy: OfficialPredictionSelectionPolicy,
    mappings: MarketMappingRegistry,
    publication_states: PublicationStateProtection,
) -> AssessmentEligibilityEvaluation:
    assert request.selection_timestamp is not None
    assert request.kickoff_timestamp is not None
    reasons: set[SelectionReason] = set()
    logical_identity = logical_market_identity(
        assessment.match_id,
        assessment.market_type,
        assessment.selection,
        assessment.market_line,
    )
    if assessment.market_type not in policy.supported_markets:
        reasons.add(SelectionReason.UNSUPPORTED_MARKET)
    try:
        mappings.resolve(
            assessment.market_type,
            assessment.selection,
            assessment.market_line,
        )
    except (IncompatibleMarketError, AttributeError, TypeError, ValueError):
        reasons.add(SelectionReason.UNSUPPORTED_MARKET)
    if assessment.actionability_status is not ActionabilityStatus.ACTIONABLE:
        reasons.add(SelectionReason.NON_ACTIONABLE_ASSESSMENT)

    states = (
        assessment.overall_freshness,
        assessment.odds_freshness,
        assessment.calibrated_freshness,
    )
    if FreshnessState.EXPIRED in states:
        reasons.add(SelectionReason.EXPIRED_ASSESSMENT)
    elif FreshnessState.STALE in states and not policy.allow_stale_assessments:
        reasons.add(SelectionReason.STALE_ASSESSMENT)
    elif FreshnessState.AGING in states and not policy.allow_aging_assessments:
        reasons.add(SelectionReason.AGING_ASSESSMENT)

    remaining = request.kickoff_timestamp - request.selection_timestamp
    if remaining < timedelta(seconds=policy.minimum_time_before_kickoff_seconds):
        reasons.add(SelectionReason.TOO_CLOSE_TO_KICKOFF)
    if assessment.bookmaker_decimal_odds < policy.minimum_decimal_odds:
        reasons.add(SelectionReason.ODDS_BELOW_OFFICIAL_MINIMUM)
    if assessment.expected_value < policy.minimum_expected_value:
        reasons.add(SelectionReason.EV_BELOW_OFFICIAL_MINIMUM)
    if assessment.value_classification not in policy.required_value_classifications:
        reasons.add(SelectionReason.VALUE_CLASSIFICATION_INSUFFICIENT)
    if not (
        policy.minimum_fair_probability
        <= assessment.fair_probability
        <= policy.maximum_fair_probability
    ):
        reasons.add(SelectionReason.FAIR_PROBABILITY_INVALID)

    try:
        publication_state = publication_states.classify(
            logical_prediction_identity(logical_identity),
            assessment.match_id,
            request.selection_timestamp,
        )
    except Exception:
        publication_state = PublicationProtectionState.INDETERMINATE
    if not isinstance(publication_state, PublicationProtectionState):
        publication_state = PublicationProtectionState.INDETERMINATE
    if publication_state is PublicationProtectionState.PUBLISHED:
        reasons.add(SelectionReason.ALREADY_PUBLISHED)
    elif publication_state is PublicationProtectionState.ACTIVE_CLAIM:
        reasons.add(SelectionReason.ACTIVE_PUBLICATION_CLAIM)
    elif publication_state is PublicationProtectionState.INDETERMINATE:
        reasons.add(SelectionReason.INDETERMINATE_PUBLICATION_STATE)
    elif (
        publication_state is PublicationProtectionState.UNKNOWN
        and policy.unknown_publication_state_blocks
    ):
        reasons.add(SelectionReason.INDETERMINATE_PUBLICATION_STATE)

    freshness = AssessmentFreshnessSummary(
        odds_freshness=assessment.odds_freshness,
        calibrated_freshness=assessment.calibrated_freshness,
        overall_freshness=assessment.overall_freshness,
        odds_effective_timestamp=(
            assessment.assessment_timestamp.astimezone(timezone.utc)
            - timedelta(seconds=assessment.odds_age_seconds)
        ),
    )
    reason_codes = ordered_reasons(reasons)
    status = (
        AssessmentEligibilityStatus.ELIGIBLE
        if not reason_codes
        else AssessmentEligibilityStatus.REJECTED
    )
    fingerprint = evaluation_fingerprint(
        assessment_fingerprint=assessment.assessment_fingerprint,
        eligibility_status=status,
        ordered_rejection_reasons=reason_codes,
        logical_identity=logical_identity,
        verified_odds=assessment.bookmaker_decimal_odds,
        verified_fair_probability=assessment.fair_probability,
        verified_expected_value=assessment.expected_value,
        freshness=freshness,
        policy_version=policy.version,
    )
    return AssessmentEligibilityEvaluation(
        evaluation_id=selection_evaluation_id(
            request_identity_fingerprint,
            assessment.assessment_fingerprint,
        ),
        value_assessment_id=assessment.value_assessment_id,
        assessment_fingerprint=assessment.assessment_fingerprint,
        deterministic_input_order=deterministic_input_order,
        eligibility_status=status,
        logical_market_identity=logical_identity,
        market_type=assessment.market_type,
        selection=assessment.selection,
        market_line=assessment.market_line,
        source_provider=assessment.source_provider,
        bookmaker_id=assessment.bookmaker_id,
        verified_odds=assessment.bookmaker_decimal_odds,
        verified_fair_probability=assessment.fair_probability,
        verified_expected_value=assessment.expected_value,
        absolute_probability_edge=assessment.absolute_probability_edge,
        freshness=freshness,
        ordered_rejection_reasons=reason_codes,
        evaluation_fingerprint=fingerprint,
        created_timestamp=request.selection_timestamp,
    )
