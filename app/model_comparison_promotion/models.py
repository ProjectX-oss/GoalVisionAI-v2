"""Immutable commands, evidence, scores, recommendations, and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class ComparisonMode(str, Enum):
    EXACT_SHARED_BACKTEST_SCOPE = "EXACT_SHARED_BACKTEST_SCOPE"
    INTERSECTION_SCOPE = "INTERSECTION_SCOPE"
    POLICY_NORMALIZED_SCOPE = "POLICY_NORMALIZED_SCOPE"


class Recommendation(str, Enum):
    PROMOTE_CHALLENGER = "PROMOTE_CHALLENGER"
    KEEP_CHAMPION = "KEEP_CHAMPION"
    REJECT_CHALLENGER = "REJECT_CHALLENGER"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ComparisonStatus(str, Enum):
    COMPARISON_COMPLETED = "COMPARISON_COMPLETED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    NO_VALID_CHALLENGERS = "NO_VALID_CHALLENGERS"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_CHAMPION_SOURCE = "REJECTED_CHAMPION_SOURCE"
    REJECTED_CHALLENGER_SOURCE = "REJECTED_CHALLENGER_SOURCE"
    REJECTED_SCOPE_INCOMPATIBILITY = "REJECTED_SCOPE_INCOMPATIBILITY"
    REJECTED_POLICY_INCOMPATIBILITY = "REJECTED_POLICY_INCOMPATIBILITY"
    REJECTED_METRIC_INTEGRITY = "REJECTED_METRIC_INTEGRITY"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class Direction(str, Enum):
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"


class Materiality(str, Enum):
    MATERIAL_IMPROVEMENT = "MATERIAL_IMPROVEMENT"
    SMALL_IMPROVEMENT = "SMALL_IMPROVEMENT"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    SMALL_DEGRADATION = "SMALL_DEGRADATION"
    MATERIAL_DEGRADATION = "MATERIAL_DEGRADATION"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CompatibilityStatus(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    NORMALIZED = "NORMALIZED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INCOMPATIBLE = "INCOMPATIBLE"


class StabilityStatus(str, Enum):
    IMPROVED = "IMPROVED"
    STABLE = "STABLE"
    DEGRADED = "DEGRADED"
    SEVERELY_DEGRADED = "SEVERELY_DEGRADED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class UncertaintyClassification(str, Enum):
    STRONG_EVIDENCE = "STRONG_EVIDENCE"
    MODERATE_EVIDENCE = "MODERATE_EVIDENCE"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class ChallengerCandidate:
    challenger_candidate_id: str
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    backtest_run_id: str
    backtest_run_fingerprint: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonScope:
    comparison_scope_version: str
    mode: ComparisonMode | str = ComparisonMode.EXACT_SHARED_BACKTEST_SCOPE
    required_competitions: tuple[str, ...] = ()
    required_seasons: tuple[str, ...] = ()
    required_markets: tuple[str, ...] = ()
    kickoff_lower_bound: datetime | str | None = None
    kickoff_upper_bound: datetime | str | None = None
    required_odds_policy_version: str = "exact-latest-supplied-pre-kickoff-v1"
    required_selection_policy_version: str = "official-prediction-selection-policy-v1"
    required_staking_policy_version: str = "official-risk-v1"
    required_settlement_policy_version: str = "official-half-goal-settlement-v1"
    required_metric_policy_version: str = "historical-backtesting-metrics-v1"
    required_minimum_shared_sample_size: int = 100
    required_minimum_selected_bet_count: int = 30


@dataclass(frozen=True, slots=True)
class ModelComparisonCommand:
    comparison_request_id: str
    comparison_run_name: str
    champion_model_artifact_id: str
    champion_model_artifact_fingerprint: str
    champion_calibration_artifact_set_id: str
    champion_calibration_artifact_set_fingerprint: str
    champion_backtest_run_id: str
    champion_backtest_run_fingerprint: str
    challengers: tuple[ChallengerCandidate, ...]
    scope: ComparisonScope
    comparison_timestamp: datetime | str
    promotion_policy_version: str = "model-promotion-policy-v1"
    evidence_policy_version: str = "model-promotion-evidence-v1"
    compatibility_policy_version: str = "model-promotion-compatibility-v1"
    significance_policy_version: str = "model-promotion-significance-v1"
    predictive_score_policy_version: str = "model-promotion-predictive-score-v1"
    calibration_score_policy_version: str = "model-promotion-calibration-score-v1"
    betting_score_policy_version: str = "model-promotion-betting-score-v1"
    risk_score_policy_version: str = "model-promotion-risk-score-v1"
    stability_score_policy_version: str = "model-promotion-stability-score-v1"
    tie_break_policy_version: str = "model-promotion-tie-break-v1"
    code_metadata_version: str = "goalvision-ai"
    dependency_metadata_version: str = "v1"
    environment_metadata_version: str = "v1"
    metadata_version: str = "v1"


@dataclass(frozen=True, slots=True)
class NormalizedComparisonScope:
    comparison_scope_version: str
    mode: ComparisonMode
    required_competitions: tuple[str, ...]
    required_seasons: tuple[str, ...]
    required_markets: tuple[str, ...]
    kickoff_lower_bound: str | None
    kickoff_upper_bound: str | None
    required_odds_policy_version: str
    required_selection_policy_version: str
    required_staking_policy_version: str
    required_settlement_policy_version: str
    required_metric_policy_version: str
    required_minimum_shared_sample_size: int
    required_minimum_selected_bet_count: int


@dataclass(frozen=True, slots=True)
class NormalizedComparisonCommand:
    comparison_request_id: str
    comparison_run_name: str
    champion_model_artifact_id: str
    champion_model_artifact_fingerprint: str
    champion_calibration_artifact_set_id: str
    champion_calibration_artifact_set_fingerprint: str
    champion_backtest_run_id: str
    champion_backtest_run_fingerprint: str
    challengers: tuple[ChallengerCandidate, ...]
    scope: NormalizedComparisonScope
    comparison_timestamp: str
    promotion_policy_version: str
    evidence_policy_version: str
    compatibility_policy_version: str
    significance_policy_version: str
    predictive_score_policy_version: str
    calibration_score_policy_version: str
    betting_score_policy_version: str
    risk_score_policy_version: str
    stability_score_policy_version: str
    tie_break_policy_version: str
    code_metadata_version: str
    dependency_metadata_version: str
    environment_metadata_version: str
    metadata_version: str


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    evidence_row_id: str
    category: str
    name: str
    champion_value_snapshot: str
    challenger_value_snapshot: str
    compatibility_status: CompatibilityStatus
    detail_snapshot: str
    evidence_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class MetricEvaluation:
    metric_evaluation_id: str
    category: str
    group_identity: str
    metric_name: str
    direction: Direction
    champion_value: Decimal | None
    challenger_value: Decimal | None
    absolute_delta: Decimal | None
    relative_delta: Decimal | None
    normalized_score: Decimal
    materiality: Materiality
    gate_status: GateStatus
    reason_codes: tuple[str, ...]
    metric_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class StabilityGroup:
    stability_row_id: str
    group_category: str
    group_identity: str
    champion_sample_count: int
    challenger_sample_count: int
    champion_metric_snapshot: str
    challenger_metric_snapshot: str
    delta_snapshot: str
    stability_status: StabilityStatus
    concentration_evidence_snapshot: str
    stability_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class StatisticalEvidence:
    statistical_row_id: str
    evidence_name: str
    paired_sample_count: int
    deterministic_seed: int
    bootstrap_iterations: int
    effect_size: Decimal | None
    lower_confidence_bound: Decimal | None
    upper_confidence_bound: Decimal | None
    uncertainty_classification: UncertaintyClassification
    detail_snapshot: str
    evidence_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    gate_evaluation_id: str
    gate_category: str
    gate_name: str
    mandatory: bool
    status: GateStatus
    champion_value_snapshot: str
    challenger_value_snapshot: str
    threshold_snapshot: str
    reason_codes: tuple[str, ...]
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    score_component_id: str
    score_category: str
    raw_score: Decimal
    normalized_score: Decimal
    weight: Decimal
    weighted_contribution: Decimal
    gate_status: GateStatus
    detail_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class RecommendationRecord:
    recommendation_id: str
    recommendation_scope: str
    recommendation: Recommendation
    promotion_rank: int | None
    promotion_score: Decimal
    evidence_classification: UncertaintyClassification
    reason_codes: tuple[str, ...]
    recommendation_fingerprint: str


@dataclass(frozen=True, slots=True)
class ComparisonExclusion:
    exclusion_id: str
    challenger_candidate_id: str | None
    exclusion_stage: str
    exclusion_reason: str
    detail_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class VerifiedSourceBundle:
    model_artifact: object
    calibration_artifact_set: object
    backtest_run: object
    evidence: tuple[SourceEvidence, ...]
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class ChallengerEvaluation:
    candidate: ChallengerCandidate
    source_compatibility_fingerprint: str
    evaluation_fingerprint: str
    shared_prediction_count: int
    shared_selected_bet_count: int
    source_evidence: tuple[SourceEvidence, ...]
    metric_evaluations: tuple[MetricEvaluation, ...]
    stability_groups: tuple[StabilityGroup, ...]
    statistical_evidence: tuple[StatisticalEvidence, ...]
    gate_evaluations: tuple[GateEvaluation, ...]
    score_components: tuple[ScoreComponent, ...]
    promotion_score: Decimal
    recommendation: Recommendation
    deterministic_rank: int | None
    reason_codes: tuple[str, ...]
    exclusions: tuple[ComparisonExclusion, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedComparisonRun:
    comparison_run_id: str
    command: NormalizedComparisonCommand
    request_fingerprint: str
    comparison_run_fingerprint: str
    evaluations: tuple[ChallengerEvaluation, ...]
    final_recommended_challenger_id: str | None
    final_recommendation: Recommendation
    reason_codes: tuple[str, ...]
    exclusions: tuple[ComparisonExclusion, ...]
    deterministic_run_snapshot: str


@dataclass(frozen=True, slots=True)
class ComparisonOutcome:
    status: ComparisonStatus
    comparison_run_id: str | None
    comparison_request_id: str
    request_fingerprint: str | None
    comparison_run_fingerprint: str | None
    champion_model_artifact_id: str
    champion_model_artifact_fingerprint: str
    champion_calibration_artifact_set_id: str
    champion_calibration_artifact_set_fingerprint: str
    champion_backtest_run_id: str
    champion_backtest_run_fingerprint: str
    challenger_count: int
    valid_challenger_count: int
    final_recommended_challenger_id: str | None
    final_recommendation: Recommendation | None
    challenger_evaluations: tuple[ChallengerEvaluation, ...]
    ordered_reason_codes: tuple[str, ...]
    policy_versions: tuple[tuple[str, str], ...]
    comparison_scope: NormalizedComparisonScope | None
    comparison_timestamp: str | None
