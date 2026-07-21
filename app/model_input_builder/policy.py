from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN


@dataclass(frozen=True, slots=True)
class ModelInputBuilderPolicy:
    schema_name: str = "goalvision_model_input"
    schema_version: str = "v1"
    schema_identifier: str = "goalvision_model_input_v1"
    compatibility_version: str = "official_prediction_model_input_v1"
    source_feature_schema_name: str = "official_prematch_features"
    source_feature_schema_version: str = "v1"
    decimal_quantum: Decimal = Decimal("0.000001")
    rounding: str = ROUND_HALF_EVEN

    def __post_init__(self) -> None:
        identifiers = (
            self.schema_name,
            self.schema_version,
            self.schema_identifier,
            self.compatibility_version,
            self.source_feature_schema_name,
            self.source_feature_schema_version,
        )
        if any(not value.strip() for value in identifiers):
            raise ValueError("Model-input schema identifiers are required.")
        if self.decimal_quantum <= 0:
            raise ValueError("Model-input Decimal quantum must be positive.")


DEFAULT_MODEL_INPUT_BUILDER_POLICY = ModelInputBuilderPolicy()
