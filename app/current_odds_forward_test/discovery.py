"""Bounded, deterministic API-Football current-fixture discovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.leagues import TOP_LEAGUES

from .input import CurrentOddsValidationError, normalize_api_football_current_odds, parse_current_odds


UPCOMING_STATUSES = frozenset({"NS", "TBD"})


async def discover_current_fixture(
    client,
    *,
    now: datetime,
    maximum_candidates: int = 50,
    maximum_api_calls: int = 8,
    horizon_days: int = 7,
    minimum_lead_minutes: int = 60,
) -> dict:
    """Return sanitized discovery evidence; never runs inference or publication."""

    if not 1 <= maximum_candidates <= 50 or not 1 <= maximum_api_calls <= 50:
        raise ValueError("Discovery limits must be between 1 and 50.")
    now = now.astimezone(timezone.utc)
    calls = 1
    payload = await client.fixtures_between(
        now.date().isoformat(), (now.date() + timedelta(days=horizon_days)).isoformat()
    )
    raw_fixtures = payload.get("response") if isinstance(payload, dict) else None
    fixtures = sorted(
        raw_fixtures if isinstance(raw_fixtures, list) else [], key=_fixture_order
    )[:maximum_candidates]
    skipped: dict[str, int] = {}
    inspected = 0
    selected = None
    terminal = "NO_ELIGIBLE_CURRENT_FIXTURE"
    for item in fixtures:
        inspected += 1
        fixture = _fixture_identity(item)
        reason = _fixture_rejection(fixture, now, minimum_lead_minutes)
        if reason:
            _increment(skipped, reason)
            continue
        if calls + 3 > maximum_api_calls:
            _increment(skipped, "API_CALL_LIMIT_REACHED")
            break
        try:
            home_history = await client.last_matches(fixture["home_team_id"], last=5)
            calls += 1
            away_history = await client.last_matches(fixture["away_team_id"], last=5)
            calls += 1
        except httpx.HTTPStatusError as exc:
            calls += 1
            terminal = "API_FOOTBALL_PLAN_RESTRICTED" if exc.response.status_code in {403, 429} else "API_FOOTBALL_UNAVAILABLE"
            _increment(skipped, terminal)
            break
        if len(home_history) < 5 or len(away_history) < 5:
            _increment(skipped, "INSUFFICIENT_REQUIRED_DATA")
            continue
        source_selected = datetime.now(timezone.utc)
        try:
            odds_payload = await client.current_odds(fixture["provider_fixture_id"])
            calls += 1
        except httpx.HTTPStatusError as exc:
            calls += 1
            reason = "API_FOOTBALL_PLAN_RESTRICTED" if exc.response.status_code in {403, 429} else "CURRENT_ODDS_UNAVAILABLE"
            _increment(skipped, reason)
            if reason == "API_FOOTBALL_PLAN_RESTRICTED":
                terminal = reason
                break
            continue
        retrieved = datetime.now(timezone.utc)
        try:
            normalized = normalize_api_football_current_odds(
                odds_payload,
                fixture_id=str(fixture["provider_fixture_id"]),
                kickoff_utc=fixture["kickoff_utc"],
                retrieved_at_utc=retrieved.isoformat(),
                source_selected_at_utc=source_selected.isoformat(),
            )
            snapshot = parse_current_odds(normalized, now=retrieved)
        except CurrentOddsValidationError as exc:
            reason = _safe_reason(exc)
            _increment(skipped, reason)
            terminal = "CURRENT_ODDS_UNAVAILABLE" if reason == "CURRENT_ODDS_UNAVAILABLE" else terminal
            continue
        if len(snapshot.quotes) < 3:
            _increment(skipped, "INSUFFICIENT_SUPPORTED_MARKETS")
            continue
        selected = {
            **fixture,
            "bookmaker": snapshot.bookmaker_name,
            "available_markets": [quote.market for quote in snapshot.quotes],
            "decimal_odds": {quote.market: str(quote.decimal_odds) for quote in snapshot.quotes},
            "api_retrieval_timestamp_utc": retrieved.isoformat(),
            "provider_update_timestamp_utc": (
                snapshot.quotes[0].provider_origin_timestamp_utc.isoformat()
                if snapshot.quotes[0].provider_origin_timestamp_utc else None
            ),
            "goalvision_captured_at_utc": snapshot.captured_at_utc.isoformat(),
            "timestamp_origin": (
                "PROVIDER_ORIGIN" if snapshot.quotes[0].provider_origin_timestamp_utc
                else "GOALVISION_ORIGIN"
            ),
            "odds_snapshot_id": snapshot.snapshot_id,
            "odds_snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "feature_baseline": {"home_recent_matches": 5, "away_recent_matches": 5},
        }
        terminal = "ELIGIBLE_CURRENT_FIXTURE_FOUND"
        break
    return {
        "terminal_result": terminal,
        "actual_utc_clock": now.isoformat(),
        "candidate_fixture_count": len(fixtures),
        "fixtures_inspected": inspected,
        "skipped_candidate_count": sum(skipped.values()),
        "skip_reasons": dict(sorted(skipped.items())),
        "selected_fixture": selected,
        "api_call_count": calls,
        "maximum_candidates": maximum_candidates,
        "maximum_api_calls": maximum_api_calls,
        "fixture_order": "KICKOFF_UTC_THEN_PROVIDER_FIXTURE_ID",
        "inference_executed": False,
        "telegram_sends": 0,
        "delivery_records": 0,
        "official_publications": 0,
    }


def _fixture_order(item: object) -> tuple[str, str]:
    fixture = item.get("fixture") if isinstance(item, dict) else None
    return (str(fixture.get("date", "")), str(fixture.get("id", ""))) if isinstance(fixture, dict) else ("", "")


def _fixture_identity(item: object) -> dict:
    if not isinstance(item, dict):
        return {}
    fixture = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    status = fixture.get("status") or {}
    return {
        "provider_fixture_id": fixture.get("id"),
        "kickoff_utc": fixture.get("date"),
        "fixture_status": status.get("short"),
        "competition_id": league.get("id"),
        "competition": league.get("name"),
        "season": league.get("season"),
        "home_team_id": home.get("id"),
        "home_team": home.get("name"),
        "away_team_id": away.get("id"),
        "away_team": away.get("name"),
    }


def _fixture_rejection(fixture: dict, now: datetime, minimum_lead_minutes: int) -> str | None:
    required = ("provider_fixture_id", "kickoff_utc", "competition_id", "competition", "home_team_id", "home_team", "away_team_id", "away_team")
    if any(fixture.get(name) in {None, ""} for name in required):
        return "MALFORMED_FIXTURE_IDENTITY"
    if fixture["fixture_status"] not in UPCOMING_STATUSES:
        return "NOT_UPCOMING_OR_POSTPONED"
    if fixture["competition"] not in TOP_LEAGUES:
        return "UNSUPPORTED_COMPETITION"
    try:
        kickoff = datetime.fromisoformat(str(fixture["kickoff_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return "MALFORMED_FIXTURE_IDENTITY"
    if kickoff <= now:
        return "NOT_UPCOMING_OR_POSTPONED"
    if kickoff <= now + timedelta(minutes=minimum_lead_minutes):
        return "KICKOFF_TOO_CLOSE"
    fixture["kickoff_utc"] = kickoff.isoformat()
    return None


def _safe_reason(exc: CurrentOddsValidationError) -> str:
    text = str(exc)
    if "STALE_CURRENT_ODDS" in text:
        return "STALE_CURRENT_ODDS"
    if "empty" in text.lower() or "At least one current quote" in text:
        return "CURRENT_ODDS_UNAVAILABLE"
    return "INCOMPATIBLE_MARKET_DATA"


def _increment(values: dict[str, int], key: str) -> None:
    values[key] = values.get(key, 0) + 1
