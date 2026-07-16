from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class OddsSourceType(str, Enum):
    BOOKMAKER = "BOOKMAKER"
    EXCHANGE = "EXCHANGE"
    AGGREGATOR = "AGGREGATOR"
    INTERNAL = "INTERNAL"
    TEST = "TEST"


class OddsReliability(str, Enum):
    RELIABLE = "RELIABLE"
    UNVERIFIED = "UNVERIFIED"
    DEGRADED = "DEGRADED"


class OddsMarket(str, Enum):
    MATCH_WINNER = "MATCH_WINNER"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    DRAW_NO_BET = "DRAW_NO_BET"
    OVER_UNDER_GOALS = "OVER_UNDER_GOALS"
    BTTS = "BTTS"
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    TEAM_TOTAL = "TEAM_TOTAL"
    CORRECT_SCORE = "CORRECT_SCORE"
    OTHER = "OTHER"


class OddsObservationRole(str, Enum):
    OPENING = "OPENING"
    REFERENCE = "REFERENCE"
    PUBLICATION = "PUBLICATION"
    PRE_KICKOFF = "PRE_KICKOFF"
    CLOSING = "CLOSING"


class OddsErrorCode(str, Enum):
    INVALID_ODDS = "INVALID_ODDS"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    AFTER_KICKOFF = "AFTER_KICKOFF"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    DISABLED_SOURCE = "DISABLED_SOURCE"
    INVALID_COMMISSION = "INVALID_COMMISSION"
    INCOMPLETE_MARKET = "INCOMPLETE_MARKET"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    CLOSING_ODDS_UNAVAILABLE = "CLOSING_ODDS_UNAVAILABLE"


class ConsensusCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CLVClassification(str, Enum):
    POSITIVE = "POSITIVE"
    ZERO = "ZERO"
    NEGATIVE = "NEGATIVE"
    UNAVAILABLE = "UNAVAILABLE"


class ClosingSelectionPath(str, Enum):
    PREFERRED_EXCHANGE = "PREFERRED_EXCHANGE"
    WEIGHTED_CONSENSUS = "WEIGHTED_CONSENSUS"
    PRIORITY_BOOKMAKER = "PRIORITY_BOOKMAKER"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class OddsSource:
    source_id: str
    source_name: str
    source_type: OddsSourceType
    priority: int
    reliability: OddsReliability
    commission_applies: bool
    default_commission: Decimal | None
    enabled: bool

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.source_name.strip():
            raise ValueError("Odds source identifiers must not be empty.")
        if type(self.priority) is not int or self.priority < 0:
            raise ValueError("Odds source priority must be a non-negative integer.")
        if self.default_commission is not None:
            _commission(self.default_commission)


@dataclass(frozen=True, slots=True)
class OddsSelection:
    selection_id: str
    name: str
    line: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.selection_id.strip() or not self.name.strip():
            raise ValueError("Odds selection identity must not be empty.")
        if self.line is not None and not self.line.is_finite():
            raise ValueError("Selection line must be finite.")


@dataclass(frozen=True, slots=True)
class OddsObservation:
    observation_id: str
    fixture_id: str
    competition: str
    kickoff_time: datetime
    observed_at: datetime
    source_name: str
    source_type: OddsSourceType
    bookmaker_or_exchange: str
    market: OddsMarket
    selection: OddsSelection
    decimal_odds: Decimal
    created_at: datetime
    available_limit: Decimal | None = None
    currency: str | None = None
    is_exchange: bool = False
    commission_rate: Decimal | None = None
    raw_provider_reference: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.observation_id, "Observation ID"),
            (self.fixture_id, "Fixture ID"),
            (self.competition, "Competition"),
            (self.source_name, "Source name"),
            (self.bookmaker_or_exchange, "Bookmaker or exchange"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must not be empty.")
        _aware(self.kickoff_time, "Kickoff timestamp")
        _aware(self.observed_at, "Observation timestamp")
        _aware(self.created_at, "Created timestamp")
        _odds(self.decimal_odds)
        if self.available_limit is not None and (
            not self.available_limit.is_finite() or self.available_limit < 0
        ):
            raise ValueError("Available limit must be finite and non-negative.")
        if self.currency is not None and not self.currency.strip():
            raise ValueError("Currency must not be empty when supplied.")
        if self.commission_rate is not None:
            _commission(self.commission_rate)


@dataclass(frozen=True, slots=True)
class OddsSnapshot:
    fixture_id: str
    market: OddsMarket
    selection: OddsSelection
    cutoff: datetime
    observations: tuple[OddsObservation, ...]

    def __post_init__(self) -> None:
        _aware(self.cutoff, "Snapshot cutoff")
        if any(item.observed_at > self.cutoff for item in self.observations):
            raise ValueError("Snapshots cannot contain future observations.")


@dataclass(frozen=True, slots=True)
class OddsRoleAssignment:
    assignment_id: str
    observation_id: str
    role: OddsObservationRole
    assigned_at: datetime

    def __post_init__(self) -> None:
        if not self.assignment_id.strip() or not self.observation_id.strip():
            raise ValueError("Odds role assignment identity must not be empty.")
        _aware(self.assigned_at, "Role assignment timestamp")


@dataclass(frozen=True, slots=True)
class OddsConsensus:
    fixture_id: str
    market: OddsMarket
    selection: OddsSelection
    source_count: int
    minimum_odds: Decimal
    maximum_odds: Decimal
    mean_odds: Decimal
    median_odds: Decimal
    weighted_mean_odds: Decimal | None
    source_dispersion: Decimal
    implied_probabilities: tuple[tuple[str, Decimal], ...]
    no_vig_probabilities: tuple[tuple[str, Decimal], ...]
    completeness: ConsensusCompleteness
    observation_cutoff: datetime
    consensus_timestamp: datetime


@dataclass(frozen=True, slots=True)
class MarketDisagreement:
    model_probability: Decimal
    market_probability: Decimal | None
    absolute_disagreement: Decimal | None
    signed_disagreement: Decimal | None
    model_edge: Decimal | None
    source_count: int
    consensus_completeness: ConsensusCompleteness
    observation_cutoff: datetime
    consensus_timestamp: datetime


@dataclass(frozen=True, slots=True)
class OddsMovement:
    fixture_id: str
    market: OddsMarket
    selection: OddsSelection
    opening_odds: Decimal
    latest_odds: Decimal
    closing_odds: Decimal | None
    absolute_change: Decimal
    percentage_change: Decimal
    implied_probability_change: Decimal
    observation_count: int
    first_observed_at: datetime
    latest_observed_at: datetime


@dataclass(frozen=True, slots=True)
class ClosingOddsRecord:
    closing_id: str
    fixture_id: str
    market: OddsMarket
    selection: OddsSelection
    kickoff_time: datetime
    selected_at: datetime
    closing_observed_at: datetime
    decimal_odds: Decimal
    source_name: str
    source_type: OddsSourceType
    selection_path: ClosingSelectionPath
    source_count: int
    cutoff: datetime
    observation_id: str | None = None

    def __post_init__(self) -> None:
        _aware(self.kickoff_time, "Kickoff timestamp")
        _aware(self.selected_at, "Selected timestamp")
        _aware(self.closing_observed_at, "Closing observation timestamp")
        _aware(self.cutoff, "Closing cutoff")
        _odds(self.decimal_odds)
        if self.closing_observed_at >= self.kickoff_time:
            raise ValueError("Closing odds must be observed before kickoff.")


@dataclass(frozen=True, slots=True)
class CLVResult:
    classification: CLVClassification
    raw_clv: Decimal | None
    clv_percentage: Decimal | None
    publication_odds: Decimal
    closing_odds: Decimal | None
    publication_timestamp: datetime
    closing_timestamp: datetime | None
    publication_source: str
    closing_source: str | None


@dataclass(frozen=True, slots=True)
class OddsObservationError:
    source: str
    fixture_id: str
    market: str
    selection: str
    code: OddsErrorCode
    safe_message: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "Error timestamp")
        if not self.safe_message.strip():
            raise ValueError("Odds errors require a safe message.")


@dataclass(frozen=True, slots=True)
class OddsIngestionReport:
    received_count: int
    inserted_count: int
    duplicate_count: int
    rejected_count: int
    ordered_errors: tuple[OddsObservationError, ...]
    sources_processed: tuple[str, ...]
    fixtures_processed: tuple[str, ...]
    observation_time_range: tuple[datetime, datetime] | None


@dataclass(frozen=True, slots=True)
class ClosingOddsSelection:
    record: ClosingOddsRecord | None
    path: ClosingSelectionPath
    reason: str


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")


def _odds(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 1:
        raise ValueError("Decimal odds must be finite and greater than 1.")


def _commission(value: Decimal) -> None:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not Decimal("0") <= value < Decimal("1")
    ):
        raise ValueError("Commission must be a finite fraction in [0, 1).")
