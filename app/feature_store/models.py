from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.match_data_snapshot import MatchDataSnapshotVersion


class FeatureGenerationStatus(str, Enum):
    GENERATED = "GENERATED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_SNAPSHOT = "REJECTED_INVALID_SNAPSHOT"
    REJECTED_UNSUPPORTED_SCHEMA = "REJECTED_UNSUPPORTED_SCHEMA"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class FeatureValueType(str, Enum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    name: str
    value_type: FeatureValueType
    description: str
    source_fields: tuple[str, ...]
    formula_summary: str
    missing_data_behavior: str
    valid_range: tuple[Decimal | None, Decimal | None] | None
    schema_version_introduced: str


@dataclass(frozen=True, slots=True)
class FeatureValue:
    name: str
    value: Decimal | int | bool | None


@dataclass(frozen=True, slots=True)
class DataQualitySummary:
    completeness_score: Decimal
    available_feature_count: int
    missing_feature_count: int
    total_feature_count: int
    source_group_availability: tuple[tuple[str, bool], ...]


@dataclass(frozen=True, slots=True)
class MatchFeatureSet:
    feature_set_id: str
    snapshot_id: str
    match_id: str
    feature_schema_name: str
    feature_schema_version: str
    model_compatibility_version: str
    feature_timestamp: datetime
    ordered_feature_values: tuple[FeatureValue, ...]
    missingness_indicators: tuple[tuple[str, bool], ...]
    data_quality_summary: DataQualitySummary
    source_snapshot_fingerprint: str
    feature_fingerprint: str
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class FeatureGenerationRequest:
    snapshot: MatchDataSnapshotVersion
    schema_version: str
    feature_timestamp: datetime
    historical_replay: bool = False
    model_compatibility_version: str = "official_prediction_model_input_v1"


@dataclass(frozen=True, slots=True)
class FeatureGenerationOutcome:
    status: FeatureGenerationStatus
    feature_set: MatchFeatureSet | None
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
