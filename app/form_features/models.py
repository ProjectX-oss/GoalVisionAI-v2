from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum


class VenueSplit(str, Enum):
    OVERALL = "OVERALL"
    HOME = "HOME"
    AWAY = "AWAY"


class RecencyWeight(str, Enum):
    UNIFORM = "UNIFORM"
    EXPONENTIAL = "EXPONENTIAL"
    EXPLICIT = "EXPLICIT"


class OpponentStrengthSource(str, Enum):
    STANDINGS_RANK = "STANDINGS_RANK"
    POINTS_PER_MATCH = "POINTS_PER_MATCH"
    GOAL_DIFFERENCE_PER_MATCH = "GOAL_DIFFERENCE_PER_MATCH"
    INTERNAL_RATING = "INTERNAL_RATING"
    CALLER_PROVIDED = "CALLER_PROVIDED"


class OpponentStrengthTransform(str, Enum):
    RATIO_TO_BASELINE = "RATIO_TO_BASELINE"
    INVERSE_RANK_RATIO = "INVERSE_RANK_RATIO"


class ExpectedGoalsStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    STALE = "STALE"


class FormEvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DistortionEvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FormSignal(str, Enum):
    RESULTS_GOAL_RATE_DIVERGENCE = "RESULTS_GOAL_RATE_DIVERGENCE"
    VERY_SMALL_SAMPLE = "VERY_SMALL_SAMPLE"
    GOALS_XG_DIVERGENCE = "GOALS_XG_DIVERGENCE"
    POINTS_EXPECTED_PROCESS_DIVERGENCE = "POINTS_EXPECTED_PROCESS_DIVERGENCE"
    HIGH_FINISHING_RATE = "HIGH_FINISHING_RATE"
    GOALKEEPER_OVERPERFORMANCE = "GOALKEEPER_OVERPERFORMANCE"


class FormFeatureErrorCode(str, Enum):
    INVALID_FIXTURE = "INVALID_FIXTURE"
    INVALID_TEAM = "INVALID_TEAM"
    INVALID_SCORE = "INVALID_SCORE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    FUTURE_MATCH = "FUTURE_MATCH"
    INCOMPLETE_MATCH = "INCOMPLETE_MATCH"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    DISABLED_SOURCE = "DISABLED_SOURCE"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    MALFORMED_PROVIDER_RECORD = "MALFORMED_PROVIDER_RECORD"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    OPPONENT_STRENGTH_MISSING = "OPPONENT_STRENGTH_MISSING"
    XG_UNAVAILABLE = "XG_UNAVAILABLE"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"


COMPLETED_MATCH_STATUSES = frozenset({"FT", "AET", "PEN"})


@dataclass(frozen=True, slots=True)
class HistoricalMatchObservation:
    fixture_id: str
    competition: str
    kickoff_time: datetime
    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    match_status: str
    observed_at: datetime
    home_xg: Decimal | None
    away_xg: Decimal | None
    home_shots: int | None
    away_shots: int | None
    home_red_cards: int | None
    away_red_cards: int | None
    penalties: int | None
    source_name: str
    source_reference: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.kickoff_time, "Kickoff"),
            (self.observed_at, "Observed"),
            (self.created_at, "Created"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} timestamp must be timezone-aware.")
        if not self.fixture_id.strip():
            raise ValueError("Fixture ID must not be empty.")
        if not self.home_team_id.strip() or not self.away_team_id.strip():
            raise ValueError("Team identities must not be empty.")
        if self.home_team_id == self.away_team_id:
            raise ValueError("Home and away teams must differ.")
        if self.home_goals < 0 or self.away_goals < 0:
            raise ValueError("Scores must not be negative.")
        for value in (self.home_xg, self.away_xg):
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError("xG must be a finite non-negative Decimal.")
        for value in (
            self.home_shots,
            self.away_shots,
            self.home_red_cards,
            self.away_red_cards,
            self.penalties,
        ):
            if value is not None and value < 0:
                raise ValueError("Optional event counts must not be negative.")

    @property
    def completed(self) -> bool:
        return self.match_status.upper() in COMPLETED_MATCH_STATUSES


@dataclass(frozen=True, slots=True)
class TeamMatchPerformance:
    fixture_id: str
    opponent_team_id: str
    venue: VenueSplit
    kickoff_time: datetime
    observed_at: datetime
    goals_for: int
    goals_against: int
    points: int
    xg_for: Decimal | None
    xg_against: Decimal | None
    shots_for: int | None
    shots_against: int | None

    def __post_init__(self) -> None:
        _require_aware(self.kickoff_time, "Performance kickoff")
        _require_aware(self.observed_at, "Performance observation")


@dataclass(frozen=True, slots=True)
class OpponentStrengthObservation:
    team_id: str
    source: OpponentStrengthSource
    raw_value: Decimal
    observed_at: datetime
    source_reference: str

    def __post_init__(self) -> None:
        if not self.team_id.strip():
            raise ValueError("Opponent team ID must not be empty.")
        if not self.raw_value.is_finite():
            raise ValueError("Opponent strength must be finite.")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Opponent-strength timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class MatchDistortionPolicy:
    apply_adjustments: bool = False


@dataclass(frozen=True, slots=True)
class FormFeaturePolicy:
    recent_window: int = 5
    minimum_sample: int = 3
    venue_minimum_sample: int = 2
    venue_blend: Decimal = Decimal("0.60")
    recency_weight: RecencyWeight = RecencyWeight.UNIFORM
    exponential_decay: Decimal = Decimal("0.85")
    explicit_weights: tuple[Decimal, ...] = ()
    opponent_strength_source: OpponentStrengthSource = (
        OpponentStrengthSource.POINTS_PER_MATCH
    )
    opponent_strength_transform: OpponentStrengthTransform = (
        OpponentStrengthTransform.RATIO_TO_BASELINE
    )
    opponent_baseline: Decimal = Decimal("1.50")
    opponent_adjustment_min: Decimal = Decimal("0.75")
    opponent_adjustment_max: Decimal = Decimal("1.25")
    missing_opponent_fallback: Decimal | None = None
    maximum_history_age: timedelta = timedelta(days=365)
    divergence_threshold: Decimal = Decimal("0.35")
    distortion_policy: MatchDistortionPolicy = MatchDistortionPolicy()

    def __post_init__(self) -> None:
        if self.recent_window <= 0 or self.minimum_sample <= 0:
            raise ValueError("Form window and minimum sample must be positive.")
        if self.venue_minimum_sample <= 0:
            raise ValueError("Venue minimum sample must be positive.")
        if not Decimal("0") <= self.venue_blend <= Decimal("1"):
            raise ValueError("Venue blend must be between 0 and 1.")
        if not Decimal("0") < self.exponential_decay <= Decimal("1"):
            raise ValueError("Exponential decay must be in (0, 1].")
        if any(weight <= 0 for weight in self.explicit_weights):
            raise ValueError("Explicit weights must be positive.")
        if self.opponent_baseline <= 0:
            raise ValueError("Opponent baseline must be positive.")
        if (
            self.opponent_strength_source is OpponentStrengthSource.STANDINGS_RANK
            and self.opponent_strength_transform
            is not OpponentStrengthTransform.INVERSE_RANK_RATIO
        ):
            raise ValueError("Standings rank requires inverse-rank transformation.")
        if (
            self.opponent_strength_source is not OpponentStrengthSource.STANDINGS_RANK
            and self.opponent_strength_transform
            is OpponentStrengthTransform.INVERSE_RANK_RATIO
        ):
            raise ValueError("Inverse-rank transformation requires standings rank.")
        if self.opponent_adjustment_min <= 0:
            raise ValueError("Opponent adjustment minimum must be positive.")
        if self.opponent_adjustment_max < self.opponent_adjustment_min:
            raise ValueError("Opponent adjustment limits are invalid.")
        if self.missing_opponent_fallback is not None and (
            self.missing_opponent_fallback <= 0
        ):
            raise ValueError("Missing-opponent fallback must be positive.")
        if self.maximum_history_age < timedelta(0):
            raise ValueError("Maximum history age must not be negative.")
        if self.divergence_threshold < 0:
            raise ValueError("Divergence threshold must not be negative.")


@dataclass(frozen=True, slots=True)
class FormMetrics:
    matches_played: int
    wins: int
    draws: int
    losses: int
    points: int
    goals_for: int
    goals_against: int
    goal_difference: int
    clean_sheets: int
    failed_to_score: int
    average_goals_for: Decimal
    average_goals_against: Decimal
    result_form_score: Decimal


@dataclass(frozen=True, slots=True)
class WeightedFormMetrics:
    normalized_weights: tuple[Decimal, ...]
    weighted_points_per_match: Decimal
    weighted_goals_for: Decimal
    weighted_goals_against: Decimal


@dataclass(frozen=True, slots=True)
class ExpectedGoalsEvidence:
    status: ExpectedGoalsStatus
    sample_size: int
    xg_for: Decimal | None
    xg_against: Decimal | None
    xg_difference: Decimal | None
    average_xg_for: Decimal | None
    average_xg_against: Decimal | None
    recency_weighted_xg_for: Decimal | None
    recency_weighted_xg_against: Decimal | None
    opponent_adjusted_xg_for: Decimal | None
    opponent_adjusted_xg_against: Decimal | None
    home_average_xg_for: Decimal | None
    away_average_xg_for: Decimal | None


@dataclass(frozen=True, slots=True)
class FormConflict:
    fixture_id: str
    observation_ids: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class MatchDistortionEvidence:
    early_red_card: DistortionEvidenceStatus
    late_red_card: DistortionEvidenceStatus
    penalty_heavy: DistortionEvidenceStatus
    extreme_scoreline: DistortionEvidenceStatus
    abandoned: DistortionEvidenceStatus
    extra_time: DistortionEvidenceStatus
    shootout: DistortionEvidenceStatus


@dataclass(frozen=True, slots=True)
class TeamFormSnapshot:
    team_id: str
    venue: VenueSplit
    selected_fixture_ids: tuple[str, ...]
    excluded_fixtures: tuple[tuple[str, str], ...]
    overall: FormMetrics
    home: FormMetrics
    away: FormMetrics
    recent: FormMetrics
    weighted: WeightedFormMetrics
    venue_weighted_goals_for: Decimal
    venue_weighted_goals_against: Decimal
    venue_fallback_used: bool
    expected_goals: ExpectedGoalsEvidence
    evidence_status: FormEvidenceStatus
    freshness_status: FormEvidenceStatus
    sample_size: int
    signals: tuple[FormSignal, ...]
    distortions: MatchDistortionEvidence
    calculation_timestamp: datetime
    latest_source_observed_at: datetime | None

    def __post_init__(self) -> None:
        _require_aware(self.calculation_timestamp, "Calculation")
        if self.latest_source_observed_at is not None:
            _require_aware(self.latest_source_observed_at, "Latest source")


@dataclass(frozen=True, slots=True)
class OpponentAdjustedFormSnapshot:
    form: TeamFormSnapshot
    opponent_strengths: tuple[tuple[str, Decimal | None], ...]
    adjustment_factors: tuple[tuple[str, Decimal | None], ...]
    adjusted_attacking_form: Decimal | None
    adjusted_defensive_form: Decimal | None
    missing_opponents: tuple[str, ...]
    conflicts: tuple[FormConflict, ...]


@dataclass(frozen=True, slots=True)
class FormFeatureError:
    fixture_id: str
    code: FormFeatureErrorCode
    safe_message: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "Error occurrence")


@dataclass(frozen=True, slots=True)
class FormFeatureReport:
    received: int
    inserted: int
    duplicates: int
    rejected: int
    competitions: tuple[str, ...]
    teams: tuple[str, ...]
    fixtures: tuple[str, ...]
    time_range: tuple[datetime, datetime] | None
    ordered_errors: tuple[FormFeatureError, ...]

    def __post_init__(self) -> None:
        if self.time_range is not None:
            _require_aware(self.time_range[0], "Report start")
            _require_aware(self.time_range[1], "Report end")


@dataclass(frozen=True, slots=True)
class HistoricalFormFeature:
    team_id: str
    calculation_timestamp: datetime
    evidence_status: FormEvidenceStatus
    sample_size: int
    goals_based_attack: Decimal | None
    goals_based_defense: Decimal | None
    xg_status: ExpectedGoalsStatus
    xg_attack: Decimal | None
    xg_defense: Decimal | None

    def __post_init__(self) -> None:
        _require_aware(self.calculation_timestamp, "Historical feature")


@dataclass(frozen=True, slots=True)
class HistoricalFormWalkForwardInput:
    target_fixture_id: str
    cutoff: datetime
    feature: HistoricalFormFeature

    def __post_init__(self) -> None:
        _require_aware(self.cutoff, "Walk-forward cutoff")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} timestamp must be timezone-aware.")
