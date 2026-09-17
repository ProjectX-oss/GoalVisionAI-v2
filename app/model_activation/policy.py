"""Conservative, explicit activation and rollback policy."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ModelActivationPolicy:
    version: str = "controlled-model-activation-policy-v1"
    minimum_settled_shadow_evaluations: int = 30
    minimum_shadow_observation_days: int = 14
    minimum_agreement_ratio: Decimal = Decimal("0.50")
    maximum_critical_disagreement_ratio: Decimal = Decimal("0.10")
    maximum_predictive_degradation: Decimal = Decimal("0.01")
    maximum_calibration_degradation: Decimal = Decimal("0.01")
    maximum_betting_performance_degradation: Decimal = Decimal("0.05")
    maximum_drawdown_deterioration: Decimal = Decimal("0.10")
    minimum_evidence_completeness: Decimal = Decimal("0.95")
    required_recommendation: str = "PROMOTE_CHALLENGER"
    required_probability_contract_version: str = "canonical-11-target-contract-v1"
    required_runtime_compatibility_version: str = "probability-calibration-v1"
    warnings_require_manual_override: bool = True
    rollback_enabled: bool = True
    minimum_retained_generations: int = 2

    def __post_init__(self) -> None:
        if self.minimum_settled_shadow_evaluations < 1:
            raise ValueError("A positive settled-shadow minimum is required.")
        if self.minimum_shadow_observation_days < 1:
            raise ValueError("A positive shadow observation duration is required.")
        ratios = (
            self.minimum_agreement_ratio, self.maximum_critical_disagreement_ratio,
            self.minimum_evidence_completeness,
        )
        if any(not Decimal(0) <= item <= Decimal(1) for item in ratios):
            raise ValueError("Activation policy ratios must be inside [0,1].")
        if any(item < 0 for item in (
            self.maximum_predictive_degradation,
            self.maximum_calibration_degradation,
            self.maximum_betting_performance_degradation,
            self.maximum_drawdown_deterioration,
        )):
            raise ValueError("Degradation allowances cannot be negative.")
        if self.required_recommendation != "PROMOTE_CHALLENGER":
            raise ValueError("Activation v1 requires PROMOTE_CHALLENGER.")
        if not self.rollback_enabled or self.minimum_retained_generations < 2:
            raise ValueError("Manual rollback and at least two retained generations are mandatory.")


DEFAULT_MODEL_ACTIVATION_POLICY = ModelActivationPolicy()
