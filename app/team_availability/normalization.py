import re
import unicodedata
from decimal import Decimal

from .models import (
    AvailabilityReason,
    PlayerIdentity,
    TeamIdentity,
)


def normalize_text(value: str, label: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not normalized:
        raise ValueError(f"{label} must not be empty.")
    return normalized


def normalize_identifier(value: object, label: str) -> str:
    return normalize_text(str(value), label)


def normalize_team(team_id: object, team_name: str) -> TeamIdentity:
    return TeamIdentity(
        normalize_identifier(team_id, "Team ID"),
        normalize_text(team_name, "Team name"),
    )


def normalize_player(
    player_id: object | None,
    player_name: str | None,
) -> PlayerIdentity:
    normalized_id = (
        normalize_identifier(player_id, "Player ID")
        if player_id is not None
        else None
    )
    normalized_name = (
        normalize_text(player_name, "Player name")
        if player_name and player_name.strip()
        else ""
    )
    return PlayerIdentity(normalized_id, normalized_name)


def normalize_player_name(value: str) -> str:
    return normalize_text(value, "Player name")


def normalize_source_name(value: str) -> str:
    return normalize_text(value, "Source name")


def normalize_position(value: str) -> str:
    aliases = {
        "g": "GOALKEEPER",
        "gk": "GOALKEEPER",
        "goalkeeper": "GOALKEEPER",
        "d": "DEFENDER",
        "def": "DEFENDER",
        "defender": "DEFENDER",
        "m": "MIDFIELDER",
        "mid": "MIDFIELDER",
        "midfielder": "MIDFIELDER",
        "f": "FORWARD",
        "fw": "FORWARD",
        "attacker": "FORWARD",
        "forward": "FORWARD",
    }
    text = normalize_text(value, "Position")
    return aliases.get(text.lower(), text.upper())


def normalize_formation(value: str) -> str:
    text = normalize_text(value, "Formation").replace("–", "-")
    compact = re.sub(r"\s+", "", text)
    if not re.fullmatch(r"\d(?:-\d){2,4}", compact):
        raise ValueError("Formation must be a deterministic numeric shape.")
    return compact


def normalize_reason(value: AvailabilityReason | str) -> AvailabilityReason:
    if isinstance(value, AvailabilityReason):
        return value
    key = normalize_text(value, "Availability reason").upper().replace(" ", "_")
    aliases = {
        "INJURED": AvailabilityReason.INJURY,
        "SUSPENDED": AvailabilityReason.SUSPENSION,
        "ILL": AvailabilityReason.ILLNESS,
        "RESTED": AvailabilityReason.REST,
        "NOT_SELECTED": AvailabilityReason.SELECTION,
    }
    return aliases.get(key, AvailabilityReason.__members__.get(key, AvailabilityReason.UNKNOWN))


def decimal_or_none(value: object | None) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Decimal value must be finite.")
    return result
