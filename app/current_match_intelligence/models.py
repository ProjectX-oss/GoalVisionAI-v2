"""Immutable Current Match Intelligence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


SCHEMA_VERSION = "goalvision-current-match-intelligence-v1"
FUTURE_FEATURE_CONTRACT = "goalvision-current-match-intelligence-features-v1"


class DataClass(str, Enum):
    PRE_MATCH_STABLE = "PRE_MATCH_STABLE"
    PRE_MATCH_DYNAMIC = "PRE_MATCH_DYNAMIC"
    LINEUP_SENSITIVE = "LINEUP_SENSITIVE"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    provider: str
    endpoint: str
    retrieved_at: datetime
    provider_timestamp: datetime | None
    fixture_id: str
    team_id: str | None = None
    player_id: str | None = None


@dataclass(frozen=True, slots=True)
class IntelligenceField:
    name: str
    data_class: DataClass
    value: Any
    provenance: tuple[FieldProvenance, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.provenance:
            raise ValueError("Every intelligence field requires provenance.")


@dataclass(frozen=True, slots=True)
class FreshnessEvidence:
    signal: str
    status: FreshnessStatus
    evaluated_at: datetime
    newest_retrieved_at: datetime | None
    expires_at: datetime | None
    policy_seconds: int


@dataclass(frozen=True, slots=True)
class ApiCallEvidence:
    endpoint: str
    query: str
    cache_status: str
    calls_used: int
    required: bool
    outcome: str


@dataclass(frozen=True, slots=True)
class CurrentMatchIntelligenceSnapshot:
    schema_version: str
    snapshot_id: str
    fixture_id: str
    version: int
    kickoff_utc: datetime
    evaluated_at: datetime
    fields: tuple[IntelligenceField, ...]
    freshness: tuple[FreshnessEvidence, ...]
    missing_data: tuple[str, ...]
    blockers: tuple[str, ...]
    api_calls: tuple[ApiCallEvidence, ...]
    content_fingerprint: str

    def field(self, name: str) -> IntelligenceField | None:
        return next((item for item in self.fields if item.name == name), None)


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    snapshot: CurrentMatchIntelligenceSnapshot
    api_calls_used: int
    api_call_limit: int
    cache_hits: int
    cache_misses: int


@dataclass(frozen=True, slots=True)
class FutureFeatureVector:
    contract_version: str
    snapshot_id: str
    ordered_names: tuple[str, ...]
    ordered_values: tuple[Any, ...]
    missing_names: tuple[str, ...]
    fingerprint: str
