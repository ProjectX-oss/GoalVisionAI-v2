"""Adaptive, bounded and deterministic API-Football fixture discovery."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

import httpx

from app.football.quota import FootballQuotaError

from .input import CurrentOddsValidationError, normalize_api_football_current_odds, parse_current_odds
from .provider import PRIORITY_COMPETITIONS, resolve_current_competitions


UPCOMING_STATUSES = frozenset({"NS", "TBD"})
EXCLUDED_IDENTITY = re.compile(
    r"(?i)(\byouth\b|\bu[- ]?\d{2}\b|\breserves?\b|\bacademy\b|"
    r"\bvirtual\b|\besports?\b|\bfriendly\b|\bfriendlies\b)"
)


async def discover_current_fixture(
    client,
    *,
    now: datetime,
    maximum_candidates: int = 50,
    maximum_api_calls: int = 40,
    horizon_days: int = 7,
    minimum_lead_minutes: int = 60,
    daily_quota_reserve: int = 20,
) -> dict:
    """Search staged current fixtures and odds without invoking inference."""

    if not 1 <= maximum_candidates <= 50 or not 1 <= maximum_api_calls <= 40:
        raise ValueError("Discovery limits exceed the reviewed 50-candidate/40-call policy.")
    if not 1 <= horizon_days <= 7 or minimum_lead_minutes < 60:
        raise ValueError("Discovery horizon or safe kickoff lead is outside policy.")
    now = now.astimezone(timezone.utc)
    reports: list[dict] = []
    skipped: dict[str, int] = {}
    rejection_seen: set[tuple[object, str]] = set()
    evaluated: set[int] = set()
    odds_requested: set[int] = set()
    all_rows: dict[int, dict] = {}
    fixture_results = 0

    leagues_payload = await client.leagues(current=True)
    reports.append(_stage_report("COMPETITION_RESOLUTION", client.response_metadata()))
    competitions = resolve_current_competitions(leagues_payload, observed_at=now)
    catalog = _competition_catalog(leagues_payload, now.date())
    priority = {league_id: rank for rank, (league_id, *_rest) in enumerate(PRIORITY_COMPETITIONS)}
    try:
        effective_limit = _effective_call_limit(client, maximum_api_calls, daily_quota_reserve)
    except FootballQuotaError as exc:
        return _result(
            now, reports, competitions, skipped, None, fixture_results, 0,
            client, str(exc), maximum_candidates=maximum_candidates,
            maximum_api_calls=maximum_api_calls,
        )

    stage_dates = (
        ("PRIORITY_24_TO_72_HOURS", range(0, min(3, horizon_days) + 1), True),
        ("PRIORITY_NEXT_7_DAYS", range(min(3, horizon_days) + 1, horizon_days + 1), True),
    )
    selected = None
    candidates_considered = 0
    coverage_limited = False
    for stage_name, offsets, priority_only in stage_dates:
        for offset in offsets:
            if _request_count(client) >= effective_limit:
                coverage_limited = True
                break
            day = (now.date() + timedelta(days=offset)).isoformat()
            payload = await client.fixtures_by_date(day, timezone_name="UTC")
            metadata = client.response_metadata()
            reports.append(_stage_report(stage_name, metadata))
            if metadata.get("errors"):
                errors_text = str(metadata["errors"]).casefold()
                reason = "API_FOOTBALL_PLAN_RESTRICTED" if "plan" in errors_text or "access" in errors_text else "PROVIDER_FIXTURE_QUERY_REJECTED"
                _increment(skipped, reason)
                if reason == "API_FOOTBALL_PLAN_RESTRICTED":
                    coverage_limited = True
                    break
                continue
            rows = payload.get("response") if isinstance(payload, dict) else None
            rows = rows if isinstance(rows, list) else []
            fixture_results += len(rows)
            new_rows = []
            for row in rows:
                identity = _fixture_identity(row)
                fixture_id = identity.get("provider_fixture_id")
                if isinstance(fixture_id, int) and fixture_id not in all_rows:
                    all_rows[fixture_id] = row
                    new_rows.append(row)
            stage_candidates = _ordered_candidates(
                new_rows, now=now, minimum_lead_minutes=minimum_lead_minutes,
                catalog=catalog, priority=priority, priority_only=priority_only,
                skipped=skipped, rejection_seen=rejection_seen,
            )
            selected, used = await _evaluate_candidates(
                client, stage_candidates, evaluated=evaluated, odds_requested=odds_requested,
                skipped=skipped, effective_limit=effective_limit,
                remaining_candidates=maximum_candidates - candidates_considered,
            )
            candidates_considered += used
            reports.append({"stage": stage_name, "date": day, "provider_rows_seen": len(new_rows), "eligible_candidates_evaluated": used, "selected_fixture_id": selected.get("provider_fixture_id") if selected else None})
            if selected or candidates_considered >= maximum_candidates or skipped.get("API_FOOTBALL_QUOTA_INSUFFICIENT") or _request_count(client) >= effective_limit:
                break
        if selected or candidates_considered >= maximum_candidates or skipped.get("API_FOOTBALL_QUOTA_INSUFFICIENT") or coverage_limited or _request_count(client) >= effective_limit:
            break

    if selected is None and candidates_considered < maximum_candidates and not skipped.get("API_FOOTBALL_QUOTA_INSUFFICIENT"):
        fallback = _ordered_candidates(
            all_rows.values(), now=now, minimum_lead_minutes=minimum_lead_minutes,
            catalog=catalog, priority=priority, priority_only=False,
            skipped=skipped, rejection_seen=rejection_seen,
        )
        fallback = [item for item in fallback if item["provider_fixture_id"] not in evaluated]
        selected, used = await _evaluate_candidates(
            client, fallback, evaluated=evaluated, odds_requested=odds_requested,
            skipped=skipped, effective_limit=effective_limit,
            remaining_candidates=maximum_candidates - candidates_considered,
        )
        candidates_considered += used
        reports.append({"stage": "ALL_SUPPORTED_PROFESSIONAL_SENIOR_NEXT_7_DAYS", "provider_rows_seen": len(all_rows), "eligible_candidates_evaluated": used, "selected_fixture_id": selected.get("provider_fixture_id") if selected else None})

    terminal = "ELIGIBLE_CURRENT_FIXTURE_FOUND" if selected else (
        "API_FOOTBALL_QUOTA_INSUFFICIENT" if _request_count(client) >= effective_limit else
        "API_FOOTBALL_PLAN_RESTRICTED" if coverage_limited and skipped.get("API_FOOTBALL_PLAN_RESTRICTED") else
        "CURRENT_ODDS_UNAVAILABLE" if skipped.get("CURRENT_ODDS_UNAVAILABLE") else
        "NO_ELIGIBLE_CURRENT_FIXTURE"
    )
    return _result(
        now, reports, competitions, skipped, selected, fixture_results,
        candidates_considered, client, terminal, odds_requests=len(odds_requested),
        maximum_candidates=maximum_candidates, maximum_api_calls=maximum_api_calls,
    )


async def _evaluate_candidates(client, candidates, *, evaluated, odds_requested, skipped, effective_limit, remaining_candidates):
    used = 0
    for fixture in candidates[:max(0, remaining_candidates)]:
        fixture_id = fixture["provider_fixture_id"]
        evaluated.add(fixture_id)
        used += 1
        if _request_count(client) + 3 > effective_limit:
            _increment(skipped, "API_FOOTBALL_QUOTA_INSUFFICIENT")
            break
        try:
            home_history = await client.last_matches(fixture["home_team_id"], last=5)
            away_history = await client.last_matches(fixture["away_team_id"], last=5)
        except httpx.HTTPStatusError as exc:
            _increment(skipped, "API_FOOTBALL_PLAN_RESTRICTED" if exc.response.status_code in {403, 429} else "INSUFFICIENT_REQUIRED_DATA")
            continue
        if not isinstance(home_history, list) or not isinstance(away_history, list) or not home_history or not away_history:
            _increment(skipped, "INSUFFICIENT_REQUIRED_DATA")
            continue
        if fixture_id in odds_requested:
            _increment(skipped, "DUPLICATE_ODDS_REQUEST_BLOCKED")
            continue
        odds_requested.add(fixture_id)
        source_selected = datetime.now(timezone.utc)
        try:
            odds_payload = await client.current_odds(fixture_id)
        except httpx.HTTPStatusError as exc:
            _increment(skipped, "API_FOOTBALL_PLAN_RESTRICTED" if exc.response.status_code in {403, 429} else "CURRENT_ODDS_UNAVAILABLE")
            continue
        retrieved = datetime.now(timezone.utc)
        try:
            normalized = normalize_api_football_current_odds(
                odds_payload, fixture_id=str(fixture_id), kickoff_utc=fixture["kickoff_utc"],
                retrieved_at_utc=retrieved.isoformat(), source_selected_at_utc=source_selected.isoformat(),
            )
            snapshot = parse_current_odds(normalized, now=retrieved)
        except CurrentOddsValidationError as exc:
            _increment(skipped, _safe_reason(exc))
            continue
        if snapshot.canonical_fixture_id != str(fixture_id):
            _increment(skipped, "FIXTURE_ODDS_IDENTITY_MISMATCH")
            continue
        if len(snapshot.quotes) < 3:
            _increment(skipped, "INSUFFICIENT_SUPPORTED_MARKETS")
            continue
        return ({
            **fixture,
            "fixture_selected_at_utc": source_selected.isoformat(),
            "bookmaker": snapshot.bookmaker_name,
            "available_markets": [quote.market for quote in snapshot.quotes],
            "missing_markets": [market for market in _supported_markets() if market not in {quote.market for quote in snapshot.quotes}],
            "decimal_odds": {quote.market: str(quote.decimal_odds) for quote in snapshot.quotes},
            "quote_count": len(snapshot.quotes),
            "api_retrieval_timestamp_utc": retrieved.isoformat(),
            "provider_update_timestamp_utc": snapshot.quotes[0].provider_origin_timestamp_utc.isoformat() if snapshot.quotes[0].provider_origin_timestamp_utc else None,
            "goalvision_captured_at_utc": snapshot.captured_at_utc.isoformat(),
            "timestamp_origin": "PROVIDER_ORIGIN" if snapshot.quotes[0].provider_origin_timestamp_utc else "GOALVISION_ORIGIN",
            "odds_freshness": snapshot.freshness_status,
            "odds_snapshot_id": snapshot.snapshot_id,
            "odds_snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "odds_contract": normalized,
            "feature_baseline": {"home_recent_matches": len(home_history), "away_recent_matches": len(away_history)},
        }, used)
    return None, used


def _ordered_candidates(rows, *, now, minimum_lead_minutes, catalog, priority, priority_only, skipped, rejection_seen=None):
    values = []
    for row in rows:
        fixture = _fixture_identity(row)
        reason = _fixture_rejection(fixture, now, minimum_lead_minutes, catalog)
        if reason:
            identity = (fixture.get("provider_fixture_id"), reason)
            if rejection_seen is None or identity not in rejection_seen:
                _increment(skipped, reason)
                if rejection_seen is not None: rejection_seen.add(identity)
            continue
        league_id = fixture["competition_id"]
        if priority_only and league_id not in priority:
            continue
        fixture["competition_priority"] = priority.get(league_id, len(priority))
        values.append(fixture)
    return sorted(values, key=lambda item: (item["kickoff_utc"], item["competition_priority"], item["provider_fixture_id"]))


def _fixture_identity(item: object) -> dict:
    if not isinstance(item, dict): return {}
    fixture, league, teams = item.get("fixture") or {}, item.get("league") or {}, item.get("teams") or {}
    home, away, status = teams.get("home") or {}, teams.get("away") or {}, fixture.get("status") or {}
    return {"provider_fixture_id": fixture.get("id"), "kickoff_utc": fixture.get("date"), "fixture_status": status.get("short"), "competition_id": league.get("id"), "competition": league.get("name"), "season": league.get("season"), "home_team_id": home.get("id"), "home_team": home.get("name"), "away_team_id": away.get("id"), "away_team": away.get("name")}


def _fixture_rejection(fixture, now, minimum_lead_minutes, catalog):
    required = ("provider_fixture_id", "kickoff_utc", "competition_id", "competition", "season", "home_team_id", "home_team", "away_team_id", "away_team")
    if any(fixture.get(name) in {None, ""} for name in required): return "MALFORMED_FIXTURE_IDENTITY"
    if fixture["fixture_status"] not in UPCOMING_STATUSES: return "NOT_UPCOMING_OR_POSTPONED"
    competition = catalog.get(fixture["competition_id"])
    if competition is None or competition["type"] not in {"League", "Cup"}: return "UNSUPPORTED_COMPETITION_TYPE"
    if int(fixture["season"]) != competition["season"]: return "STALE_OR_UNRESOLVED_SEASON"
    if EXCLUDED_IDENTITY.search(" ".join(str(fixture.get(key, "")) for key in ("competition", "home_team", "away_team"))): return "EXCLUDED_FIXTURE_CLASS"
    try: kickoff = datetime.fromisoformat(str(fixture["kickoff_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError: return "MALFORMED_FIXTURE_IDENTITY"
    if kickoff <= now: return "ALREADY_STARTED"
    if kickoff <= now + timedelta(minutes=minimum_lead_minutes): return "KICKOFF_TOO_CLOSE"
    fixture["kickoff_utc"] = kickoff.isoformat()
    return None


def _competition_catalog(payload, today):
    result = {}
    rows = payload.get("response") if isinstance(payload, dict) else None
    for row in rows if isinstance(rows, list) else []:
        league = row.get("league") if isinstance(row, dict) and isinstance(row.get("league"), dict) else {}
        seasons = row.get("seasons") if isinstance(row, dict) and isinstance(row.get("seasons"), list) else []
        covering = [season for season in seasons if isinstance(season, dict) and season.get("current") is True and _season_covers(season, today)]
        season = max(covering, key=lambda item: int(item.get("year", 0)), default=None)
        if isinstance(league.get("id"), int) and season is not None:
            result[league["id"]] = {"type": league.get("type"), "name": league.get("name"), "season": int(season["year"]), "coverage": season.get("coverage") or {}}
    return result


def _season_covers(season, today):
    try: return date.fromisoformat(str(season["start"])) <= today <= date.fromisoformat(str(season["end"]))
    except (KeyError, TypeError, ValueError): return False


def _effective_call_limit(client, maximum, reserve):
    quota = client.quota_snapshot()
    if quota.get("interpretation_status") != "NORMALIZED" or quota.get("daily_remaining") is None: raise FootballQuotaError("API_FOOTBALL_QUOTA_AMBIGUOUS")
    available = int(quota["daily_remaining"]) - reserve
    minute_remaining = quota.get("minute_remaining")
    if minute_remaining is None: raise FootballQuotaError("API_FOOTBALL_QUOTA_AMBIGUOUS")
    available = min(available, int(minute_remaining))
    if available < 1: raise FootballQuotaError("API_FOOTBALL_QUOTA_INSUFFICIENT")
    return min(maximum, _request_count(client) + available)


def _request_count(client): return int(getattr(client, "request_count", getattr(client, "calls", 0)))
def _stage_report(stage, metadata): return {"stage": stage, "request": metadata}
def _supported_markets():
    from app.real_match_lab_analysis.policy import SUPPORTED_MARKETS
    return SUPPORTED_MARKETS
def _safe_reason(exc):
    text = str(exc)
    if "STALE_CURRENT_ODDS" in text: return "STALE_CURRENT_ODDS"
    if "empty" in text.lower() or "At least one current quote" in text: return "CURRENT_ODDS_UNAVAILABLE"
    if "Unsupported" in text or "Correct score" in text: return "UNSUPPORTED_MARKET_DATA"
    return "MALFORMED_ODDS"
def _increment(values, key): values[key] = values.get(key, 0) + 1
def _result(
    now, reports, competitions, skipped, selected, fixture_results, candidates,
    client, terminal, odds_requests=0, *, maximum_candidates=50,
    maximum_api_calls=40,
):
    return {"schema_version": "goalvision-adaptive-current-fixture-discovery-v1", "terminal_result": terminal, "actual_utc_clock": now.isoformat(), "discovery_stages": reports, "competition_resolver": list(competitions), "provider_fixture_rows": fixture_results, "candidate_fixture_count": candidates, "fixtures_inspected": candidates, "maximum_candidates": maximum_candidates, "maximum_api_calls": maximum_api_calls, "skipped_candidate_count": sum(skipped.values()), "skip_reasons": dict(sorted(skipped.items())), "selected_fixture": selected, "api_call_count": _request_count(client), "odds_request_count": odds_requests, "fixture_order": "EARLIEST_SAFE_KICKOFF_THEN_COMPETITION_PRIORITY_THEN_PROVIDER_FIXTURE_ID", "inference_executed": False, "telegram_sends": 0, "delivery_records": 0, "official_publications": 0}
