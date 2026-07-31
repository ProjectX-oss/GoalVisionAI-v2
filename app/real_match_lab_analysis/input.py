"""Versioned JSON input loading and fail-closed normalization."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.match_data_snapshot import (
    AggregateRecord,
    FormRecord,
    HeadToHeadRecord,
    MatchContextRecord,
    MatchDataSnapshotRegistrationCommand,
    MatchSnapshotStatus,
    SeasonAggregateRecord,
    TeamAvailabilityRecord,
    VenueSplitRecord,
)

from .models import (
    INPUT_SCHEMA_VERSION,
    MODEL_SCOPE,
    ManualOdds,
    RealMatchLabInput,
)
from .policy import SUPPORTED_MARKETS


class InputValidationError(ValueError):
    pass


def load_input(path: Path, *, now: datetime | None = None) -> RealMatchLabInput:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError("Input must be readable versioned JSON.") from exc
    return parse_input(raw, now=now)


def parse_input(raw: object, *, now: datetime | None = None) -> RealMatchLabInput:
    if not isinstance(raw, dict):
        raise InputValidationError("Input root must be an object.")
    if raw.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise InputValidationError("Unsupported input schema version.")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    kickoff = _timestamp(raw.get("kickoff_utc"), "kickoff_utc")
    collected = _timestamp(raw.get("collected_at"), "collected_at")
    source_updated = _timestamp(raw.get("source_updated_at"), "source_updated_at")
    if kickoff <= now:
        raise InputValidationError("Kickoff must be in the future.")
    if collected > now or source_updated > now:
        raise InputValidationError("Input timestamps cannot be in the future.")
    if source_updated > collected:
        raise InputValidationError("Source update cannot follow collection.")
    required = (
        "request_id", "operator_identity", "match_id", "competition", "season",
        "home_team", "away_team", "source_provider", "source_event_id",
        "source_snapshot_id",
    )
    values = {key: _text(raw.get(key), key) for key in required}
    if values["home_team"].casefold() == values["away_team"].casefold():
        raise InputValidationError("Home and away teams must differ.")
    if raw.get("environment") != "LAB":
        raise InputValidationError("Environment must be exactly LAB.")
    if raw.get("scope") != MODEL_SCOPE:
        raise InputValidationError("Only the controlled OFFICIAL_GLOBAL model scope is supported.")
    odds_raw = raw.get("odds")
    if not isinstance(odds_raw, list) or not odds_raw:
        raise InputValidationError("At least one immutable odds snapshot is required.")
    odds = tuple(_odds(item, kickoff, collected) for item in odds_raw)
    if len({item.market for item in odds}) != len(odds):
        raise InputValidationError("Only one supplied price per market is supported.")
    snapshot = _snapshot(raw, values, kickoff, collected, source_updated)
    notes = raw.get("operator_notes")
    if notes is not None:
        notes = _text(notes, "operator_notes", maximum=1000)
    source_commit = raw.get("source_commit")
    if source_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise InputValidationError("source_commit must be a full lowercase SHA-1.")
    return RealMatchLabInput(
        schema_version=INPUT_SCHEMA_VERSION,
        request_id=values["request_id"],
        environment="LAB",
        scope=MODEL_SCOPE,
        operator_identity=values["operator_identity"],
        match_id=values["match_id"],
        competition_id=_optional_text(raw.get("competition_id")),
        competition=values["competition"],
        season=values["season"],
        home_team_id=_optional_text(raw.get("home_team_id")),
        home_team=values["home_team"],
        away_team_id=_optional_text(raw.get("away_team_id")),
        away_team=values["away_team"],
        kickoff_utc=kickoff,
        collected_at=collected,
        source_updated_at=source_updated,
        source_provider=values["source_provider"],
        source_event_id=values["source_event_id"],
        source_snapshot_id=values["source_snapshot_id"],
        match_snapshot=snapshot,
        odds=odds,
        operator_notes=notes,
        source_commit=source_commit,
    )


def _snapshot(raw, values, kickoff, collected, source_updated):
    data = raw.get("data")
    if not isinstance(data, dict):
        raise InputValidationError("data object is required.")
    home_form = _form(data.get("home_recent_form"), "home_recent_form")
    away_form = _form(data.get("away_recent_form"), "away_recent_form")
    return MatchDataSnapshotRegistrationCommand(
        source_provider=values["source_provider"],
        source_event_id=values["source_event_id"],
        source_snapshot_id=values["source_snapshot_id"],
        match_id=values["match_id"],
        competition_id=_optional_text(raw.get("competition_id")),
        competition_name=values["competition"],
        season_identifier=values["season"],
        home_team_id=_optional_text(raw.get("home_team_id")),
        home_team_name=values["home_team"],
        away_team_id=_optional_text(raw.get("away_team_id")),
        away_team_name=values["away_team"],
        kickoff_timestamp=kickoff,
        snapshot_effective_timestamp=collected,
        source_updated_timestamp=source_updated,
        registration_timestamp=collected,
        scheduled_status=MatchSnapshotStatus.SCHEDULED,
        postponed_indicator=False,
        cancelled_indicator=False,
        neutral_venue_indicator=bool(data.get("neutral_venue", False)),
        venue=_optional_text(data.get("venue")),
        home_recent_form=home_form,
        away_recent_form=away_form,
        home_venue_split=_venue(data.get("home_venue_split")),
        away_venue_split=_venue(data.get("away_venue_split")),
        home_season_aggregate=_season(data.get("home_season")),
        away_season_aggregate=_season(data.get("away_season")),
        head_to_head=_h2h(data.get("head_to_head")),
        home_availability=_availability(data.get("home_availability")),
        away_availability=_availability(data.get("away_availability")),
        context=_context(data.get("context")),
        is_live=False,
    )


def _odds(raw, kickoff, collected):
    if not isinstance(raw, dict):
        raise InputValidationError("Each odds item must be an object.")
    market = _text(raw.get("market"), "odds.market")
    if market not in SUPPORTED_MARKETS:
        raise InputValidationError("Unsupported market; combos and correct scores are forbidden.")
    captured = _timestamp(raw.get("captured_at"), "odds.captured_at")
    if captured >= kickoff:
        raise InputValidationError("Odds must be captured before kickoff.")
    if captured > collected:
        raise InputValidationError("Odds capture cannot follow data collection.")
    try:
        price = Decimal(str(raw.get("decimal_odds")))
    except Exception as exc:
        raise InputValidationError("Odds must be a decimal number.") from exc
    if not price.is_finite() or price <= 1:
        raise InputValidationError("Odds must be finite and greater than 1.")
    return ManualOdds(
        snapshot_id=_text(raw.get("snapshot_id"), "odds.snapshot_id"),
        market=market,
        decimal_odds=price,
        source_provider=_text(raw.get("source_provider"), "odds.source_provider"),
        bookmaker_id=_text(raw.get("bookmaker_id"), "odds.bookmaker_id"),
        source_event_id=_text(raw.get("source_event_id"), "odds.source_event_id"),
        captured_at=captured,
    )


def _form(raw, label):
    if not isinstance(raw, dict):
        raise InputValidationError(f"{label} is required.")
    return FormRecord(**_record_values(raw, label), **_optional_metrics(raw))


def _venue(raw):
    if raw is None:
        return None
    return VenueSplitRecord(**_record_values(raw, "venue_split"), **{
        key: value for key, value in _optional_metrics(raw).items()
        if key in {"expected_goals_for", "expected_goals_against"}
    })


def _record_values(raw, label):
    if not isinstance(raw, dict):
        raise InputValidationError(f"{label} must be an object.")
    names = ("match_count", "wins", "draws", "losses", "goals_scored",
             "goals_conceded", "clean_sheets", "failed_to_score")
    try:
        return {name: int(raw[name]) for name in names}
    except (KeyError, TypeError, ValueError) as exc:
        raise InputValidationError(f"{label} requires complete integer results.") from exc


def _optional_metrics(raw):
    result = {}
    for name in ("expected_goals_for", "expected_goals_against", "possession"):
        result[name] = Decimal(str(raw[name])) if raw.get(name) is not None else None
    for name in ("shots", "shots_on_target"):
        result[name] = int(raw[name]) if raw.get(name) is not None else None
    return result


def _aggregate(raw):
    if raw is None:
        return None
    names = ("match_count", "wins", "draws", "losses", "goals_scored", "goals_conceded")
    return AggregateRecord(**{name: int(raw[name]) for name in names})


def _season(raw):
    if raw is None:
        return None
    return SeasonAggregateRecord(
        matches_played=int(raw["matches_played"]), points=int(raw["points"]),
        goals_scored=int(raw["goals_scored"]), goals_conceded=int(raw["goals_conceded"]),
        league_position=int(raw["league_position"]) if raw.get("league_position") is not None else None,
        expected_goals_for=Decimal(str(raw["expected_goals_for"])) if raw.get("expected_goals_for") is not None else None,
        expected_goals_against=Decimal(str(raw["expected_goals_against"])) if raw.get("expected_goals_against") is not None else None,
        home_record=_aggregate(raw.get("home_record")), away_record=_aggregate(raw.get("away_record")),
    )


def _h2h(raw):
    if raw is None:
        return None
    return HeadToHeadRecord(
        match_count=int(raw["match_count"]), home_team_wins=int(raw["home_team_wins"]),
        draws=int(raw["draws"]), away_team_wins=int(raw["away_team_wins"]),
        total_goals=int(raw["total_goals"]),
        both_teams_to_score_count=int(raw["both_teams_to_score_count"]),
        over_2_5_count=int(raw["over_2_5_count"]),
        most_recent_match_timestamp=_timestamp(raw["most_recent_match_timestamp"], "h2h timestamp")
        if raw.get("most_recent_match_timestamp") else None,
    )


def _availability(raw):
    if raw is None:
        return None
    return TeamAvailabilityRecord(
        confirmed_lineup=raw.get("confirmed_lineup"),
        probable_lineup=raw.get("probable_lineup"),
        injuries_count=_optional_int(raw.get("injuries_count")),
        suspensions_count=_optional_int(raw.get("suspensions_count")),
        missing_key_players_count=_optional_int(raw.get("missing_key_players_count")),
        goalkeeper_availability_status=_optional_text(raw.get("goalkeeper_availability_status")),
        lineup_source_timestamp=_timestamp(raw["lineup_source_timestamp"], "lineup timestamp")
        if raw.get("lineup_source_timestamp") else None,
        injury_source_timestamp=_timestamp(raw["injury_source_timestamp"], "injury timestamp")
        if raw.get("injury_source_timestamp") else None,
    )


def _context(raw):
    if raw is None:
        return None
    kwargs = {}
    for name in ("home_rest_days", "away_rest_days", "home_fixture_congestion_count",
                 "away_fixture_congestion_count"):
        kwargs[name] = _optional_int(raw.get(name))
    for name in ("home_travel_distance", "away_travel_distance"):
        kwargs[name] = Decimal(str(raw[name])) if raw.get(name) is not None else None
    for name in ("competition_stage", "weather_summary", "pitch_status"):
        kwargs[name] = _optional_text(raw.get(name))
    kwargs["derby_indicator"] = raw.get("derby_indicator")
    return MatchContextRecord(**kwargs)


def _timestamp(value, label):
    if not isinstance(value, str):
        raise InputValidationError(f"{label} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputValidationError(f"{label} is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InputValidationError(f"{label} must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def _text(value, label, maximum=200):
    if not isinstance(value, str):
        raise InputValidationError(f"{label} is required.")
    result = " ".join(value.strip().split())
    if not result or len(result) > maximum:
        raise InputValidationError(f"{label} is missing or too long.")
    return result


def _optional_text(value):
    return None if value is None else _text(value, "optional value")


def _optional_int(value):
    return None if value is None else int(value)
