"""Conservative normalization of current API-Football `/predictions` evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from app.real_match_lab_analysis.fingerprint import fingerprint

NORMALIZATION_VERSION = "API_FOOTBALL_PERCENT_UNITS_V2"
# Existing rounding allowance, not a provider calibration claim.
DISTRIBUTION_SUM_TOLERANCE = Decimal("0.02")


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
    normalization_version: str = NORMALIZATION_VERSION
    source_fingerprint: str | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None


def normalize_api_prediction(payload: object, *, fixture_id: int,
                             home_team_id: int | None = None, away_team_id: int | None = None,
                             league_id: int | None = None, season: int | None = None) -> ApiPredictionSignal:
    if not isinstance(payload, dict) or payload.get("errors"):
        return _unavailable(fixture_id, "PROVIDER_PREDICTION_ERROR")
    rows = payload.get("response")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return _unavailable(fixture_id, "PREDICTION_NOT_COVERED")
    root = rows[0]
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict):
        return _unavailable(fixture_id, "PREDICTION_IDENTITY_MISMATCH")
    if "fixture" in parameters and _integer(parameters["fixture"]) != fixture_id:
        return _unavailable(fixture_id, "PREDICTION_FIXTURE_MISMATCH")
    teams = root.get("teams") or {}
    if not isinstance(teams, dict) or any(not isinstance(teams.get(side, {}), dict) for side in ("home", "away")):
        return _unavailable(fixture_id, "PREDICTION_IDENTITY_MISMATCH")
    actual_home = _integer((teams.get("home") or {}).get("id"))
    actual_away = _integer((teams.get("away") or {}).get("id"))
    league = root.get("league") or {}
    if not isinstance(league, dict):
        return _unavailable(fixture_id, "PREDICTION_IDENTITY_MISMATCH")
    if any(expected is not None and actual != expected for expected, actual in (
        (home_team_id, actual_home), (away_team_id, actual_away),
        (league_id, _integer(league.get("id"))), (season, _integer(league.get("season"))),
    )):
        return _unavailable(fixture_id, "PREDICTION_IDENTITY_MISMATCH")
    prediction = root.get("predictions") if isinstance(root.get("predictions"), dict) else {}
    winner = prediction.get("winner") if isinstance(prediction.get("winner"), dict) else {}
    percent = prediction.get("percent") if isinstance(prediction.get("percent"), dict) else {}
    probabilities = {
        market: value for market, raw in (
            ("HOME_WIN", percent.get("home")),
            ("DRAW", percent.get("draw")),
            ("AWAY_WIN", percent.get("away")),
        ) if (value := _provider_percentage(raw)) is not None
    }
    if len(probabilities) != 3:
        return _unavailable(fixture_id, "PREDICTION_PERCENTAGES_INCOMPLETE_OR_INVALID")
    total = sum(probabilities.values(), Decimal(0))
    if abs(total - Decimal(1)) > DISTRIBUTION_SUM_TOLERANCE:
        return _unavailable(fixture_id, "PREDICTION_PERCENTAGES_INVALID")
    # Only the existing small rounding allowance may be rescaled; never fill an outcome.
    probabilities = {key: value / total for key, value in probabilities.items()}
    # Provider goals/under_over are recommendations/bounds, not documented Poisson rates.
    expected_home = expected_away = None
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
        source_fingerprint=fingerprint(payload), home_team_id=actual_home, away_team_id=actual_away,
    )


def _comparison(value: object) -> dict[str, dict[str, Decimal]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Decimal]] = {}
    for category, raw in sorted(value.items()):
        if not isinstance(raw, dict):
            continue
        sides = {side: parsed for side in ("home", "away")
                 if (parsed := _provider_percentage(raw.get(side))) is not None}
        if len(sides) == 2:
            result[str(category)] = sides
    return result


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


def _provider_percentage(value: object) -> Decimal | None:
    """Accept the percent-string wire representation; unverified bare formats fail closed."""
    if not isinstance(value, str) or not value.strip().endswith("%"):
        return None
    return _probability(value, unit="percentage")


def _probability(value: object, *, unit: str = "percentage") -> Decimal | None:
    """Explicit percent-field or normalized-internal contract; never infer from magnitude.

    Bare numbers require a percentage or normalized-internal unit contract;
    provider wire validation is separate. Internal callers select unit='probability'. A percent
    suffix always means percent and is forbidden in a normalized-internal field.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    text = str(value).strip()
    marked = text.endswith("%")
    if unit not in {"percentage", "probability"} or (marked and unit == "probability"):
        return None
    text = text[:-1] if marked else text
    pattern = r"[0-9]+(?:\.[0-9]+)?"
    if unit == "probability":
        pattern = r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    if re.fullmatch(pattern, text) is None:
        return None
    number = _decimal(text)
    limit = Decimal(100) if unit == "percentage" else Decimal(1)
    if number is None or not Decimal(0) <= number <= limit:
        return None
    return number / Decimal(100) if unit == "percentage" else number


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return int(value) if re.fullmatch(r"[0-9]+", str(value)) else None


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
