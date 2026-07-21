"""Immutable domain models for Official single-market selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.market_value_assessment import (
    FreshnessState,
    MarketSelection,
    MarketType,
    MarketValueAssessment,
    ValueClassification,
)
from app.prediction_inference import PredictionTarget
from app.risk_management import RiskProductScope


class OfficialSelectionOutcomeStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_SELECTION = "NO_SELECTION"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_PROVENANCE = "REJECTED_PROVENANCE"
    REJECTED_SCOPE = "REJECTED_SCOPE"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class AssessmentEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    DEDUPLICATED = "DEDUPLICATED"


class PublicationProtectionState(str, Enum):
    NOT_PUBLISHED = "NOT_PUBLISHED"
    PUBLISHED = "PUBLISHED"
    ACTIVE_CLAIM = "ACTIVE_CLAIM"
    INDETERMINATE = "INDETERMINATE"
    UNKNOWN = "UNKNOWN"


class SelectionReason(str, Enum):
    NON_OFFICIAL_SCOPE = "NON_OFFICIAL_SCOPE"
    NON_OFFICIAL_DESTINATION = "NON_OFFICIAL_DESTINATION"
    POLICY_INCOMPATIBLE = "POLICY_INCOMPATIBLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_METADATA = "INVALID_METADATA"
    COLLECTION_LIMIT_EXCEEDED = "COLLECTION_LIMIT_EXCEEDED"
    DUPLICATE_ASSESSMENT = "DUPLICATE_ASSESSMENT"
    MATCH_MISMATCH = "MATCH_MISMATCH"
    KICKOFF_MISMATCH = "KICKOFF_MISMATCH"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    CORRECT_SCORE_FORBIDDEN = "CORRECT_SCORE_FORBIDDEN"
    LIVE_MARKET_FORBIDDEN = "LIVE_MARKET_FORBIDDEN"
    NON_ACTIONABLE_ASSESSMENT = "NON_ACTIONABLE_ASSESSMENT"
    AGING_ASSESSMENT = "AGING_ASSESSMENT"
    STALE_ASSESSMENT = "STALE_ASSESSMENT"
    EXPIRED_ASSESSMENT = "EXPIRED_ASSESSMENT"
    TOO_CLOSE_TO_KICKOFF = "TOO_CLOSE_TO_KICKOFF"
    ODDS_BELOW_OFFICIAL_MINIMUM = "ODDS_BELOW_OFFICIAL_MINIMUM"
    EV_BELOW_OFFICIAL_MINIMUM = "EV_BELOW_OFFICIAL_MINIMUM"
    VALUE_CLASSIFICATION_INSUFFICIENT = (
        "VALUE_CLASSIFICATION_INSUFFICIENT"
    )
    FAIR_PROBABILITY_INVALID = "FAIR_PROBABILITY_INVALID"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    ACTIVE_PUBLICATION_CLAIM = "ACTIVE_PUBLICATION_CLAIM"
    INDETERMINATE_PUBLICATION_STATE = "INDETERMINATE_PUBLICATION_STATE"
    DUPLICATE_LOGICAL_MARKET = "DUPLICATE_LOGICAL_MARKET"
    NO_ELIGIBLE_ASSESSMENTS = "NO_ELIGIBLE_ASSESSMENTS"
    SELECTED_HIGHEST_RANKED = "SELECTED_HIGHEST_RANKED"
    REQUEST_IDENTITY_CONFLICT = "REQUEST_IDENTITY_CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class OfficialPredictionSelectionCommand:
    selection_request_identity: str
    match_id: str
    selection_timestamp: datetime | None
    kickoff_timestamp: datetime | None
    bankroll_scope: RiskProductScope | str
    destination_scope: RiskProductScope | str
    assessments: tuple[MarketValueAssessment, ...]
    selection_policy_version: str
    source_run_identity: str | None = None
    metadata_version: str = "v1"
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class AssessmentFreshnessSummary:
    odds_freshness: FreshnessState
    calibrated_freshness: FreshnessState
    overall_freshness: FreshnessState
    odds_effective_timestamp: datetime


@dataclass(frozen=True, slots=True)
class AssessmentEligibilityEvaluation:
    evaluation_id: str
    value_assessment_id: str
    assessment_fingerprint: str
    deterministic_input_order: int
    eligibility_status: AssessmentEligibilityStatus
    logical_market_identity: str
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    source_provider: str
    bookmaker_id: str
    verified_odds: Decimal
    verified_fair_probability: Decimal
    verified_expected_value: Decimal
    absolute_probability_edge: Decimal
    freshness: AssessmentFreshnessSummary
    ordered_rejection_reasons: tuple[SelectionReason, ...]
    evaluation_fingerprint: str
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class SelectedOfficialPrediction:
    selection_decision_id: str
    selection_request_identity: str
    selection_request_fingerprint: str
    match_id: str
    kickoff_timestamp: datetime
    selection_timestamp: datetime
    selected_value_assessment_id: str
    selected_assessment_fingerprint: str
    source_provider: str
    bookmaker_id: str
    logical_market_identity: str
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    fair_probability: Decimal
    bookmaker_decimal_odds: Decimal
    implied_probability: Decimal
    fair_decimal_odds: Decimal
    absolute_probability_edge: Decimal
    relative_probability_edge: Decimal
    expected_value: Decimal
    expected_return: Decimal
    value_classification: ValueClassification
    freshness: AssessmentFreshnessSummary
    source_model_artifact_id: str
    source_model_version: str
    inference_id: str
    model_input_id: str
    source_snapshot_id: str
    feature_set_id: str
    calibrated_assembly_id: str
    calibration_set_id: str | None
    calibration_set_fingerprint: str
    source_calibrated_targets: tuple[PredictionTarget, ...]
    odds_fingerprint: str
    calibrated_assembly_fingerprint: str
    value_policy_version: str
    selection_policy_version: str
    ranking_policy_version: str
    selected_rank: int
    eligible_assessment_count: int
    rejected_assessment_count: int
    selection_fingerprint: str
    ordered_reason_codes: tuple[SelectionReason, ...]
    deterministic_decision_summary: tuple[tuple[str, str], ...]
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class OfficialNoSelectionDecision:
    selection_decision_id: str
    selection_request_identity: str
    selection_request_fingerprint: str
    match_id: str
    kickoff_timestamp: datetime
    selection_timestamp: datetime
    final_reason_code: SelectionReason
    evaluation_summaries: tuple[AssessmentEligibilityEvaluation, ...]
    assessment_count: int
    eligible_assessment_count: int
    rejected_assessment_count: int
    rejection_reason_counts: tuple[tuple[SelectionReason, int], ...]
    selection_policy_version: str
    ranking_policy_version: str
    no_selection_fingerprint: str
    ordered_reason_codes: tuple[SelectionReason, ...]
    deterministic_decision_summary: tuple[tuple[str, str], ...]
    created_timestamp: datetime


OfficialSelectionDecision = SelectedOfficialPrediction | OfficialNoSelectionDecision


@dataclass(frozen=True, slots=True)
class SelectionDecisionWithEvaluations:
    decision: OfficialSelectionDecision
    evaluations: tuple[AssessmentEligibilityEvaluation, ...]


@dataclass(frozen=True, slots=True)
class OfficialPredictionSelectionOutcome:
    selection_decision_id: str | None
    selection_request_identity: str
    match_id: str
    selected_value_assessment_id: str | None
    selected_market_identity: str | None
    selected_odds: Decimal | None
    selected_fair_probability: Decimal | None
    selected_expected_value: Decimal | None
    final_status: OfficialSelectionOutcomeStatus
    ordered_reason_codes: tuple[SelectionReason, ...]
    explanations: tuple[str, ...]
    eligible_assessment_count: int
    rejected_assessment_count: int
    decision_fingerprint: str | None
    selection_timestamp: datetime | None
    policy_version: str
    decision: OfficialSelectionDecision | None = None


@dataclass(frozen=True, slots=True)
class OfficialSelectionRiskInput:
    selection_decision_id: str
    selected_value_assessment_id: str
    match_id: str
    kickoff_timestamp: datetime
    logical_market_identity: str
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    source_provider: str
    bookmaker_id: str
    fair_probability: Decimal
    bookmaker_decimal_odds: Decimal
    implied_probability: Decimal
    fair_decimal_odds: Decimal
    expected_value: Decimal
    absolute_probability_edge: Decimal
    relative_probability_edge: Decimal
    value_classification: ValueClassification
    freshness: AssessmentFreshnessSummary
    source_model_artifact_id: str
    source_model_version: str
    inference_id: str
    calibrated_assembly_id: str
    calibration_set_id: str | None
    calibration_set_fingerprint: str
    odds_fingerprint: str
    calibrated_assembly_fingerprint: str
    assessment_fingerprint: str
    selection_fingerprint: str
    selection_policy_version: str
    ranking_policy_version: str
