"""Validation and deterministic normalization of supplied odds snapshots."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TypeVar

from .exceptions import InvalidOddsError
from .fingerprint import odds_fingerprint
from .models import (
    MarketOddsSnapshot,
    MarketSelection,
    MarketStatus,
    MarketType,
    SuppliedOddsSnapshot,
)
from .policy import MarketValueAssessmentPolicy


_FORBIDDEN_METADATA = re.compile(
    r"https?://|www\.|token|secret|password|api[_ -]?key|affiliate",
    re.IGNORECASE,
)
_EnumType = TypeVar("_EnumType", bound=Enum)


def _text(value: object, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise InvalidOddsError(f"{label} must be text.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not normalized:
        raise InvalidOddsError(f"{label} is required.")
    if len(normalized) > maximum:
        raise InvalidOddsError(f"{label} exceeds the supported length.")
    return normalized


def _enum(
    value: object,
    kind: type[_EnumType],
    label: str,
) -> _EnumType:
    if isinstance(value, kind):
        return value
    try:
        return kind(_text(value, label).replace(" ", "_").upper())
    except ValueError as exc:
        raise InvalidOddsError(f"Unsupported {label}.") from exc


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidOddsError(f"{label} timestamp must be timezone-aware.")
    if value.utcoffset() is None:
        raise InvalidOddsError(f"{label} timestamp must have a UTC offset.")
    return value.astimezone(timezone.utc)


def _original(value: MarketType | MarketSelection | str, label: str) -> str:
    public_value = value.value if isinstance(value, Enum) else value
    return _text(public_value, label)


def _metadata(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        raise InvalidOddsError("Metadata must be an immutable tuple of text pairs.")
    normalized: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise InvalidOddsError("Metadata must contain only immutable text pairs.")
        key = _text(item[0], "Metadata key")
        item_value = _text(item[1], "Metadata value", maximum=2048)
        if _FORBIDDEN_METADATA.search(key) or _FORBIDDEN_METADATA.search(item_value):
            raise InvalidOddsError(
                "Metadata contains forbidden credential, URL, or affiliate content."
            )
        normalized.append((key, item_value))
    ordered = tuple(sorted(normalized))
    if len({key for key, _ in ordered}) != len(ordered):
        raise InvalidOddsError("Metadata contains duplicate normalized keys.")
    return ordered


def normalize_odds_snapshot(
    value: SuppliedOddsSnapshot,
    policy: MarketValueAssessmentPolicy,
) -> MarketOddsSnapshot:
    """Fail closed and return one canonical, immutable odds snapshot."""

    if not isinstance(value, SuppliedOddsSnapshot):
        raise InvalidOddsError("Immutable supplied odds snapshot is required.")
    if any(
        not isinstance(flag, bool)
        for flag in (
            value.is_live,
            value.suspended,
            value.available,
        )
    ):
        raise InvalidOddsError("Odds state indicators must be booleans.")

    snapshot_id = _text(value.snapshot_id, "Odds snapshot ID")
    provider = _text(value.source_provider, "Source provider")
    bookmaker = _text(value.bookmaker_id, "Bookmaker")
    event_id = _text(value.source_event_id, "Source event ID")
    match_id = _text(value.match_id, "Match ID")
    original_market = _original(value.market_type, "Original market")
    original_selection = _original(value.selection, "Original selection")
    market_type = _enum(value.market_type, MarketType, "market")
    selection = _enum(value.selection, MarketSelection, "selection")
    market_status = _enum(value.market_status, MarketStatus, "market status")

    if (
        not isinstance(value.decimal_odds, Decimal)
        or not value.decimal_odds.is_finite()
    ):
        raise InvalidOddsError("Decimal odds must be a finite Decimal.")
    if (
        value.decimal_odds <= policy.structural_minimum_odds
        or value.decimal_odds > policy.structural_maximum_odds
    ):
        raise InvalidOddsError("Decimal odds are outside structural bounds.")

    market_line = value.market_line
    supported_lines = (Decimal("1.5"), Decimal("2.5"), Decimal("3.5"))
    if market_type is MarketType.TOTALS:
        if (
            not isinstance(market_line, Decimal)
            or not market_line.is_finite()
            or market_line not in supported_lines
        ):
            raise InvalidOddsError(
                "Totals line must be exactly 1.5, 2.5, or 3.5."
            )
        market_line = market_line.normalize()
    elif market_line is not None:
        raise InvalidOddsError("This market does not accept a line.")

    if (
        value.is_live
        or value.suspended
        or not value.available
        or market_status is not MarketStatus.OPEN
    ):
        raise InvalidOddsError("Only available, open pre-match odds are supported.")

    effective_timestamp = _timestamp(
        value.odds_effective_timestamp, "Odds effective"
    )
    updated_timestamp = _timestamp(value.source_updated_timestamp, "Source updated")
    registration_timestamp = _timestamp(
        value.registration_timestamp, "Registration"
    )
    kickoff_timestamp = _timestamp(value.kickoff_timestamp, "Kickoff")
    if effective_timestamp >= kickoff_timestamp:
        raise InvalidOddsError("Odds must be effective before kickoff.")
    if (
        updated_timestamp > registration_timestamp
        or effective_timestamp > registration_timestamp
    ):
        raise InvalidOddsError("Odds timestamps contradict registration.")

    metadata = _metadata(value.metadata)
    currency = (
        _text(value.currency, "Currency").upper()
        if value.currency is not None
        else None
    )
    if currency and currency not in policy.supported_currencies:
        raise InvalidOddsError("Currency is unsupported.")
    for stake in (value.minimum_stake, value.maximum_stake):
        if stake is not None and (
            not isinstance(stake, Decimal)
            or not stake.is_finite()
            or stake < 0
        ):
            raise InvalidOddsError(
                "Stake limits must be non-negative finite Decimals."
            )
    if (
        value.minimum_stake is not None
        and value.maximum_stake is not None
        and value.minimum_stake > value.maximum_stake
    ):
        raise InvalidOddsError("Minimum stake exceeds maximum stake.")

    source_data_version = _text(value.source_data_version, "Source data version")
    metadata_version = _text(value.metadata_version, "Metadata version")
    normalized = MarketOddsSnapshot(
        odds_record_id="",
        supplied_snapshot_id=snapshot_id,
        odds_fingerprint="",
        source_provider=provider,
        bookmaker_id=bookmaker,
        source_event_id=event_id,
        match_id=match_id,
        market_type=market_type,
        selection=selection,
        market_line=market_line,
        original_market=original_market,
        original_selection=original_selection,
        decimal_odds=value.decimal_odds,
        odds_effective_timestamp=effective_timestamp,
        source_updated_timestamp=updated_timestamp,
        registration_timestamp=registration_timestamp,
        kickoff_timestamp=kickoff_timestamp,
        market_status=market_status,
        suspended=value.suspended,
        available=value.available,
        minimum_stake=value.minimum_stake,
        maximum_stake=value.maximum_stake,
        currency=currency,
        source_data_version=source_data_version,
        metadata_version=metadata_version,
        metadata=metadata,
        created_timestamp=registration_timestamp,
    )
    fingerprint = odds_fingerprint(normalized)
    record_id = "market-odds-" + hashlib.sha256(
        f"market-odds-id-v1|{fingerprint}".encode("utf-8")
    ).hexdigest()
    return replace(
        normalized,
        odds_record_id=record_id,
        odds_fingerprint=fingerprint,
    )
