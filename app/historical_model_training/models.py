"""Immutable commands, artifacts, metrics, and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.historical_dataset_split import Partition
from app.historical_training_dataset import FEATURE_SCHEMA_VERSION, LABEL_SCHEMA_VERSION
from app.prediction_inference.models import OFFICIAL_TARGET_ORDER, PredictionTarget, RawProbabilitySet

from .policy import (
    ARTIFACT_FORMAT_VERSION, METADATA_VERSION, MODEL_FAMILY, MODEL_POLICY_VERSION,
    PREPROCESSING_POLICY_VERSION, TARGET_SCHEMA_VERSION, ClassWeightPolicy,
    MissingValuePolicy, ScalingPolicy,
)


class TrainingStatus(str, Enum):
    MODEL_TRAINED = "MODEL_TRAINED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_SOURCE_SPLIT = "REJECTED_SOURCE_SPLIT"
    REJECTED_PARTITION_SAFETY = "REJECTED_PARTITION_SAFETY"
    REJECTED_FEATURE_SCHEMA = "REJECTED_FEATURE_SCHEMA"
    REJECTED_LABEL_SCHEMA = "REJECTED_LABEL_SCHEMA"
    REJECTED_INSUFFICIENT_EXAMPLES = "REJECTED_INSUFFICIENT_EXAMPLES"
    REJECTED_INSUFFICIENT_CLASS_SUPPORT = "REJECTED_INSUFFICIENT_CLASS_SUPPORT"
    REJECTED_PREPROCESSING = "REJECTED_PREPROCESSING"
    REJECTED_CONVERGENCE = "REJECTED_CONVERGENCE"
    REJECTED_INVALID_PROBABILITIES = "REJECTED_INVALID_PROBABILITIES"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class EstimatorConfiguration:
    regularization: Decimal = Decimal("0.001")
    learning_rate: Decimal = Decimal("0.05")
    solver: str = "DETERMINISTIC_BATCH_GRADIENT_DESCENT_V1"
    class_weight_policy: ClassWeightPolicy = ClassWeightPolicy.NONE
    maximum_iterations: int = 1000
    convergence_tolerance: Decimal = Decimal("0.0001")
    random_seed: int = 0


@dataclass(frozen=True, slots=True)
class HistoricalModelTrainingCommand:
    training_request_id: str
    training_run_name: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    training_partition: Partition | str = Partition.TRAIN
    evaluate_validation: bool = True
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    feature_schema_fingerprint: str = ""
    ordered_feature_names: tuple[str, ...] = ()
    label_schema_version: str = LABEL_SCHEMA_VERSION
    target_schema_version: str = TARGET_SCHEMA_VERSION
    preprocessing_policy_version: str = PREPROCESSING_POLICY_VERSION
    model_policy_version: str = MODEL_POLICY_VERSION
    artifact_format_version: str = ARTIFACT_FORMAT_VERSION
    model_family: str = MODEL_FAMILY
    estimator: EstimatorConfiguration = EstimatorConfiguration()
    missing_value_policy: MissingValuePolicy = MissingValuePolicy.DETERMINISTIC_MEDIAN_IMPUTATION_V1
    scaling_policy: ScalingPolicy = ScalingPolicy.STANDARD_SCALING_V1
    append_missingness_indicators: bool = False
    training_timestamp: datetime | str = ""
    code_version: str = "goalvision-ai"
    environment_metadata_version: str = "v1"
    dependency_metadata_version: str = "v1"
    metadata_version: str = METADATA_VERSION


@dataclass(frozen=True, slots=True)
class NormalizedTrainingCommand:
    training_request_id: str
    training_run_name: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    training_partition: Partition
    evaluate_validation: bool
    feature_schema_version: str
    feature_schema_fingerprint: str
    ordered_feature_names: tuple[str, ...]
    label_schema_version: str
    target_schema_version: str
    preprocessing_policy_version: str
    model_policy_version: str
    artifact_format_version: str
    model_family: str
    estimator: EstimatorConfiguration
    missing_value_policy: MissingValuePolicy
    scaling_policy: ScalingPolicy
    append_missingness_indicators: bool
    training_timestamp: str
    code_version: str
    environment_metadata_version: str
    dependency_metadata_version: str
    metadata_version: str


@dataclass(frozen=True, slots=True)
class PreprocessingFeature:
    feature_name: str
    original_feature_index: int
    transformed_feature_index: int
    imputation_value: float
    missing_training_count: int
    scaling_mean: float
    scaling_scale: float
    zero_variance: bool
    row_fingerprint: str


@dataclass(frozen=True, slots=True)
class FittedPreprocessing:
    policy_version: str
    missing_value_policy: str
    scaling_policy: str
    append_missingness_indicators: bool
    original_feature_names: tuple[str, ...]
    transformed_feature_names: tuple[str, ...]
    features: tuple[PreprocessingFeature, ...]
    preprocessing_fingerprint: str


@dataclass(frozen=True, slots=True)
class FittedEstimator:
    estimator_identity: str
    model_type: str
    class_order: tuple[str, ...]
    coefficients: tuple[tuple[float, ...], ...]
    intercepts: tuple[float, ...]
    iterations: int
    converged: bool
    final_delta: float
    estimator_fingerprint: str


@dataclass(frozen=True, slots=True)
class MetricRecord:
    partition: Partition
    target_identity: str
    metric_name: str
    metric_value: Decimal | None
    metric_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class TrainingExampleLink:
    training_example_id: str
    example_fingerprint: str
    partition: Partition
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class ArtifactTarget:
    target_identity: str
    target_order: int
    estimator_fingerprint: str
    model_type: str
    class_order: tuple[str, ...]
    coefficients: tuple[tuple[float, ...], ...]
    intercepts: tuple[float, ...]
    convergence_snapshot: str


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    artifact_id: str
    artifact_fingerprint: str
    training_run_id: str
    training_request_fingerprint: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    model_family: str
    feature_schema_version: str
    feature_schema_fingerprint: str
    ordered_feature_names: tuple[str, ...]
    label_schema_version: str
    target_schema_version: str
    canonical_target_order: tuple[PredictionTarget, ...]
    artifact_format_version: str
    preprocessing: FittedPreprocessing
    estimators: tuple[FittedEstimator, ...]
    training_timestamp: str
    compatibility_snapshot: str
    provenance_snapshot: str


@dataclass(frozen=True, slots=True)
class PreparedTrainingRun:
    training_run_id: str
    command: NormalizedTrainingCommand
    request_fingerprint: str
    training_run_fingerprint: str
    artifact: ModelArtifact
    training_examples: tuple[TrainingExampleLink, ...]
    metrics: tuple[MetricRecord, ...]
    aggregate_training_metrics: tuple[tuple[str, Decimal], ...]
    aggregate_validation_metrics: tuple[tuple[str, Decimal], ...]
    deterministic_run_snapshot: str


@dataclass(frozen=True, slots=True)
class TrainingOutcome:
    status: TrainingStatus
    training_run_id: str | None
    artifact_id: str | None
    training_request_id: str
    training_request_fingerprint: str | None
    training_run_fingerprint: str | None
    artifact_fingerprint: str | None
    source_split_id: str
    fold_id: str
    model_family: str
    training_row_count: int
    validation_row_count: int
    original_feature_count: int
    transformed_feature_count: int
    target_count: int
    ordered_target_identities: tuple[str, ...]
    aggregate_training_metrics: tuple[tuple[str, Decimal], ...]
    aggregate_validation_metrics: tuple[tuple[str, Decimal], ...]
    ordered_reason_codes: tuple[str, ...]
    policy_versions: tuple[tuple[str, str], ...]
    training_timestamp: str | None


@dataclass(frozen=True, slots=True)
class ArtifactPrediction:
    artifact_id: str
    artifact_fingerprint: str
    raw_probabilities: RawProbabilitySet


CANONICAL_TARGET_ORDER = tuple(item.value for item in OFFICIAL_TARGET_ORDER)
