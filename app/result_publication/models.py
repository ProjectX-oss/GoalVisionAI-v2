from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.bankroll import BankrollProduct, BankrollTransaction
from app.results import PublishedPredictionReference, ResolvedPredictionResult


class ResultPublicationStatus(str, Enum):
    ATTEMPTING = "ATTEMPTING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ResultPublicationFailureReason(str, Enum):
    NON_TERMINAL_RESULT = "NON_TERMINAL_RESULT"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    PUBLICATION_IN_PROGRESS = "PUBLICATION_IN_PROGRESS"
    PUBLISHED_PREDICTION_MISSING = "PUBLISHED_PREDICTION_MISSING"
    BANKROLL_TRANSACTION_MISSING = "BANKROLL_TRANSACTION_MISSING"
    PRESENTATION_METADATA_MISSING = "PRESENTATION_METADATA_MISSING"
    PRESENTATION_FAILED = "PRESENTATION_FAILED"
    TELEGRAM_FAILED = "TELEGRAM_FAILED"
    DATABASE_FAILED = "DATABASE_FAILED"


@dataclass(frozen=True, slots=True)
class ResultPresentationMetadata:
    league: str
    home_team: str
    away_team: str

    def __post_init__(self) -> None:
        values = (self.league, self.home_team, self.away_team)
        if any(not value.strip() for value in values):
            raise ValueError("Result presentation metadata must be complete.")


@dataclass(frozen=True, slots=True)
class ResultPublicationCandidate:
    result: ResolvedPredictionResult
    prediction: PublishedPredictionReference
    transaction: BankrollTransaction
    destination: str
    metadata: ResultPresentationMetadata | None = None


@dataclass(frozen=True, slots=True)
class ResultPublicationMessage:
    text: str
    parse_mode: str
    format_version: str


@dataclass(frozen=True, slots=True)
class ResultPublicationAuditRecord:
    prediction_id: str
    product_id: BankrollProduct
    destination: str
    status: ResultPublicationStatus
    telegram_message_id: int | None
    attempted_at: datetime
    published_at: datetime | None
    failure_reason: ResultPublicationFailureReason | None
    format_version: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ResultPublicationClaim:
    record: ResultPublicationAuditRecord
    acquired: bool


@dataclass(frozen=True, slots=True)
class ResultPublicationOutcome:
    prediction_id: str
    fixture_id: int
    status: ResultPublicationStatus
    reasons: tuple[ResultPublicationFailureReason, ...]
    telegram_message_id: int | None = None


@dataclass(frozen=True, slots=True)
class ResultPublicationBatchReport:
    outcomes: tuple[ResultPublicationOutcome, ...]
    processed_count: int
    published_count: int
    failed_count: int
    skipped_count: int
    won_count: int
    lost_count: int
    void_count: int
    started_at: datetime
    completed_at: datetime
    format_version: str
