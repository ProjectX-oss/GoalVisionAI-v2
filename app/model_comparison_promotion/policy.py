"""Central versioned promotion thresholds, gates, weights, and tie-breaks."""

from dataclasses import dataclass
from decimal import Decimal


PROMOTION_POLICY_VERSION = "model-promotion-policy-v1"
EVIDENCE_POLICY_VERSION = "model-promotion-evidence-v1"
COMPATIBILITY_POLICY_VERSION = "model-promotion-compatibility-v1"
SIGNIFICANCE_POLICY_VERSION = "model-promotion-significance-v1"
PREDICTIVE_SCORE_POLICY_VERSION = "model-promotion-predictive-score-v1"
CALIBRATION_SCORE_POLICY_VERSION = "model-promotion-calibration-score-v1"
BETTING_SCORE_POLICY_VERSION = "model-promotion-betting-score-v1"
RISK_SCORE_POLICY_VERSION = "model-promotion-risk-score-v1"
STABILITY_SCORE_POLICY_VERSION = "model-promotion-stability-score-v1"
TIE_BREAK_POLICY_VERSION = "model-promotion-tie-break-v1"


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    version: str = PROMOTION_POLICY_VERSION
    evidence_policy_version: str = EVIDENCE_POLICY_VERSION
    compatibility_policy_version: str = COMPATIBILITY_POLICY_VERSION
    significance_policy_version: str = SIGNIFICANCE_POLICY_VERSION
    predictive_score_policy_version: str = PREDICTIVE_SCORE_POLICY_VERSION
    calibration_score_policy_version: str = CALIBRATION_SCORE_POLICY_VERSION
    betting_score_policy_version: str = BETTING_SCORE_POLICY_VERSION
    risk_score_policy_version: str = RISK_SCORE_POLICY_VERSION
    stability_score_policy_version: str = STABILITY_SCORE_POLICY_VERSION
    tie_break_policy_version: str = TIE_BREAK_POLICY_VERSION
    predictive_weight: Decimal = Decimal("0.20")
    calibration_weight: Decimal = Decimal("0.20")
    betting_weight: Decimal = Decimal("0.25")
    risk_weight: Decimal = Decimal("0.20")
    stability_weight: Decimal = Decimal("0.10")
    evidence_weight: Decimal = Decimal("0.05")
    minimum_promotion_score: Decimal = Decimal("0.60")
    material_improvement: Decimal = Decimal("0.02")
    catastrophic_predictive_degradation: Decimal = Decimal("0.10")
    catastrophic_calibration_degradation: Decimal = Decimal("0.05")
    minimum_roi: Decimal = Decimal("0")
    minimum_yield: Decimal = Decimal("0")
    minimum_net_profit: Decimal = Decimal("0")
    maximum_drawdown_percentage: Decimal = Decimal("0.25")
    maximum_drawdown_degradation: Decimal = Decimal("0.05")
    maximum_volatility_degradation: Decimal = Decimal("0.25")
    insolvency_floor_ratio: Decimal = Decimal("0.05")
    maximum_profit_concentration: Decimal = Decimal("0.70")
    maximum_severe_stability_groups: int = 0
    minimum_group_sample_size: int = 5
    bootstrap_iterations: int = 500
    confidence_level: Decimal = Decimal("0.95")
    allow_partial_challenger_exclusion: bool = True
    require_clv: bool = False

    def __post_init__(self) -> None:
        versions = self.versions
        if not all(value.strip() for _, value in versions):
            raise ValueError("Every promotion policy version is required.")
        weights = self.weights
        if sum((value for _, value in weights), Decimal(0)) != Decimal(1):
            raise ValueError("Promotion score weights must total exactly 1.")
        if any(value < 0 or value > 1 for _, value in weights):
            raise ValueError("Promotion score weights must be bounded by [0, 1].")
        if not Decimal(0) <= self.minimum_promotion_score <= Decimal(1):
            raise ValueError("Minimum promotion score must be within [0, 1].")
        if self.bootstrap_iterations < 100:
            raise ValueError("Bootstrap policy requires at least 100 iterations.")
        if not Decimal(0) < self.confidence_level < Decimal(1):
            raise ValueError("Confidence level must be within (0, 1).")
        if self.minimum_group_sample_size < 1:
            raise ValueError("Group sample threshold must be positive.")

    @property
    def weights(self) -> tuple[tuple[str, Decimal], ...]:
        return (
            ("PREDICTIVE", self.predictive_weight),
            ("CALIBRATION", self.calibration_weight),
            ("BETTING", self.betting_weight),
            ("RISK", self.risk_weight),
            ("STABILITY", self.stability_weight),
            ("EVIDENCE", self.evidence_weight),
        )

    @property
    def versions(self) -> tuple[tuple[str, str], ...]:
        return (
            ("promotion", self.version),
            ("evidence", self.evidence_policy_version),
            ("compatibility", self.compatibility_policy_version),
            ("significance", self.significance_policy_version),
            ("predictive_score", self.predictive_score_policy_version),
            ("calibration_score", self.calibration_score_policy_version),
            ("betting_score", self.betting_score_policy_version),
            ("risk_score", self.risk_score_policy_version),
            ("stability_score", self.stability_score_policy_version),
            ("tie_break", self.tie_break_policy_version),
        )


DEFAULT_PROMOTION_POLICY = PromotionPolicy()
