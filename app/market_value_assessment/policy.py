"""Versioned numeric, compatibility, and freshness policy."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN


@dataclass(frozen=True, slots=True)
class MarketValueAssessmentPolicy:
    version: str = "market-value-assessment-policy-v1"
    mapping_version: str = "market-mapping-v1"
    probability_quantum: Decimal = Decimal("0.000001")
    odds_quantum: Decimal = Decimal("0.000001")
    ev_quantum: Decimal = Decimal("0.000001")
    edge_quantum: Decimal = Decimal("0.000001")
    fair_odds_quantum: Decimal = Decimal("0.000001")
    structural_minimum_odds: Decimal = Decimal("1.00")
    structural_maximum_odds: Decimal = Decimal("1000")
    odds_fresh_seconds: int = 300
    odds_aging_seconds: int = 900
    odds_stale_seconds: int = 1800
    calibrated_fresh_seconds: int = 1800
    calibrated_aging_seconds: int = 7200
    minimum_time_before_kickoff_seconds: int = 300
    positive_value_threshold: Decimal = Decimal("0.02")
    strong_value_threshold: Decimal = Decimal("0.05")
    supported_assembly_policy_versions: tuple[str, ...] = (
        "calibrated-market-probability-policy-v1",
    )
    supported_currencies: tuple[str, ...] = ("EUR", "USD", "GBP")
    allow_odds_older_than_calibration: bool = True
    stale_is_actionable: bool = False
    rounding: str = ROUND_HALF_EVEN

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.mapping_version.strip():
            raise ValueError("Value-assessment policy versions are required.")
        decimals = (
            self.probability_quantum,
            self.odds_quantum,
            self.ev_quantum,
            self.edge_quantum,
            self.fair_odds_quantum,
            self.structural_minimum_odds,
            self.structural_maximum_odds,
            self.positive_value_threshold,
            self.strong_value_threshold,
        )
        if any(
            not isinstance(value, Decimal) or not value.is_finite()
            for value in decimals
        ):
            raise TypeError("Value-assessment numeric policy must use finite Decimals.")
        if any(
            quantum <= 0
            for quantum in (
                self.probability_quantum,
                self.odds_quantum,
                self.ev_quantum,
                self.edge_quantum,
                self.fair_odds_quantum,
            )
        ):
            raise ValueError("Value-assessment quantization must be positive.")
        if not Decimal(1) <= self.structural_minimum_odds < self.structural_maximum_odds:
            raise ValueError("Structural odds bounds are invalid.")
        if not Decimal(0) <= self.positive_value_threshold <= self.strong_value_threshold:
            raise ValueError("Value classification thresholds are invalid.")
        if not 0 <= self.odds_fresh_seconds <= self.odds_aging_seconds <= self.odds_stale_seconds:
            raise ValueError("Odds freshness thresholds are invalid.")
        if not 0 <= self.calibrated_fresh_seconds <= self.calibrated_aging_seconds:
            raise ValueError("Calibrated freshness thresholds are invalid.")
        if self.minimum_time_before_kickoff_seconds < 0:
            raise ValueError("Minimum kickoff lead time cannot be negative.")
        if not self.supported_assembly_policy_versions:
            raise ValueError("At least one calibrated assembly policy is required.")
        if any(
            not isinstance(currency, str)
            or len(currency) != 3
            or currency != currency.upper()
            for currency in self.supported_currencies
        ):
            raise ValueError("Supported currencies must be uppercase ISO-style codes.")


DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY = MarketValueAssessmentPolicy()
