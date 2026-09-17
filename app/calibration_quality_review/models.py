"""Immutable calibration-quality, trace, and live-shift evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class CalibrationQualityStatus(str, Enum):
    ACCEPTABLE = "CALIBRATION_QUALITY_ACCEPTABLE"
    REVIEW_REQUIRED = "CALIBRATION_QUALITY_REVIEW_REQUIRED"
    INELIGIBLE = "CALIBRATION_QUALITY_INELIGIBLE"


class DistributionShiftStatus(str, Enum):
    ACCEPTABLE = "DISTRIBUTION_SHIFT_ACCEPTABLE"
    REVIEW_REQUIRED = "CALIBRATION_DISTRIBUTION_SHIFT"
    INELIGIBLE = "DISTRIBUTION_SHIFT_INELIGIBLE"


@dataclass(frozen=True, slots=True)
class TargetQualityEvidence:
    target: str
    fitted_source_target: str
    derived_complement: bool
    method: str
    parameter_count: int
    validation_count: int
    positive_count: int
    negative_count: int
    base_rate: Decimal
    unique_raw_probability_count: int
    unique_calibrated_probability_count: int
    raw_range: tuple[Decimal, Decimal]
    raw_quantiles: tuple[tuple[str, Decimal], ...]
    calibrated_range: tuple[Decimal, Decimal]
    calibrated_quantiles: tuple[tuple[str, Decimal], ...]
    reliability_bin_count: int
    populated_bin_count: int
    minimum_bin_support: int
    maximum_bin_support: int
    expected_calibration_error: Decimal
    maximum_calibration_error: Decimal
    brier_before: Decimal
    brier_after: Decimal
    log_loss_before: Decimal
    log_loss_after: Decimal
    calibration_slope: Decimal | None
    calibration_intercept: Decimal | None
    discrimination_metric: Decimal | None
    fraction_at_minimum: Decimal
    fraction_at_maximum: Decimal
    fraction_below_0_01: Decimal
    fraction_above_0_99: Decimal
    fraction_adjusted_over_0_10: Decimal
    fraction_adjusted_over_0_25: Decimal
    maximum_absolute_adjustment: Decimal
    monotonicity_correction_count: int
    complement_correction_count: int
    simplex_correction_count: int
    support_status: str
    reason_codes: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CalibrationTrace:
    target: str
    fitted_source_target: str
    method: str
    raw_probability: Decimal
    calibration_parameters_snapshot: str
    validation_count: int
    positive_count: int
    negative_count: int
    unique_raw_probability_count: int
    validation_raw_range: tuple[Decimal, Decimal]
    calibrator_output_before_clamp: Decimal
    fitted_output_after_clamp: Decimal
    output_after_reconciliation: Decimal
    output_after_final_clamp: Decimal
    complement_changed: bool
    simplex_changed: bool
    totals_monotonicity_changed: bool
    clamp_changed: bool
    outside_validation_support: bool
    absolute_adjustment: Decimal
    extreme_status: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FeatureShiftEvidence:
    feature_name: str
    live_value: Decimal | None
    missing: bool
    train_median: Decimal | None
    validation_median: Decimal | None
    test_median: Decimal | None
    robust_dispersion: Decimal | None
    percentile_rank: Decimal | None
    standardized_distance: Decimal | None
    historical_minimum: Decimal | None
    historical_maximum: Decimal | None
    outside_historical_range: bool
    imputed: bool
    absent: bool
    strongly_shifted: bool


@dataclass(frozen=True, slots=True)
class DistributionShiftReport:
    feature_count: int
    completeness: Decimal
    optional_missing_count: int
    required_missing_count: int
    out_of_range_feature_count: int
    strongly_shifted_feature_count: int
    imputed_feature_count: int
    missingness_pattern_similarity: Decimal
    status: DistributionShiftStatus
    shifted_feature_names: tuple[str, ...]
    features: tuple[FeatureShiftEvidence, ...]
    reason_codes: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CalibrationQualityReport:
    schema_version: str
    policy_version: str
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    source_mode: str
    controlled_synthetic: bool
    target_evidence: tuple[TargetQualityEvidence, ...]
    traces: tuple[CalibrationTrace, ...]
    distribution_shift: DistributionShiftReport
    artifact_status: CalibrationQualityStatus
    lab_outcome: CalibrationQualityStatus
    official_outcome: CalibrationQualityStatus
    analysis_preview_allowed: bool
    send_eligible: bool
    reason_codes: tuple[str, ...]
    fingerprint: str
