from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN


@dataclass(frozen=True, slots=True)
class FeatureStorePolicy:
    schema_name: str = "official_prematch_features"
    schema_version: str = "v1"
    schema_identifier: str = "official_prematch_features_v1"
    model_compatibility_version: str = "official_prediction_model_input_v1"
    decimal_quantum: Decimal = Decimal("0.000001")
    rounding: str = ROUND_HALF_EVEN

    def __post_init__(self) -> None:
        if not all((self.schema_name, self.schema_version, self.schema_identifier, self.model_compatibility_version)):
            raise ValueError("Feature schema identifiers are required.")
        if self.decimal_quantum <= 0:
            raise ValueError("Feature Decimal quantum must be positive.")

    def supports(self, value: str) -> bool:
        return value in {self.schema_version, self.schema_identifier}


DEFAULT_FEATURE_STORE_POLICY = FeatureStorePolicy()
