"""Central versioned policy for factual reasoning and presentation."""

from dataclasses import dataclass
from decimal import Decimal

from app.real_match_lab_analysis.fingerprint import fingerprint


@dataclass(frozen=True, slots=True)
class ReasoningPolicy:
    version: str = "goalvision-prediction-reasoning-policy-v1"
    maximum_public_supporting_factors: int = 4
    maximum_public_risk_factors: int = 3
    maximum_operator_factors: int = 78
    materiality_threshold: Decimal = Decimal("0.025")
    materiality_share_threshold: Decimal = Decimal("0.02")
    score_tolerance: Decimal = Decimal("0.000000001")
    probability_tolerance: Decimal = Decimal("0.000000001")
    large_calibration_adjustment: Decimal = Decimal("0.08")
    extreme_probability: Decimal = Decimal("0.95")
    ev_sensitivity_interval: Decimal = Decimal("0.01")
    stability_perturbation: Decimal = Decimal("0.05")
    public_message_character_limit: int = 1800
    telegram_length_reserve: int = 500
    percentage_precision: int = 1
    odds_precision: int = 2
    prohibited_phrases: tuple[str, ...] = (
        "garantēta peļņa", "droša likme", "noteikti uzvarēs", "AI thinks",
        "strong defense", "team is in good form", "market underestimates",
        "home advantage", "lineup advantage", "injury impact",
    )
    certainty_blacklist: tuple[str, ...] = ("garantēti", "neapšaubāmi", "100%", "bez riska")

    @property
    def policy_fingerprint(self) -> str:
        return fingerprint(self)


DEFAULT_REASONING_POLICY = ReasoningPolicy()
