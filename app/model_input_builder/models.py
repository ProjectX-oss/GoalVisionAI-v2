from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.feature_store import FeatureValueType, MatchFeatureSet


class ModelInputGenerationStatus(str, Enum):
    GENERATED = "GENERATED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID = "REJECTED_INVALID"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class ModelInputFeatureMetadata:
    index: int
    name: str
    value_type: FeatureValueType
    description: str
    required_baseline: bool
    source_feature_schema: str


@dataclass(frozen=True, slots=True)
class ModelInputSchema:
    name: str
    version: str
    identifier: str
    compatibility_version: str
    source_feature_schema_name: str
    source_feature_schema_version: str
    ordered_feature_metadata: tuple[ModelInputFeatureMetadata, ...]

    @property
    def ordered_feature_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.ordered_feature_metadata)


@dataclass(frozen=True, slots=True)
class PreparedModelInputVector:
    source_feature_set: MatchFeatureSet
    schema: ModelInputSchema
    ordered_feature_names: tuple[str, ...]
    ordered_feature_values: tuple[Decimal | int | bool | None, ...]
    missingness_mask: tuple[bool, ...]
    missing_feature_names: tuple[str, ...]
    completeness_score: Decimal
    feature_metadata: tuple[ModelInputFeatureMetadata, ...]
    feature_fingerprint: str
    source_snapshot_fingerprint: str
    source_feature_fingerprint: str
    model_input_fingerprint: str


@dataclass(frozen=True, slots=True)
class ModelInputVector:
    model_input_id: str
    feature_set_id: str
    snapshot_id: str
    match_id: str
    schema_name: str
    schema_version: str
    compatibility_version: str
    ordered_feature_names: tuple[str, ...]
    ordered_feature_values: tuple[Decimal | int | bool | None, ...]
    missingness_mask: tuple[bool, ...]
    missing_feature_names: tuple[str, ...]
    completeness_score: Decimal
    feature_metadata: tuple[ModelInputFeatureMetadata, ...]
    feature_fingerprint: str
    source_snapshot_fingerprint: str
    source_feature_fingerprint: str
    model_input_fingerprint: str
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class ModelInputGenerationOutcome:
    status: ModelInputGenerationStatus
    model_input: ModelInputVector | None
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistedSourceFeatureIdentity:
    feature_set_id: str
    snapshot_id: str
    match_id: str
    feature_schema_name: str
    feature_schema_version: str
    compatibility_version: str
    source_snapshot_fingerprint: str
    feature_fingerprint: str
    created_timestamp: datetime
