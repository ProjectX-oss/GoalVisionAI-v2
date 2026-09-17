from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.official_prediction_orchestration import (
    ApprovedOfficialPredictionPublication,
)
from app.risk_management import (
    RiskAssessmentDecision,
    RiskProductScope,
    StakeRecommendation,
)


class PredictionPublicationEventStatus(str, Enum):
    CLAIMED = "CLAIMED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class PredictionPublicationFailureReason(str, Enum):
    TELEGRAM_CONFIRMED_FAILED = "TELEGRAM_CONFIRMED_FAILED"
    TELEGRAM_DELIVERY_UNKNOWN = "TELEGRAM_DELIVERY_UNKNOWN"
    PUBLISHED_REFERENCE_FAILED = "PUBLISHED_REFERENCE_FAILED"
    FINALIZATION_FAILED = "FINALIZATION_FAILED"


@dataclass(frozen=True, slots=True)
class OfficialPredictionDestination:
    product_scope: RiskProductScope
    channel_id: str

    def __post_init__(self) -> None:
        if self.product_scope is not RiskProductScope.OFFICIAL:
            raise ValueError("Only the Official prediction destination is supported.")
        if not self.channel_id.strip():
            raise ValueError("Official Telegram channel identifier is required.")


@dataclass(frozen=True, slots=True)
class ApprovedPublicReasoning:
    ordered_facts: tuple[str, ...]
    data_status_note: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialPredictionPublicFacts:
    prediction_id: str
    match_id: str
    orchestration_id: str
    gate_evaluation_id: str
    candidate_fingerprint: str
    model_version: str
    policy_version: str
    competition: str
    home_team: str
    away_team: str
    bankroll_scope: RiskProductScope
    risk_decision: RiskAssessmentDecision
    stake_recommendation: StakeRecommendation | None
    reasoning: ApprovedPublicReasoning


@dataclass(frozen=True, slots=True)
class PublicStakeRating:
    stars: int
    rendered: str


@dataclass(frozen=True, slots=True)
class OfficialPredictionPublicationPayload:
    prediction_id: str
    match_id: str
    orchestration_id: str
    gate_evaluation_id: str
    candidate_fingerprint: str
    message_fingerprint: str
    destination_scope: RiskProductScope
    rendered_text: str
    parse_mode: str
    approved_odds: Decimal
    calibrated_probability: Decimal
    public_confidence: str
    public_stake_rating: PublicStakeRating
    created_timestamp: datetime
    model_version: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class PredictionPublicationEvent:
    event_id: str
    attempt_reference: str
    attempt_number: int
    event_sequence: int
    status: PredictionPublicationEventStatus
    payload: OfficialPredictionPublicationPayload
    occurred_at: datetime
    telegram_message_id: int | None = None
    failure_reason: PredictionPublicationFailureReason | None = None


@dataclass(frozen=True, slots=True)
class PredictionPublicationClaim:
    acquired: bool
    event: PredictionPublicationEvent


@dataclass(frozen=True, slots=True)
class OfficialPredictionMessageInput:
    approved: ApprovedOfficialPredictionPublication
    facts: OfficialPredictionPublicFacts
    destination: OfficialPredictionDestination
