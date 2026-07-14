from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.results import ResolutionStatus


class BankrollProduct(str, Enum):
    OFFICIAL = "OFFICIAL"
    LIVE = "LIVE"
    HIGH_RISK = "HIGH_RISK"
    COMBO = "COMBO"
    LAB = "LAB"


class StakeTier(str, Enum):
    STANDARD = "STANDARD"
    STRONG = "STRONG"
    ELITE = "ELITE"


def _validate_money(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal.")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite.")
    if value.as_tuple().exponent < -2:
        raise ValueError(f"{field_name} must use at most two decimal places.")


@dataclass(frozen=True, slots=True)
class BankrollAccount:
    product_id: BankrollProduct
    currency: str
    starting_balance: Decimal
    balance: Decimal

    def __post_init__(self) -> None:
        _validate_money(self.starting_balance, "Starting balance")
        _validate_money(self.balance, "Balance")
        if not self.currency.strip():
            raise ValueError("Currency must not be empty.")
        if self.starting_balance <= Decimal("0"):
            raise ValueError("Starting balance must be positive.")
        if self.balance < Decimal("0"):
            raise ValueError("Balance must not be negative.")


@dataclass(frozen=True, slots=True)
class StakeRecommendation:
    product_id: BankrollProduct
    tier: StakeTier
    percentage: Decimal
    public_stars: int
    opening_balance: Decimal
    stake: Decimal
    currency: str
    rule_version: str


@dataclass(frozen=True, slots=True)
class BankrollSettlementInput:
    product_id: BankrollProduct
    prediction_id: str
    fixture_id: int
    status: ResolutionStatus
    stake_tier: StakeTier
    odds: Decimal | None
    settled_at: datetime

    def __post_init__(self) -> None:
        if not self.prediction_id.strip():
            raise ValueError("Prediction ID must not be empty.")
        if self.fixture_id <= 0:
            raise ValueError("Fixture ID must be positive.")
        if self.odds is not None and not isinstance(self.odds, Decimal):
            raise TypeError("Odds must be a Decimal when provided.")
        if self.odds is not None and not self.odds.is_finite():
            raise ValueError("Odds must be finite.")
        if self.settled_at.tzinfo is None:
            raise ValueError("Settlement timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class BankrollTransaction:
    product_id: BankrollProduct
    prediction_id: str
    fixture_id: int
    opening_balance: Decimal
    stake: Decimal
    odds: Decimal
    gross_return: Decimal
    profit_loss: Decimal
    closing_balance: Decimal
    settlement_status: ResolutionStatus
    stake_tier: StakeTier
    settled_at: datetime
    currency: str
    rule_version: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.opening_balance, "Opening balance"),
            (self.stake, "Stake"),
            (self.gross_return, "Gross return"),
            (self.profit_loss, "Profit/loss"),
            (self.closing_balance, "Closing balance"),
        ):
            _validate_money(value, field_name)
        if self.settlement_status not in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }:
            raise ValueError("Transactions require a terminal settlement status.")
        if not isinstance(self.odds, Decimal) or not self.odds.is_finite():
            raise TypeError("Transaction odds must be a finite Decimal.")
        if self.stake <= Decimal("0"):
            raise ValueError("Transaction stake must be positive.")
        if self.closing_balance < Decimal("0"):
            raise ValueError("Closing balance must not be negative.")
        if self.settled_at.tzinfo is None:
            raise ValueError("Settlement timestamp must be timezone-aware.")
        if not self.rule_version.strip():
            raise ValueError("Settlement rule version must not be empty.")


@dataclass(frozen=True, slots=True)
class BankrollSnapshot:
    product_id: BankrollProduct
    currency: str
    starting_balance: Decimal
    balance: Decimal
    transaction_count: int
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class BankrollSettlementResult:
    product_id: BankrollProduct
    prediction_id: str
    fixture_id: int
    status: ResolutionStatus
    applied: bool
    transaction: BankrollTransaction | None
    snapshot: BankrollSnapshot
