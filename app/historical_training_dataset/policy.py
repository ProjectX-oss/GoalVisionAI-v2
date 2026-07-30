"""Central immutable policy for historical training dataset v1."""

from dataclasses import dataclass


FEATURE_SCHEMA_VERSION = "historical_training_features_v1"
LABEL_SCHEMA_VERSION = "historical_training_labels_v1"
DATASET_POLICY_VERSION = "historical_training_dataset_policy_v1"
METADATA_VERSION = "v1"
CUTOFF_POLICY = "STRICTLY_BEFORE_KICKOFF"


@dataclass(frozen=True, slots=True)
class HistoricalTrainingDatasetPolicy:
    version: str = DATASET_POLICY_VERSION
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    label_schema_version: str = LABEL_SCHEMA_VERSION
    cutoff_policy: str = CUTOFF_POLICY
    minimum_prior_matches_per_team: int = 3
    rolling_windows: tuple[int, ...] = (3, 5, 10)
    head_to_head_window: int = 5
    calculation_precision: str = "0.000001"
    neutral_venue_indicator: bool | None = None

    def __post_init__(self) -> None:
        if self.minimum_prior_matches_per_team < 1:
            raise ValueError("Minimum prior matches must be positive.")
        if self.rolling_windows != tuple(sorted(set(self.rolling_windows))):
            raise ValueError("Rolling windows must be unique and ordered.")
        if any(window < 1 for window in self.rolling_windows):
            raise ValueError("Rolling windows must be positive.")
        if self.head_to_head_window < 1:
            raise ValueError("Head-to-head window must be positive.")


DEFAULT_HISTORICAL_TRAINING_POLICY = HistoricalTrainingDatasetPolicy()

LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY = HistoricalTrainingDatasetPolicy(
    version="historical_live_model_input_dataset_policy_v1",
    feature_schema_version="v1",
    neutral_venue_indicator=False,
)
