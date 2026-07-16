from dataclasses import dataclass
from decimal import Decimal

from .models import (
    ExposureLimit,
    ExposureType,
    RiskProductScope,
    RiskReason,
    StakeStars,
)


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    version: str = "official-risk-v1"
    product_scope: RiskProductScope = RiskProductScope.OFFICIAL
    explicit_non_official_policy: bool = False
    currency: str = "EUR"
    currency_quantum: Decimal = Decimal("0.01")
    minimum_stake_percentage: Decimal = Decimal("0.01")
    standard_stake_percentage: Decimal = Decimal("0.02")
    maximum_stake_percentage: Decimal = Decimal("0.03")
    minimum_expected_value: Decimal = Decimal("0.02")
    strong_expected_value: Decimal = Decimal("0.05")
    exceptional_expected_value: Decimal = Decimal("0.10")
    minimum_calibration_sample: int = 100
    minimum_model_sample: int = 100
    strong_confidence_threshold: Decimal = Decimal("0.70")
    exceptional_confidence_threshold: Decimal = Decimal("0.80")
    strong_uncertainty_maximum: Decimal = Decimal("0.20")
    exceptional_uncertainty_maximum: Decimal = Decimal("0.10")
    caution_drawdown_threshold: Decimal = Decimal("0.05")
    defensive_drawdown_threshold: Decimal = Decimal("0.10")
    halted_drawdown_threshold: Decimal = Decimal("0.15")
    loss_streak_minimum_cap: int = 3
    loss_streak_review: int = 5
    review_required_minimum_stake_only: bool = True
    star_mapping: tuple[tuple[Decimal, StakeStars], ...] = (
        (Decimal("0.01"), StakeStars.ONE),
        (Decimal("0.02"), StakeStars.TWO),
        (Decimal("0.03"), StakeStars.THREE),
    )
    exposure_limits: tuple[ExposureLimit, ...] = (
        ExposureLimit(
            ExposureType.SINGLE_PREDICTION,
            Decimal("0.03"),
            RiskReason.SINGLE_STAKE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.DAILY_TOTAL,
            Decimal("0.10"),
            RiskReason.DAILY_EXPOSURE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.COMPETITION_TOTAL,
            Decimal("0.05"),
            RiskReason.COMPETITION_EXPOSURE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.FIXTURE_TOTAL,
            Decimal("0.03"),
            RiskReason.FIXTURE_EXPOSURE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.TEAM_TOTAL,
            Decimal("0.05"),
            RiskReason.TEAM_EXPOSURE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.MARKET_TOTAL,
            Decimal("0.05"),
            RiskReason.MARKET_EXPOSURE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.CORRELATED_GROUP_TOTAL,
            Decimal("0.05"),
            RiskReason.CORRELATED_EXPOSURE_LIMIT,
        ),
        ExposureLimit(
            ExposureType.UNSETTLED_TOTAL,
            Decimal("0.10"),
            RiskReason.UNSETTLED_EXPOSURE_LIMIT,
        ),
    )

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.currency.strip():
            raise ValueError("Risk policy version and currency are required.")
        if (
            self.product_scope is not RiskProductScope.OFFICIAL
            and not self.explicit_non_official_policy
        ):
            from .models import UnsupportedRiskProductPolicy

            raise UnsupportedRiskProductPolicy(
                "Non-Official scopes require an explicit product policy."
            )
        if (
            self.product_scope is RiskProductScope.OFFICIAL
            and (self.currency != "EUR" or self.currency_quantum != Decimal("0.01"))
        ):
            raise ValueError("Official risk recommendations use EUR cents.")
        if self.product_scope is RiskProductScope.OFFICIAL and not (
            self.minimum_stake_percentage == Decimal("0.01")
            < self.standard_stake_percentage == Decimal("0.02")
            < self.maximum_stake_percentage == Decimal("0.03")
        ):
            raise ValueError("Official stake percentages must remain 1%, 2%, and 3%.")
        if not (
            Decimal("0")
            < self.minimum_stake_percentage
            <= self.standard_stake_percentage
            <= self.maximum_stake_percentage
            <= Decimal("1")
        ):
            raise ValueError("Risk stake percentages must be ordered within (0, 1].")
        if not (
            self.minimum_expected_value
            < self.strong_expected_value
            < self.exceptional_expected_value
        ):
            raise ValueError("Expected-value thresholds must increase.")
        if not (
            Decimal("0")
            < self.caution_drawdown_threshold
            < self.defensive_drawdown_threshold
            < self.halted_drawdown_threshold
            <= Decimal("1")
        ):
            raise ValueError("Drawdown thresholds must increase within (0, 1].")
        if self.loss_streak_minimum_cap <= 0 or (
            self.loss_streak_review <= self.loss_streak_minimum_cap
        ):
            raise ValueError("Loss-streak thresholds must increase.")
        if self.product_scope is RiskProductScope.OFFICIAL and self.star_mapping != (
            (Decimal("0.01"), StakeStars.ONE),
            (Decimal("0.02"), StakeStars.TWO),
            (Decimal("0.03"), StakeStars.THREE),
        ):
            raise ValueError("Official public risk stars map deterministically to 1-3.")
        types = tuple(item.exposure_type for item in self.exposure_limits)
        if len(set(types)) != len(types):
            raise ValueError("Exposure-limit types must be unique.")


DEFAULT_OFFICIAL_RISK_POLICY = RiskPolicy()
