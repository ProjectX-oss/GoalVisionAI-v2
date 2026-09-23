"""Immutable offline facts and results, not runtime source or persistence adapters.

SourceRef.known_at asserts proven observation of the completed facts. Freshness
and format verdicts are supplied evidence, not discovered here. Phase B must
establish those assertions before any real prospective use.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
import unicodedata

from .fingerprint import feature_text, utc
from .policy import FEATURE_NAMES, REASONS, Profile


class Neutral(StrEnum):
    TRUE = 'TRUE'
    FALSE = 'FALSE'
    UNKNOWN = 'UNKNOWN'


class Freshness(StrEnum):
    FRESH_COLLECTION = 'FRESH_COLLECTION'
    STALE_COLLECTION = 'STALE_COLLECTION'
    UNAVAILABLE = 'UNAVAILABLE'


class Status(StrEnum):
    AVAILABLE = 'AVAILABLE'
    MISSING = 'MISSING'


def positive_id(value: int) -> None:
    """Booleans and integer-like strings are not provider identifiers."""
    if type(value) is not int or value <= 0:
        raise ValueError('INVALID_IDENTITY')


def require_text(value: str) -> None:
    """Require explicit, nonempty supplied identity/evidence text."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('INVALID_IDENTITY')


def require_hash(value: str) -> None:
    """Validate a supplied lowercase SHA-256 identity, without claiming payload verification."""
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('INVALID_HASH')


@dataclass(frozen=True, slots=True)
class Classification:
    profile: Profile
    version: str
    reason: str
    flags: tuple[str, ...]
    gender: str
    age_group: str
    team_category: str
    evidence_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.profile, Profile) or type(self.flags) is not tuple:
            raise ValueError('INVALID_CLASSIFICATION')
        for value in (self.version, self.reason, self.gender, self.age_group, self.team_category, *self.flags):
            require_text(value)
        require_hash(self.evidence_hash)
        for name in ('version', 'reason', 'gender', 'age_group', 'team_category'):
            object.__setattr__(self, name, unicodedata.normalize('NFC', getattr(self, name)))
        object.__setattr__(self, 'flags', tuple(unicodedata.normalize('NFC', flag) for flag in self.flags))

    @property
    def entity_scope(self) -> tuple[str, str, str]:
        """Pinned entity category; never infer women/youth/reserves from names."""
        return self.gender, self.age_group, self.team_category


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Stable supplied evidence identity/hash, never a temporary database surrogate.

    known_at asserts completed facts were observed; equality at cutoff additionally
    requires available_before_capture. These assertions need Phase B proof before
    real use; Phase A neither discovers nor certifies that proof.
    """
    namespace: str
    identity: str
    payload_hash: str
    known_at: datetime
    available_before_capture: bool = False

    def __post_init__(self) -> None:
        if type(self.available_before_capture) is not bool:
            raise ValueError('INVALID_CAPTURE_ORDER_PROOF')
        require_text(self.namespace)
        require_text(self.identity)
        require_hash(self.payload_hash)
        object.__setattr__(self, 'namespace', unicodedata.normalize('NFC', self.namespace))
        object.__setattr__(self, 'identity', unicodedata.normalize('NFC', self.identity))
        object.__setattr__(self, 'known_at', utc(self.known_at))


@dataclass(frozen=True, slots=True)
class Regulation:
    minutes: int | None
    evidence_id: str | None
    evidence_hash: str | None

    def __post_init__(self) -> None:
        if self.minutes is not None:
            positive_id(self.minutes)
        if (self.evidence_id is None) != (self.evidence_hash is None):
            raise ValueError('INCOMPLETE_FORMAT_EVIDENCE')
        if self.evidence_id is not None:
            require_text(self.evidence_id)
            require_hash(self.evidence_hash)
            object.__setattr__(self, 'evidence_id', unicodedata.normalize('NFC', self.evidence_id))

    @property
    def reason(self) -> str | None:
        """Unproven duration remains missing even when a caller guesses 90."""
        if self.minutes is None or self.evidence_id is None:
            return 'REGULATION_UNVERIFIED'
        return None if self.minutes == 90 else 'UNSUPPORTED_REGULATION'


@dataclass(frozen=True, slots=True)
class Target:
    provider: str
    fixture_id: int
    competition_id: int
    season: int
    home_team_id: int
    away_team_id: int
    kickoff: datetime
    cutoff: datetime
    classification: Classification
    regulation: Regulation
    source: SourceRef
    neutral: Neutral = Neutral.UNKNOWN
    status: str = 'NS'

    def __post_init__(self) -> None:
        if not isinstance(self.classification, Classification) or not isinstance(self.regulation, Regulation) or not isinstance(self.source, SourceRef):
            raise ValueError('INVALID_TARGET_CONTRACT')
        if self.provider != 'API_FOOTBALL':
            raise ValueError('UNSUPPORTED_PROVIDER')
        for value in (self.fixture_id, self.competition_id, self.season, self.home_team_id, self.away_team_id):
            positive_id(value)
        if self.home_team_id == self.away_team_id or not isinstance(self.neutral, Neutral):
            raise ValueError('INVALID_TARGET_IDENTITY')
        object.__setattr__(self, 'kickoff', utc(self.kickoff))
        object.__setattr__(self, 'cutoff', utc(self.cutoff))
        if self.cutoff >= self.kickoff or self.source.known_at > self.cutoff or self.status != 'NS' or (
            self.source.known_at == self.cutoff and not self.source.available_before_capture
        ):
            raise ValueError('INVALID_PREMATCH_CUTOFF_OR_STATUS')


@dataclass(frozen=True, slots=True)
class Fixture:
    """Supplied football facts; invalid score/team/status rows are diagnosed and excluded.

    Fulltime pair is regulation only. goals_* is a separate optional FT fallback;
    it may contain ET totals for AET/PEN and is never read in those statuses.
    """
    provider: str
    fixture_id: int
    competition_id: int
    season: int
    home_team_id: int
    away_team_id: int
    kickoff: datetime
    entity_scope: tuple[str, str, str]
    fulltime_home: int | None
    fulltime_away: int | None
    status: str = 'FT'
    goals_home: int | None = None
    goals_away: int | None = None
    neutral: Neutral = Neutral.UNKNOWN
    phase: str | None = None

    def __post_init__(self) -> None:
        positive_id(self.fixture_id)
        require_text(self.provider)
        require_text(self.status)
        if self.phase is not None:
            require_text(self.phase)
        if any(type(value) is not int for value in (self.competition_id, self.season, self.home_team_id, self.away_team_id)):
            raise ValueError('INVALID_INTEGER_IDENTITY_TYPE')
        if any(value is not None and type(value) is not int for value in (
            self.fulltime_home, self.fulltime_away, self.goals_home, self.goals_away
        )):
            raise ValueError('INVALID_SCORE_TYPE')
        if type(self.entity_scope) is not tuple or len(self.entity_scope) != 3:
            raise ValueError('INVALID_ENTITY_SCOPE')
        for part in self.entity_scope:
            require_text(part)
        object.__setattr__(self, 'entity_scope', tuple(unicodedata.normalize('NFC', part) for part in self.entity_scope))
        if self.phase is not None:
            object.__setattr__(self, 'phase', unicodedata.normalize('NFC', self.phase))
        if not isinstance(self.neutral, Neutral):
            raise ValueError('INVALID_NEUTRAL_STATUS')
        object.__setattr__(self, 'kickoff', utc(self.kickoff))


@dataclass(frozen=True, slots=True)
class History:
    """One supplied season response; source None means unavailable, rows=() means empty.

    The caller supplies a freshness verdict after source validation; this object
    implements no selection, TTL reader, pinning, or registration infrastructure.
    """
    season: int
    source: SourceRef | None
    regulation: Regulation
    rows: tuple[Fixture, ...]
    freshness: Freshness = Freshness.FRESH_COLLECTION

    def __post_init__(self) -> None:
        positive_id(self.season)
        if not isinstance(self.regulation, Regulation) or (self.source is not None and not isinstance(self.source, SourceRef)):
            raise ValueError('INVALID_HISTORY_CONTRACT')
        if type(self.rows) is not tuple or not all(isinstance(row, Fixture) for row in self.rows):
            raise ValueError('IMMUTABLE_FIXTURE_TUPLE_REQUIRED')
        if not isinstance(self.freshness, Freshness):
            raise ValueError('INVALID_FRESHNESS')
        if self.source is None and self.rows:
            raise ValueError('ROWS_WITHOUT_SOURCE')


@dataclass(frozen=True, slots=True)
class ContextInput:
    target: Target
    current: History | None
    previous: History | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, Target) or any(
            h is not None and not isinstance(h, History) for h in (self.current, self.previous)
        ):
            raise ValueError('INVALID_CONTEXT_INPUT')


@dataclass(frozen=True, slots=True)
class Game:
    """Eligible normalized score pair with all equivalent supplied evidence refs."""
    fixture: Fixture
    gf_home: int
    gf_away: int
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class Exclusion:
    fixture_id: int | None
    reasons: tuple[str, ...]
    facts: tuple[Fixture, ...]
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class Pool:
    target: Target
    games: tuple[Game, ...]
    exclusions: tuple[Exclusion, ...]
    reasons: tuple[str, ...]
    history_available: bool
    previous_present: bool
    sources: tuple[SourceRef, ...]
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class SelectedGame:
    fixture_id: int
    kickoff: datetime
    designation: str
    opponent_id: int
    gf: int
    ga: int
    weight: Decimal
    fact_hash: str


@dataclass(frozen=True, slots=True)
class Sample:
    team_id: int
    games: tuple[SelectedGame, ...]
    horizon_days: int | None
    half_life_days: int | None
    count: int | None
    effective_sample_size: Decimal | None
    oldest: datetime | None
    latest: datetime | None
    reasons: tuple[str, ...]
    exclusions: tuple[Exclusion, ...]
    pool_fingerprint: str
    cutoff: datetime


@dataclass(frozen=True, slots=True)
class TeamRating:
    team_id: int
    home: Decimal
    away: Decimal
    total: int
    designated_home: int
    designated_away: int

    def __post_init__(self) -> None:
        positive_id(self.team_id)
        if any(not isinstance(v, Decimal) or not v.is_finite() for v in (self.home, self.away)):
            raise ValueError('INVALID_PI_RATING')
        if any(type(n) is not int or not 0 <= n <= 198 for n in (self.total, self.designated_home, self.designated_away)):
            raise ValueError('INVALID_PI_COUNTS')
        if self.total != self.designated_home + self.designated_away:
            raise ValueError('INVALID_PI_COUNTS')


@dataclass(frozen=True, slots=True)
class PiState:
    ratings: tuple[TeamRating, ...]
    updates: tuple[Game, ...]
    cutoff: datetime
    pool_fingerprint: str
    semantic_fingerprint: str

    def rating(self, team_id: int) -> TeamRating | None:
        """Absent is absent; zero-state seed is not supported output."""
        return next((r for r in self.ratings if r.team_id == team_id), None)


@dataclass(frozen=True, slots=True)
class FormComponent:
    fixture_id: int
    designation: str
    opponent_id: int
    actual: Decimal
    expected: Decimal | None
    margin: Decimal
    performance: Decimal | None
    rank_weight: int
    team_rating: TeamRating | None
    opponent_rating: TeamRating | None
    supported: bool


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    value: str | None
    status: Status
    reasons: tuple[str, ...]
    sample_count: int | None
    sample: Sample | None = None
    form_components: tuple[FormComponent, ...] = ()
    support: tuple[TeamRating | None, ...] = ()
    pi_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.name not in FEATURE_NAMES or not isinstance(self.status, Status):
            raise ValueError('INVALID_FEATURE_IDENTITY')
        if type(self.reasons) is not tuple or self.reasons != tuple(r for r in REASONS if r in self.reasons):
            raise ValueError('INVALID_FEATURE_REASONS')
        if self.sample_count is not None and (type(self.sample_count) is not int or not 0 <= self.sample_count <= 198):
            raise ValueError('INVALID_SAMPLE_COUNT')
        if self.status == Status.AVAILABLE:
            if not isinstance(self.value, str) or self.reasons or self.sample_count is None:
                raise ValueError('INVALID_FEATURE_AVAILABILITY')
            if not re.fullmatch(r'-?[0-9]+\.[0-9]{6}', self.value) or feature_text(Decimal(self.value), FEATURE_NAMES.index(self.name)) != self.value:
                raise ValueError('INVALID_FEATURE_VALUE')
        elif self.value is not None or not self.reasons:
            raise ValueError('INVALID_FEATURE_AVAILABILITY')

    @property
    def unit(self) -> str:
        """Version-bound units without adding model coordinates."""
        index = FEATURE_NAMES.index(self.name)
        return 'goals per observed 90-minute fixture' if index < 4 else (
            'dimensionless performance' if index < 6 else 'local Pi rating units')

    @property
    def freshness(self) -> Freshness:
        """Collection verdict; never a claim about provider update freshness."""
        if 'SOURCE_UNAVAILABLE' in self.reasons:
            return Freshness.UNAVAILABLE
        if 'STALE_SOURCE' in self.reasons:
            return Freshness.STALE_COLLECTION
        return Freshness.FRESH_COLLECTION


@dataclass(frozen=True, slots=True)
class ContextResult:
    contract: str
    semantic_fingerprint: str
    target: Target
    pool: Pool
    pi_state: PiState
    features: tuple[Feature, ...]
    history_scope: str = 'OBSERVED_COMPETITION_QUERY'
    complete_team_history: bool = False
