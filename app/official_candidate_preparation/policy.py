"""Versioned Official candidate-preparation policy."""

from dataclasses import dataclass
from decimal import Decimal

from app.market_value_assessment import FreshnessState, MarketType
from app.official_prediction_selection import (
    DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
)
from app.risk_management import DEFAULT_OFFICIAL_RISK_POLICY, RiskProductScope


@dataclass(frozen=True, slots=True)
class OfficialCandidatePreparationPolicy:
    version: str = "official-candidate-preparation-policy-v1"
    bankroll_scope: RiskProductScope = RiskProductScope.OFFICIAL
    destination_scope: RiskProductScope = RiskProductScope.OFFICIAL
    currency: str = "EUR"
    minimum_decimal_odds: Decimal = (
        DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.minimum_decimal_odds
    )
    minimum_expected_value: Decimal = (
        DEFAULT_OFFICIAL_RISK_POLICY.minimum_expected_value
    )
    risk_policy_version: str = DEFAULT_OFFICIAL_RISK_POLICY.version
    supported_markets: tuple[MarketType, ...] = (
        MarketType.MATCH_WINNER,
        MarketType.DOUBLE_CHANCE,
        MarketType.TOTALS,
        MarketType.BTTS,
    )
    allowed_freshness_states: tuple[FreshnessState, ...] = (
        FreshnessState.FRESH,
    )
    require_risk_at_or_before_preparation: bool = True
    metadata_version: str = "v1"
    maximum_metadata_items: int = 5
    maximum_metadata_value_length: int = 2048

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.risk_policy_version.strip():
            raise ValueError("Candidate-preparation policy versions are required.")
        if (
            self.bankroll_scope is not RiskProductScope.OFFICIAL
            or self.destination_scope is not RiskProductScope.OFFICIAL
        ):
            raise ValueError("Candidate preparation supports Official scopes only.")
        if self.currency != "EUR":
            raise ValueError("Official candidate preparation supports EUR only.")
        if self.minimum_decimal_odds != Decimal("1.60"):
            raise ValueError("Official minimum decimal odds must remain 1.60.")
        if self.minimum_expected_value != Decimal("0.02"):
            raise ValueError("Official minimum expected value must remain 0.02.")
        if self.risk_policy_version != DEFAULT_OFFICIAL_RISK_POLICY.version:
            raise ValueError("Official candidate preparation requires official-risk-v1.")
        if self.supported_markets != (
            MarketType.MATCH_WINNER,
            MarketType.DOUBLE_CHANCE,
            MarketType.TOTALS,
            MarketType.BTTS,
        ):
            raise ValueError("Official candidate-preparation market scope is fixed.")
        if self.allowed_freshness_states != (FreshnessState.FRESH,):
            raise ValueError("Official v1 candidate preparation requires fresh inputs.")
        if not self.require_risk_at_or_before_preparation:
            raise ValueError("Risk must not postdate candidate preparation.")
        if not self.metadata_version.strip():
            raise ValueError("Candidate-preparation metadata version is required.")
        if self.maximum_metadata_items <= 0 or self.maximum_metadata_value_length <= 0:
            raise ValueError("Candidate-preparation metadata limits must be positive.")
        if self.maximum_metadata_items > 5:
            raise ValueError(
                "Candidate-preparation metadata must leave bounded provenance capacity."
            )


DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY = (
    OfficialCandidatePreparationPolicy()
)
