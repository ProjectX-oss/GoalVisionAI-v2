"""Central immutable policy for the manual Official publication pipeline."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OfficialPredictionPipelinePolicy:
    version: str = "official-prediction-pipeline-policy-v1"
    minimum_odds: Decimal = Decimal("1.60")
    minimum_expected_value: Decimal = Decimal("0.02")
    metadata_version: str = "v1"
    maximum_metadata_items: int = 24
    maximum_batch_size: int = 20
    scheduling_enabled: bool = False
    startup_execution_enabled: bool = False
    automatic_retry_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.version.strip() or self.version != "official-prediction-pipeline-policy-v1":
            raise ValueError("Unsupported Official pipeline policy version.")
        if self.minimum_odds != Decimal("1.60") or self.minimum_expected_value != Decimal("0.02"):
            raise ValueError("Official v1 odds and EV guardrails cannot be changed here.")
        if not self.metadata_version.strip() or self.maximum_metadata_items <= 0:
            raise ValueError("Pipeline metadata policy is invalid.")
        if self.maximum_batch_size <= 0:
            raise ValueError("Pipeline batch bound must be positive.")
        if self.scheduling_enabled or self.startup_execution_enabled or self.automatic_retry_enabled:
            raise ValueError("Scheduling, startup execution, and automatic retry are forbidden.")


DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY = OfficialPredictionPipelinePolicy()
