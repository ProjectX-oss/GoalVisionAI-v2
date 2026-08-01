"""Adaptive, bounded and deterministic API-Football fixture discovery."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re

import httpx

from app.football.quota import FootballQuotaError

from .efficiency import (
    CompetitionCapabilityCache,
    RunDataCache,
    empty_candidate_costs,
    plan_candidate,
)
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
    capability_cache_path: Path | None = None,
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
    request_cost_report: list[dict] = []
    stage_request_costs: list[dict] = []
    data_cache = RunDataCache()

    capability_cache = (
        CompetitionCapabilityCache.load(capability_cache_path, now=now)
        if capability_cache_path is not None else None
    )
    if capability_cache is None:
        before = _request_count(client)
        leagues_payload = await client.leagues(current=True)
        after = _request_count(client)
        reports.append(_stage_report("COMPETITION_RESOLUTION", client.response_metadata()))
        stage_request_costs.append({"stage": "COMPETITION_RESOLUTION", "actual_calls": after - before, "cache": "MISS"})
        competitions = resolve_current_competitions(leagues_payload, observed_at=now)
        capability_cache = CompetitionCapabilityCache.from_provider_payload(
            leagues_payload, retrieved_at_utc=now
        )
        if capability_cache_path is not None:
            capability_cache.save(capability_cache_path)
        capability_cache_status = "REFRESHED"
    else:
        before = _request_count(client)
        await client.account_status()
        after = _request_count(client)
        reports.append(_stage_report("QUOTA_REFRESH_CAPABILITY_CACHE_HIT", client.response_metadata()))
        stage_request_costs.append({"stage": "QUOTA_REFRESH_CAPABILITY_CACHE_HIT", "actual_calls": after - before, "cache": "HIT"})
        competitions = _resolved_from_cache(capability_cache, observed_at=now)
        capability_cache_status = "HIT"
    catalog = _catalog_from_cache(capability_cache, now.date())
    priority = {league_id: rank for rank, (league_id, *_rest) in enumerate(PRIORITY_COMPETITIONS)}
    try:
        effective_limit = _effective_call_limit(client, maximum_api_calls, daily_quota_reserve)
    except FootballQuotaError as exc:
        terminal = (
            "DISCOVERY_QUOTA_INSUFFICIENT"
            if "INSUFFICIENT" in str(exc) else str(exc)
        )
        return _result(
            now, reports, competitions, skipped, None, fixture_results, 0,
            client, terminal, maximum_candidates=maximum_candidates,
            maximum_api_calls=maximum_api_calls, request_cost_report=request_cost_report,
            stage_request_costs=stage_request_costs, capability_cache=capability_cache,
            capability_cache_status=capability_cache_status,
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
            before = _request_count(client)
            payload = await client.fixtures_by_date(day, timezone_name="UTC")
            after = _request_count(client)
            metadata = client.response_metadata()
            reports.append(_stage_report(stage_name, metadata))
            stage_request_costs.append({"stage": stage_name, "date": day, "actual_calls": after - before, "cache": "MISS", "retries": max(0, after - before - 1)})
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
                elif isinstance(fixture_id, int):
                    _increment(skipped, "DUPLICATE_EVENT")
            stage_candidates = _ordered_candidates(
                new_rows, now=now, minimum_lead_minutes=minimum_lead_minutes,
                catalog=catalog, priority=priority, priority_only=priority_only,
                skipped=skipped, rejection_seen=rejection_seen,
            )
            for candidate in stage_candidates:
                candidate["fixture_list_reference"] = f"{stage_name}:{day}"
            selected, used, traces = await _evaluate_candidates(
                client, stage_candidates, evaluated=evaluated, odds_requested=odds_requested,
                skipped=skipped, effective_limit=effective_limit,
                remaining_candidates=maximum_candidates - candidates_considered,
                data_cache=data_cache, cutoff=now,
            )
            request_cost_report.extend(traces)
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
        selected, used, traces = await _evaluate_candidates(
            client, fallback, evaluated=evaluated, odds_requested=odds_requested,
            skipped=skipped, effective_limit=effective_limit,
            remaining_candidates=maximum_candidates - candidates_considered,
            data_cache=data_cache, cutoff=now,
        )
        request_cost_report.extend(traces)
        candidates_considered += used
        reports.append({"stage": "ALL_SUPPORTED_PROFESSIONAL_SENIOR_NEXT_7_DAYS", "provider_rows_seen": len(all_rows), "eligible_candidates_evaluated": used, "selected_fixture_id": selected.get("provider_fixture_id") if selected else None})

    terminal = "ELIGIBLE_CURRENT_FIXTURE_FOUND" if selected else (
        "DISCOVERY_QUOTA_INSUFFICIENT" if skipped.get("API_FOOTBALL_QUOTA_INSUFFICIENT") or _request_count(client) >= effective_limit else
        "API_FOOTBALL_PLAN_RESTRICTED" if coverage_limited and skipped.get("API_FOOTBALL_PLAN_RESTRICTED") else
        "CURRENT_ODDS_UNAVAILABLE" if skipped.get("CURRENT_ODDS_UNAVAILABLE") else
        "NO_ELIGIBLE_CURRENT_FIXTURE"
    )
    return _result(
        now, reports, competitions, skipped, selected, fixture_results,
        candidates_considered, client, terminal, odds_requests=len(odds_requested),
        maximum_candidates=maximum_candidates, maximum_api_calls=maximum_api_calls,
        request_cost_report=request_cost_report, stage_request_costs=stage_request_costs,
        capability_cache=capability_cache, capability_cache_status=capability_cache_status,
    )


async def _evaluate_candidates(
    client, candidates, *, evaluated, odds_requested, skipped, effective_limit,
    remaining_candidates, data_cache, cutoff,
):
    used = 0
    traces = []
    remaining = list(candidates)
    while remaining and used < max(0, remaining_candidates):
        remaining.sort(key=lambda item: _candidate_priority(item, data_cache, cutoff))
        fixture = remaining.pop(0)
        fixture_id = fixture["provider_fixture_id"]
        evaluated.add(fixture_id)
        used += 1
        plan = plan_candidate(
            fixture, data_cache, cutoff=cutoff,
            request_count=_request_count(client), effective_call_limit=effective_limit,
        )
        trace = {
            "provider_fixture_id": fixture_id,
            "competition_id": fixture["competition_id"],
            "season": fixture["season"],
            "shared_fixture_list_call": fixture.get("fixture_list_reference"),
            "planner": asdict(plan),
            "calls": empty_candidate_costs(),
            "cache_hits": [],
            "cache_misses": [],
            "required_order": ["HOME_TEAM_HISTORY", "AWAY_TEAM_HISTORY", "CURRENT_ODDS"],
            "optional_calls": {
                "standings": "NOT_REQUIRED_BY_EXISTING_BASELINE",
                "injuries": "NOT_REQUIRED_BEFORE_BASELINE",
                "lineups": "NOT_REQUIRED_BEFORE_BASELINE",
                "statistics": "NOT_REQUIRED_BEFORE_BASELINE",
            },
            "result": None,
        }
        if plan.status != "CANDIDATE_EVALUATION_ALLOWED":
            _increment(skipped, "API_FOOTBALL_QUOTA_INSUFFICIENT")
            trace["result"] = "CANDIDATE_SKIPPED_QUOTA"
            traces.append(trace)
            break
        home_history, home_reason = await _team_history(
            client, data_cache, fixture, fixture["home_team_id"], "HOME",
            cutoff=cutoff, trace=trace,
        )
        if home_reason is not None or not isinstance(home_history, list) or not home_history:
            reason = home_reason or "INSUFFICIENT_REQUIRED_DATA"
            _increment(skipped, reason)
            trace["result"] = "CANDIDATE_SKIPPED_BASELINE"
            trace["rejection_reason"] = reason
            traces.append(trace)
            continue
        away_history, away_reason = await _team_history(
            client, data_cache, fixture, fixture["away_team_id"], "AWAY",
            cutoff=cutoff, trace=trace,
        )
        if away_reason is not None or not isinstance(away_history, list) or not away_history:
            reason = away_reason or "INSUFFICIENT_REQUIRED_DATA"
            _increment(skipped, reason)
            trace["result"] = "CANDIDATE_SKIPPED_BASELINE"
            trace["rejection_reason"] = reason
            traces.append(trace)
            continue
        if fixture_id in odds_requested:
            _increment(skipped, "DUPLICATE_ODDS_REQUEST_BLOCKED")
            trace["result"] = "DUPLICATE_ODDS_REQUEST_BLOCKED"
            traces.append(trace)
            continue
        odds_requested.add(fixture_id)
        source_selected = datetime.now(timezone.utc)
        before = _request_count(client)
        try:
            odds_payload = await client.current_odds(fixture_id)
        except httpx.HTTPStatusError as exc:
            actual = _request_count(client) - before
            trace["calls"]["odds"] += actual
            trace["calls"]["retries"] += max(0, actual - 1)
            reason = "API_FOOTBALL_PLAN_RESTRICTED" if exc.response.status_code in {403, 429} else "CURRENT_ODDS_UNAVAILABLE"
            _increment(skipped, reason)
            trace["result"] = reason
            traces.append(trace)
            continue
        actual = _request_count(client) - before
        trace["calls"]["odds"] += actual
        trace["calls"]["retries"] += max(0, actual - 1)
        retrieved = datetime.now(timezone.utc)
        try:
            normalized = normalize_api_football_current_odds(
                odds_payload, fixture_id=str(fixture_id), kickoff_utc=fixture["kickoff_utc"],
                retrieved_at_utc=retrieved.isoformat(), source_selected_at_utc=source_selected.isoformat(),
            )
            snapshot = parse_current_odds(normalized, now=retrieved)
        except CurrentOddsValidationError as exc:
            reason = _safe_reason(exc)
            _increment(skipped, reason)
            trace["result"] = reason
            traces.append(trace)
            continue
        if snapshot.canonical_fixture_id != str(fixture_id):
            _increment(skipped, "FIXTURE_ODDS_IDENTITY_MISMATCH")
            trace["result"] = "FIXTURE_ODDS_IDENTITY_MISMATCH"
            traces.append(trace)
            continue
        if len(snapshot.quotes) < 3:
            _increment(skipped, "INSUFFICIENT_SUPPORTED_MARKETS")
            trace["result"] = "INSUFFICIENT_SUPPORTED_MARKETS"
            traces.append(trace)
            continue
        trace["result"] = "REQUIRED_BASELINE_READY"
        traces.append(trace)
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
        }, used, traces)
    return None, used, traces


async def _team_history(client, cache, fixture, team_id, side, *, cutoff, trace):
    key = (
        int(team_id), int(fixture["competition_id"]), int(fixture["season"]),
        cutoff.isoformat(),
    )
    cached = cache.team_history(key, now=cutoff)
    label = f"{side}_TEAM_HISTORY"
    if cached is not None:
        trace["cache_hits"].append(label)
        return cached.value, None
    trace["cache_misses"].append(label)
    before = _request_count(client)
    try:
        value = await client.last_matches(
            int(team_id), last=5, league_id=int(fixture["competition_id"]),
            season=int(fixture["season"]),
        )
    except httpx.HTTPStatusError as exc:
        actual = _request_count(client) - before
        trace["calls"]["team_history"] += actual
        trace["calls"]["retries"] += max(0, actual - 1)
        return None, (
            "API_FOOTBALL_PLAN_RESTRICTED"
            if exc.response.status_code in {403, 429}
            else "INSUFFICIENT_REQUIRED_DATA"
        )
    actual = _request_count(client) - before
    trace["calls"]["team_history"] += actual
    trace["calls"]["retries"] += max(0, actual - 1)
    metadata = client.response_metadata()
    if metadata.get("errors"):
        trace.setdefault("provider_errors", {})[label] = metadata["errors"]
        text = str(metadata["errors"]).casefold()
        return None, (
            "API_FOOTBALL_PLAN_RESTRICTED"
            if "plan" in text or "access" in text
            else "INSUFFICIENT_REQUIRED_DATA"
        )
    retrieved = datetime.now(timezone.utc)
    cache.save_team_history(key, value, retrieved_at=retrieved)
    return value, None


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
    venue = fixture.get("venue") if isinstance(fixture.get("venue"), dict) else {}
    return {"provider_fixture_id": fixture.get("id"), "kickoff_utc": fixture.get("date"), "fixture_status": status.get("short"), "competition_id": league.get("id"), "competition": league.get("name"), "competition_country": league.get("country"), "competition_round": league.get("round"), "season": league.get("season"), "venue_id": venue.get("id"), "venue_name": venue.get("name"), "home_team_id": home.get("id"), "home_team": home.get("name"), "away_team_id": away.get("id"), "away_team": away.get("name")}


def _fixture_rejection(fixture, now, minimum_lead_minutes, catalog):
    required = ("provider_fixture_id", "kickoff_utc", "competition_id", "competition", "season", "home_team_id", "home_team", "away_team_id", "away_team")
    if any(fixture.get(name) in {None, ""} for name in required): return "MALFORMED_FIXTURE_IDENTITY"
    if fixture["home_team_id"] == fixture["away_team_id"] or fixture["home_team"] == fixture["away_team"]: return "MALFORMED_FIXTURE_IDENTITY"
    if fixture["fixture_status"] not in UPCOMING_STATUSES: return "NOT_UPCOMING_OR_POSTPONED"
    competition = catalog.get(fixture["competition_id"])
    if competition is None or competition["type"] not in {"League", "Cup"}: return "UNSUPPORTED_COMPETITION_TYPE"
    if int(fixture["season"]) != competition["season"]: return "STALE_OR_UNRESOLVED_SEASON"
    if competition.get("fixtures") is False: return "NO_FIXTURE_COVERAGE"
    if competition.get("odds") is False: return "NO_ODDS_CAPABILITY"
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
            coverage = season.get("coverage") or {}
            fixture_flags = coverage.get("fixtures") if isinstance(coverage.get("fixtures"), dict) else {}
            result[league["id"]] = {"type": league.get("type"), "name": league.get("name"), "season": int(season["year"]), "coverage": coverage, "fixtures": any(bool(value) for value in fixture_flags.values()) if fixture_flags else bool(coverage.get("fixtures")), "odds": bool(coverage.get("odds"))}
    return result


def _catalog_from_cache(cache, today):
    result = {}
    for record in cache.records:
        try:
            covers = date.fromisoformat(record.season_start) <= today <= date.fromisoformat(record.season_end)
        except ValueError:
            covers = False
        if covers:
            result[record.league_id] = {
                "type": record.competition_type,
                "name": record.competition_name,
                "season": record.season,
                "fixtures": record.fixtures,
                "odds": record.odds,
                "coverage": asdict(record),
            }
    return result


def _resolved_from_cache(cache, *, observed_at):
    records = {record.league_id: record for record in cache.records}
    today = observed_at.date()
    values = []
    for priority, (league_id, name, country, kind) in enumerate(PRIORITY_COMPETITIONS):
        record = records.get(league_id)
        covers = False
        if record is not None:
            try:
                covers = date.fromisoformat(record.season_start) <= today <= date.fromisoformat(record.season_end)
            except ValueError:
                pass
        values.append({
            "priority": priority, "provider_league_id": league_id,
            "country": record.country if record else country,
            "competition_name": record.competition_name if record else name,
            "competition_type": record.competition_type if record else kind,
            "resolution_status": "RESOLVED" if covers else "UNRESOLVED",
            "reason_code": None if covers else "CURRENT_SEASON_UNAVAILABLE",
            "current_season": record.season if covers else None,
            "season_start": record.season_start if covers else None,
            "season_end": record.season_end if covers else None,
            "fixture_coverage": record.fixtures if covers else False,
            "odds_coverage": record.odds if covers else False,
            "last_successful_refresh_timestamp_utc": cache.retrieved_at_utc.isoformat(),
            "source_provenance": record.source_provenance if record else "API_FOOTBALL_CAPABILITY_CACHE",
        })
    return tuple(values)


def _candidate_priority(fixture, cache, cutoff):
    return (
        fixture.get("competition_priority", len(PRIORITY_COMPETITIONS)),
        -cache.team_hit_count(fixture, cutoff=cutoff),
        fixture["kickoff_utc"],
        fixture["provider_fixture_id"],
    )


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
    maximum_api_calls=40, request_cost_report=(), stage_request_costs=(),
    capability_cache=None, capability_cache_status="NOT_CONFIGURED",
):
    prefilter_reasons = {
        "MALFORMED_FIXTURE_IDENTITY", "NOT_UPCOMING_OR_POSTPONED",
        "UNSUPPORTED_COMPETITION_TYPE", "STALE_OR_UNRESOLVED_SEASON",
        "NO_FIXTURE_COVERAGE", "NO_ODDS_CAPABILITY", "EXCLUDED_FIXTURE_CLASS",
        "ALREADY_STARTED", "KICKOFF_TOO_CLOSE", "DUPLICATE_EVENT",
    }
    cache_summary = {
        "status": capability_cache_status,
        "record_count": len(capability_cache.records) if capability_cache is not None else 0,
        "retrieved_at_utc": capability_cache.retrieved_at_utc.isoformat() if capability_cache is not None else None,
        "expires_at_utc": capability_cache.expires_at_utc.isoformat() if capability_cache is not None else None,
        "cache_fingerprint": capability_cache.cache_fingerprint if capability_cache is not None else None,
        "contains_credentials": False,
    }
    return {"schema_version": "goalvision-adaptive-current-fixture-discovery-v2", "terminal_result": terminal, "actual_utc_clock": now.isoformat(), "discovery_stages": reports, "stage_request_costs": list(stage_request_costs), "request_cost_report": list(request_cost_report), "competition_resolver": list(competitions), "capability_cache": cache_summary, "provider_fixture_rows": fixture_results, "candidates_prefiltered": sum(count for reason, count in skipped.items() if reason in prefilter_reasons), "candidate_fixture_count": candidates, "fixtures_inspected": candidates, "maximum_candidates": maximum_candidates, "maximum_api_calls": maximum_api_calls, "skipped_candidate_count": sum(skipped.values()), "skip_reasons": dict(sorted(skipped.items())), "selected_fixture": selected, "api_call_count": _request_count(client), "odds_request_count": odds_requests, "fixture_order": "COMPETITION_PRIORITY_THEN_CACHE_REUSE_THEN_EARLIEST_SAFE_KICKOFF_THEN_PROVIDER_FIXTURE_ID", "inference_executed": False, "telegram_sends": 0, "delivery_records": 0, "official_publications": 0}
