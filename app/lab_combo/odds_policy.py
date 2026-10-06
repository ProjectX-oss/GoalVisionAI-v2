"""Reviewed PREMATCH Lab COMBO leg floor; combined odds have no added floor."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import os

from app.lab_v2_shadow.single_odds_policy import single_odds_blocker

ENVIRONMENT_FLAG = "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130"
COMBO_LEG_ODDS_FLOOR = Decimal("1.30")
FLOOR_POLICY = "LAB_COMBO_ACCURACY_FROM_SINGLES_V2_LEG_MIN_ODDS_130"
LEG_POLICY = "LAB_COMBO_LEG_MIN_ODDS_130_V1"
BELOW_FLOOR = "LAB_COMBO_LEG_ODDS_BELOW_1_30"


def minimum_combo_leg_odds() -> Decimal | None:
    flag = os.environ.get(ENVIRONMENT_FLAG, "0")
    if flag not in {"0", "1"}:
        raise ValueError("INVALID_LAB_COMBO_LEG_MIN_ODDS_CONFIGURATION")
    return COMBO_LEG_ODDS_FLOOR if flag == "1" else None


def combo_leg_odds_blocker(odds: object, *, minimum: Decimal | None) -> str | None:
    """Reuse exact Decimal validation; never compare rounded display odds."""
    reason = single_odds_blocker(odds, minimum=minimum)
    return BELOW_FLOOR if reason == "LAB_SINGLE_ODDS_BELOW_1_30" else reason


def floor_metadata(minimum: Decimal | None) -> dict:
    return ({"combo_leg_odds_policy": LEG_POLICY, "minimum_combo_leg_decimal_odds": str(minimum)}
            if minimum is not None else {})


def combo_odds_blocker(value: dict, *, minimum: Decimal | None) -> str | None:
    """Guard new deliveries across both current and legacy COMBO entry points."""
    if minimum is None:
        return None
    try:
        legs = value["legs"]
        from .cardinality import leg_count
        if not isinstance(legs, list) or len(legs) != leg_count(value):
            return "INVALID_CURRENT_DECIMAL_ODDS"
        for leg in legs:
            captured = leg.get("captured_odds", leg.get("odds"))
            reason = combo_leg_odds_blocker(captured, minimum=minimum)
            if reason:
                return reason
            if "odds" in leg and Decimal(str(leg["odds"])) != Decimal(str(captured)):
                return "INVALID_CURRENT_DECIMAL_ODDS"
    except (KeyError, AttributeError, TypeError, ValueError, InvalidOperation):
        return "INVALID_CURRENT_DECIMAL_ODDS"
    return None
