"""Deterministic offline parser for reviewed Football-Data.co.uk CSV files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from app.historical_backtesting.models import SupportedMarket

from .fingerprint import sha256_fingerprint
from .models import (
    RawOddsQuoteEvidence,
    RawQuoteEvidenceStatus,
    SourceOddsEvent,
)


PARSER_VERSION = "football-data-csv-raw-evidence-v1"
SOURCE_TIMEZONE = ZoneInfo("Europe/London")
SOURCE_TIMESTAMP_SEMANTICS = (
    "NO_ROW_LEVEL_QUOTE_CAPTURE_TIMESTAMP; source publishes a general Friday/Tuesday "
    "collection schedule only; no timestamp may be inferred"
)


@dataclass(frozen=True, slots=True)
class FootballDataColumn:
    column_name: str
    bookmaker_id: str
    bookmaker_name: str
    market: SupportedMarket
    odds_semantics: str


@dataclass(frozen=True, slots=True)
class FootballDataRowRejection:
    source_file_name: str
    source_row_number: int
    reason: str


@dataclass(frozen=True, slots=True)
class ParsedFootballDataArchive:
    events: tuple[SourceOddsEvent, ...]
    raw_quotes: tuple[RawOddsQuoteEvidence, ...]
    row_count: int
    file_row_counts: tuple[tuple[str, int], ...]
    row_rejections: tuple[FootballDataRowRejection, ...]
    missing_value_count: int
    unsupported_column_count: int


_BOOKMAKERS = {
    "B365": ("bet365", "Bet365"),
    "BW": ("bwin", "Bwin"),
    "IW": ("interwetten", "Interwetten"),
    "PS": ("pinnacle", "Pinnacle"),
    "WH": ("william_hill", "William Hill"),
    "VC": ("betvictor", "BetVictor"),
    "1XB": ("1xbet", "1xBet"),
    "BF": ("betfair_sportsbook", "Betfair Sportsbook"),
    "BFE": ("betfair_exchange", "Betfair Exchange"),
}


def supported_columns() -> tuple[FootballDataColumn, ...]:
    """Return the explicit, policy-bounded bookmaker columns understood by GoalVision."""
    result: list[FootballDataColumn] = []
    for prefix in ("B365", "BW", "IW", "PS", "WH", "VC", "1XB", "BF", "BFE"):
        bookmaker_id, bookmaker_name = _BOOKMAKERS[prefix]
        for suffix, market in (
            ("H", SupportedMarket.HOME_WIN),
            ("D", SupportedMarket.DRAW),
            ("A", SupportedMarket.AWAY_WIN),
        ):
            result.append(FootballDataColumn(prefix + suffix, bookmaker_id, bookmaker_name, market, "PRE_CLOSING_UNTIMESTAMPED"))
            result.append(FootballDataColumn(prefix + "C" + suffix, bookmaker_id, bookmaker_name, market, "CLOSING_UNTIMESTAMPED"))
    for prefix in ("B365", "P", "BFE"):
        bookmaker_key = "PS" if prefix == "P" else prefix
        bookmaker_id, bookmaker_name = _BOOKMAKERS[bookmaker_key]
        for marker, market in ((">2.5", SupportedMarket.OVER_2_5), ("<2.5", SupportedMarket.UNDER_2_5)):
            result.append(FootballDataColumn(prefix + marker, bookmaker_id, bookmaker_name, market, "PRE_CLOSING_UNTIMESTAMPED"))
            result.append(FootballDataColumn(prefix + "C" + marker, bookmaker_id, bookmaker_name, market, "CLOSING_UNTIMESTAMPED"))
    return tuple(sorted(result, key=lambda item: item.column_name))


def parse_football_data_files(
    paths: tuple[str | Path, ...], *, season_by_file: dict[str, str], competition: str,
) -> ParsedFootballDataArchive:
    """Parse only explicit bookmaker 1X2 and 2.5-total columns; never infer quote time."""
    events: list[SourceOddsEvent] = []
    quotes: list[RawOddsQuoteEvidence] = []
    rejections: list[FootballDataRowRejection] = []
    file_counts: list[tuple[str, int]] = []
    missing_values = 0
    unsupported_columns: set[str] = set()
    column_specs = {item.column_name: item for item in supported_columns()}
    required = {"Div", "Date", "Time", "HomeTeam", "AwayTeam"}
    for path in sorted((Path(item) for item in paths), key=lambda item: item.name):
        if path.name not in season_by_file:
            raise ValueError(f"No reviewed season identity for {path.name}.")
        row_count = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required <= set(reader.fieldnames):
                raise ValueError(f"Football-Data file lacks required identity columns: {path.name}")
            unsupported_columns.update(
                name for name in reader.fieldnames
                if _looks_like_supported_market(name) and name not in column_specs
            )
            for row_number, row in enumerate(reader, start=2):
                row_count += 1
                try:
                    event = _parse_event(
                        row, path.name, row_number, season_by_file[path.name], competition,
                    )
                except ValueError as exc:
                    rejections.append(FootballDataRowRejection(path.name, row_number, str(exc)))
                    continue
                events.append(event)
                for column_name in sorted(set(reader.fieldnames) & set(column_specs)):
                    original = (row.get(column_name) or "").strip()
                    if not original:
                        missing_values += 1
                        continue
                    quotes.append(_raw_quote(event, path.name, row_number, column_specs[column_name], original))
        file_counts.append((path.name, row_count))
    return ParsedFootballDataArchive(
        events=tuple(sorted(events, key=lambda item: item.source_event_id)),
        raw_quotes=tuple(sorted(quotes, key=lambda item: item.source_quote_id)),
        row_count=sum(value for _, value in file_counts),
        file_row_counts=tuple(file_counts),
        row_rejections=tuple(rejections),
        missing_value_count=missing_values,
        unsupported_column_count=len(unsupported_columns),
    )


def _parse_event(
    row: dict[str, str], file_name: str, row_number: int, season: str, competition: str,
) -> SourceOddsEvent:
    date_value = (row.get("Date") or "").strip()
    time_value = (row.get("Time") or "").strip()
    home = (row.get("HomeTeam") or "").strip()
    away = (row.get("AwayTeam") or "").strip()
    if not all((date_value, time_value, home, away)):
        raise ValueError("MISSING_FIXTURE_IDENTITY_OR_TIME")
    try:
        local = datetime.strptime(f"{date_value} {time_value}", "%d/%m/%Y %H:%M").replace(tzinfo=SOURCE_TIMEZONE)
    except ValueError as exc:
        raise ValueError("INVALID_MATCH_DATE_OR_TIME") from exc
    kickoff = local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    identity = sha256_fingerprint({
        "source": "football-data.co.uk", "file": file_name, "row": row_number,
        "competition": competition, "season": season, "kickoff_utc": kickoff,
        "home": home, "away": away,
    })
    return SourceOddsEvent(
        source_event_id=f"football-data-event-{identity}", competition=competition,
        kickoff_utc=kickoff, home_team=home, away_team=away, season=season,
    )


def _raw_quote(
    event: SourceOddsEvent, file_name: str, row_number: int,
    column: FootballDataColumn, original: str,
) -> RawOddsQuoteEvidence:
    try:
        decimal = Decimal(original)
        valid = decimal.is_finite() and decimal > Decimal(1)
    except InvalidOperation:
        decimal, valid = None, False
    status = (
        RawQuoteEvidenceStatus.REJECTED_MISSING_CAPTURE_TIMESTAMP
        if valid else RawQuoteEvidenceStatus.REJECTED_INVALID_DECIMAL_ODDS
    )
    reason = "UNKNOWN_CAPTURE_TIME" if valid else "INVALID_DECIMAL_ODDS"
    source_quote_id = f"{event.source_event_id}:{file_name}:{row_number}:{column.column_name}"
    material = {
        "source_quote_id": source_quote_id, "source_event_id": event.source_event_id,
        "source_file_name": file_name, "source_row_number": row_number,
        "source_column_name": column.column_name,
        "bookmaker_id": column.bookmaker_id, "market": column.market,
        "original_value": original, "parsed_decimal_odds": decimal,
        "odds_semantics": column.odds_semantics, "captured_at_utc": None,
        "source_timestamp_semantics": SOURCE_TIMESTAMP_SEMANTICS,
        "evidence_status": status, "rejection_reason": reason,
    }
    fingerprint = sha256_fingerprint(material)
    return RawOddsQuoteEvidence(
        raw_quote_evidence_id=f"historical-odds-raw-quote-{fingerprint}",
        source_quote_id=source_quote_id, source_event_id=event.source_event_id,
        source_file_name=file_name, source_row_number=row_number,
        source_column_name=column.column_name,
        source_bookmaker_id=column.bookmaker_id,
        source_bookmaker_name=column.bookmaker_name,
        source_market_name=column.column_name, canonical_market=column.market,
        original_value=original, parsed_decimal_odds=decimal,
        odds_semantics=column.odds_semantics, captured_at_utc=None,
        source_timestamp_semantics=SOURCE_TIMESTAMP_SEMANTICS,
        evidence_status=status, rejection_reason=reason,
        provenance_fingerprint=fingerprint,
    )


def _looks_like_supported_market(name: str) -> bool:
    return name.endswith(("H", "D", "A", ">2.5", "<2.5")) and not name.startswith(("Max", "Avg", "Bb"))
