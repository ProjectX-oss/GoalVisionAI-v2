"""Deterministic chronology-safe historical dataset splitting."""

from .builder import HistoricalDatasetSplitter, create_historical_dataset_split
from .chronology import (
    assert_fold_safe, example_order_key, group_equal_kickoffs,
    verify_equal_kickoff_assignments, verify_fold_chronology, verify_fold_exclusivity,
)
from .exceptions import (
    DatasetSplitConflictError, DatasetSplitPersistenceError, HistoricalDatasetSplitError,
    SourceDatasetVerificationError, SplitChronologyError, SplitPartitionSizeError,
    SplitRequestValidationError,
)
from .factory import build_historical_dataset_split_service
from .inspection import (
    inspect_partition_assignment, inspect_split_fold, summarize_dataset_split,
    summarize_partition_labels, verify_equal_kickoff_grouping,
    verify_partition_chronology, verify_partition_exclusivity,
    verify_source_dataset_linkage, verify_split_fingerprints,
)
from .models import (
    DatasetSplitCommand, DatasetSplitFold, DatasetSplitOutcome, DatasetSplitStatus,
    DatasetSplitSummary, ExpandingWindow, ExplicitTimeBoundaries, GapConfiguration,
    MinimumPartitionSizes, Partition, PartitionAssignment, PreparedDatasetSplit,
    RatioByChronology, SplitStrategy,
)
from .policy import (
    DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY, EQUAL_KICKOFF_POLICY, METADATA_VERSION,
    SPLIT_POLICY_VERSION, HistoricalDatasetSplitPolicy,
)
from .repository import SQLiteHistoricalDatasetSplitRepository

__all__ = [
    "DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY", "DatasetSplitCommand",
    "DatasetSplitConflictError", "DatasetSplitFold", "DatasetSplitOutcome",
    "DatasetSplitPersistenceError", "DatasetSplitStatus", "DatasetSplitSummary",
    "EQUAL_KICKOFF_POLICY", "ExpandingWindow", "ExplicitTimeBoundaries",
    "GapConfiguration", "HistoricalDatasetSplitError", "HistoricalDatasetSplitPolicy",
    "HistoricalDatasetSplitter", "METADATA_VERSION", "MinimumPartitionSizes", "Partition",
    "PartitionAssignment", "PreparedDatasetSplit", "RatioByChronology", "SPLIT_POLICY_VERSION",
    "SQLiteHistoricalDatasetSplitRepository", "SourceDatasetVerificationError",
    "SplitChronologyError", "SplitPartitionSizeError", "SplitRequestValidationError",
    "SplitStrategy", "assert_fold_safe", "build_historical_dataset_split_service",
    "create_historical_dataset_split", "example_order_key", "group_equal_kickoffs",
    "inspect_partition_assignment", "inspect_split_fold", "summarize_dataset_split",
    "summarize_partition_labels", "verify_equal_kickoff_assignments",
    "verify_equal_kickoff_grouping", "verify_fold_chronology", "verify_fold_exclusivity",
    "verify_partition_chronology", "verify_partition_exclusivity",
    "verify_source_dataset_linkage", "verify_split_fingerprints",
]
