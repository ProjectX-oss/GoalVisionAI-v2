"""Immutable split commands, assignments, folds, outcomes, and summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.historical_training_dataset import FEATURE_SCHEMA_VERSION, LABEL_SCHEMA_VERSION

from .policy import EQUAL_KICKOFF_POLICY, METADATA_VERSION, SPLIT_POLICY_VERSION


DecimalInput = Decimal | str | int


class SplitStrategy(str, Enum):
    EXPLICIT_TIME_BOUNDARIES_V1 = "EXPLICIT_TIME_BOUNDARIES_V1"
    EXPANDING_WINDOW_V1 = "EXPANDING_WINDOW_V1"
    RATIO_BY_CHRONOLOGY_V1 = "RATIO_BY_CHRONOLOGY_V1"


class Partition(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    EXCLUDED_GAP = "EXCLUDED_GAP"
    EXCLUDED_FILTER = "EXCLUDED_FILTER"
    EXCLUDED_BOUNDARY_GROUP = "EXCLUDED_BOUNDARY_GROUP"
    EXCLUDED_INVALID_PROVENANCE = "EXCLUDED_INVALID_PROVENANCE"


class DatasetSplitStatus(str, Enum):
    SPLIT_CREATED = "SPLIT_CREATED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    NO_ELIGIBLE_EXAMPLES = "NO_ELIGIBLE_EXAMPLES"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_SOURCE_DATASET = "REJECTED_SOURCE_DATASET"
    REJECTED_CHRONOLOGY = "REJECTED_CHRONOLOGY"
    REJECTED_PARTITION_SIZE = "REJECTED_PARTITION_SIZE"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class ExplicitTimeBoundaries:
    train_end_exclusive: datetime | str
    validation_start_inclusive: datetime | str
    validation_end_exclusive: datetime | str
    test_start_inclusive: datetime | str
    test_end_exclusive: datetime | str | None = None


@dataclass(frozen=True, slots=True)
class RatioByChronology:
    train_ratio: DecimalInput
    validation_ratio: DecimalInput
    test_ratio: DecimalInput


@dataclass(frozen=True, slots=True)
class ExpandingWindow:
    initial_train_end_exclusive: datetime | str
    validation_window_days: int
    test_window_days: int
    step_days: int
    maximum_folds: int


@dataclass(frozen=True, slots=True)
class GapConfiguration:
    train_to_validation_days: int = 0
    validation_to_test_days: int = 0


@dataclass(frozen=True, slots=True)
class MinimumPartitionSizes:
    train: int = 1
    validation: int = 1
    test: int = 1


@dataclass(frozen=True, slots=True)
class DatasetSplitCommand:
    split_request_id: str
    split_name: str
    source_dataset_build_id: str
    source_dataset_fingerprint: str
    strategy: SplitStrategy | str = SplitStrategy.EXPLICIT_TIME_BOUNDARIES_V1
    explicit_boundaries: ExplicitTimeBoundaries | None = None
    ratios: RatioByChronology | None = None
    expanding_window: ExpandingWindow | None = None
    gaps: GapConfiguration = GapConfiguration()
    minimum_partition_sizes: MinimumPartitionSizes = MinimumPartitionSizes()
    equal_kickoff_policy: str = EQUAL_KICKOFF_POLICY
    maximum_folds: int | None = None
    split_timestamp: datetime | str = ""
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    label_schema_version: str = LABEL_SCHEMA_VERSION
    split_policy_version: str = SPLIT_POLICY_VERSION
    metadata_version: str = METADATA_VERSION
    competition_filters: tuple[str, ...] = ()
    season_filters: tuple[str, ...] = ()
    kickoff_lower_bound: datetime | str | None = None
    kickoff_upper_bound: datetime | str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedDatasetSplitCommand:
    split_request_id: str
    split_name: str
    source_dataset_build_id: str
    source_dataset_fingerprint: str
    strategy: SplitStrategy
    explicit_boundaries: tuple[tuple[str, str | None], ...]
    ratios: tuple[tuple[str, Decimal], ...]
    expanding_window: tuple[tuple[str, str | int], ...]
    gaps: GapConfiguration
    minimum_partition_sizes: MinimumPartitionSizes
    equal_kickoff_policy: str
    maximum_folds: int | None
    split_timestamp: str
    feature_schema_version: str
    label_schema_version: str
    split_policy_version: str
    metadata_version: str
    competition_filters: tuple[str, ...]
    season_filters: tuple[str, ...]
    kickoff_lower_bound: str | None
    kickoff_upper_bound: str | None


@dataclass(frozen=True, slots=True)
class PartitionAssignment:
    assignment_id: str
    split_id: str
    fold_id: str
    training_example_id: str
    historical_match_id: str
    kickoff_utc: str
    competition: str
    season: str
    partition: Partition
    assignment_order: int
    example_fingerprint: str
    assignment_fingerprint: str
    exclusion_reason: str | None


@dataclass(frozen=True, slots=True)
class DatasetSplitFold:
    fold_id: str
    split_id: str
    fold_index: int
    fold_fingerprint: str
    train_boundary: tuple[tuple[str, str | None], ...]
    validation_boundary: tuple[tuple[str, str | None], ...]
    test_boundary: tuple[tuple[str, str | None], ...]
    assignments: tuple[PartitionAssignment, ...]
    achieved_counts: tuple[tuple[str, int], ...]
    achieved_ratios: tuple[tuple[str, Decimal], ...]
    earliest_latest_kickoffs: tuple[tuple[str, str | None, str | None], ...]


@dataclass(frozen=True, slots=True)
class PreparedDatasetSplit:
    split_id: str
    command: NormalizedDatasetSplitCommand
    request_fingerprint: str
    split_fingerprint: str
    folds: tuple[DatasetSplitFold, ...]
    aggregate_counts: tuple[tuple[str, int], ...]
    deterministic_split_snapshot: str


@dataclass(frozen=True, slots=True)
class DatasetSplitOutcome:
    status: DatasetSplitStatus
    split_id: str | None
    split_request_id: str
    split_fingerprint: str | None
    source_dataset_build_id: str
    source_dataset_fingerprint: str
    strategy: str
    fold_count: int
    train_count: int
    validation_count: int
    test_count: int
    excluded_gap_count: int
    excluded_filter_count: int
    excluded_boundary_count: int
    excluded_invalid_provenance_count: int
    actual_achieved_ratios: tuple[tuple[str, Decimal], ...]
    earliest_latest_kickoffs: tuple[tuple[str, str | None, str | None], ...]
    ordered_reason_codes: tuple[str, ...]
    policy_version: str
    split_timestamp: str | None


@dataclass(frozen=True, slots=True)
class DatasetSplitSummary:
    split_id: str
    split_name: str
    strategy: str
    fold_count: int
    aggregate_counts: tuple[tuple[str, int], ...]
    source_dataset_build_id: str
    source_dataset_fingerprint: str
