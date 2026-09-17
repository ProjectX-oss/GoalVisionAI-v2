"""Immutable commands, source facts, examples, outcomes, and inspection models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Iterator

from app.historical_data_import import NormalizedHistoricalStatistics

from .policy import (
    CUTOFF_POLICY,
    DATASET_POLICY_VERSION,
    FEATURE_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    METADATA_VERSION,
)


FeatureScalar = Decimal | int | None


class DatasetBuildStatus(str, Enum):
    DATASET_BUILT = "DATASET_BUILT"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    NO_ELIGIBLE_MATCHES = "NO_ELIGIBLE_MATCHES"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_SOURCE_PROVENANCE = "REJECTED_SOURCE_PROVENANCE"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class ExclusionReason(str, Enum):
    INSUFFICIENT_HISTORY = "EXCLUDED_INSUFFICIENT_HISTORY"
    INVALID_PROVENANCE = "EXCLUDED_INVALID_PROVENANCE"


class LeakageReason(str, Enum):
    SOURCE_TIMESTAMP_MISSING = "LEAKAGE_SOURCE_TIMESTAMP_MISSING"
    SOURCE_NOT_STRICTLY_EARLIER = "LEAKAGE_SOURCE_NOT_STRICTLY_EARLIER"
    SOURCE_AFTER_TARGET = "LEAKAGE_SOURCE_AFTER_TARGET"
    SOURCE_EQUALS_TARGET_KICKOFF = "LEAKAGE_SOURCE_EQUALS_TARGET_KICKOFF"
    TARGET_AS_SOURCE = "LEAKAGE_TARGET_AS_SOURCE"
    SOURCE_FINGERPRINT_MISMATCH = "LEAKAGE_SOURCE_FINGERPRINT_MISMATCH"


class FeatureDataType(str, Enum):
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"


@dataclass(frozen=True, slots=True)
class HistoricalFeatureDefinition:
    index: int
    name: str
    data_type: FeatureDataType
    semantic_definition: str
    source_window: str
    missingness_rule: str
    leakage_classification: str


@dataclass(frozen=True, slots=True)
class DatasetBuildCommand:
    request_id: str
    dataset_name: str
    source_import_ids: tuple[str, ...]
    competition_filters: tuple[str, ...] = ()
    season_filters: tuple[str, ...] = ()
    kickoff_lower_bound: datetime | str | None = None
    kickoff_upper_bound: datetime | str | None = None
    cutoff_policy: str = CUTOFF_POLICY
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    label_schema_version: str = LABEL_SCHEMA_VERSION
    dataset_policy_version: str = DATASET_POLICY_VERSION
    build_timestamp: datetime | str = ""
    metadata_version: str = METADATA_VERSION


@dataclass(frozen=True, slots=True)
class NormalizedDatasetBuildCommand:
    request_id: str
    dataset_name: str
    source_import_ids: tuple[str, ...]
    competition_filters: tuple[str, ...]
    season_filters: tuple[str, ...]
    kickoff_lower_bound: str | None
    kickoff_upper_bound: str | None
    cutoff_policy: str
    feature_schema_version: str
    label_schema_version: str
    dataset_policy_version: str
    build_timestamp: str
    metadata_version: str


@dataclass(frozen=True, slots=True)
class HistoricalSourceMatch:
    historical_match_id: str
    import_ids: tuple[str, ...]
    match_fingerprint: str
    competition: str
    competition_identity: str
    season: str
    kickoff_utc: str
    home_team_identity: str
    away_team_identity: str
    full_time_home_score: int
    full_time_away_score: int
    home_statistics: NormalizedHistoricalStatistics | None = None
    away_statistics: NormalizedHistoricalStatistics | None = None


@dataclass(frozen=True, slots=True)
class TrainingExampleSource:
    source_historical_match_id: str
    source_match_fingerprint: str
    source_kickoff: str
    source_role: str
    deterministic_order_index: int
    lookback_window_identity: str


@dataclass(frozen=True, slots=True)
class HistoricalTrainingExample:
    training_example_id: str
    dataset_build_id: str
    historical_match_id: str
    historical_match_fingerprint: str
    competition: str
    season: str
    kickoff_utc: str
    home_team_identity: str
    away_team_identity: str
    ordered_feature_vector: tuple[FeatureScalar, ...]
    missingness_mask: tuple[bool, ...]
    completeness_score: Decimal
    feature_provenance: tuple[tuple[str, str], ...]
    lookback_window_identity: str
    cutoff_timestamp: str
    historical_source_fingerprints: tuple[str, ...]
    labels: tuple[tuple[str, int], ...]
    feature_schema_version: str
    label_schema_version: str
    policy_version: str
    example_fingerprint: str
    sources: tuple[TrainingExampleSource, ...]


@dataclass(frozen=True, slots=True)
class HistoricalTrainingExclusion:
    historical_match_id: str
    reason: ExclusionReason
    ordered_reason_codes: tuple[str, ...]
    detail: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PreparedDatasetBuild:
    dataset_build_id: str
    command: NormalizedDatasetBuildCommand
    request_fingerprint: str
    dataset_fingerprint: str
    source_match_count: int
    examples: tuple[HistoricalTrainingExample, ...]
    exclusions: tuple[HistoricalTrainingExclusion, ...]
    deterministic_build_snapshot: str


@dataclass(frozen=True, slots=True)
class DatasetBuildOutcome:
    status: DatasetBuildStatus
    dataset_build_id: str | None
    request_id: str
    dataset_fingerprint: str | None
    source_import_ids: tuple[str, ...]
    total_source_matches: int
    included_examples: int
    excluded_insufficient_history_count: int
    excluded_invalid_provenance_count: int
    feature_schema_version: str
    label_schema_version: str
    policy_version: str
    ordered_reason_codes: tuple[str, ...]
    build_timestamp: str | None


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    dataset_build_id: str
    dataset_name: str
    source_match_count: int
    included_count: int
    excluded_count: int
    completeness_minimum: Decimal | None
    completeness_average: Decimal | None
    completeness_maximum: Decimal | None
    positive_label_counts: tuple[tuple[str, int], ...]


ExampleIterator = Iterator[HistoricalTrainingExample]
