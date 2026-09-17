from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

from app.prediction_inference import OFFICIAL_TARGET_ORDER, PredictionTarget


@dataclass(frozen=True, slots=True)
class CalibratedMarketProbabilityPolicy:
    version: str = "calibrated-market-probability-policy-v1"
    probability_quantum: Decimal = Decimal("0.000001")
    minimum_probability: Decimal = Decimal("0.001")
    maximum_probability: Decimal = Decimal("0.999")
    match_result_tolerance: Decimal = Decimal("0.000001")
    complement_tolerance: Decimal = Decimal("0.000001")
    monotonicity_tolerance: Decimal = Decimal("0.000001")
    target_order: tuple[PredictionTarget, ...] = OFFICIAL_TARGET_ORDER
    supported_raw_inference_policy_versions: tuple[str, ...] = ("prediction-inference-policy-v1",)
    supported_calibration_policy_versions: tuple[str, ...] = ("probability-calibration-v1",)
    input_probability_schema: str = "goalvision_raw_probability"
    input_probability_schema_version: str = "v1"
    allow_explicit_inactive_artifacts: bool = False
    allow_mixed_calibration_policy_versions: bool = False
    permit_post_calibration_normalization: bool = False
    rounding: str = ROUND_HALF_EVEN

    def __post_init__(self) -> None:
        if not self.version.strip() or self.target_order != OFFICIAL_TARGET_ORDER:
            raise ValueError("Calibrated probability v1 policy identity/order is invalid.")
        values = (
            self.probability_quantum, self.minimum_probability,
            self.maximum_probability, self.match_result_tolerance,
            self.complement_tolerance, self.monotonicity_tolerance,
        )
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in values):
            raise TypeError("Probability policy values must be finite Decimals.")
        if not Decimal(0) < self.minimum_probability < self.maximum_probability < Decimal(1):
            raise ValueError("Calibrated probability bounds must be inside (0, 1).")
        if self.permit_post_calibration_normalization:
            raise ValueError("Post-calibration normalization is not supported in v1.")


DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY = CalibratedMarketProbabilityPolicy()
