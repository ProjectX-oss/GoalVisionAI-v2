"""Central immutable policies for Lab-only shadow evaluation."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ShadowEvaluationPolicy:
    version: str = "shadow-evaluation-policy-v1"
    probability_contract_version: str = "canonical-11-target-contract-v1"
    market_value_policy_version: str = "market-value-assessment-policy-v1"
    selection_policy_version: str = "official-prediction-selection-policy-v1"
    comparison_policy_version: str = "shadow-disagreement-policy-v1"
    settlement_policy_version: str = "official-half-goal-settlement-v1"
    metric_policy_version: str = "shadow-evaluation-metrics-v1"
    odds_policy_version: str = "exact-supplied-pre-kickoff-v1"
    minimum_decimal_odds: Decimal = Decimal("1.60")
    minimum_expected_value: Decimal = Decimal("0.02")
    minimum_probability: Decimal = Decimal("0.001")
    maximum_probability: Decimal = Decimal("0.999")
    probability_delta_low: Decimal = Decimal("0.02")
    probability_delta_moderate: Decimal = Decimal("0.05")
    probability_delta_high: Decimal = Decimal("0.10")
    allow_review_recommendation: bool = False
    runtime_enabled: bool = False

    def __post_init__(self) -> None:
        if self.minimum_decimal_odds != Decimal("1.60"):
            raise ValueError("Shadow v1 preserves the Official minimum odds of 1.60.")
        if self.minimum_expected_value != Decimal("0.02"):
            raise ValueError("Shadow v1 requires the reviewed EV threshold of 0.02.")
        if not Decimal(0) < self.minimum_probability < self.maximum_probability < Decimal(1):
            raise ValueError("Probability bounds must be inside (0,1).")


DEFAULT_SHADOW_EVALUATION_POLICY = ShadowEvaluationPolicy()
