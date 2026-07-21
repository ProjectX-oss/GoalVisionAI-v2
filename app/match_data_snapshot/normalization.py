import json
import re
import unicodedata
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar

from .exceptions import SnapshotValidationError
from .models import (
    AggregateRecord,
    FormRecord,
    HeadToHeadRecord,
    MatchContextRecord,
    MatchDataSnapshotRegistrationCommand,
    MatchSnapshotStatus,
    OddsContextRecord,
    SeasonAggregateRecord,
    TeamAvailabilityRecord,
    VenueSplitRecord,
)
from .policy import MatchDataSnapshotPolicy


_T = TypeVar("_T")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._:/-]*$")
_AVAILABILITY = {"AVAILABLE", "UNAVAILABLE", "DOUBTFUL", "UNKNOWN"}


def normalize_text(value: str, *, maximum: int, field_name: str) -> str:
    if not isinstance(value, str):
        _invalid("MALFORMED_TEXT", f"{field_name} must be text.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized or len(normalized) > maximum:
        _invalid("INVALID_TEXT", f"{field_name} is missing or too long.")
    return normalized


def normalize_identifier(
    value: str,
    *,
    maximum: int,
    field_name: str,
) -> str:
    normalized = normalize_text(value, maximum=maximum, field_name=field_name).casefold()
    if not _IDENTIFIER.fullmatch(normalized):
        _invalid("INVALID_IDENTIFIER", f"{field_name} is not a supported identifier.")
    return normalized


def normalize_optional_identifier(
    value: str | None,
    *,
    maximum: int,
    field_name: str,
) -> str | None:
    return None if value is None else normalize_identifier(
        value,
        maximum=maximum,
        field_name=field_name,
    )


def normalize_timestamp(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _invalid("INVALID_TIMESTAMP", f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def normalize_decimal(value: Decimal | None, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        _invalid("INVALID_DECIMAL", f"{field_name} must be a finite Decimal.")
    return Decimal(0) if value == 0 else value.normalize()


def normalize_command(
    command: MatchDataSnapshotRegistrationCommand,
    policy: MatchDataSnapshotPolicy,
) -> MatchDataSnapshotRegistrationCommand:
    if not isinstance(command, MatchDataSnapshotRegistrationCommand):
        _invalid("UNSUPPORTED_DATA_OBJECT", "Snapshot command has an unsupported type.")
    nested = (
        (command.home_recent_form, FormRecord, "home_recent_form"),
        (command.away_recent_form, FormRecord, "away_recent_form"),
        (command.home_venue_split, VenueSplitRecord, "home_venue_split"),
        (command.away_venue_split, VenueSplitRecord, "away_venue_split"),
        (command.home_season_aggregate, SeasonAggregateRecord, "home_season_aggregate"),
        (command.away_season_aggregate, SeasonAggregateRecord, "away_season_aggregate"),
        (command.head_to_head, HeadToHeadRecord, "head_to_head"),
        (command.home_availability, TeamAvailabilityRecord, "home_availability"),
        (command.away_availability, TeamAvailabilityRecord, "away_availability"),
        (command.context, MatchContextRecord, "context"),
        (command.odds_snapshot, OddsContextRecord, "odds_snapshot"),
    )
    for value, expected, label in nested:
        if value is not None and not isinstance(value, expected):
            _invalid("UNSUPPORTED_DATA_OBJECT", f"{label} has an unsupported type.")
    for value, label in (
        (command.postponed_indicator, "postponed_indicator"),
        (command.cancelled_indicator, "cancelled_indicator"),
        (command.neutral_venue_indicator, "neutral_venue_indicator"),
        (command.is_live, "is_live"),
    ):
        if not isinstance(value, bool):
            _invalid("MALFORMED_BOOLEAN", f"{label} must be a boolean.")
    try:
        status = MatchSnapshotStatus(command.scheduled_status)
    except (TypeError, ValueError):
        _invalid("INVALID_MATCH_STATUS", "scheduled_status is unsupported.")
    normalized = replace(
        command,
        source_provider=normalize_identifier(
            command.source_provider,
            maximum=policy.maximum_identifier_length,
            field_name="source_provider",
        ),
        source_event_id=normalize_identifier(
            command.source_event_id,
            maximum=policy.maximum_identifier_length,
            field_name="source_event_id",
        ),
        source_snapshot_id=normalize_identifier(
            command.source_snapshot_id,
            maximum=policy.maximum_identifier_length,
            field_name="source_snapshot_id",
        ),
        match_id=normalize_identifier(
            command.match_id,
            maximum=policy.maximum_identifier_length,
            field_name="match_id",
        ),
        competition_id=normalize_optional_identifier(
            command.competition_id,
            maximum=policy.maximum_identifier_length,
            field_name="competition_id",
        ),
        competition_name=normalize_text(
            command.competition_name,
            maximum=policy.maximum_name_length,
            field_name="competition_name",
        ),
        season_identifier=normalize_identifier(
            command.season_identifier,
            maximum=policy.maximum_identifier_length,
            field_name="season_identifier",
        ),
        home_team_id=normalize_optional_identifier(
            command.home_team_id,
            maximum=policy.maximum_identifier_length,
            field_name="home_team_id",
        ),
        home_team_name=normalize_text(
            command.home_team_name,
            maximum=policy.maximum_name_length,
            field_name="home_team_name",
        ),
        away_team_id=normalize_optional_identifier(
            command.away_team_id,
            maximum=policy.maximum_identifier_length,
            field_name="away_team_id",
        ),
        away_team_name=normalize_text(
            command.away_team_name,
            maximum=policy.maximum_name_length,
            field_name="away_team_name",
        ),
        kickoff_timestamp=normalize_timestamp(command.kickoff_timestamp, "kickoff_timestamp"),
        snapshot_effective_timestamp=normalize_timestamp(
            command.snapshot_effective_timestamp, "snapshot_effective_timestamp"
        ),
        source_updated_timestamp=normalize_timestamp(
            command.source_updated_timestamp, "source_updated_timestamp"
        ),
        registration_timestamp=normalize_timestamp(
            command.registration_timestamp, "registration_timestamp"
        ),
        scheduled_status=status,
        venue=_optional_text(command.venue, policy, "venue"),
        home_recent_form=_normalize_dataclass(command.home_recent_form, policy),
        away_recent_form=_normalize_dataclass(command.away_recent_form, policy),
        home_venue_split=_normalize_dataclass(command.home_venue_split, policy),
        away_venue_split=_normalize_dataclass(command.away_venue_split, policy),
        home_season_aggregate=_normalize_dataclass(command.home_season_aggregate, policy),
        away_season_aggregate=_normalize_dataclass(command.away_season_aggregate, policy),
        head_to_head=_normalize_dataclass(command.head_to_head, policy),
        home_availability=_normalize_dataclass(command.home_availability, policy),
        away_availability=_normalize_dataclass(command.away_availability, policy),
        context=_normalize_dataclass(command.context, policy),
        odds_snapshot=_normalize_dataclass(command.odds_snapshot, policy),
    )
    return normalized


def canonical_data(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Canonical Decimal must be finite.")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        return normalize_timestamp(value, "timestamp").isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: canonical_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): canonical_data(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [canonical_data(item) for item in value]
    raise ValueError(f"Unsupported canonical value: {type(value).__name__}.")


def canonical_json(value: object) -> str:
    return json.dumps(canonical_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_dataclass(value: _T | None, policy: MatchDataSnapshotPolicy) -> _T | None:
    if value is None:
        return None
    if isinstance(value, OddsContextRecord):
        value = replace(
            value,
            source_identifier=normalize_identifier(
                value.source_identifier,
                maximum=policy.maximum_identifier_length,
                field_name="odds_source_identifier",
            ),
            market_type=normalize_text(
                value.market_type,
                maximum=policy.maximum_name_length,
                field_name="market_type",
            ).casefold(),
            selection=normalize_text(
                value.selection,
                maximum=policy.maximum_name_length,
                field_name="selection",
            ).casefold(),
        )
    changes: dict[str, Any] = {}
    for item in fields(value):
        current = getattr(value, item.name)
        if isinstance(current, Decimal):
            changes[item.name] = normalize_decimal(current, item.name)
        elif isinstance(current, datetime):
            changes[item.name] = normalize_timestamp(current, item.name)
        elif isinstance(current, str):
            text = normalize_text(
                current,
                maximum=policy.maximum_context_length,
                field_name=item.name,
            )
            if item.name == "goalkeeper_availability_status":
                text = text.upper().replace(" ", "_")
                if text not in _AVAILABILITY:
                    _invalid("INVALID_AVAILABILITY_STATUS", "Goalkeeper status is unsupported.")
            changes[item.name] = text
        elif is_dataclass(current):
            changes[item.name] = _normalize_dataclass(current, policy)
    return replace(value, **changes)


def _optional_text(
    value: str | None,
    policy: MatchDataSnapshotPolicy,
    field_name: str,
) -> str | None:
    return None if value is None else normalize_text(
        value,
        maximum=policy.maximum_context_length,
        field_name=field_name,
    )


def _invalid(code: str, explanation: str) -> None:
    raise SnapshotValidationError(code, explanation)
