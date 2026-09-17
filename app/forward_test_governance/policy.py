"""Conservative, immutable governance policy."""

from dataclasses import dataclass
from decimal import Decimal

from app.real_match_lab_analysis.fingerprint import fingerprint


@dataclass(frozen=True, slots=True)
class GovernancePolicy:
    policy_id: str = "goalvision-forward-test-governance-policy"
    version: str = "goalvision-forward-test-governance-policy-v1"
    timezone: str = "Europe/Riga"
    minimum_total_settled_sample: int = 30
    minimum_recent_window_sample: int = 20
    minimum_scope_sample: int = 10
    minimum_calibration_bin_sample: int = 5
    minimum_explanation_sample: int = 10
    warm_up_sample: int = 10
    warning_consecutive_evaluations: int = 2
    blocking_consecutive_evaluations: int = 2
    recovery_consecutive_evaluations: int = 3
    maximum_evaluation_age_hours: int = 24
    brier_warning: Decimal = Decimal("0.27")
    brier_block: Decimal = Decimal("0.34")
    log_loss_warning: Decimal = Decimal("0.78")
    log_loss_block: Decimal = Decimal("1.00")
    ece_warning: Decimal = Decimal("0.12")
    ece_block: Decimal = Decimal("0.20")
    probability_bias_warning: Decimal = Decimal("0.10")
    probability_bias_block: Decimal = Decimal("0.18")
    missingness_warning: Decimal = Decimal("0.15")
    missingness_block: Decimal = Decimal("0.30")
    psi_warning: Decimal = Decimal("0.20")
    psi_block: Decimal = Decimal("0.35")
    stale_odds_warning: Decimal = Decimal("0.10")
    stale_odds_block: Decimal = Decimal("0.25")
    market_concentration_warning: Decimal = Decimal("0.60")
    explanation_fragile_warning: Decimal = Decimal("0.25")
    explanation_fragile_block: Decimal = Decimal("0.50")
    audit_failure_warning: Decimal = Decimal("0.10")
    audit_failure_block: Decimal = Decimal("0.25")
    rolling_observation_windows: tuple[int,...] = (7,20,50)
    rolling_day_windows: tuple[int,...] = (7,30)

    @property
    def fingerprint(self)->str:return fingerprint(self)


DEFAULT_POLICY=GovernancePolicy()
