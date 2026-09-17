from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from .models import EvidenceCategory


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    category: EvidenceCategory
    required: bool
    blocking_when_stale: bool
    review_when_partial: bool


@dataclass(frozen=True, slots=True)
class ExposureLimits:
    per_prediction: Decimal
    daily_total: Decimal
    competition_total: Decimal
    correlated_total: Decimal

    def __post_init__(self) -> None:
        for value in (
            self.per_prediction,
            self.daily_total,
            self.competition_total,
            self.correlated_total,
        ):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError("Exposure limits must be positive finite Decimals.")


DEFAULT_EVIDENCE_REQUIREMENTS = (
    EvidenceRequirement(EvidenceCategory.ODDS, True, True, True),
    EvidenceRequirement(EvidenceCategory.TEAM_FORM, True, True, True),
    EvidenceRequirement(
        EvidenceCategory.COMPETITION_CONTEXT,
        True,
        True,
        True,
    ),
    EvidenceRequirement(EvidenceCategory.LINEUP, False, False, True),
    EvidenceRequirement(EvidenceCategory.INJURIES, False, False, True),
    EvidenceRequirement(EvidenceCategory.MODEL_FEATURES, True, True, True),
    EvidenceRequirement(EvidenceCategory.MARKET_CONSENSUS, False, False, True),
    EvidenceRequirement(EvidenceCategory.CALIBRATION, True, True, True),
)


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    version: str = "official-quality-gate-v1"
    product_scope: str = "OFFICIAL"
    minimum_single_odds: Decimal = Decimal("1.60")
    maximum_odds_age: timedelta = timedelta(minutes=15)
    forbidden_markets: tuple[str, ...] = ()
    combo_exception_enabled: bool = True
    maximum_combo_selections: int = 2
    minimum_combo_odds: Decimal = Decimal("2.00")
    combo_high_confidence_threshold: Decimal = Decimal("0.75")
    calibration_required: bool = True
    identity_calibration_allowed: bool = False
    raw_probability_allowed: bool = False
    minimum_calibration_sample_size: int = 100
    minimum_model_sample_size: int = 100
    minimum_expected_value: Decimal = Decimal("0")
    market_disagreement_review_threshold: Decimal = Decimal("0.10")
    market_disagreement_rejection_threshold: Decimal = Decimal("0.20")
    uncertainty_review_threshold: Decimal = Decimal("0.20")
    uncertainty_rejection_threshold: Decimal = Decimal("0.35")
    exposure_limits: ExposureLimits = ExposureLimits(
        per_prediction=Decimal("1"),
        daily_total=Decimal("10"),
        competition_total=Decimal("5"),
        correlated_total=Decimal("2"),
    )
    evidence_requirements: tuple[EvidenceRequirement, ...] = (
        DEFAULT_EVIDENCE_REQUIREMENTS
    )

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Policy version must not be empty.")
        if not self.product_scope.strip():
            raise ValueError("Policy product scope must not be empty.")
        self._positive_decimal(self.minimum_single_odds, "Minimum single odds")
        self._positive_decimal(self.minimum_combo_odds, "Minimum combo odds")
        if self.maximum_odds_age < timedelta(0):
            raise ValueError("Maximum odds age must not be negative.")
        if (
            type(self.maximum_combo_selections) is not int
            or self.maximum_combo_selections <= 0
        ):
            raise ValueError("Maximum combo selections must be positive.")
        for value, name in (
            (self.combo_high_confidence_threshold, "Combo confidence"),
            (self.market_disagreement_review_threshold, "Market review"),
            (self.market_disagreement_rejection_threshold, "Market rejection"),
            (self.uncertainty_review_threshold, "Uncertainty review"),
            (self.uncertainty_rejection_threshold, "Uncertainty rejection"),
        ):
            self._unit_interval(value, name)
        if (
            self.market_disagreement_review_threshold
            >= self.market_disagreement_rejection_threshold
        ):
            raise ValueError("Market review threshold must be below rejection.")
        if self.uncertainty_review_threshold >= self.uncertainty_rejection_threshold:
            raise ValueError("Uncertainty review threshold must be below rejection.")
        if (
            type(self.minimum_calibration_sample_size) is not int
            or self.minimum_calibration_sample_size <= 0
        ):
            raise ValueError("Minimum calibration sample size must be positive.")
        if (
            type(self.minimum_model_sample_size) is not int
            or self.minimum_model_sample_size <= 0
        ):
            raise ValueError("Minimum model sample size must be positive.")
        if (
            not isinstance(self.minimum_expected_value, Decimal)
            or not self.minimum_expected_value.is_finite()
        ):
            raise ValueError("Minimum expected value must be a finite Decimal.")
        categories = tuple(item.category for item in self.evidence_requirements)
        if len(set(categories)) != len(categories):
            raise ValueError("Evidence policy categories must be unique.")

    @staticmethod
    def _positive_decimal(value: Decimal, name: str) -> None:
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 1:
            raise ValueError(f"{name} must be a finite decimal odds value above 1.")

    @staticmethod
    def _unit_interval(value: Decimal, name: str) -> None:
        if (
            not isinstance(value, Decimal)
            or not value.is_finite()
            or not Decimal("0") <= value <= Decimal("1")
        ):
            raise ValueError(f"{name} must be a finite Decimal between 0 and 1.")


DEFAULT_OFFICIAL_QUALITY_GATE_POLICY = QualityGatePolicy()
