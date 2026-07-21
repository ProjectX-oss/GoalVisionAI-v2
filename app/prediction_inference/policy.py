from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

from app.model_input_builder import (
    GOALVISION_MODEL_INPUT_V1,
    REQUIRED_BASELINE_FEATURES,
)

from .models import OFFICIAL_TARGET_ORDER, MissingValueSupport, PredictionTarget


@dataclass(frozen=True, slots=True)
class PredictionInferencePolicy:
    version: str = "prediction-inference-policy-v1"
    probability_quantum: Decimal = Decimal("0.000001")
    group_sum_tolerance: Decimal = Decimal("0.000001")
    monotonicity_tolerance: Decimal = Decimal("0.000001")
    minimum_probability: Decimal = Decimal("0")
    maximum_probability: Decimal = Decimal("1")
    required_targets: tuple[PredictionTarget, ...] = OFFICIAL_TARGET_ORDER
    supported_input_schema_name: str = GOALVISION_MODEL_INPUT_V1.name
    supported_input_schema_version: str = GOALVISION_MODEL_INPUT_V1.version
    supported_compatibility_versions: tuple[str, ...] = (
        GOALVISION_MODEL_INPUT_V1.compatibility_version,
    )
    required_feature_names: frozenset[str] = REQUIRED_BASELINE_FEATURES
    allowed_missing_value_support: tuple[MissingValueSupport, ...] = (
        MissingValueSupport.NONE,
        MissingValueSupport.OPTIONAL_FEATURES,
    )
    rounding: str = ROUND_HALF_EVEN

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Inference policy version is required.")
        decimal_values = (
            self.probability_quantum,
            self.group_sum_tolerance,
            self.monotonicity_tolerance,
            self.minimum_probability,
            self.maximum_probability,
        )
        if any(
            not isinstance(value, Decimal) or not value.is_finite()
            for value in decimal_values
        ):
            raise TypeError("Inference policy numeric values must be finite Decimals.")
        if self.probability_quantum <= 0:
            raise ValueError("Probability quantum must be positive.")
        if self.group_sum_tolerance < 0 or self.monotonicity_tolerance < 0:
            raise ValueError("Inference tolerances cannot be negative.")
        if not (
            Decimal(0)
            <= self.minimum_probability
            < self.maximum_probability
            <= Decimal(1)
        ):
            raise ValueError("Inference probability bounds must be within [0, 1].")
        if self.required_targets != OFFICIAL_TARGET_ORDER:
            raise ValueError("Official inference target ordering cannot be changed in v1.")
        if len(set(self.supported_compatibility_versions)) != len(
            self.supported_compatibility_versions
        ):
            raise ValueError("Compatibility versions must be unique.")


DEFAULT_PREDICTION_INFERENCE_POLICY = PredictionInferencePolicy()
