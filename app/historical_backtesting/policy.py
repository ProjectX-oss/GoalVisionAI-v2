"""Versioned, fail-closed policy for historical Official backtests."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

from app.market_value_assessment import DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY
from app.official_prediction_selection import (
    DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
)
from app.risk_management import DEFAULT_OFFICIAL_RISK_POLICY


BACKTEST_POLICY_VERSION = "historical-backtesting-policy-v1"
ODDS_SELECTION_POLICY_VERSION = "exact-latest-supplied-pre-kickoff-v1"
DECISION_SNAPSHOT_POLICY = "LATEST_PER_SOURCE_STRICTLY_BEFORE_KICKOFF_V1"
SETTLEMENT_POLICY_VERSION = "official-half-goal-settlement-v1"
BANKROLL_POLICY_VERSION = "isolated-official-eur-bankroll-v1"
METRIC_POLICY_VERSION = "historical-backtesting-metrics-v1"
PREDICTION_IMPLEMENTATION_VERSION = "persisted-historical-artifacts-v1"
METADATA_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class HistoricalBacktestPolicy:
    version: str = BACKTEST_POLICY_VERSION
    odds_selection_policy_version: str = ODDS_SELECTION_POLICY_VERSION
    decision_snapshot_policy: str = DECISION_SNAPSHOT_POLICY
    market_eligibility_policy_version: str = (
        DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.version
    )
    value_policy_version: str = DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY.version
    selection_policy_version: str = (
        DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.version
    )
    ranking_policy_version: str = "historical-official-ranking-adapter-v1"
    staking_policy_version: str = DEFAULT_OFFICIAL_RISK_POLICY.version
    settlement_policy_version: str = SETTLEMENT_POLICY_VERSION
    bankroll_policy_version: str = BANKROLL_POLICY_VERSION
    metric_policy_version: str = METRIC_POLICY_VERSION
    minimum_decimal_odds: Decimal = Decimal("1.60")
    minimum_expected_value: Decimal = Decimal("0.02")
    strong_expected_value: Decimal = Decimal("0.05")
    exceptional_expected_value: Decimal = Decimal("0.10")
    conservative_stake_percentage: Decimal = Decimal("0.01")
    standard_stake_percentage: Decimal = Decimal("0.02")
    maximum_stake_percentage: Decimal = Decimal("0.03")
    maximum_equal_kickoff_exposure: Decimal = Decimal("0.10")
    maximum_odds_age_seconds: int | None = None
    reliability_bin_count: int = 10
    currency_quantum: Decimal = Decimal("0.01")
    rounding: str = ROUND_HALF_EVEN
    metadata_version: str = METADATA_VERSION

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.version,
                self.odds_selection_policy_version,
                self.decision_snapshot_policy,
                self.selection_policy_version,
                self.staking_policy_version,
                self.settlement_policy_version,
                self.bankroll_policy_version,
                self.metric_policy_version,
                self.metadata_version,
            )
        ):
            raise ValueError("Every historical backtest policy version is required.")
        if self.minimum_decimal_odds != Decimal("1.60"):
            raise ValueError("Official minimum decimal odds must remain 1.60.")
        if self.minimum_expected_value != Decimal("0.02"):
            raise ValueError("Official minimum expected value must remain 0.02.")
        if (
            self.conservative_stake_percentage,
            self.standard_stake_percentage,
            self.maximum_stake_percentage,
        ) != (Decimal("0.01"), Decimal("0.02"), Decimal("0.03")):
            raise ValueError("Official historical stakes must remain 1%, 2%, and 3%.")
        if not Decimal(0) < self.maximum_equal_kickoff_exposure <= Decimal(1):
            raise ValueError("Equal-kickoff exposure must be within (0, 1].")
        if self.maximum_odds_age_seconds is not None and self.maximum_odds_age_seconds < 0:
            raise ValueError("Maximum odds age cannot be negative.")
        if self.reliability_bin_count <= 1:
            raise ValueError("At least two reliability bins are required.")

    @property
    def versions(self) -> tuple[tuple[str, str], ...]:
        return (
            ("backtest", self.version),
            ("odds_selection", self.odds_selection_policy_version),
            ("decision_snapshot", self.decision_snapshot_policy),
            ("market_eligibility", self.market_eligibility_policy_version),
            ("value", self.value_policy_version),
            ("selection", self.selection_policy_version),
            ("ranking", self.ranking_policy_version),
            ("staking", self.staking_policy_version),
            ("settlement", self.settlement_policy_version),
            ("bankroll", self.bankroll_policy_version),
            ("metrics", self.metric_policy_version),
        )


DEFAULT_HISTORICAL_BACKTEST_POLICY = HistoricalBacktestPolicy()
