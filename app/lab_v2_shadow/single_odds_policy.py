"""Operator-controlled PREMATCH Lab SINGLE floors; never a COMBO leg rule."""
import os
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

ENVIRONMENT_FLAG = "GOALVISION_LAB_SINGLE_MIN_ODDS_130"
ENVIRONMENT_FLAG_150 = "GOALVISION_LAB_SINGLE_MIN_ODDS_150"
FLOOR_SELECTION_POLICY = "LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V3_MIN_ODDS_130"
TEST_SELECTION_POLICY = "LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V4_MIN_ODDS_150"
SINGLE_ODDS_FLOOR = Decimal("1.30")
TEST_ODDS_FLOOR = Decimal("1.50")
FLOOR_POLICIES = MappingProxyType({
    FLOOR_SELECTION_POLICY: SINGLE_ODDS_FLOOR,
    TEST_SELECTION_POLICY: TEST_ODDS_FLOOR,
})


def minimum_single_odds() -> Decimal | None:
    flags = [os.environ.get(name, "0") for name in (ENVIRONMENT_FLAG, ENVIRONMENT_FLAG_150)]
    if any(flag not in {"0", "1"} for flag in flags):
        raise ValueError("INVALID_LAB_SINGLE_MIN_ODDS_CONFIGURATION")
    if flags[1] == "1":
        return TEST_ODDS_FLOOR
    return SINGLE_ODDS_FLOOR if flags[0] == "1" else None


def floor_selection_policy(minimum: Decimal | None) -> str | None:
    if minimum is None:
        return None
    for policy, floor in FLOOR_POLICIES.items():
        if minimum == floor:
            return policy
    raise ValueError("UNSUPPORTED_SINGLE_ODDS_FLOOR")


def single_odds_blocker(captured_odds: object, *, minimum: Decimal | None) -> str | None:
    if minimum is None:
        return None
    floor_selection_policy(minimum)
    try:
        odds = Decimal(str(captured_odds))
        if not odds.is_finite() or odds <= 1:
            return "INVALID_CURRENT_DECIMAL_ODDS"
        if odds < minimum:
            return ("LAB_SINGLE_ODDS_BELOW_1_50" if minimum == TEST_ODDS_FLOOR
                    else "LAB_SINGLE_ODDS_BELOW_1_30")
    except (InvalidOperation, TypeError, ValueError):
        return "INVALID_CURRENT_DECIMAL_ODDS"
    return None
