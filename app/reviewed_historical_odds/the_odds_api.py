"""Offline parser for The Odds API version-four historical snapshot format."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import SourceOddsEvent, SourceOddsQuote


PARSER_VERSION = "the-odds-api-historical-v4-offline-parser-v1"


@dataclass(frozen=True, slots=True)
class ParsedOddsSnapshot:
    snapshot_timestamp_utc: str
    events: tuple[SourceOddsEvent, ...]
    quotes: tuple[SourceOddsQuote, ...]
    unsupported_market_rows: int


def parse_historical_snapshot(path: str | Path) -> ParsedOddsSnapshot:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    snapshot_timestamp = _required(payload, "timestamp")
    events: list[SourceOddsEvent] = []
    quotes: list[SourceOddsQuote] = []
    unsupported = 0
    for raw_event in payload.get("data", ()):
        event_id = _required(raw_event, "id")
        event = SourceOddsEvent(
            source_event_id=event_id,
            competition=_required(raw_event, "sport_title"),
            kickoff_utc=_required(raw_event, "commence_time"),
            home_team=_required(raw_event, "home_team"),
            away_team=_required(raw_event, "away_team"),
        )
        events.append(event)
        for bookmaker in raw_event.get("bookmakers", ()):
            bookmaker_id = _required(bookmaker, "key")
            captured = bookmaker.get("last_update")
            for market in bookmaker.get("markets", ()):
                market_name = _required(market, "key")
                if market_name != "h2h":
                    unsupported += len(market.get("outcomes", ()))
                    continue
                for index, outcome in enumerate(market.get("outcomes", ())):
                    quotes.append(SourceOddsQuote(
                        source_quote_id=f"{event_id}:{bookmaker_id}:{market_name}:{index}:{outcome.get('name', '')}",
                        source_event_id=event_id,
                        source_bookmaker_id=bookmaker_id,
                        source_bookmaker_name=_required(bookmaker, "title"),
                        source_market_name=market_name,
                        source_selection_name=_required(outcome, "name"),
                        odds_value=str(outcome.get("price", "")),
                        original_odds_format="DECIMAL",
                        captured_at_utc=str(captured) if captured else None,
                        source_effective_timestamp_utc=snapshot_timestamp,
                    ))
    return ParsedOddsSnapshot(
        snapshot_timestamp_utc=snapshot_timestamp,
        events=tuple(sorted(events, key=lambda item: item.source_event_id)),
        quotes=tuple(sorted(quotes, key=lambda item: item.source_quote_id)),
        unsupported_market_rows=unsupported,
    )


def _required(value: dict, key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"The Odds API field {key!r} is required.")
    return result.strip()
