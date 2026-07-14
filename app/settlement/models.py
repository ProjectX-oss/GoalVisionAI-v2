from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.bankroll import StakeTier
from app.results import (
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
)


class SettlementOutcomeState(str, Enum):
    SETTLED = "SETTLED"
    PENDING = "PENDING"
    UNRESOLVED = "UNRESOLVED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class SettlementFailureReasonCode(str, Enum):
    FIXTURE_RESULT_MISSING = "FIXTURE_RESULT_MISSING"
    FIXTURE_PROVIDER_FAILED = "FIXTURE_PROVIDER_FAILED"
    DUPLICATE_PREDICTION = "DUPLICATE_PREDICTION"
    DUPLICATE_FIXTURE_RESPONSE = "DUPLICATE_FIXTURE_RESPONSE"
    CONFLICTING_FIXTURE_RESPONSES = "CONFLICTING_FIXTURE_RESPONSES"
    MISSING_STAKE_TIER = "MISSING_STAKE_TIER"
    MISSING_ODDS = "MISSING_ODDS"
    INVALID_ODDS = "INVALID_ODDS"
    PUBLISHED_PREDICTION_MISSING = "PUBLISHED_PREDICTION_MISSING"
    RESULT_PERSISTENCE_FAILED = "RESULT_PERSISTENCE_FAILED"
    BANKROLL_SETTLEMENT_FAILED = "BANKROLL_SETTLEMENT_FAILED"
    BANKROLL_ALREADY_SETTLED = "BANKROLL_ALREADY_SETTLED"


@dataclass(frozen=True, slots=True)
class SettlementCandidate:
    prediction: PublishedPredictionReference
    stake_tier: StakeTier | None
    odds: Decimal | None
    persisted_result: ResolvedPredictionResult | None = None

    @property
    def is_recovery(self) -> bool:
        return self.persisted_result is not None


@dataclass(frozen=True, slots=True)
class SettlementBatchRequest:
    requested_at: datetime
    stake_tiers: tuple[tuple[str, StakeTier], ...]

    def __post_init__(self) -> None:
        if self.requested_at.tzinfo is None:
            raise ValueError("Batch timestamp must be timezone-aware.")
        prediction_ids = tuple(item[0] for item in self.stake_tiers)
        if any(not prediction_id.strip() for prediction_id in prediction_ids):
            raise ValueError("Stake-tier prediction IDs must not be empty.")
        if len(set(prediction_ids)) != len(prediction_ids):
            raise ValueError("Each prediction may have only one explicit tier.")

    def tier_for(self, prediction_id: str) -> StakeTier | None:
        return dict(self.stake_tiers).get(prediction_id)


@dataclass(frozen=True, slots=True)
class PredictionSettlementOutcome:
    prediction_id: str
    fixture_id: int
    state: SettlementOutcomeState
    resolution_status: ResolutionStatus | None
    reason_codes: tuple[SettlementFailureReasonCode, ...]
    processed_at: datetime
    result_rule_version: str | None = None
    bankroll_rule_version: str | None = None


@dataclass(frozen=True, slots=True)
class SettlementBatchReport:
    outcomes: tuple[PredictionSettlementOutcome, ...]
    processed_count: int
    settled_count: int
    won_count: int
    lost_count: int
    void_count: int
    pending_count: int
    unresolved_count: int
    skipped_duplicates: int
    failed_count: int
    started_at: datetime
    completed_at: datetime
    rule_version: str
