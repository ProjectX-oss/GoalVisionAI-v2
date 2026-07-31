"""Centralized Lab-only selection policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from .models import MarketEvaluation
from app.calibration_freshness import DEFAULT_CALIBRATION_FRESHNESS_POLICY
from app.market_value_assessment import DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY


SUPPORTED_MARKETS = (
    "HOME_WIN", "DRAW", "AWAY_WIN",
    "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5",
    "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO",
)


LAB_MARKET_VALUE_ASSESSMENT_POLICY = replace(
    DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY,
    version="market-value-assessment-policy-lab-v2",
    calibrated_fresh_seconds=(
        DEFAULT_CALIBRATION_FRESHNESS_POLICY.lab_evidence_max_age_seconds
    ),
    calibrated_aging_seconds=(
        DEFAULT_CALIBRATION_FRESHNESS_POLICY.lab_evidence_max_age_seconds
    ),
)


@dataclass(frozen=True, slots=True)
class LabSelectionPolicy:
    version: str = "goalvision-real-match-lab-selection-policy-v1"
    minimum_expected_value: Decimal = Decimal("0")
    official_minimum_odds: Decimal = Decimal("1.60")
    feature_snapshot_max_age_seconds: int = 15 * 60
    lineup_snapshot_max_age_seconds: int = 60 * 60

    def select(
        self, values: tuple[MarketEvaluation, ...]
    ) -> tuple[tuple[MarketEvaluation, ...], MarketEvaluation | None]:
        if any(item.market not in SUPPORTED_MARKETS for item in values):
            raise ValueError("Unsupported or non-single market supplied to Lab policy.")
        eligible = tuple(
            item for item in values
            if item.expected_value > self.minimum_expected_value
            and item.bookmaker_odds > Decimal("1")
            and not item.rejection_reasons
        )
        winner = min(
            eligible,
            key=lambda item: (
                -item.calibrated_probability,
                -item.expected_value,
                SUPPORTED_MARKETS.index(item.market),
                item.value_assessment_id,
            ),
            default=None,
        )
        evaluated = tuple(
            replace(
                item,
                selected=winner is not None
                and item.value_assessment_id == winner.value_assessment_id,
                rejection_reasons=(
                    item.rejection_reasons
                    if item.rejection_reasons
                    else ()
                    if winner is not None
                    and item.value_assessment_id == winner.value_assessment_id
                    else ("LOWER_DETERMINISTIC_RANK",)
                    if item in eligible
                    else ("NON_POSITIVE_EXPECTED_VALUE",)
                ),
            )
            for item in values
        )
        return evaluated, next((item for item in evaluated if item.selected), None)
