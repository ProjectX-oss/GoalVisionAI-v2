from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.official_prediction_orchestration import (
    BankrollScopeRecord,
    ExposureEvaluationRecord,
    ModelHealthRecord,
    RiskEvaluationRecord,
)
from app.probability_calibration import ProbabilityCalibrationReport
from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import RiskProductScope


class OfficialCandidateMarket(str, Enum):
    MATCH_WINNER = "MATCH_WINNER"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    TOTALS = "TOTALS"
    BTTS = "BTTS"


class CandidateLifecycleState(str, Enum):
    READY = "READY"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    INVALIDATED = "INVALIDATED"


class CandidateRegistrationStatus(str, Enum):
    REGISTERED = "REGISTERED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    SUPERSEDED_PREVIOUS = "SUPERSEDED_PREVIOUS"
    REJECTED_INVALID = "REJECTED_INVALID"
    REJECTED_SCOPE = "REJECTED_SCOPE"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class CandidateLifecycleResultStatus(str, Enum):
    APPLIED = "APPLIED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class CandidatePublicationGuardState(str, Enum):
    UNPUBLISHED = "UNPUBLISHED"
    PUBLISHED = "PUBLISHED"
    ACTIVE_CLAIM = "ACTIVE_CLAIM"
    INDETERMINATE = "INDETERMINATE"
    UNKNOWN = "UNKNOWN"


class ReasoningFactType(str, Enum):
    RECENT_FORM = "RECENT_FORM"
    HOME_STRENGTH = "HOME_STRENGTH"
    AWAY_WEAKNESS = "AWAY_WEAKNESS"
    ATTACKING_TREND = "ATTACKING_TREND"
    DEFENSIVE_TREND = "DEFENSIVE_TREND"
    TOTAL_GOALS_TREND = "TOTAL_GOALS_TREND"
    BTTS_TREND = "BTTS_TREND"
    LINEUP_STATUS = "LINEUP_STATUS"
    INJURY_SUSPENSION_SUMMARY = "INJURY_SUSPENSION_SUMMARY"
    MARKET_STATISTICAL_EVIDENCE = "MARKET_STATISTICAL_EVIDENCE"


@dataclass(frozen=True, slots=True)
class OfficialPredictionReasoningFact:
    fact_type: ReasoningFactType
    text: str
    source_reference: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialPredictionCandidateRegistrationCommand:
    source_event_id: str
    prediction_id: str
    match_id: str
    competition_id: str | None
    competition_name: str
    home_team_id: str | None
    home_team_name: str
    away_team_id: str | None
    away_team_name: str
    kickoff_timestamp: datetime
    prediction_creation_timestamp: datetime
    model_version: str
    market_type: str
    selection: str
    market_line: Decimal | None
    raw_model_probability: Decimal
    supplied_expected_value: Decimal
    decimal_odds: Decimal
    odds_timestamp: datetime
    odds_source_id: str
    core_match_data_timestamp: datetime
    lineup_status: LineupStatus
    lineup_data_timestamp: datetime | None
    injury_suspension_status: FactStatus
    injury_suspension_data_timestamp: datetime | None
    confidence_level: ConfidenceLevel
    public_reasoning_facts: tuple[OfficialPredictionReasoningFact, ...]
    source_data_version: str
    supporting_data_status: FactStatus
    market_availability: MarketAvailability
    bankroll_scope: RiskProductScope
    destination_scope: RiskProductScope
    registration_timestamp: datetime
    is_live: bool = False
    is_accumulator: bool = False


@dataclass(frozen=True, slots=True)
class OfficialCandidateMarketIdentity:
    market: OfficialCandidateMarket
    selection: str
    market_line: Decimal | None


@dataclass(frozen=True, slots=True)
class PreparedOfficialPredictionCandidate:
    logical_identity_fingerprint: str
    content_fingerprint: str
    source_event_id: str
    prediction_id: str
    match_id: str
    competition_id: str | None
    competition_name: str
    normalized_competition_name: str
    home_team_id: str | None
    home_team_name: str
    normalized_home_team_name: str
    away_team_id: str | None
    away_team_name: str
    normalized_away_team_name: str
    kickoff_timestamp: datetime
    prediction_creation_timestamp: datetime
    model_version: str
    market_identity: OfficialCandidateMarketIdentity
    raw_model_probability: Decimal
    supplied_expected_value: Decimal
    decimal_odds: Decimal
    odds_timestamp: datetime
    odds_source_id: str
    core_match_data_timestamp: datetime
    lineup_status: LineupStatus
    lineup_data_timestamp: datetime | None
    injury_suspension_status: FactStatus
    injury_suspension_data_timestamp: datetime | None
    confidence_level: ConfidenceLevel
    public_reasoning_facts: tuple[OfficialPredictionReasoningFact, ...]
    source_data_version: str
    supporting_data_status: FactStatus
    market_availability: MarketAvailability
    bankroll_scope: RiskProductScope
    destination_scope: RiskProductScope
    registration_timestamp: datetime
    normalized_snapshot: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class OfficialPredictionCandidateVersion:
    registry_candidate_id: str
    candidate_version: int
    prepared: PreparedOfficialPredictionCandidate
    lifecycle_state_at_creation: CandidateLifecycleState = (
        CandidateLifecycleState.READY
    )

    @property
    def prediction_id(self) -> str:
        return self.prepared.prediction_id

    @property
    def match_id(self) -> str:
        return self.prepared.match_id

    @property
    def content_fingerprint(self) -> str:
        return self.prepared.content_fingerprint

    @property
    def logical_identity_fingerprint(self) -> str:
        return self.prepared.logical_identity_fingerprint


@dataclass(frozen=True, slots=True)
class CandidateVersionRegistration:
    candidate: OfficialPredictionCandidateVersion
    previous_candidate: OfficialPredictionCandidateVersion | None
    identical_existing: bool


@dataclass(frozen=True, slots=True)
class OfficialPredictionCandidateRegistrationOutcome:
    registry_candidate_id: str | None
    prediction_id: str
    match_id: str
    logical_identity_fingerprint: str | None
    candidate_content_fingerprint: str | None
    candidate_version: int | None
    final_status: CandidateRegistrationStatus
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    previous_candidate_id: str | None
    registration_timestamp: datetime
    model_version: str
    market_identity: OfficialCandidateMarketIdentity | None


@dataclass(frozen=True, slots=True)
class CandidateLifecycleEvent:
    event_id: str
    registry_candidate_id: str
    event_sequence: int
    event_type: CandidateLifecycleState
    reason_code: str
    previous_candidate_id: str | None
    event_timestamp: datetime
    event_snapshot: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CandidateLifecycleOutcome:
    registry_candidate_id: str
    state: CandidateLifecycleState | None
    status: CandidateLifecycleResultStatus
    reason_code: str
    event_timestamp: datetime


@dataclass(frozen=True, slots=True)
class OfficialCandidateAssemblyContext:
    calibration_records: tuple[ProbabilityCalibrationReport, ...]
    model_health_records: tuple[ModelHealthRecord, ...]
    risk_evaluations: tuple[RiskEvaluationRecord, ...]
    exposure_evaluations: tuple[ExposureEvaluationRecord, ...]
    bankroll: BankrollScopeRecord | None
