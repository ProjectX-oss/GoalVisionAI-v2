from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class MatchSnapshotStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    LIVE = "LIVE"


class SnapshotLifecycleState(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    INVALIDATED = "INVALIDATED"


class SnapshotRegistrationStatus(str, Enum):
    REGISTERED = "REGISTERED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    SUPERSEDED_PREVIOUS = "SUPERSEDED_PREVIOUS"
    REJECTED_INVALID = "REJECTED_INVALID"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class SnapshotLifecycleResultStatus(str, Enum):
    APPLIED = "APPLIED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class FormRecord:
    match_count: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    clean_sheets: int
    failed_to_score: int
    expected_goals_for: Decimal | None = None
    expected_goals_against: Decimal | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    possession: Decimal | None = None


@dataclass(frozen=True, slots=True)
class VenueSplitRecord:
    match_count: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    clean_sheets: int
    failed_to_score: int
    expected_goals_for: Decimal | None = None
    expected_goals_against: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AggregateRecord:
    match_count: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int


@dataclass(frozen=True, slots=True)
class SeasonAggregateRecord:
    matches_played: int
    points: int
    goals_scored: int
    goals_conceded: int
    league_position: int | None = None
    expected_goals_for: Decimal | None = None
    expected_goals_against: Decimal | None = None
    home_record: AggregateRecord | None = None
    away_record: AggregateRecord | None = None


@dataclass(frozen=True, slots=True)
class HeadToHeadRecord:
    match_count: int
    home_team_wins: int
    draws: int
    away_team_wins: int
    total_goals: int
    both_teams_to_score_count: int
    over_2_5_count: int
    most_recent_match_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class TeamAvailabilityRecord:
    confirmed_lineup: bool | None
    probable_lineup: bool | None
    injuries_count: int | None
    suspensions_count: int | None
    missing_key_players_count: int | None
    goalkeeper_availability_status: str | None = None
    lineup_source_timestamp: datetime | None = None
    injury_source_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class MatchContextRecord:
    home_rest_days: int | None = None
    away_rest_days: int | None = None
    home_travel_distance: Decimal | None = None
    away_travel_distance: Decimal | None = None
    home_fixture_congestion_count: int | None = None
    away_fixture_congestion_count: int | None = None
    competition_stage: str | None = None
    derby_indicator: bool | None = None
    weather_summary: str | None = None
    pitch_status: str | None = None


@dataclass(frozen=True, slots=True)
class OddsContextRecord:
    source_identifier: str
    market_type: str
    selection: str
    market_line: Decimal | None
    decimal_odds: Decimal
    odds_timestamp: datetime


@dataclass(frozen=True, slots=True)
class MatchDataSnapshotRegistrationCommand:
    source_provider: str
    source_event_id: str
    source_snapshot_id: str
    match_id: str
    competition_id: str | None
    competition_name: str
    season_identifier: str
    home_team_id: str | None
    home_team_name: str
    away_team_id: str | None
    away_team_name: str
    kickoff_timestamp: datetime
    snapshot_effective_timestamp: datetime
    source_updated_timestamp: datetime
    registration_timestamp: datetime
    scheduled_status: MatchSnapshotStatus | str
    postponed_indicator: bool
    cancelled_indicator: bool
    neutral_venue_indicator: bool
    venue: str | None = None
    home_recent_form: FormRecord | None = None
    away_recent_form: FormRecord | None = None
    home_venue_split: VenueSplitRecord | None = None
    away_venue_split: VenueSplitRecord | None = None
    home_season_aggregate: SeasonAggregateRecord | None = None
    away_season_aggregate: SeasonAggregateRecord | None = None
    head_to_head: HeadToHeadRecord | None = None
    home_availability: TeamAvailabilityRecord | None = None
    away_availability: TeamAvailabilityRecord | None = None
    context: MatchContextRecord | None = None
    odds_snapshot: OddsContextRecord | None = None
    is_live: bool = False


@dataclass(frozen=True, slots=True)
class PreparedMatchDataSnapshot:
    logical_identity_fingerprint: str
    content_fingerprint: str
    command: MatchDataSnapshotRegistrationCommand
    deterministic_snapshot: str


@dataclass(frozen=True, slots=True)
class MatchDataSnapshotVersion:
    snapshot_id: str
    snapshot_version: int
    prepared: PreparedMatchDataSnapshot
    lifecycle_state_at_creation: SnapshotLifecycleState = SnapshotLifecycleState.ACTIVE

    @property
    def match_id(self) -> str:
        return self.prepared.command.match_id

    @property
    def content_fingerprint(self) -> str:
        return self.prepared.content_fingerprint

    @property
    def logical_identity_fingerprint(self) -> str:
        return self.prepared.logical_identity_fingerprint


@dataclass(frozen=True, slots=True)
class SnapshotVersionRegistration:
    snapshot: MatchDataSnapshotVersion
    previous_snapshot: MatchDataSnapshotVersion | None
    identical_existing: bool


@dataclass(frozen=True, slots=True)
class MatchDataSnapshotRegistrationOutcome:
    snapshot_id: str | None
    match_id: str
    logical_identity_fingerprint: str | None
    content_fingerprint: str | None
    version: int | None
    status: SnapshotRegistrationStatus
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    previous_snapshot_id: str | None
    effective_timestamp: datetime
    registration_timestamp: datetime


@dataclass(frozen=True, slots=True)
class SnapshotLifecycleEvent:
    event_id: str
    snapshot_id: str
    event_sequence: int
    event_type: SnapshotLifecycleState
    reason_code: str
    previous_snapshot_id: str | None
    event_timestamp: datetime
    event_snapshot: str


@dataclass(frozen=True, slots=True)
class SnapshotLifecycleOutcome:
    snapshot_id: str
    state: SnapshotLifecycleState | None
    status: SnapshotLifecycleResultStatus
    reason_code: str
    event_timestamp: datetime
