from decimal import Decimal
from hashlib import sha256

from .models import OddsMarket, OddsSelection


def normalize_text(value: str, label: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{label} must not be empty.")
    return normalized


def normalize_identifier(value: str, label: str) -> str:
    normalized = "-".join(normalize_text(value, label).lower().split())
    return normalized


def normalize_source_name(value: str) -> str:
    return normalize_text(value, "Source name")


def normalize_fixture_id(value: object) -> str:
    return normalize_text(str(value), "Fixture ID")


def normalize_market(value: OddsMarket | str) -> OddsMarket:
    if isinstance(value, OddsMarket):
        return value
    identifier = normalize_identifier(value, "Market").replace("-", "_").upper()
    aliases = {
        "MATCH_WINNER": OddsMarket.MATCH_WINNER,
        "1X2": OddsMarket.MATCH_WINNER,
        "DOUBLE_CHANCE": OddsMarket.DOUBLE_CHANCE,
        "DRAW_NO_BET": OddsMarket.DRAW_NO_BET,
        "OVER_UNDER": OddsMarket.OVER_UNDER_GOALS,
        "OVER_UNDER_GOALS": OddsMarket.OVER_UNDER_GOALS,
        "BTTS": OddsMarket.BTTS,
        "BOTH_TEAMS_TO_SCORE": OddsMarket.BTTS,
        "ASIAN_HANDICAP": OddsMarket.ASIAN_HANDICAP,
        "TEAM_TOTAL": OddsMarket.TEAM_TOTAL,
        "CORRECT_SCORE": OddsMarket.CORRECT_SCORE,
        "OTHER": OddsMarket.OTHER,
    }
    if identifier not in aliases:
        return OddsMarket.OTHER
    return aliases[identifier]


def normalize_selection(
    value: str,
    *,
    line: Decimal | None = None,
) -> OddsSelection:
    name = normalize_text(value, "Selection")
    base = normalize_identifier(name, "Selection")
    identifier = f"{base}:{line}" if line is not None else base
    return OddsSelection(identifier, name, line)


def normalize_decimal_odds(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, float):
        value = str(value)
    try:
        odds = value if isinstance(value, Decimal) else Decimal(value)
    except Exception as exc:
        raise ValueError("Decimal odds are invalid.") from exc
    if not odds.is_finite() or odds <= Decimal("1"):
        raise ValueError("Decimal odds must be finite and greater than 1.")
    return odds


def normalize_percentage_commission(value: Decimal | str | int) -> Decimal:
    try:
        commission = value if isinstance(value, Decimal) else Decimal(value)
    except Exception as exc:
        raise ValueError("Commission is invalid.") from exc
    if not commission.is_finite() or commission < 0:
        raise ValueError("Commission must be non-negative and finite.")
    if commission >= 1:
        if commission >= 100:
            raise ValueError("Percentage commission must be below 100.")
        commission = commission / Decimal("100")
    if commission >= 1:
        raise ValueError("Commission must be below one.")
    return commission


def exchange_odds_after_commission(
    decimal_odds: Decimal,
    commission_rate: Decimal,
) -> Decimal:
    odds = normalize_decimal_odds(decimal_odds)
    commission = normalize_percentage_commission(commission_rate)
    return Decimal("1") + ((odds - Decimal("1")) * (Decimal("1") - commission))


def quantize_decimal(value: Decimal, quantum: Decimal) -> Decimal:
    if not value.is_finite() or not quantum.is_finite() or quantum <= 0:
        raise ValueError("Quantization requires finite values and a positive quantum.")
    return value.quantize(quantum)


def deterministic_observation_id(*parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    return sha256(material.encode("utf-8")).hexdigest()
