"""Central immutable policy for chronology-first dataset splitting."""

from dataclasses import dataclass


SPLIT_POLICY_VERSION = "historical_dataset_split_policy_v1"
METADATA_VERSION = "v1"
EQUAL_KICKOFF_POLICY = "KEEP_TOGETHER_OR_EXCLUDE"


@dataclass(frozen=True, slots=True)
class HistoricalDatasetSplitPolicy:
    version: str = SPLIT_POLICY_VERSION
    default_strategy: str = "EXPLICIT_TIME_BOUNDARIES_V1"
    supported_strategies: tuple[str, ...] = (
        "EXPLICIT_TIME_BOUNDARIES_V1",
        "EXPANDING_WINDOW_V1",
        "RATIO_BY_CHRONOLOGY_V1",
    )
    equal_kickoff_policy: str = EQUAL_KICKOFF_POLICY
    ratio_precision: str = "0.000001"

    def __post_init__(self) -> None:
        if self.default_strategy not in self.supported_strategies:
            raise ValueError("Default split strategy must be supported.")


DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY = HistoricalDatasetSplitPolicy()
