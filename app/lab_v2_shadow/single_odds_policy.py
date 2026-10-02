"""Operator-controlled PREMATCH Lab SINGLE floor; never a COMBO leg rule."""
import os
from decimal import Decimal, InvalidOperation

ENVIRONMENT_FLAG = "GOALVISION_LAB_SINGLE_MIN_ODDS_130"
FLOOR_SELECTION_POLICY = "LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V3_MIN_ODDS_130"
SINGLE_ODDS_FLOOR = Decimal("1.30")


def minimum_single_odds() -> Decimal | None:
    flag = os.environ.get(ENVIRONMENT_FLAG, "0")
    if flag not in {"0", "1"}:
        raise ValueError("INVALID_LAB_SINGLE_MIN_ODDS_CONFIGURATION")
    return SINGLE_ODDS_FLOOR if flag == "1" else None


def single_odds_blocker(captured_odds: object, *, minimum: Decimal | None) -> str | None:
    if minimum is None:
        return None
    try:
        odds = Decimal(str(captured_odds))
        if not odds.is_finite() or odds <= 1:
            return "INVALID_CURRENT_DECIMAL_ODDS"
        if odds < minimum:
            return "LAB_SINGLE_ODDS_BELOW_1_30"
    except (InvalidOperation, TypeError, ValueError):
        return "INVALID_CURRENT_DECIMAL_ODDS"
    return None
