from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OfficialPredictionCandidateRegistryPolicy:
    """Structural and security limits for supplied Official candidates."""

    version: str = "official-prediction-candidate-registry-policy-v1"
    maximum_identifier_length: int = 128
    maximum_display_name_length: int = 160
    maximum_model_version_length: int = 96
    maximum_reasoning_fact_count: int = 8
    maximum_reasoning_fact_length: int = 280
    maximum_reasoning_source_length: int = 128
    maximum_total_reasoning_length: int = 1400
    maximum_lifecycle_reason_length: int = 96
    maximum_provenance_item_count: int = 64
    maximum_provenance_value_length: int = 2048

    def __post_init__(self) -> None:
        values = (
            self.maximum_identifier_length,
            self.maximum_display_name_length,
            self.maximum_model_version_length,
            self.maximum_reasoning_fact_count,
            self.maximum_reasoning_fact_length,
            self.maximum_reasoning_source_length,
            self.maximum_total_reasoning_length,
            self.maximum_lifecycle_reason_length,
            self.maximum_provenance_item_count,
            self.maximum_provenance_value_length,
        )
        if not self.version.strip() or any(value <= 0 for value in values):
            raise ValueError("Candidate registry policy limits must be positive.")
        if self.maximum_reasoning_fact_count > 32:
            raise ValueError("Reasoning fact count must remain operationally bounded.")
        if self.maximum_provenance_item_count > 128:
            raise ValueError("Candidate provenance must remain operationally bounded.")


DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY = (
    OfficialPredictionCandidateRegistryPolicy()
)
