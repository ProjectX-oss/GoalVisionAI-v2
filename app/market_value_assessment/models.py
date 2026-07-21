"""Immutable domain models for market probability and value assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.prediction_inference import PredictionTarget


class MarketType(str, Enum):
    MATCH_WINNER = "MATCH_WINNER"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    TOTALS = "TOTALS"
    BTTS = "BTTS"


class MarketSelection(str, Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    HOME_DRAW = "HOME_DRAW"
    HOME_AWAY = "HOME_AWAY"
    DRAW_AWAY = "DRAW_AWAY"
    OVER = "OVER"
    UNDER = "UNDER"
    YES = "YES"
    NO = "NO"


class MarketStatus(str, Enum):
    OPEN = "OPEN"


class ProbabilitySourceType(str, Enum):
    CALIBRATED_TARGET = "CALIBRATED_TARGET"
    DERIVED_DOUBLE_CHANCE = "DERIVED_DOUBLE_CHANCE"


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


class ValueClassification(str, Enum):
    NEGATIVE_VALUE = "NEGATIVE_VALUE"
    NEUTRAL_VALUE = "NEUTRAL_VALUE"
    POSITIVE_VALUE = "POSITIVE_VALUE"
    STRONG_VALUE = "STRONG_VALUE"


class ActionabilityStatus(str, Enum):
    ACTIONABLE = "ACTIONABLE"
    NON_ACTIONABLE_STALE = "NON_ACTIONABLE_STALE"
    NON_ACTIONABLE_EXPIRED = "NON_ACTIONABLE_EXPIRED"
    NON_ACTIONABLE_TOO_CLOSE_TO_KICKOFF = (
        "NON_ACTIONABLE_TOO_CLOSE_TO_KICKOFF"
    )
    NON_ACTIONABLE_MARKET_UNAVAILABLE = "NON_ACTIONABLE_MARKET_UNAVAILABLE"
    NON_ACTIONABLE_INVALID = "NON_ACTIONABLE_INVALID"


class AssessmentOutcomeStatus(str, Enum):
    ASSESSED = "ASSESSED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_CALIBRATION = "REJECTED_INVALID_CALIBRATION"
    REJECTED_INVALID_ODDS = "REJECTED_INVALID_ODDS"
    REJECTED_INCOMPATIBLE_MARKET = "REJECTED_INCOMPATIBLE_MARKET"
    REJECTED_PROVENANCE_MISMATCH = "REJECTED_PROVENANCE_MISMATCH"
    NON_ACTIONABLE = "NON_ACTIONABLE"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class SuppliedOddsSnapshot:
    """Caller-owned immutable pre-match odds command."""

    snapshot_id: str
    source_provider: str
    bookmaker_id: str
    source_event_id: str
    match_id: str
    market_type: MarketType | str
    selection: MarketSelection | str
    market_line: Decimal | None
    decimal_odds: object
    odds_effective_timestamp: datetime
    source_updated_timestamp: datetime
    registration_timestamp: datetime
    kickoff_timestamp: datetime
    is_live: bool
    market_status: MarketStatus | str
    suspended: bool
    available: bool
    maximum_stake: Decimal | None = None
    minimum_stake: Decimal | None = None
    currency: str | None = None
    source_data_version: str = "v1"
    metadata_version: str = "v1"
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MarketOddsSnapshot:
    """Canonical persisted odds content."""

    odds_record_id: str
    supplied_snapshot_id: str
    odds_fingerprint: str
    source_provider: str
    bookmaker_id: str
    source_event_id: str
    match_id: str
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    original_market: str
    original_selection: str
    decimal_odds: Decimal
    odds_effective_timestamp: datetime
    source_updated_timestamp: datetime
    registration_timestamp: datetime
    kickoff_timestamp: datetime
    market_status: MarketStatus
    suspended: bool
    available: bool
    minimum_stake: Decimal | None
    maximum_stake: Decimal | None
    currency: str | None
    source_data_version: str
    metadata_version: str
    metadata: tuple[tuple[str, str], ...]
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class MarketMapping:
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    probability_source_type: ProbabilitySourceType
    source_targets: tuple[PredictionTarget, ...]
    derivation_formula: str
    valid_probability_range: tuple[Decimal, Decimal]
    version_introduced: str
    description: str


@dataclass(frozen=True, slots=True)
class AssessmentValidationSummary:
    mapping_version: str
    ordered_checks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketValueAssessment:
    value_assessment_id: str
    calibrated_assembly_id: str
    inference_id: str
    model_input_id: str
    match_id: str
    source_snapshot_id: str
    feature_set_id: str
    source_model_artifact_id: str
    source_model_version: str
    calibration_set_id: str | None
    calibration_set_fingerprint: str
    odds_record_id: str
    odds_fingerprint: str
    source_provider: str
    bookmaker_id: str
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    source_calibrated_targets: tuple[PredictionTarget, ...]
    probability_derivation_type: ProbabilitySourceType
    derivation_version: str
    fair_probability: Decimal
    fair_decimal_odds: Decimal
    bookmaker_decimal_odds: Decimal
    implied_probability: Decimal
    break_even_probability: Decimal
    absolute_probability_edge: Decimal
    relative_probability_edge: Decimal
    expected_value: Decimal
    expected_return: Decimal
    potential_profit: Decimal
    odds_age_seconds: int
    calibrated_age_seconds: int
    time_to_kickoff_seconds: int
    value_classification: ValueClassification
    odds_freshness: FreshnessState
    calibrated_freshness: FreshnessState
    overall_freshness: FreshnessState
    actionability_status: ActionabilityStatus
    assessment_timestamp: datetime
    kickoff_timestamp: datetime
    value_policy_version: str
    calibrated_assembly_fingerprint: str
    assessment_fingerprint: str
    ordered_reason_codes: tuple[str, ...]
    validation_summary: AssessmentValidationSummary
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class MarketValueAssessmentOutcome:
    value_assessment_id: str | None
    calibrated_assembly_id: str
    match_id: str
    bookmaker_id: str
    market_identity: str
    final_status: AssessmentOutcomeStatus
    value_classification: ValueClassification | None
    actionability_status: ActionabilityStatus | None
    fair_probability: Decimal | None
    fair_odds: Decimal | None
    bookmaker_odds: Decimal | None
    expected_value: Decimal | None
    probability_edge: Decimal | None
    assessment_fingerprint: str | None
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    assessment_timestamp: datetime
    policy_version: str


@dataclass(frozen=True, slots=True)
class FutureOfficialSelectionInput:
    """Read-only handoff; deliberately contains no decision or stake fields."""

    value_assessment_id: str
    calibrated_assembly_id: str
    match_id: str
    kickoff_timestamp: datetime
    market_type: MarketType
    selection: MarketSelection
    market_line: Decimal | None
    fair_probability: Decimal
    bookmaker_odds: Decimal
    implied_probability: Decimal
    fair_odds: Decimal
    expected_value: Decimal
    absolute_edge: Decimal
    relative_edge: Decimal
    value_classification: ValueClassification
    freshness: FreshnessState
    source_provider: str
    bookmaker_id: str
    source_model_artifact_id: str
    source_model_version: str
    calibration_set_id: str | None
    calibration_set_fingerprint: str
    calibrated_assembly_fingerprint: str
    odds_fingerprint: str
    assessment_fingerprint: str
