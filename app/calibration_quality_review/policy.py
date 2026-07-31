"""Centralized fail-closed Lab calibration-quality policy."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CalibrationQualityPolicy:
    version: str = "goalvision-lab-calibration-quality-policy-v1"
    minimum_validation_count: int = 100
    minimum_positive_count: int = 20
    minimum_negative_count: int = 20
    minimum_unique_raw_probabilities: int = 20
    minimum_populated_reliability_bins: int = 3
    maximum_ece: Decimal = Decimal("0.15")
    maximum_mce: Decimal = Decimal("0.35")
    maximum_brier_degradation: Decimal = Decimal("0.01")
    maximum_log_loss_degradation: Decimal = Decimal("0.01")
    maximum_extreme_fraction: Decimal = Decimal("0.05")
    maximum_large_adjustment_fraction: Decimal = Decimal("0.10")
    maximum_single_adjustment: Decimal = Decimal("0.35")
    extreme_minimum: Decimal = Decimal("0.001")
    extreme_maximum: Decimal = Decimal("0.999")
    strong_shift_distance: Decimal = Decimal("6")
    maximum_strongly_shifted_features: int = 8
    official_policy_authorized: bool = False
    controlled_synthetic_send_authorized: bool = False

    def __post_init__(self) -> None:
        if self.official_policy_authorized:
            raise ValueError("Official calibration-quality authorization is unset.")
        if self.controlled_synthetic_send_authorized:
            raise ValueError("Controlled-synthetic Lab publication is unauthorized.")


DEFAULT_CALIBRATION_QUALITY_POLICY = CalibrationQualityPolicy()
