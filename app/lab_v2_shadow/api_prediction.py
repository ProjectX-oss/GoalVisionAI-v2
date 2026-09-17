"""Conservative normalization of current API-Football `/predictions` evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import factorial


@dataclass(frozen=True, slots=True)
class ApiPredictionSignal:
    available: bool
    fixture_id: int
    predicted_winner_id: int | None
    predicted_winner_name: str | None
    winner_comment: str | None
    probabilities: dict[str, Decimal]
    under_over: str | None
    expected_goals_home: Decimal | None
    expected_goals_away: Decimal | None
    comparison: dict[str, dict[str, Decimal]]
    unavailable_reason: str | None


def normalize_api_prediction(payload: object, *, fixture_id: int) -> ApiPredictionSignal:
    if not isinstance(payload, dict) or payload.get("errors"):
        return _unavailable(fixture_id, "PROVIDER_PREDICTION_ERROR")
    rows = payload.get("response")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return _unavailable(fixture_id, "PREDICTION_NOT_COVERED")
    root = rows[0]
    prediction = root.get("predictions") if isinstance(root.get("predictions"), dict) else {}
    winner = prediction.get("winner") if isinstance(prediction.get("winner"), dict) else {}
    percent = prediction.get("percent") if isinstance(prediction.get("percent"), dict) else {}
    probabilities = {
        market: value for market, raw in (
            ("HOME_WIN", percent.get("home")),
            ("DRAW", percent.get("draw")),
            ("AWAY_WIN", percent.get("away")),
        ) if (value := _probability(raw)) is not None
    }
    if len(probabilities) == 3:
        total = sum(probabilities.values(), Decimal(0))
        if not Decimal("0.98") <= total <= Decimal("1.02"):
            return _unavailable(fixture_id, "PREDICTION_PERCENTAGES_INVALID")
        probabilities = {key: value / total for key, value in probabilities.items()}
    goals = prediction.get("goals") if isinstance(prediction.get("goals"), dict) else {}
    expected_home = _expected_goals(goals.get("home"))
    expected_away = _expected_goals(goals.get("away"))
    if expected_home is not None and expected_away is not None:
        probabilities.update(_goals_market_probabilities(expected_home, expected_away))
    comparison = _comparison(root.get("comparison"))
    winner_id = _integer(winner.get("id"))
    available = bool(probabilities or winner_id is not None or prediction.get("under_over"))
    return ApiPredictionSignal(
        available=available,
        fixture_id=int(fixture_id),
        predicted_winner_id=winner_id,
        predicted_winner_name=_text(winner.get("name")),
        winner_comment=_text(winner.get("comment")),
        probabilities=probabilities,
        under_over=_normalize_total(prediction.get("under_over")),
        expected_goals_home=expected_home,
        expected_goals_away=expected_away,
        comparison=comparison,
        unavailable_reason=None if available else "PREDICTION_NOT_COVERED",
    )


def _comparison(value: object) -> dict[str, dict[str, Decimal]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Decimal]] = {}
    for category, raw in sorted(value.items()):
        if not isinstance(raw, dict):
            continue
        sides = {side: parsed for side in ("home", "away")
                 if (parsed := _probability(raw.get(side))) is not None}
        if sides:
            result[str(category)] = sides
    return result


def _goals_market_probabilities(home: Decimal, away: Decimal) -> dict[str, Decimal]:
    """Derive transparent totals/BTTS support from provider goal estimates."""
    if not (Decimal(0) <= home <= Decimal(10) and Decimal(0) <= away <= Decimal(10)):
        return {}
    joint: list[tuple[int, int, Decimal]] = []
    mass = Decimal(0)
    for home_goals in range(13):
        for away_goals in range(13):
            value = _poisson(home, home_goals) * _poisson(away, away_goals)
            joint.append((home_goals, away_goals, value))
            mass += value
    if mass <= 0:
        return {}
    btts = sum((value for h, a, value in joint if h and a), Decimal(0)) / mass
    result = {"BTTS_YES": btts, "BTTS_NO": Decimal(1) - btts}
    for line in (1, 2, 3):
        over = sum((value for h, a, value in joint if h + a > line), Decimal(0)) / mass
        result[f"OVER_{line}_5"] = over
        result[f"UNDER_{line}_5"] = Decimal(1) - over
    return result


def _poisson(rate: Decimal, goals: int) -> Decimal:
    return (-rate).exp() * (rate ** goals) / Decimal(factorial(goals))


def _unavailable(fixture_id: int, reason: str) -> ApiPredictionSignal:
    return ApiPredictionSignal(False, int(fixture_id), None, None, None, {}, None, None, None, {}, reason)


def _normalize_total(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    signed = text.replace(" ", "")
    if signed[:1] in {"+", "-"} and signed[1:] in {"1.5", "2.5", "3.5"}:
        direction = "OVER" if signed[0] == "+" else "UNDER"
        return f"{direction}_{signed[1:].replace('.', '_')}"
    normalized = text.upper().replace(" ", "_").replace(".", "_")
    return normalized if normalized in {
        "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5",
        "OVER_3_5", "UNDER_3_5",
    } else None


def _expected_goals(value: object) -> Decimal | None:
    """Accept only genuine non-negative scoring-rate estimates."""
    number = _decimal(value)
    return number if number is not None and Decimal(0) <= number <= Decimal(10) else None


def _probability(value: object) -> Decimal | None:
    number = _decimal(str(value).replace("%", "").strip())
    if number is None:
        return None
    if number > 1:
        number /= Decimal(100)
    return number if Decimal(0) <= number <= Decimal(1) else None


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
