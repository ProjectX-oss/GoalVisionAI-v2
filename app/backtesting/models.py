from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class EvaluationOutcome(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"


@dataclass(frozen=True, slots=True)
class HistoricalEvaluationRecord:
    """Immutable inputs and outcome for one historical one-unit evaluation."""

    fixture_id: int
    competition: str
    kickoff_datetime: datetime
    prediction_timestamp: datetime
    feature_timestamp: datetime
    odds_timestamp: datetime
    market: str
    selection: str
    model_probability: Decimal
    offered_odds: Decimal
    closing_odds: Decimal | None
    result: str
    outcome: EvaluationOutcome
    profit_loss: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("Outcome must be an EvaluationOutcome.")
        for name, value in (
            ("model probability", self.model_probability),
            ("offered odds", self.offered_odds),
            ("profit/loss", self.profit_loss),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{name.title()} must be a Decimal.")
        if self.closing_odds is not None and not isinstance(
            self.closing_odds, Decimal
        ):
            raise TypeError("Closing odds must be a Decimal when provided.")
        if self.fixture_id <= 0:
            raise ValueError("Fixture ID must be positive.")
        for name, value in (
            ("competition", self.competition),
            ("market", self.market),
            ("selection", self.selection),
            ("result", self.result),
        ):
            if not value.strip():
                raise ValueError(f"{name.replace('_', ' ').title()} must not be empty.")
        for name, value in (
            ("kickoff", self.kickoff_datetime),
            ("prediction", self.prediction_timestamp),
            ("feature", self.feature_timestamp),
            ("odds", self.odds_timestamp),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name.title()} timestamp must be timezone-aware.")
        if self.prediction_timestamp > self.kickoff_datetime:
            raise ValueError("Prediction timestamp must not be after kickoff.")
        if self.feature_timestamp > self.prediction_timestamp:
            raise ValueError(
                "Feature timestamp must not be newer than prediction timestamp."
            )
        if self.odds_timestamp > self.prediction_timestamp:
            raise ValueError(
                "Odds timestamp must not be newer than prediction timestamp."
            )
        if not self.model_probability.is_finite() or not (
            Decimal("0") <= self.model_probability <= Decimal("1")
        ):
            raise ValueError("Model probability must be finite and between 0 and 1.")
        if not self.offered_odds.is_finite() or self.offered_odds <= Decimal("1"):
            raise ValueError("Offered decimal odds must be finite and greater than 1.")
        if self.closing_odds is not None and (
            not self.closing_odds.is_finite() or self.closing_odds <= Decimal("1")
        ):
            raise ValueError("Closing decimal odds must be finite and greater than 1.")
        if not self.profit_loss.is_finite():
            raise ValueError("Profit/loss must be finite.")
        if self.outcome is EvaluationOutcome.WON and self.profit_loss <= 0:
            raise ValueError("Won evaluations require positive profit/loss.")
        if self.outcome is EvaluationOutcome.LOST and self.profit_loss >= 0:
            raise ValueError("Lost evaluations require negative profit/loss.")
        if self.outcome is EvaluationOutcome.VOID and self.profit_loss != 0:
            raise ValueError("Void evaluations require zero profit/loss.")


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    """Aggregate metrics with fractional hit rate/ROI and percentage CLV rate.

    Void records are excluded from hit rate, Brier Score, and Log Loss. ROI is
    total profit divided by the number of one-unit records. Average CLV uses
    ``offered_odds / closing_odds - 1`` and excludes missing closing odds.
    """

    total_bets: int
    wins: int
    losses: int
    voids: int
    hit_rate: Decimal
    roi: Decimal
    total_profit: Decimal
    average_odds: Decimal
    maximum_drawdown: Decimal
    brier_score: Decimal
    log_loss: Decimal
    average_clv: Decimal | None
    positive_clv_percentage: Decimal | None
    average_probability: Decimal
