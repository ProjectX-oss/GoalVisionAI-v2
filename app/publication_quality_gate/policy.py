from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from .models import SupportedMarket


@dataclass(frozen=True, slots=True)
class CalibrationMetricLimits:
    preferred: Decimal
    warning: Decimal
    hard: Decimal

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, Decimal) and value.is_finite() and value >= 0
            for value in (self.preferred, self.warning, self.hard)
        ):
            raise ValueError("Calibration metric limits must be finite Decimals.")
        if not self.preferred < self.warning < self.hard:
            raise ValueError("Calibration metric limits must increase strictly.")


@dataclass(frozen=True, slots=True)
class OfficialQualityGatePolicy:
    """All thresholds for the Official pre-publication eligibility boundary."""

    version: str = "official-publication-quality-gate-v1"
    minimum_odds: Decimal = Decimal("1.60")
    minimum_expected_value: Decimal = Decimal("0.02")
    normal_expected_value: Decimal = Decimal("0.05")
    expected_value_tolerance: Decimal = Decimal("0.0001")
    minimum_probability: Decimal = Decimal("0.001")
    maximum_probability: Decimal = Decimal("0.999")
    maximum_candidate_age: timedelta = timedelta(minutes=30)
    maximum_odds_age: timedelta = timedelta(minutes=15)
    maximum_core_data_age: timedelta = timedelta(minutes=60)
    minimum_calibration_sample_size: int = 100
    brier_limits: CalibrationMetricLimits = CalibrationMetricLimits(
        Decimal("0.20"), Decimal("0.25"), Decimal("0.30")
    )
    log_loss_limits: CalibrationMetricLimits = CalibrationMetricLimits(
        Decimal("0.60"), Decimal("0.75"), Decimal("0.90")
    )
    ece_limits: CalibrationMetricLimits = CalibrationMetricLimits(
        Decimal("0.05"), Decimal("0.10"), Decimal("0.15")
    )
    mce_limits: CalibrationMetricLimits = CalibrationMetricLimits(
        Decimal("0.10"), Decimal("0.20"), Decimal("0.30")
    )
    supported_markets: tuple[SupportedMarket, ...] = tuple(SupportedMarket)
    lineup_sensitive_markets: tuple[SupportedMarket, ...] = (
        SupportedMarket.MATCH_WINNER,
        SupportedMarket.DOUBLE_CHANCE,
    )
    exposure_warning_requires_review: bool = True
    exposure_hard_breach_rejects: bool = True

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Policy version must not be empty.")
        decimals = (
            self.minimum_odds,
            self.minimum_expected_value,
            self.normal_expected_value,
            self.expected_value_tolerance,
            self.minimum_probability,
            self.maximum_probability,
        )
        if not all(isinstance(value, Decimal) and value.is_finite() for value in decimals):
            raise ValueError("Policy numeric thresholds must be finite Decimals.")
        if self.minimum_odds <= 1:
            raise ValueError("Minimum Official odds must exceed one.")
        if not Decimal("0") <= self.minimum_expected_value < self.normal_expected_value:
            raise ValueError("Expected-value thresholds are inconsistent.")
        if self.expected_value_tolerance < 0:
            raise ValueError("Expected-value tolerance must not be negative.")
        if not Decimal("0") < self.minimum_probability < self.maximum_probability < Decimal("1"):
            raise ValueError("Probability limits must be strictly inside (0, 1).")
        if any(
            value < timedelta(0)
            for value in (
                self.maximum_candidate_age,
                self.maximum_odds_age,
                self.maximum_core_data_age,
            )
        ):
            raise ValueError("Freshness durations must not be negative.")
        if type(self.minimum_calibration_sample_size) is not int or self.minimum_calibration_sample_size <= 0:
            raise ValueError("Minimum calibration sample size must be positive.")
        if len(set(self.supported_markets)) != len(self.supported_markets):
            raise ValueError("Supported markets must be unique.")
        if not set(self.lineup_sensitive_markets) <= set(self.supported_markets):
            raise ValueError("Lineup-sensitive markets must be supported.")


DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY = OfficialQualityGatePolicy()
