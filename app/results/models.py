from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ResolutionStatus(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"
    PENDING = "PENDING"
    UNRESOLVED = "UNRESOLVED"


class SettlementReasonCode(str, Enum):
    MATCH_RESULT_SETTLED = "MATCH_RESULT_SETTLED"
    MATCH_PENDING = "MATCH_PENDING"
    MATCH_DATA_MISSING = "MATCH_DATA_MISSING"
    FINAL_SCORE_MISSING = "FINAL_SCORE_MISSING"
    FIXTURE_MISMATCH = "FIXTURE_MISMATCH"
    FIXTURE_CANCELLED = "FIXTURE_CANCELLED"
    FIXTURE_POSTPONED = "FIXTURE_POSTPONED"
    FIXTURE_ABANDONED = "FIXTURE_ABANDONED"
    UNSUPPORTED_FIXTURE_STATUS = "UNSUPPORTED_FIXTURE_STATUS"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    MALFORMED_PREDICTION = "MALFORMED_PREDICTION"


@dataclass(frozen=True, slots=True)
class PublishedPredictionReference:
    prediction_id: str
    fixture_id: int
    market: str
    selection: str
    published_at: datetime

    def __post_init__(self) -> None:
        if not self.prediction_id.strip():
            raise ValueError("Prediction ID must not be empty.")
        if self.fixture_id <= 0:
            raise ValueError("Fixture ID must be positive.")
        if self.published_at.tzinfo is None:
            raise ValueError("Published timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class FinishedMatchResult:
    """A fixture result snapshot; status determines whether it is final."""

    fixture_id: int
    status: str
    home_score: int | None = None
    away_score: int | None = None

    def __post_init__(self) -> None:
        if self.fixture_id <= 0:
            raise ValueError("Fixture ID must be positive.")
        for score in (self.home_score, self.away_score):
            if score is not None and score < 0:
                raise ValueError("Match scores must not be negative.")


@dataclass(frozen=True, slots=True)
class ResolvedPredictionResult:
    prediction_id: str
    fixture_id: int
    status: ResolutionStatus
    resolved_at: datetime | None
    home_score: int | None
    away_score: int | None
    settlement_rule_version: str
    reason_codes: tuple[SettlementReasonCode, ...]

    def __post_init__(self) -> None:
        if not self.prediction_id.strip():
            raise ValueError("Prediction ID must not be empty.")
        if self.fixture_id <= 0:
            raise ValueError("Fixture ID must be positive.")
        if not self.settlement_rule_version.strip():
            raise ValueError("Settlement rule version must not be empty.")
        if not self.reason_codes:
            raise ValueError("At least one settlement reason code is required.")
        if self.resolved_at is not None and self.resolved_at.tzinfo is None:
            raise ValueError("Resolved timestamp must be timezone-aware.")
        if self.is_terminal and self.resolved_at is None:
            raise ValueError("Terminal results require a resolved timestamp.")
        if not self.is_terminal and self.resolved_at is not None:
            raise ValueError("Non-terminal results cannot have a resolved timestamp.")
        if self.status in {ResolutionStatus.WON, ResolutionStatus.LOST} and (
            self.home_score is None or self.away_score is None
        ):
            raise ValueError("Won and lost results require a complete final score.")

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }
