"""Immutable calibration commands, artifacts, predictions, metrics, and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.historical_dataset_split import Partition
from app.historical_model_training import TARGET_SCHEMA_VERSION
from app.historical_training_dataset import FEATURE_SCHEMA_VERSION, LABEL_SCHEMA_VERSION
from app.prediction_inference import OFFICIAL_TARGET_ORDER, PredictionTarget, RawProbabilitySet

from .policy import (
    ARTIFACT_FORMAT_VERSION, CALIBRATION_POLICY_VERSION, CLAMP_POLICY_VERSION,
    METADATA_VERSION, MONOTONICITY_POLICY_VERSION, RECONCILIATION_POLICY_VERSION,
    RUNTIME_COMPATIBILITY_VERSION, CalibrationMethod, TargetMethodOverride,
)


class CalibrationStatus(str, Enum):
    CALIBRATION_FITTED = "CALIBRATION_FITTED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_SOURCE_TRAINING_RUN = "REJECTED_SOURCE_TRAINING_RUN"
    REJECTED_SOURCE_ARTIFACT = "REJECTED_SOURCE_ARTIFACT"
    REJECTED_SOURCE_SPLIT = "REJECTED_SOURCE_SPLIT"
    REJECTED_PARTITION_SAFETY = "REJECTED_PARTITION_SAFETY"
    REJECTED_SCHEMA_COMPATIBILITY = "REJECTED_SCHEMA_COMPATIBILITY"
    REJECTED_INSUFFICIENT_EXAMPLES = "REJECTED_INSUFFICIENT_EXAMPLES"
    REJECTED_INSUFFICIENT_CLASS_SUPPORT = "REJECTED_INSUFFICIENT_CLASS_SUPPORT"
    REJECTED_RAW_PREDICTIONS = "REJECTED_RAW_PREDICTIONS"
    REJECTED_CALIBRATION_FIT = "REJECTED_CALIBRATION_FIT"
    REJECTED_CONVERGENCE = "REJECTED_CONVERGENCE"
    REJECTED_INVALID_CALIBRATED_PROBABILITIES = "REJECTED_INVALID_CALIBRATED_PROBABILITIES"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class HistoricalCalibrationCommand:
    calibration_request_id: str
    calibration_run_name: str
    source_training_run_id: str
    source_training_run_fingerprint: str
    source_model_artifact_id: str
    source_model_artifact_fingerprint: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    calibration_partition: Partition | str = Partition.VALIDATION
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    feature_schema_fingerprint: str = ""
    label_schema_version: str = LABEL_SCHEMA_VERSION
    target_schema_version: str = TARGET_SCHEMA_VERSION
    artifact_format_version: str = ARTIFACT_FORMAT_VERSION
    runtime_compatibility_version: str = RUNTIME_COMPATIBILITY_VERSION
    match_result_method: CalibrationMethod = CalibrationMethod.PLATT_SCALING_V1
    totals_method: CalibrationMethod = CalibrationMethod.PLATT_SCALING_V1
    btts_method: CalibrationMethod = CalibrationMethod.PLATT_SCALING_V1
    target_method_overrides: tuple[TargetMethodOverride, ...] = ()
    clamp_policy_version: str = CLAMP_POLICY_VERSION
    monotonicity_policy_version: str = MONOTONICITY_POLICY_VERSION
    reconciliation_policy_version: str = RECONCILIATION_POLICY_VERSION
    calibration_policy_version: str = CALIBRATION_POLICY_VERSION
    calibration_timestamp: datetime | str = ""
    code_metadata_version: str = "goalvision-ai"
    dependency_metadata_version: str = "v1"
    environment_metadata_version: str = "v1"
    metadata_version: str = METADATA_VERSION


@dataclass(frozen=True, slots=True)
class NormalizedCalibrationCommand:
    calibration_request_id: str
    calibration_run_name: str
    source_training_run_id: str
    source_training_run_fingerprint: str
    source_model_artifact_id: str
    source_model_artifact_fingerprint: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    calibration_partition: Partition
    feature_schema_version: str
    feature_schema_fingerprint: str
    label_schema_version: str
    target_schema_version: str
    artifact_format_version: str
    runtime_compatibility_version: str
    match_result_method: CalibrationMethod
    totals_method: CalibrationMethod
    btts_method: CalibrationMethod
    target_method_overrides: tuple[TargetMethodOverride, ...]
    clamp_policy_version: str
    monotonicity_policy_version: str
    reconciliation_policy_version: str
    calibration_policy_version: str
    calibration_timestamp: str
    code_metadata_version: str
    dependency_metadata_version: str
    environment_metadata_version: str
    metadata_version: str


@dataclass(frozen=True, slots=True)
class ValidationPrediction:
    training_example_id: str
    example_fingerprint: str
    artifact_id: str
    artifact_fingerprint: str
    training_run_id: str
    split_id: str
    fold_id: str
    partition: Partition
    raw_probabilities: RawProbabilitySet
    calibrated_probabilities: RawProbabilitySet | None
    raw_prediction_fingerprint: str
    monotonicity_adjustment_snapshot: str = "{}"
    reconciliation_snapshot: str = "{}"
    deterministic_order: int = 0


@dataclass(frozen=True, slots=True)
class TargetCalibrationArtifact:
    target_identity: str
    target_order: int
    method: CalibrationMethod
    target_artifact_fingerprint: str
    fitted_parameters_snapshot: str
    class_order: tuple[str, ...]
    support_snapshot: str
    convergence_snapshot: str
    derivation_snapshot: str


@dataclass(frozen=True, slots=True)
class CalibrationMetric:
    target_identity: str
    metric_phase: str
    metric_name: str
    metric_value: Decimal | None
    metric_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    target_identity: str
    metric_phase: str
    bin_index: int
    lower_bound: Decimal
    upper_bound: Decimal
    sample_count: int
    mean_predicted_probability: Decimal | None
    observed_frequency: Decimal | None
    absolute_gap: Decimal | None
    bin_fingerprint: str


@dataclass(frozen=True, slots=True)
class CalibrationArtifactSet:
    artifact_set_id: str
    artifact_set_fingerprint: str
    calibration_run_id: str
    request_fingerprint: str
    command: NormalizedCalibrationCommand
    target_artifacts: tuple[TargetCalibrationArtifact, ...]
    reconciliation_fingerprint: str
    monotonicity_fingerprint: str
    compatibility_snapshot: str
    provenance_snapshot: str


@dataclass(frozen=True, slots=True)
class PreparedCalibrationRun:
    calibration_run_id: str
    command: NormalizedCalibrationCommand
    request_fingerprint: str
    calibration_run_fingerprint: str
    artifact_set: CalibrationArtifactSet
    predictions: tuple[ValidationPrediction, ...]
    metrics: tuple[CalibrationMetric, ...]
    reliability_bins: tuple[ReliabilityBin, ...]
    aggregate_raw_metrics: tuple[tuple[str, Decimal], ...]
    aggregate_calibrated_metrics: tuple[tuple[str, Decimal], ...]
    monotonicity_summary: tuple[tuple[str, Decimal | int], ...]
    reconciliation_summary: tuple[tuple[str, Decimal | int], ...]
    deterministic_run_snapshot: str


@dataclass(frozen=True, slots=True)
class CalibrationOutcome:
    status: CalibrationStatus
    calibration_run_id: str | None
    calibration_artifact_set_id: str | None
    calibration_request_id: str
    request_fingerprint: str | None
    calibration_run_fingerprint: str | None
    artifact_set_fingerprint: str | None
    source_training_run_id: str
    source_artifact_id: str
    split_id: str
    fold_id: str
    validation_row_count: int
    fitted_target_count: int
    derived_target_count: int
    ordered_target_identities: tuple[str, ...]
    aggregate_raw_metrics: tuple[tuple[str, Decimal], ...]
    aggregate_calibrated_metrics: tuple[tuple[str, Decimal], ...]
    monotonicity_adjustment_summary: tuple[tuple[str, Decimal | int], ...]
    reconciliation_summary: tuple[tuple[str, Decimal | int], ...]
    ordered_reason_codes: tuple[str, ...]
    policy_versions: tuple[tuple[str, str], ...]
    calibration_timestamp: str | None


CANONICAL_TARGET_ORDER = tuple(item.value for item in OFFICIAL_TARGET_ORDER)
