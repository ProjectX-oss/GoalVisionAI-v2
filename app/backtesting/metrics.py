from decimal import Decimal, localcontext
from typing import Iterable

from .models import BacktestMetrics, EvaluationOutcome, HistoricalEvaluationRecord


ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


class BacktestMetricsService:
    """Calculates deterministic metrics for immutable one-unit bet records."""

    def evaluate(
        self,
        records: Iterable[HistoricalEvaluationRecord],
    ) -> BacktestMetrics:
        with localcontext() as context:
            context.prec = 50
            return self._evaluate(records)

    def _evaluate(
        self,
        records: Iterable[HistoricalEvaluationRecord],
    ) -> BacktestMetrics:
        ordered = tuple(sorted(records, key=self._order_key))
        total_bets = len(ordered)
        wins = sum(record.outcome is EvaluationOutcome.WON for record in ordered)
        losses = sum(record.outcome is EvaluationOutcome.LOST for record in ordered)
        voids = sum(record.outcome is EvaluationOutcome.VOID for record in ordered)
        total_profit = sum((record.profit_loss for record in ordered), ZERO)
        decided = wins + losses
        scored = tuple(
            record
            for record in ordered
            if record.outcome is not EvaluationOutcome.VOID
        )
        clv_values = tuple(
            (record.offered_odds / record.closing_odds) - ONE
            for record in ordered
            if record.closing_odds is not None
        )

        return BacktestMetrics(
            total_bets=total_bets,
            wins=wins,
            losses=losses,
            voids=voids,
            hit_rate=(Decimal(wins) / Decimal(decided) if decided else ZERO),
            roi=(total_profit / Decimal(total_bets) if total_bets else ZERO),
            total_profit=total_profit,
            average_odds=self._average(
                tuple(record.offered_odds for record in ordered)
            ),
            maximum_drawdown=self._maximum_drawdown(ordered),
            brier_score=self._brier_score(scored),
            log_loss=self._log_loss(scored),
            average_clv=(self._average(clv_values) if clv_values else None),
            positive_clv_percentage=(
                Decimal(sum(value > ZERO for value in clv_values))
                / Decimal(len(clv_values))
                * HUNDRED
                if clv_values
                else None
            ),
            average_probability=self._average(
                tuple(record.model_probability for record in ordered)
            ),
        )

    @staticmethod
    def _order_key(record: HistoricalEvaluationRecord) -> tuple[object, ...]:
        return (
            record.prediction_timestamp,
            record.kickoff_datetime,
            record.fixture_id,
            record.market,
            record.selection,
        )

    @staticmethod
    def _average(values: tuple[Decimal, ...]) -> Decimal:
        if not values:
            return ZERO
        return sum(values, ZERO) / Decimal(len(values))

    @staticmethod
    def _maximum_drawdown(
        records: tuple[HistoricalEvaluationRecord, ...],
    ) -> Decimal:
        balance = ZERO
        peak = ZERO
        maximum = ZERO
        for record in records:
            balance += record.profit_loss
            peak = max(peak, balance)
            maximum = max(maximum, peak - balance)
        return maximum

    @classmethod
    def _brier_score(
        cls,
        records: tuple[HistoricalEvaluationRecord, ...],
    ) -> Decimal:
        if not records:
            return ZERO
        errors = tuple(
            (
                record.model_probability
                - (ONE if record.outcome is EvaluationOutcome.WON else ZERO)
            )
            ** 2
            for record in records
        )
        return cls._average(errors)

    @classmethod
    def _log_loss(
        cls,
        records: tuple[HistoricalEvaluationRecord, ...],
    ) -> Decimal:
        if not records:
            return ZERO
        with localcontext() as context:
            context.prec = 50
            losses: list[Decimal] = []
            for record in records:
                probability = record.model_probability
                won = record.outcome is EvaluationOutcome.WON
                likelihood = probability if won else ONE - probability
                if likelihood == ZERO:
                    return Decimal("Infinity")
                losses.append(-likelihood.ln())
            return sum(losses, ZERO) / Decimal(len(losses))
