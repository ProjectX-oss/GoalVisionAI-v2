"""Typed source, normalized, and persistence models for historical imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


DecimalInput = Decimal | str | int


class FullTimeResult(str, Enum):
    HOME_WIN = "HOME_WIN"
    DRAW = "DRAW"
    AWAY_WIN = "AWAY_WIN"


class TeamSide(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"


class HistoricalImportStatus(str, Enum):
    IMPORTED = "IMPORTED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True, slots=True)
class HistoricalTeamStatisticsInput:
    possession: DecimalInput | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    expected_goals: DecimalInput | None = None
    corners: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    fouls: int | None = None
    offsides: int | None = None


@dataclass(frozen=True, slots=True)
class HistoricalLineupInput:
    starting_xi: tuple[str, ...]
    substitutes: tuple[str, ...] = ()
    formation: str | None = None


@dataclass(frozen=True, slots=True)
class HistoricalMatchInput:
    source_match_id: str
    competition: str
    season: str
    round: str
    kickoff_utc: datetime | str
    home_team: str
    away_team: str
    full_time_home_score: int
    full_time_away_score: int
    venue: str
    half_time_home_score: int | None = None
    half_time_away_score: int | None = None
    full_time_result: FullTimeResult | str | None = None
    referee: str | None = None
    attendance: int | None = None
    home_statistics: HistoricalTeamStatisticsInput | None = None
    away_statistics: HistoricalTeamStatisticsInput | None = None
    home_lineup: HistoricalLineupInput | None = None
    away_lineup: HistoricalLineupInput | None = None


@dataclass(frozen=True, slots=True)
class HistoricalDataset:
    schema_version: str
    provider: str
    dataset_id: str
    dataset_version: str
    matches: tuple[HistoricalMatchInput, ...]


@dataclass(frozen=True, slots=True)
class NormalizedHistoricalStatistics:
    possession: Decimal | None
    shots: int | None
    shots_on_target: int | None
    expected_goals: Decimal | None
    corners: int | None
    yellow_cards: int | None
    red_cards: int | None
    fouls: int | None
    offsides: int | None


@dataclass(frozen=True, slots=True)
class NormalizedHistoricalLineup:
    starting_xi: tuple[str, ...]
    substitutes: tuple[str, ...]
    formation: str | None


@dataclass(frozen=True, slots=True)
class NormalizedHistoricalMatch:
    source_provider: str
    provider_identity: str
    source_match_id: str
    competition: str
    competition_identity: str
    season: str
    round: str
    kickoff_utc: str
    home_team: str
    home_team_identity: str
    away_team: str
    away_team_identity: str
    full_time_home_score: int
    full_time_away_score: int
    half_time_home_score: int | None
    half_time_away_score: int | None
    full_time_result: FullTimeResult
    venue: str
    referee: str | None
    attendance: int | None
    home_statistics: NormalizedHistoricalStatistics | None
    away_statistics: NormalizedHistoricalStatistics | None
    home_lineup: NormalizedHistoricalLineup | None
    away_lineup: NormalizedHistoricalLineup | None


@dataclass(frozen=True, slots=True)
class PreparedHistoricalMatch:
    match: NormalizedHistoricalMatch
    logical_identity_fingerprint: str
    natural_identity_fingerprint: str
    match_fingerprint: str
    normalized_match_snapshot: str


@dataclass(frozen=True, slots=True)
class PreparedHistoricalDataset:
    schema_version: str
    provider: str
    provider_identity: str
    dataset_id: str
    dataset_version: str
    import_timestamp: str
    matches: tuple[PreparedHistoricalMatch, ...]
    dataset_content_fingerprint: str
    dataset_fingerprint: str
    match_fingerprint_snapshot: str
    deterministic_dataset_snapshot: str
    policy_version: str
    metadata_version: str


@dataclass(frozen=True, slots=True)
class HistoricalImportResult:
    import_id: str
    status: HistoricalImportStatus
    provider: str
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    supplied_match_count: int
    inserted_match_count: int
    reused_match_count: int
    historical_match_ids: tuple[str, ...]
    import_timestamp: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class StoredHistoricalMatch:
    historical_match_id: str
    import_id: str
    logical_identity_fingerprint: str
    match_fingerprint: str
    match_version: int
    source_provider: str
    source_match_id: str
    competition: str
    season: str
    round: str
    kickoff_utc: str
    home_team: str
    away_team: str
    full_time_home_score: int
    full_time_away_score: int
    full_time_result: FullTimeResult


@dataclass(frozen=True, slots=True)
class StoredHistoricalStatistics:
    historical_match_id: str
    team_side: TeamSide
    statistics: NormalizedHistoricalStatistics
    statistics_fingerprint: str


@dataclass(frozen=True, slots=True)
class StoredHistoricalLineup:
    historical_match_id: str
    team_side: TeamSide
    lineup: NormalizedHistoricalLineup
    lineup_fingerprint: str
