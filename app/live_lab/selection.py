"""Explicit LIVE Lab probability experiment; no model fitting or transport."""
from decimal import Decimal, InvalidOperation

PROBABILITY_POLICY = "LAB_LIVE_PROBABILITY_60_70_V1"
PROBABILITY_COHORT = "LIVE_P60_70_20261009_V1"
MINIMUM_PROBABILITY = Decimal("0.60")
MAXIMUM_PROBABILITY = Decimal("0.70")


def in_probability_band(value: object) -> bool:
    """Inclusive unrounded bounds; malformed/non-finite estimates fail closed."""
    try:
        p = Decimal(str(value))
        return p.is_finite() and MINIMUM_PROBABILITY <= p <= MAXIMUM_PROBABILITY
    except (InvalidOperation, ValueError, TypeError):
        return False


def select_candidates(candidates: list[dict], *, probability_band: bool = False) -> list[dict]:
    """At most one; legacy EV ranking is preserved only outside the opt-in policy."""
    ready = [c for c in candidates if not c["blockers"]]
    if probability_band:
        ready = [c for c in ready if in_probability_band(c.get("ensemble_probability"))
                 and c.get("policy") == PROBABILITY_POLICY]
        # EV and price are deliberately absent from both filters and rank keys.
        return sorted(ready, key=lambda c: (-Decimal(str(c["ensemble_probability"])),
                                           c["prediction_id"]))[:1]
    return sorted(ready, key=lambda c: (-c["expected_value"], c["prediction_id"]))[:1]
