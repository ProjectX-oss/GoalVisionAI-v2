"""Versioned Official eligibility and deterministic ranking policy."""

from dataclasses import dataclass
from decimal import Decimal

from app.market_value_assessment import (
    FreshnessState,
    MarketSelection,
    MarketType,
    ValueClassification,
)
from app.risk_management import DEFAULT_OFFICIAL_RISK_POLICY, RiskProductScope


@dataclass(frozen=True, slots=True)
class OfficialPredictionSelectionPolicy:
    version: str = "official-prediction-selection-policy-v1"
    bankroll_scope: RiskProductScope = RiskProductScope.OFFICIAL
    destination_scope: RiskProductScope = RiskProductScope.OFFICIAL
    minimum_decimal_odds: Decimal = Decimal("1.60")
    minimum_expected_value: Decimal = (
        DEFAULT_OFFICIAL_RISK_POLICY.minimum_expected_value
    )
    strong_expected_value: Decimal = (
        DEFAULT_OFFICIAL_RISK_POLICY.strong_expected_value
    )
    minimum_fair_probability: Decimal = Decimal("0.001")
    maximum_fair_probability: Decimal = Decimal("0.999")
    minimum_time_before_kickoff_seconds: int = 300
    maximum_assessment_count: int = 100
    maximum_selected_predictions_per_match: int = 1
    supported_markets: tuple[MarketType, ...] = (
        MarketType.MATCH_WINNER,
        MarketType.DOUBLE_CHANCE,
        MarketType.TOTALS,
        MarketType.BTTS,
    )
    required_value_classifications: tuple[ValueClassification, ...] = (
        ValueClassification.POSITIVE_VALUE,
        ValueClassification.STRONG_VALUE,
    )
    allow_aging_assessments: bool = False
    allow_stale_assessments: bool = False
    unknown_publication_state_blocks: bool = True
    supported_value_policy_versions: tuple[str, ...] = (
        "market-value-assessment-policy-v1",
    )
    metadata_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.metadata_version.strip():
            raise ValueError("Official selection policy identity is required.")
        if (
            self.bankroll_scope is not RiskProductScope.OFFICIAL
            or self.destination_scope is not RiskProductScope.OFFICIAL
        ):
            raise ValueError("Official selection v1 supports Official scopes only.")
        decimal_values = (
            self.minimum_decimal_odds,
            self.minimum_expected_value,
            self.strong_expected_value,
            self.minimum_fair_probability,
            self.maximum_fair_probability,
        )
        if any(
            not isinstance(value, Decimal) or not value.is_finite()
            for value in decimal_values
        ):
            raise TypeError("Official selection thresholds must be finite Decimals.")
        if self.minimum_decimal_odds != Decimal("1.60"):
            raise ValueError("Official v1 minimum decimal odds must remain 1.60.")
        if not Decimal(0) <= self.minimum_expected_value < self.strong_expected_value:
            raise ValueError("Official EV thresholds must increase.")
        if not Decimal(0) < self.minimum_fair_probability < self.maximum_fair_probability < Decimal(1):
            raise ValueError("Official fair-probability bounds are invalid.")
        if self.minimum_time_before_kickoff_seconds < 0:
            raise ValueError("Official kickoff lead time cannot be negative.")
        if self.maximum_assessment_count <= 0:
            raise ValueError("Official selection collection limit must be positive.")
        if self.maximum_selected_predictions_per_match != 1:
            raise ValueError("Official selection v1 selects at most one single market.")
        if self.supported_markets != (
            MarketType.MATCH_WINNER,
            MarketType.DOUBLE_CHANCE,
            MarketType.TOTALS,
            MarketType.BTTS,
        ):
            raise ValueError("Official selection v1 market scope cannot be expanded.")
        if self.required_value_classifications != (
            ValueClassification.POSITIVE_VALUE,
            ValueClassification.STRONG_VALUE,
        ):
            raise ValueError("Official selection value classes cannot be weakened.")
        if self.allow_stale_assessments:
            raise ValueError("Official selection v1 does not permit stale assessments.")
        if not self.unknown_publication_state_blocks:
            raise ValueError("Official selection must fail closed on unknown publication state.")
        if not self.supported_value_policy_versions:
            raise ValueError("Supported upstream value policy versions are required.")


@dataclass(frozen=True, slots=True)
class OfficialPredictionRankingPolicy:
    version: str = "official-prediction-ranking-policy-v1"
    market_priority: tuple[MarketType, ...] = (
        MarketType.MATCH_WINNER,
        MarketType.DOUBLE_CHANCE,
        MarketType.TOTALS,
        MarketType.BTTS,
    )
    selection_priority: tuple[MarketSelection, ...] = (
        MarketSelection.HOME,
        MarketSelection.DRAW,
        MarketSelection.AWAY,
        MarketSelection.HOME_DRAW,
        MarketSelection.HOME_AWAY,
        MarketSelection.DRAW_AWAY,
        MarketSelection.OVER,
        MarketSelection.UNDER,
        MarketSelection.YES,
        MarketSelection.NO,
    )
    line_priority: tuple[Decimal | None, ...] = (
        None,
        Decimal("1.5"),
        Decimal("2.5"),
        Decimal("3.5"),
    )
    freshness_priority: tuple[FreshnessState, ...] = (
        FreshnessState.FRESH,
        FreshnessState.AGING,
        FreshnessState.STALE,
        FreshnessState.EXPIRED,
    )

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Official ranking policy version is required.")
        for values, label in (
            (self.market_priority, "market"),
            (self.selection_priority, "selection"),
            (self.line_priority, "line"),
            (self.freshness_priority, "freshness"),
        ):
            if not values or len(values) != len(set(values)):
                raise ValueError(f"Official ranking {label} priority is invalid.")
        if self.market_priority != (
            MarketType.MATCH_WINNER,
            MarketType.DOUBLE_CHANCE,
            MarketType.TOTALS,
            MarketType.BTTS,
        ):
            raise ValueError("Official ranking v1 market priority is fixed.")
        if self.selection_priority != (
            MarketSelection.HOME,
            MarketSelection.DRAW,
            MarketSelection.AWAY,
            MarketSelection.HOME_DRAW,
            MarketSelection.HOME_AWAY,
            MarketSelection.DRAW_AWAY,
            MarketSelection.OVER,
            MarketSelection.UNDER,
            MarketSelection.YES,
            MarketSelection.NO,
        ):
            raise ValueError("Official ranking v1 selection priority is fixed.")
        if self.line_priority != (
            None,
            Decimal("1.5"),
            Decimal("2.5"),
            Decimal("3.5"),
        ):
            raise ValueError("Official ranking v1 line priority is fixed.")
        if self.freshness_priority != (
            FreshnessState.FRESH,
            FreshnessState.AGING,
            FreshnessState.STALE,
            FreshnessState.EXPIRED,
        ):
            raise ValueError("Official ranking v1 freshness priority is fixed.")


DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY = OfficialPredictionSelectionPolicy()
DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY = OfficialPredictionRankingPolicy()
