from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.calibration import (
    CalibrationFittingPolicy,
    IsotonicFittingConfig,
    PlattFittingConfig,
)


class CalibrationMethod(str, Enum):
    """Supported deterministic probability transforms."""

    IDENTITY = "identity"
    PLATT = "platt"
    ISOTONIC = "isotonic"


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationConfig:
    """Deterministic configuration for post-prediction calibration."""

    method: CalibrationMethod = CalibrationMethod.IDENTITY
    reliability_bin_count: int = 10
    confidence_bin_count: int = 10
    minimum_probability: Decimal = Decimal("0.001")
    maximum_probability: Decimal = Decimal("0.999")
    calibration_version: str = "probability-calibration-v1"
    fitting_policy: CalibrationFittingPolicy = CalibrationFittingPolicy()
    platt: PlattFittingConfig = PlattFittingConfig()
    isotonic: IsotonicFittingConfig = IsotonicFittingConfig(
        output_epsilon=Decimal("0.001")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.method, CalibrationMethod):
            raise TypeError("Calibration method must be a CalibrationMethod.")
        for label, value in (
            ("Reliability bin count", self.reliability_bin_count),
            ("Confidence bin count", self.confidence_bin_count),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{label} must be a positive integer.")
        if not isinstance(self.minimum_probability, Decimal) or not isinstance(
            self.maximum_probability, Decimal
        ):
            raise TypeError("Probability limits must be Decimal values.")
        if not (
            self.minimum_probability.is_finite()
            and self.maximum_probability.is_finite()
            and Decimal("0") < self.minimum_probability
            < self.maximum_probability < Decimal("1")
        ):
            raise ValueError(
                "Probability limits must be finite and strictly inside (0, 1)."
            )
        if not self.calibration_version.strip():
            raise ValueError("Calibration version must not be empty.")
