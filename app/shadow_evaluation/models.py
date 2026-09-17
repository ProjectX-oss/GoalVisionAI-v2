"""Immutable shadow commands, evidence, decisions, settlements, and metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.prediction_inference import RawProbabilitySet


class ModelRole(str, Enum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"


class ShadowExecutionStatus(str, Enum):
    PRE_MATCH_EVALUATED = "PRE_MATCH_EVALUATED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"


class PreMatchOutcome(str, Enum):
    EVALUATED = "EVALUATED"
    NO_SELECTION = "NO_SELECTION"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class DisagreementType(str, Enum):
    EXACT_AGREEMENT = "EXACT_AGREEMENT"
    SAME_MARKET_DIFFERENT_PROBABILITY = "SAME_MARKET_DIFFERENT_PROBABILITY"
    SAME_MARKET_DIFFERENT_ELIGIBILITY = "SAME_MARKET_DIFFERENT_ELIGIBILITY"
    DIFFERENT_MARKET = "DIFFERENT_MARKET"
    CHAMPION_ONLY_SELECTION = "CHAMPION_ONLY_SELECTION"
    CHALLENGER_ONLY_SELECTION = "CHALLENGER_ONLY_SELECTION"
    BOTH_NO_SELECTION = "BOTH_NO_SELECTION"
    PROBABILITY_CONTRACT_FAILURE = "PROBABILITY_CONTRACT_FAILURE"
    SOURCE_INCOMPATIBILITY = "SOURCE_INCOMPATIBILITY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class DisagreementSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SettlementOutcome(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"
    PUSH = "PUSH"
    NO_SELECTION = "NO_SELECTION"
    UNSETTLED = "UNSETTLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ShadowOddsSnapshot:
    odds_snapshot_id: str
    source_identity: str
    source_version: str
    source_record_identity: str
    source_fingerprint: str
    match_id: str
    market_identity: str
    selection_identity: str
    bookmaker_identity: str
    decimal_odds: Decimal
    market_status: str
    snapshot_timestamp_utc: datetime | str
    kickoff_utc: datetime | str


@dataclass(frozen=True, slots=True)
class ShadowOddsSnapshotSet:
    odds_snapshot_set_id: str
    odds_snapshot_set_fingerprint: str
    snapshots: tuple[ShadowOddsSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ShadowModelInputSnapshot:
    model_input_vector_id: str
    model_input_fingerprint: str
    match_id: str
    competition: str
    season: str
    home_team: str
    away_team: str
    kickoff_utc: datetime | str
    snapshot_timestamp_utc: datetime | str
    feature_schema_version: str
    feature_schema_fingerprint: str
    feature_provenance_fingerprint: str
    ordered_feature_names: tuple[str, ...]
    ordered_feature_values: tuple[Decimal | int | None, ...]
    missingness_mask: tuple[bool, ...]
    ordered_missing_features: tuple[str, ...]
    completeness_score: Decimal
    ordered_source_timestamps: tuple[datetime | str, ...]
    input_snapshot_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowEvaluationCommand:
    shadow_request_id: str
    shadow_run_name: str
    comparison_run_id: str
    comparison_run_fingerprint: str
    challenger_candidate_id: str
    recommendation_id: str
    recommendation_fingerprint: str
    champion_model_artifact_id: str
    champion_model_artifact_fingerprint: str
    champion_calibration_artifact_set_id: str
    champion_calibration_artifact_set_fingerprint: str
    champion_runtime_policy_version: str
    challenger_model_artifact_id: str
    challenger_model_artifact_fingerprint: str
    challenger_calibration_artifact_set_id: str
    challenger_calibration_artifact_set_fingerprint: str
    challenger_runtime_policy_version: str
    model_input_vector_id: str
    model_input_fingerprint: str
    match_id: str
    competition: str
    kickoff_utc: datetime | str
    input_snapshot_timestamp_utc: datetime | str
    feature_schema_version: str
    feature_schema_fingerprint: str
    feature_provenance_fingerprint: str
    odds_snapshot_set_id: str
    odds_snapshot_set_fingerprint: str
    evaluation_timestamp_utc: datetime | str
    shadow_policy_version: str = "shadow-evaluation-policy-v1"
    probability_contract_version: str = "canonical-11-target-contract-v1"
    calibration_policy_version: str = "historical_probability_calibration_policy_v1"
    market_value_policy_version: str = "market-value-assessment-policy-v1"
    selection_policy_version: str = "official-prediction-selection-policy-v1"
    comparison_policy_version: str = "shadow-disagreement-policy-v1"
    settlement_policy_version: str = "official-half-goal-settlement-v1"
    metric_policy_version: str = "shadow-evaluation-metrics-v1"
    odds_policy_version: str = "exact-supplied-pre-kickoff-v1"
    code_metadata_version: str = "goalvision-ai"
    dependency_metadata_version: str = "v1"
    environment_metadata_version: str = "v1"
    metadata_version: str = "v1"
    correlation_id: str | None = None
    pipeline_id: str | None = None
    production_champion_prediction_id: str | None = None


@dataclass(frozen=True, slots=True)
class ShadowInference:
    inference_id: str
    model_role: ModelRole
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    raw_probabilities: RawProbabilitySet
    calibrated_probabilities: RawProbabilitySet
    raw_inference_fingerprint: str
    calibrated_inference_fingerprint: str
    preprocessing_fingerprint: str
    reconciliation_snapshot: str
    monotonicity_snapshot: str


@dataclass(frozen=True, slots=True)
class ShadowMarketAssessment:
    assessment_id: str
    model_role: ModelRole
    market_identity: str
    odds_snapshot_id: str | None
    calibrated_probability: Decimal
    fair_odds: Decimal | None
    decimal_odds: Decimal | None
    implied_probability: Decimal | None
    edge: Decimal | None
    expected_value: Decimal | None
    expected_profit_per_unit: Decimal | None
    eligible: bool
    rejection_reasons: tuple[str, ...]
    deterministic_rank: int
    assessment_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowSelection:
    selection_id: str
    model_role: ModelRole
    selected_assessment_id: str | None
    market_identity: str | None
    probability: Decimal | None
    decimal_odds: Decimal | None
    expected_value: Decimal | None
    outcome: PreMatchOutcome
    reason_codes: tuple[str, ...]
    selection_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    comparison_id: str
    disagreement_type: DisagreementType
    severity: DisagreementSeverity
    target_probability_deltas: tuple[tuple[str, Decimal], ...]
    maximum_probability_delta: Decimal
    mean_probability_delta: Decimal
    result_distribution_delta: Decimal
    totals_delta: Decimal
    btts_delta: Decimal
    fair_odds_delta: Decimal | None
    expected_value_delta: Decimal | None
    eligibility_changed: bool
    selection_changed: bool
    confidence_delta: Decimal | None
    reason_codes: tuple[str, ...]
    comparison_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowMetric:
    metric_id: str
    phase: str
    model_role: ModelRole | None
    category: str
    grouping_identity: str
    metric_name: str
    metric_value: Decimal | None
    metric_snapshot: str
    metric_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowAggregateSnapshot:
    aggregate_snapshot_id: str
    grouping_category: str
    grouping_identity: str
    sample_count: int
    settled_count: int
    metric_snapshot: str
    aggregate_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowExclusion:
    exclusion_id: str
    stage: str
    reason: str
    detail_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class ShadowExecution:
    shadow_execution_id: str
    command: ShadowEvaluationCommand
    request_fingerprint: str
    input_snapshot: ShadowModelInputSnapshot
    odds_snapshot_set: ShadowOddsSnapshotSet
    inferences: tuple[ShadowInference, ...]
    market_assessments: tuple[ShadowMarketAssessment, ...]
    selections: tuple[ShadowSelection, ...]
    comparison: ShadowComparison
    metrics: tuple[ShadowMetric, ...]
    aggregate_snapshots: tuple[ShadowAggregateSnapshot, ...]
    exclusions: tuple[ShadowExclusion, ...]
    execution_fingerprint: str
    deterministic_snapshot: str


@dataclass(frozen=True, slots=True)
class ShadowEvaluationOutcome:
    status: ShadowExecutionStatus
    shadow_execution_id: str
    shadow_request_id: str
    request_fingerprint: str
    execution_fingerprint: str
    champion_outcome: PreMatchOutcome
    challenger_outcome: PreMatchOutcome
    disagreement_type: DisagreementType
    severity: DisagreementSeverity
    champion_selection: ShadowSelection
    challenger_selection: ShadowSelection
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowSettlementCommand:
    settlement_request_id: str
    shadow_execution_id: str
    shadow_execution_fingerprint: str
    match_id: str
    final_home_score: int
    final_away_score: int
    settlement_timestamp_utc: datetime | str
    source_identity: str
    source_version: str
    source_record_identity: str
    source_fingerprint: str
    settlement_policy_version: str = "official-half-goal-settlement-v1"
    metric_policy_version: str = "shadow-evaluation-metrics-v1"
    metadata_version: str = "v1"


@dataclass(frozen=True, slots=True)
class ShadowSettlement:
    settlement_id: str
    settlement_request_id: str
    shadow_execution_id: str
    champion_outcome: SettlementOutcome
    challenger_outcome: SettlementOutcome
    champion_profit_per_unit: Decimal
    challenger_profit_per_unit: Decimal
    final_home_score: int
    final_away_score: int
    source_fingerprint: str
    settlement_timestamp_utc: str
    settlement_fingerprint: str
