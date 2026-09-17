from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class FixtureTeamSide(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"


class PlayerAvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DOUBTFUL = "DOUBTFUL"
    SUSPENDED = "SUSPENDED"
    INJURED = "INJURED"
    ILL = "ILL"
    RESTED = "RESTED"
    NOT_SELECTED = "NOT_SELECTED"
    UNKNOWN = "UNKNOWN"


class AvailabilityReason(str, Enum):
    NONE = "NONE"
    INJURY = "INJURY"
    SUSPENSION = "SUSPENSION"
    ILLNESS = "ILLNESS"
    FITNESS = "FITNESS"
    REST = "REST"
    SELECTION = "SELECTION"
    PERSONAL = "PERSONAL"
    UNKNOWN = "UNKNOWN"


class LineupStatus(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    PREDICTED = "PREDICTED"
    PARTIAL = "PARTIAL"
    CONFIRMED = "CONFIRMED"


class LineupType(str, Enum):
    STARTING = "STARTING"
    SUBSTITUTE = "SUBSTITUTE"
    SQUAD = "SQUAD"


class AvailabilityEvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AvailabilityErrorCode(str, Enum):
    INVALID_FIXTURE = "INVALID_FIXTURE"
    INVALID_TEAM = "INVALID_TEAM"
    INVALID_PLAYER = "INVALID_PLAYER"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    AFTER_KICKOFF = "AFTER_KICKOFF"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    DISABLED_SOURCE = "DISABLED_SOURCE"
    INVALID_STATUS = "INVALID_STATUS"
    INVALID_LINEUP = "INVALID_LINEUP"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    MALFORMED_PROVIDER_RECORD = "MALFORMED_PROVIDER_RECORD"


class AvailabilityReliability(str, Enum):
    RELIABLE = "RELIABLE"
    UNVERIFIED = "UNVERIFIED"
    DEGRADED = "DEGRADED"


class PublicationStage(str, Enum):
    EARLY_PREMATCH = "EARLY_PREMATCH"
    PRE_LINEUP = "PRE_LINEUP"
    POST_LINEUP = "POST_LINEUP"
    FINAL_PRE_KICKOFF = "FINAL_PRE_KICKOFF"


@dataclass(frozen=True, slots=True)
class PlayerIdentity:
    player_id: str | None
    player_name: str

    def __post_init__(self) -> None:
        if self.player_id is not None and not self.player_id.strip():
            raise ValueError("Player ID must not be blank.")
        if not self.player_name.strip() and self.player_id is None:
            raise ValueError("Player identity requires an ID or usable name.")

    @property
    def identity_key(self) -> str:
        return f"id:{self.player_id}" if self.player_id else f"name:{self.player_name}"


@dataclass(frozen=True, slots=True)
class TeamIdentity:
    team_id: str
    team_name: str

    def __post_init__(self) -> None:
        if not self.team_id.strip() or not self.team_name.strip():
            raise ValueError("Team identity must contain ID and name.")


@dataclass(frozen=True, slots=True)
class AvailabilitySource:
    source_id: str
    source_name: str
    priority: int
    reliability: AvailabilityReliability
    enabled: bool

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.source_name.strip():
            raise ValueError("Availability source identity must not be empty.")
        if type(self.priority) is not int or self.priority < 0:
            raise ValueError("Availability source priority must be non-negative.")


@dataclass(frozen=True, slots=True)
class PlayerAvailabilityObservation:
    observation_id: str
    fixture_id: str
    competition: str
    team: TeamIdentity
    player: PlayerIdentity
    fixture_team_side: FixtureTeamSide
    availability_status: PlayerAvailabilityStatus
    reason: AvailabilityReason
    provider_reason_text: str | None
    observed_at: datetime
    source_name: str
    source_reference: str
    expected_return_at: datetime | None
    confidence: Decimal | None
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.observation_id, "Observation ID"),
            (self.fixture_id, "Fixture ID"),
            (self.competition, "Competition"),
            (self.source_name, "Source name"),
            (self.source_reference, "Source reference"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must not be empty.")
        _aware(self.observed_at, "Observed timestamp")
        _aware(self.created_at, "Created timestamp")
        if self.expected_return_at is not None:
            _aware(self.expected_return_at, "Expected return timestamp")
        if self.confidence is not None and (
            not self.confidence.is_finite()
            or not Decimal("0") <= self.confidence <= Decimal("1")
        ):
            raise ValueError("Availability confidence must be in [0, 1].")


@dataclass(frozen=True, slots=True)
class LineupPlayer:
    player: PlayerIdentity
    role: str
    position: str
    shirt_number: int | None
    is_starting: bool
    is_captain: bool | None
    is_goalkeeper: bool
    source_order: int

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.position.strip():
            raise ValueError("Lineup player role and position must not be empty.")
        if self.shirt_number is not None and self.shirt_number <= 0:
            raise ValueError("Shirt number must be positive.")
        if type(self.source_order) is not int or self.source_order < 0:
            raise ValueError("Source order must be non-negative.")


@dataclass(frozen=True, slots=True)
class LineupObservation:
    lineup_observation_id: str
    fixture_id: str
    competition: str
    team: TeamIdentity
    fixture_team_side: FixtureTeamSide
    lineup_status: LineupStatus
    lineup_type: LineupType
    observed_at: datetime
    source_name: str
    source_reference: str
    formation: str | None
    players: tuple[LineupPlayer, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.lineup_observation_id.strip() or not self.fixture_id.strip():
            raise ValueError("Lineup observation identity must not be empty.")
        if not self.competition.strip() or not self.source_name.strip():
            raise ValueError("Lineup competition and source must not be empty.")
        if not self.source_reference.strip():
            raise ValueError("Lineup source reference must not be empty.")
        _aware(self.observed_at, "Lineup observed timestamp")
        _aware(self.created_at, "Lineup created timestamp")
        if self.lineup_status is LineupStatus.NOT_AVAILABLE and self.players:
            raise ValueError("Unavailable lineups cannot contain players.")
        identities = tuple(item.player.identity_key for item in self.players)
        if len(set(identities)) != len(identities):
            raise ValueError("A lineup cannot contain duplicate players.")


@dataclass(frozen=True, slots=True)
class FormationObservation:
    fixture_id: str
    team: TeamIdentity
    formation: str
    observed_at: datetime
    source_name: str


@dataclass(frozen=True, slots=True)
class CoachObservation:
    fixture_id: str
    team: TeamIdentity
    coach_id: str | None
    coach_name: str
    observed_at: datetime
    source_name: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class AvailabilityConflict:
    player: PlayerIdentity
    statuses: tuple[PlayerAvailabilityStatus, ...]
    observation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeamAvailabilitySnapshot:
    fixture_id: str
    team: TeamIdentity
    evaluation_timestamp: datetime
    kickoff: datetime
    latest_lineup_status: LineupStatus
    lineup_observed_at: datetime | None
    formation: str | None
    confirmed_starters: tuple[LineupPlayer, ...]
    predicted_starters: tuple[LineupPlayer, ...]
    substitutes: tuple[LineupPlayer, ...]
    unavailable_players: tuple[PlayerIdentity, ...]
    injured_players: tuple[PlayerIdentity, ...]
    suspended_players: tuple[PlayerIdentity, ...]
    doubtful_players: tuple[PlayerIdentity, ...]
    unknown_status_players: tuple[PlayerIdentity, ...]
    lineup_evidence_status: AvailabilityEvidenceStatus
    injury_evidence_status: AvailabilityEvidenceStatus
    data_freshness: AvailabilityEvidenceStatus
    data_completeness: AvailabilityEvidenceStatus
    source_count: int
    conflicts: tuple[AvailabilityConflict, ...]
    snapshot_timestamp: datetime

    def __post_init__(self) -> None:
        _aware(self.evaluation_timestamp, "Evaluation timestamp")
        _aware(self.kickoff, "Kickoff timestamp")
        _aware(self.snapshot_timestamp, "Snapshot timestamp")


@dataclass(frozen=True, slots=True)
class AvailabilityError:
    source: str
    fixture_id: str
    team_id: str
    player_reference: str
    code: AvailabilityErrorCode
    safe_message: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "Error timestamp")
        if not self.safe_message.strip():
            raise ValueError("Availability errors require a safe message.")


@dataclass(frozen=True, slots=True)
class AvailabilityIngestionReport:
    records_received: int
    records_inserted: int
    duplicate_records: int
    rejected_records: int
    fixtures_processed: tuple[str, ...]
    teams_processed: tuple[str, ...]
    sources_processed: tuple[str, ...]
    observation_time_range: tuple[datetime, datetime] | None
    ordered_errors: tuple[AvailabilityError, ...]


@dataclass(frozen=True, slots=True)
class PlayerImportanceInput:
    player: PlayerIdentity
    recent_minutes: Decimal | None
    recent_starts: int | None
    position: str
    is_goalkeeper: bool
    is_captain: bool | None
    provider_rating: Decimal | None
    internal_strength: Decimal | None


@dataclass(frozen=True, slots=True)
class PlayerImpactEstimate:
    player: PlayerIdentity
    score: Decimal | None
    available: bool
    reason: str


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
