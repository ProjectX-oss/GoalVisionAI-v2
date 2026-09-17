"""Explicit immutable historical calibration policies."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


CALIBRATION_POLICY_VERSION = "historical_probability_calibration_policy_v1"
ARTIFACT_FORMAT_VERSION = "goalvision_historical_calibration_artifact_v1"
RUNTIME_COMPATIBILITY_VERSION = "probability-calibration-v1"
CLAMP_POLICY_VERSION = "EXPLICIT_0_001_0_999_V1"
MONOTONICITY_POLICY_VERSION = "DECREASING_PAVA_V1"
RECONCILIATION_POLICY_VERSION = "LOWER_BOUNDED_SIMPLEX_V1"
PREDICTION_IMPLEMENTATION_VERSION = "persisted-model-artifact-inference-v1"
METADATA_VERSION = "v1"


class CalibrationMethod(str, Enum):
    IDENTITY_V1 = "IDENTITY_V1"
    PLATT_SCALING_V1 = "PLATT_SCALING_V1"
    ISOTONIC_REGRESSION_V1 = "ISOTONIC_REGRESSION_V1"


@dataclass(frozen=True, slots=True)
class TargetMethodOverride:
    target_identity: str
    method: CalibrationMethod


@dataclass(frozen=True, slots=True)
class HistoricalCalibrationPolicy:
    version: str = CALIBRATION_POLICY_VERSION
    minimum_validation_examples: int = 20
    minimum_positive_per_binary_target: int = 3
    minimum_negative_per_binary_target: int = 3
    minimum_examples_per_match_result_class: int = 3
    minimum_distinct_probabilities_for_isotonic: int = 3
    maximum_missing_predictions: int = 0
    maximum_invalid_labels: int = 0
    allow_identity_calibration: bool = False
    reject_insufficient_support: bool = True
    reliability_bin_count: int = 10
    minimum_probability: Decimal = Decimal("0.001")
    maximum_probability: Decimal = Decimal("0.999")
    reconciliation_tolerance: Decimal = Decimal("0.000001")
    monotonicity_tolerance: Decimal = Decimal("0.000001")
    platt_epsilon: Decimal = Decimal("0.000001")
    platt_regularization: Decimal = Decimal("0.001")
    platt_maximum_iterations: int = 100
    platt_convergence_tolerance: Decimal = Decimal("0.000000001")
    random_seed: int = 0

    def __post_init__(self):
        counts = (
            self.minimum_validation_examples, self.minimum_positive_per_binary_target,
            self.minimum_negative_per_binary_target, self.minimum_examples_per_match_result_class,
            self.minimum_distinct_probabilities_for_isotonic, self.reliability_bin_count,
            self.platt_maximum_iterations,
        )
        if any(type(value) is not int or value < 1 for value in counts):
            raise ValueError("Calibration sample and iteration limits must be positive integers.")
        if self.maximum_missing_predictions != 0 or self.maximum_invalid_labels != 0:
            raise ValueError("Historical calibration v1 fails closed on missing predictions and invalid labels.")
        if not self.reject_insufficient_support:
            raise ValueError("Historical calibration v1 must reject insufficient support.")
        if not Decimal(0) < self.minimum_probability < self.maximum_probability < Decimal(1):
            raise ValueError("Calibration clamp bounds must be inside (0, 1).")


DEFAULT_HISTORICAL_CALIBRATION_POLICY = HistoricalCalibrationPolicy()
