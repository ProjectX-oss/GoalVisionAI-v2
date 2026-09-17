from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from app.backtesting import EvaluationOutcome, HistoricalEvaluationRecord

from .models import (
    DrawdownState,
    RiskAssessmentDecision,
    RiskAuditRecord,
    RiskWarning,
    StakeBand,
)


ZERO = Decimal("0")
ONE = Decimal("1")


class StakeStrategy(str, Enum):
    FLAT_ONE_UNIT = "FLAT_ONE_UNIT"
    FIXED_ONE_PERCENT = "FIXED_ONE_PERCENT"
    FIXED_TWO_PERCENT = "FIXED_TWO_PERCENT"
    RECOMMENDED_POLICY = "RECOMMENDED_POLICY"


@dataclass(frozen=True, slots=True)
class RiskBacktestCase:
    record: HistoricalEvaluationRecord
    audit: RiskAuditRecord


@dataclass(frozen=True, slots=True)
class StakeBandPerformance:
    band: StakeBand
    bet_count: int
    total_staked: Decimal
    profit_loss: Decimal


@dataclass(frozen=True, slots=True)
class DrawdownStatePerformance:
    state: DrawdownState
    bet_count: int
    total_staked: Decimal
    profit_loss: Decimal


@dataclass(frozen=True, slots=True)
class StakeStrategyReport:
    strategy: StakeStrategy
    evaluated_bets: int
    placed_bets: int
    skipped_bets: int
    total_staked: Decimal
    profit_loss: Decimal
    roi: Decimal
    maximum_drawdown: Decimal
    maximum_stake: Decimal
    average_stake: Decimal
    stake_distribution: tuple[tuple[str, int], ...]
    largest_losing_streak: int
    ending_bankroll: Decimal
    volatility_proxy: Decimal
    stake_concentration: Decimal
    by_stake_band: tuple[StakeBandPerformance, ...]
    by_drawdown_state: tuple[DrawdownStatePerformance, ...]
    warnings: tuple[RiskWarning, ...]


@dataclass(frozen=True, slots=True)
class StakePolicyComparison:
    starting_bankroll: Decimal
    reports: tuple[StakeStrategyReport, ...]


class RiskPolicyBacktestService:
    """Fixed-policy evaluation only; no threshold fitting or optimization."""

    def compare(
        self,
        cases: tuple[RiskBacktestCase, ...],
        *,
        starting_bankroll: Decimal = Decimal("10000"),
        small_sample_threshold: int = 30,
    ) -> StakePolicyComparison:
        if not starting_bankroll.is_finite() or starting_bankroll <= ZERO:
            raise ValueError("Backtest starting bankroll must be positive.")
        ordered = tuple(
            sorted(
                cases,
                key=lambda item: (
                    item.record.prediction_timestamp,
                    item.record.fixture_id,
                    item.record.market,
                    item.record.selection,
                ),
            )
        )
        return StakePolicyComparison(
            starting_bankroll,
            tuple(
                self._evaluate(
                    ordered,
                    strategy,
                    starting_bankroll,
                    small_sample_threshold,
                )
                for strategy in StakeStrategy
            ),
        )

    def _evaluate(
        self,
        cases: tuple[RiskBacktestCase, ...],
        strategy: StakeStrategy,
        starting_bankroll: Decimal,
        small_sample_threshold: int,
    ) -> StakeStrategyReport:
        with localcontext() as context:
            context.prec = 50
            bankroll = starting_bankroll
            peak = starting_bankroll
            maximum_drawdown = ZERO
            stakes: list[Decimal] = []
            returns: list[Decimal] = []
            bands: list[tuple[StakeBand, Decimal, Decimal]] = []
            states: list[tuple[DrawdownState, Decimal, Decimal]] = []
            losing_streak = 0
            largest_losing_streak = 0
            skipped = 0
            for case in cases:
                stake = self._stake(strategy, case, bankroll)
                if stake is None or stake <= ZERO:
                    skipped += 1
                    continue
                profit = self._profit(case.record, stake)
                bankroll += profit
                peak = max(peak, bankroll)
                maximum_drawdown = max(maximum_drawdown, peak - bankroll)
                stakes.append(stake)
                returns.append(profit)
                band = (
                    case.audit.recommendation.band
                    if strategy is StakeStrategy.RECOMMENDED_POLICY
                    and case.audit.recommendation is not None
                    else self._fixed_band(strategy)
                )
                bands.append((band, stake, profit))
                states.append((case.audit.drawdown_state, stake, profit))
                if case.record.outcome is EvaluationOutcome.LOST:
                    losing_streak += 1
                    largest_losing_streak = max(
                        largest_losing_streak, losing_streak
                    )
                elif case.record.outcome is EvaluationOutcome.WON:
                    losing_streak = 0
            total_staked = sum(stakes, ZERO)
            total_return = sum(returns, ZERO)
            average = total_staked / Decimal(len(stakes)) if stakes else ZERO
            mean_return = total_return / Decimal(len(returns)) if returns else ZERO
            variance = (
                sum(((value - mean_return) ** 2 for value in returns), ZERO)
                / Decimal(len(returns))
                if returns
                else ZERO
            )
            warnings = (
                (RiskWarning.SMALL_EVALUATION_SAMPLE,)
                if len(cases) < small_sample_threshold
                else ()
            )
            return StakeStrategyReport(
                strategy=strategy,
                evaluated_bets=len(cases),
                placed_bets=len(stakes),
                skipped_bets=skipped,
                total_staked=total_staked,
                profit_loss=total_return,
                roi=(total_return / total_staked if total_staked else ZERO),
                maximum_drawdown=maximum_drawdown,
                maximum_stake=max(stakes, default=ZERO),
                average_stake=average,
                stake_distribution=self._distribution(stakes),
                largest_losing_streak=largest_losing_streak,
                ending_bankroll=bankroll,
                volatility_proxy=variance.sqrt(),
                stake_concentration=(
                    max(stakes) / total_staked if total_staked else ZERO
                ),
                by_stake_band=self._band_performance(bands),
                by_drawdown_state=self._state_performance(states),
                warnings=warnings,
            )

    @staticmethod
    def _stake(
        strategy: StakeStrategy,
        case: RiskBacktestCase,
        bankroll: Decimal,
    ) -> Decimal | None:
        if strategy is StakeStrategy.FLAT_ONE_UNIT:
            return ONE
        if strategy is StakeStrategy.FIXED_ONE_PERCENT:
            return bankroll * Decimal("0.01")
        if strategy is StakeStrategy.FIXED_TWO_PERCENT:
            return bankroll * Decimal("0.02")
        if case.audit.final_decision not in {
            RiskAssessmentDecision.ELIGIBLE,
            RiskAssessmentDecision.REDUCED_STAKE,
        } or case.audit.recommendation is None:
            return None
        return bankroll * case.audit.recommendation.internal_stake_percentage

    @staticmethod
    def _profit(record: HistoricalEvaluationRecord, stake: Decimal) -> Decimal:
        if record.outcome is EvaluationOutcome.WON:
            return stake * (record.offered_odds - ONE)
        if record.outcome is EvaluationOutcome.LOST:
            return -stake
        return ZERO

    @staticmethod
    def _fixed_band(strategy: StakeStrategy) -> StakeBand:
        return {
            StakeStrategy.FLAT_ONE_UNIT: StakeBand.NONE,
            StakeStrategy.FIXED_ONE_PERCENT: StakeBand.MINIMUM,
            StakeStrategy.FIXED_TWO_PERCENT: StakeBand.STANDARD,
        }.get(strategy, StakeBand.NONE)

    @staticmethod
    def _distribution(stakes: list[Decimal]) -> tuple[tuple[str, int], ...]:
        counts: dict[str, int] = {}
        for stake in stakes:
            key = format(stake, "f")
            counts[key] = counts.get(key, 0) + 1
        return tuple(sorted(counts.items(), key=lambda item: Decimal(item[0])))

    @staticmethod
    def _band_performance(
        values: list[tuple[StakeBand, Decimal, Decimal]],
    ) -> tuple[StakeBandPerformance, ...]:
        return tuple(
            StakeBandPerformance(
                band,
                sum(item[0] is band for item in values),
                sum((item[1] for item in values if item[0] is band), ZERO),
                sum((item[2] for item in values if item[0] is band), ZERO),
            )
            for band in StakeBand
            if any(item[0] is band for item in values)
        )

    @staticmethod
    def _state_performance(
        values: list[tuple[DrawdownState, Decimal, Decimal]],
    ) -> tuple[DrawdownStatePerformance, ...]:
        return tuple(
            DrawdownStatePerformance(
                state,
                sum(item[0] is state for item in values),
                sum((item[1] for item in values if item[0] is state), ZERO),
                sum((item[2] for item in values if item[0] is state), ZERO),
            )
            for state in DrawdownState
            if any(item[0] is state for item in values)
        )
