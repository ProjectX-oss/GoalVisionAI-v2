"""Sanitized API-Football capability and current-season diagnostics."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.football.quota import FootballQuotaError
from app.real_match_lab_analysis.fingerprint import fingerprint


PRIORITY_COMPETITIONS = (
    (39, "Premier League", "England", "League"),
    (78, "Bundesliga", "Germany", "League"),
    (140, "La Liga", "Spain", "League"),
    (135, "Serie A", "Italy", "League"),
    (61, "Ligue 1", "France", "League"),
    (88, "Eredivisie", "Netherlands", "League"),
    (94, "Primeira Liga", "Portugal", "League"),
    (179, "Premiership", "Scotland", "League"),
    (2, "UEFA Champions League", "World", "Cup"),
    (3, "UEFA Europa League", "World", "Cup"),
    (848, "UEFA Conference League", "World", "Cup"),
    (253, "Major League Soccer", "USA", "League"),
    (144, "Jupiler Pro League", "Belgium", "League"),
    (203, "Süper Lig", "Turkey", "League"),
)


def resolve_current_competitions(payload: object, *, observed_at: datetime) -> tuple[dict, ...]:
    """Resolve reviewed priority competitions using provider season chronology."""

    rows = payload.get("response") if isinstance(payload, dict) else None
    by_id = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        league = row.get("league") if isinstance(row.get("league"), dict) else {}
        by_id[league.get("id")] = row
    result = []
    today = observed_at.astimezone(timezone.utc).date()
    for priority, (league_id, expected_name, expected_country, expected_type) in enumerate(PRIORITY_COMPETITIONS):
        row = by_id.get(league_id)
        if row is None:
            result.append(_unresolved(priority, league_id, expected_name, expected_country, expected_type, observed_at, "LEAGUE_NOT_IN_CURRENT_PROVIDER_RESPONSE"))
            continue
        league = row.get("league") or {}
        country = row.get("country") or {}
        if league.get("type") != expected_type:
            result.append(_unresolved(priority, league_id, expected_name, expected_country, expected_type, observed_at, "COMPETITION_TYPE_MISMATCH"))
            continue
        seasons = row.get("seasons") if isinstance(row.get("seasons"), list) else []
        current = [item for item in seasons if isinstance(item, dict) and item.get("current") is True]
        covering = [item for item in current if _covers(item, today)]
        season = max(covering, key=lambda item: int(item.get("year", 0)), default=None)
        reason = None
        if season is None and current:
            reason = "STALE_HARD_CODED_CURRENT_SEASON_REJECTED"
        elif season is None:
            reason = "CURRENT_SEASON_UNAVAILABLE"
        coverage = season.get("coverage") if isinstance(season, dict) and isinstance(season.get("coverage"), dict) else {}
        result.append({
            "priority": priority,
            "provider_league_id": league_id,
            "country": country.get("name") or expected_country,
            "competition_name": league.get("name") or expected_name,
            "competition_type": league.get("type") or expected_type,
            "resolution_status": "RESOLVED" if season is not None else "UNRESOLVED",
            "reason_code": reason,
            "current_season": season.get("year") if season else None,
            "season_start": season.get("start") if season else None,
            "season_end": season.get("end") if season else None,
            "fixture_coverage": bool(coverage.get("fixtures")) if season else False,
            "odds_coverage": bool(coverage.get("odds")) if season else False,
            "last_successful_refresh_timestamp_utc": observed_at.isoformat(),
            "source_provenance": "API_FOOTBALL_/leagues?current=true",
        })
    return tuple(result)


async def diagnose_fixture_discovery(client, *, now: datetime, daily_reserve: int = 20) -> dict:
    """Run six bounded provider calls plus one local coverage check."""

    now = now.astimezone(timezone.utc)
    metadata = []
    status = await client.account_status()
    metadata.append(client.response_metadata())
    _require(client, 6, daily_reserve)
    leagues_payload = await client.leagues(current=True)
    metadata.append(client.response_metadata())
    resolved = resolve_current_competitions(leagues_payload, observed_at=now)
    date_text = now.date().isoformat()
    end_text = (now.date() + timedelta(days=7)).isoformat()
    await client.fixtures_by_date(date_text, timezone_name="UTC")
    metadata.append(client.response_metadata())
    # Prove that adding UTC alone does not make an unscoped range valid.
    await client._get(
        "/fixtures",
        params={"from": date_text, "to": end_text, "timezone": "UTC"},
    )
    metadata.append(client.response_metadata())
    # Reproduce the exact previous request: from/to only, with no timezone,
    # league, season, status, or pagination parameters.
    response = await client._get("/fixtures", params={"from": date_text, "to": end_text})
    previous_payload = response.json()
    metadata.append(client.response_metadata())
    known = next((item for item in resolved if item["resolution_status"] == "RESOLVED" and item["fixture_coverage"]), None)
    if known is not None:
        await client.fixtures_between(date_text, end_text, timezone_name="UTC", league_id=int(known["provider_league_id"]), season=int(known["current_season"]))
        metadata.append(client.response_metadata())
    metadata.append({"stage": "ODDS_COVERAGE_METADATA", "source": "/leagues season.coverage.odds", "resolved_competitions_with_odds": [item["provider_league_id"] for item in resolved if item["resolution_status"] == "RESOLVED" and item["odds_coverage"]], "network_request": False})
    previous_meta = next(item for item in metadata if item["endpoint"] == "/fixtures" and item["query"] == {"from": date_text, "to": end_text})
    cause = _zero_cause(previous_meta, previous_payload, resolved, now.date())
    response = status.get("response") if isinstance(status, dict) else None
    subscription = response.get("subscription") if isinstance(response, dict) else None
    value = {
        "schema_version": "goalvision-api-football-fixture-diagnosis-v1",
        "execution_timestamp_utc": now.isoformat(),
        "authentication_status": "AUTHENTICATED",
        "plan_status": "AVAILABLE" if isinstance(subscription, dict) and subscription.get("active") else "PLAN_RESTRICTED",
        "previous_zero_result_cause": cause,
        "previous_request": previous_meta,
        "requests": metadata,
        "competition_resolver": list(resolved),
        "api_calls_used": client.request_count,
        "quota": client.quota_snapshot(),
        "daily_reserve": daily_reserve,
        "raw_response_persisted": False,
        "secret_redacted": True,
    }
    value["diagnostic_fingerprint"] = fingerprint(value)
    return value


def write_sanitized_metadata(path: Path, value: dict) -> None:
    """Persist only canonical sanitized diagnostics beneath ignored ``var``."""

    root = (Path.cwd() / "var").resolve()
    target = path.resolve()
    if target != root and root not in target.parents:
        raise ValueError("Diagnostic metadata output must be beneath var/.")
    from app.real_match_lab_analysis.fingerprint import canonical_json
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _require(client, additional_calls: int, reserve: int) -> None:
    quota = client.quota_snapshot()
    if (
        quota.get("interpretation_status") != "NORMALIZED"
        or quota.get("daily_remaining") is None
        or quota.get("minute_remaining") is None
    ):
        raise FootballQuotaError("API_FOOTBALL_QUOTA_AMBIGUOUS")
    if (
        int(quota["daily_remaining"]) - additional_calls < reserve
        or int(quota["minute_remaining"]) < additional_calls
    ):
        raise FootballQuotaError("API_FOOTBALL_QUOTA_INSUFFICIENT")


def _covers(season: dict, today: date) -> bool:
    try:
        return date.fromisoformat(str(season["start"])) <= today <= date.fromisoformat(str(season["end"]))
    except (KeyError, TypeError, ValueError):
        return False


def _unresolved(priority, league_id, name, country, kind, observed_at, reason):
    return {"priority": priority, "provider_league_id": league_id, "country": country, "competition_name": name, "competition_type": kind, "resolution_status": "UNRESOLVED", "reason_code": reason, "current_season": None, "season_start": None, "season_end": None, "fixture_coverage": False, "odds_coverage": False, "last_successful_refresh_timestamp_utc": observed_at.isoformat(), "source_provenance": "API_FOOTBALL_/leagues?current=true"}


def _zero_cause(metadata: dict, payload: object, competitions: tuple[dict, ...], today: date) -> dict:
    errors = metadata.get("errors")
    if errors:
        return {"code": "PROVIDER_QUERY_REJECTED", "details": errors}
    results = metadata.get("results")
    response = payload.get("response") if isinstance(payload, dict) else None
    resolved = [item for item in competitions if item["resolution_status"] == "RESOLVED"]
    if results == 0 and isinstance(response, list) and not response:
        return {
            "code": "PROVIDER_RETURNED_NO_FIXTURES_FOR_REQUESTED_FUTURE_WINDOW",
            "details": {
                "parser_schema_valid": True,
                "resolved_priority_competitions": len(resolved),
                "requested_date_after_all_resolved_season_ends": bool(resolved) and all(date.fromisoformat(item["season_end"]) < today for item in resolved),
            },
        }
    return {"code": "PARSER_OR_RESPONSE_COUNT_MISMATCH", "details": {"results": results}}
