"""Canonical 11-target probability verification."""

from decimal import Decimal

from app.prediction_inference import OFFICIAL_TARGET_ORDER

from .exceptions import ShadowProbabilityContractError


def verify_probability_contract(probabilities, tolerance=Decimal("0.000001")) -> None:
    rows = probabilities.ordered_probabilities
    if tuple(item.target for item in rows) != OFFICIAL_TARGET_ORDER:
        raise ShadowProbabilityContractError("Canonical target order differs.")
    values = {item.target.value: item.probability for item in rows}
    if any(not value.is_finite() or not Decimal(0) <= value <= Decimal(1) for value in values.values()):
        raise ShadowProbabilityContractError("Probabilities must be finite and inside [0,1].")
    if abs(values["HOME_WIN"] + values["DRAW"] + values["AWAY_WIN"] - Decimal(1)) > tolerance:
        raise ShadowProbabilityContractError("Match-result probabilities do not form a simplex.")
    for left, right in (("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("BTTS_YES", "BTTS_NO")):
        if abs(values[left] + values[right] - Decimal(1)) > tolerance:
            raise ShadowProbabilityContractError(f"{left}/{right} are not complements.")
    if not values["OVER_1_5"] >= values["OVER_2_5"] >= values["OVER_3_5"]:
        raise ShadowProbabilityContractError("Totals probabilities are not monotonic.")
    if any("SCORE" in name for name in values):
        raise ShadowProbabilityContractError("Correct-score targets are prohibited.")
