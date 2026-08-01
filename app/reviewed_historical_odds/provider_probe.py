"""Deterministic, low-volume provider coverage probing and evidence creation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .fingerprint import sha256_fingerprint
from .provider_http import ProviderHttpError
from .provider_models import (
    CoverageProbeReport, CoverageProbeRequest, CoverageSamplePeriod,
    HistoricalOddsProvider, ProviderOutcome, ProviderQuotaSnapshot,
)
from .provider_ports import HistoricalOddsProviderPort


MAX_SAMPLE_LIMIT = 10
MAX_PROBE_REQUESTS = 25


def prepare_probe_request(
    provider: HistoricalOddsProvider, competition_query: str, date_from: str, date_to: str,
    sample_limit: int = 10, max_requests: int = 25,
) -> CoverageProbeRequest:
    start, end = _date(date_from), _date(date_to)
    if start > end: raise ValueError("date_from must not exceed date_to")
    if not 1 <= sample_limit <= MAX_SAMPLE_LIMIT: raise ValueError("sample_limit must be between 1 and 10")
    if not 2 <= max_requests <= MAX_PROBE_REQUESTS: raise ValueError("max_requests must be between 2 and 25")
    raw = {"provider": provider, "competition_query": competition_query.strip(), "date_from": date_from, "date_to": date_to, "sample_limit": sample_limit, "max_requests": max_requests}
    if not raw["competition_query"]: raise ValueError("competition_query is required")
    return CoverageProbeRequest(**raw, request_fingerprint=sha256_fingerprint(raw))


def canonical_sample_periods() -> tuple[CoverageSamplePeriod, ...]:
    return (
        CoverageSamplePeriod("validation_beginning", "VALIDATION", "2023-05-13", "2023-05-21"),
        CoverageSamplePeriod("validation_middle", "VALIDATION", "2023-11-03", "2023-11-12"),
        CoverageSamplePeriod("validation_end", "VALIDATION", "2024-05-03", "2024-05-11"),
        CoverageSamplePeriod("test_beginning", "TEST", "2024-05-11", "2024-05-19"),
        CoverageSamplePeriod("test_middle", "TEST", "2024-11-01", "2024-11-10"),
        CoverageSamplePeriod("test_end", "TEST", "2025-05-09", "2025-05-17"),
    )


def run_coverage_probe(request: CoverageProbeRequest, adapter: HistoricalOddsProviderPort | None) -> CoverageProbeReport:
    periods = canonical_sample_periods()
    empty_quota = ProviderQuotaSnapshot(None, None, None, None, sha256_fingerprint({"quota": "unknown"}))
    if adapter is None:
        return _report(request, periods, ProviderOutcome.PROVIDER_CREDENTIAL_NOT_CONFIGURED,
                       ProviderOutcome.PROVIDER_CREDENTIAL_NOT_CONFIGURED, quota=empty_quota,
                       reasons=("CREDENTIAL_ENVIRONMENT_VARIABLE_ABSENT",))
    try:
        valid, _ = adapter.diagnose_credentials()
        if not valid:
            return _report(request, periods, ProviderOutcome.PROVIDER_AUTHENTICATION_FAILED,
                           ProviderOutcome.PROVIDER_AUTHENTICATION_FAILED, quota=adapter.inspect_quota(), reasons=("CREDENTIAL_REJECTED",))
        competition = adapter.resolve_competition(request.competition_query)
        if competition is None:
            return _report(request, periods, ProviderOutcome.PROVIDER_COVERAGE_INSUFFICIENT,
                           ProviderOutcome.PROVIDER_COVERAGE_CONFIRMED, quota=adapter.inspect_quota(), reasons=("COMPETITION_NOT_FOUND",))
        fixtures = []
        period_by_fixture: dict[str, str] = {}
        for period in periods:
            if _request_count(adapter) >= request.max_requests: break
            candidates = adapter.list_historical_fixtures(competition.provider_competition_id, period.date_from, period.date_to)
            if candidates:
                selected = candidates[len(candidates) // 2]
                fixtures.append(selected); period_by_fixture[selected.provider_fixture_id] = period.name
        fixtures = fixtures[:request.sample_limit]
        events, quotes, covered = [], [], set()
        for fixture in fixtures:
            if _request_count(adapter) >= request.max_requests: break
            event, fixture_quotes = adapter.fetch_fixture_odds_sample(fixture.provider_fixture_id)
            events.append(event); quotes.extend(fixture_quotes)
            if fixture_quotes and all(quote.captured_at_utc for quote in fixture_quotes): covered.add(period_by_fixture[fixture.provider_fixture_id])
        validation = tuple(period.name for period in periods if period.partition == "VALIDATION" and period.name in covered)
        test = tuple(period.name for period in periods if period.partition == "TEST" and period.name in covered)
        complete = bool(quotes) and all(quote.captured_at_utc for quote in quotes)
        status = (ProviderOutcome.PROVIDER_COVERAGE_CONFIRMED if len(validation) == 3 and len(test) == 3 and complete
                  else ProviderOutcome.PROVIDER_COVERAGE_PARTIAL if covered
                  else ProviderOutcome.PROVIDER_COVERAGE_INSUFFICIENT)
        reasons = () if status == ProviderOutcome.PROVIDER_COVERAGE_CONFIRMED else (("PARTIAL_PERIOD_COVERAGE",) if covered else ("NO_TIMESTAMPED_ODDS_IN_SAMPLE",))
        return _report(
            request, periods, status, ProviderOutcome.PROVIDER_COVERAGE_CONFIRMED,
            competition_id=competition.provider_competition_id, fixtures=fixtures, events=events, quotes=quotes,
            validation=validation, test=test, quota=adapter.inspect_quota(), reasons=reasons,
            receipts=tuple(getattr(getattr(adapter, "client", None), "receipts", ())),
            request_count=_request_count(adapter),
        )
    except ProviderHttpError as exc:
        status = (ProviderOutcome.PROVIDER_AUTHENTICATION_FAILED if exc.status_code in (401, 403)
                  else ProviderOutcome.PROVIDER_QUOTA_INSUFFICIENT if exc.status_code == 429
                  else ProviderOutcome.PROVIDER_RESPONSE_INCOMPATIBLE)
        return _report(request, periods, status, status, quota=adapter.inspect_quota(), reasons=(f"HTTP_{exc.status_code or 'TRANSPORT'}",), request_count=_request_count(adapter))
    except (KeyError, TypeError, ValueError):
        return _report(request, periods, ProviderOutcome.PROVIDER_RESPONSE_INCOMPATIBLE,
                       ProviderOutcome.PROVIDER_COVERAGE_CONFIRMED, quota=adapter.inspect_quota(), reasons=("PROVIDER_RESPONSE_SCHEMA_INCOMPATIBLE",), request_count=_request_count(adapter))


def _report(request, periods, status, credential_status, *, competition_id=None, fixtures=(), events=(), quotes=(), validation=(), test=(), quota, reasons=(), receipts=(), request_count=None):
    bookmaker_names = tuple(sorted({quote.source_bookmaker_name for quote in quotes}))
    markets = tuple(sorted({quote.source_market_name for quote in quotes}))
    fixture_dates = sorted(fixture.kickoff_utc for fixture in fixtures)
    raw = dict(
        provider=request.provider, status=status, credential_status=credential_status,
        provider_competition_id=competition_id, sample_periods=tuple(periods),
        successful_sample_count=len(validation) + len(test), failed_sample_count=len(periods) - len(validation) - len(test),
        request_count=len(receipts) if request_count is None else request_count, fixture_count=len(fixtures), odds_fixture_count=len({quote.source_event_id for quote in quotes}),
        normalized_quote_count=len(quotes), bookmakers=bookmaker_names, markets=markets,
        opening_available=any(quote.source_point == "opening" for quote in quotes),
        last_seen_available=any(quote.source_point == "last_seen" for quote in quotes),
        capture_timestamps_complete=bool(quotes) and all(quote.captured_at_utc for quote in quotes),
        earliest_fixture_date=fixture_dates[0] if fixture_dates else None, latest_fixture_date=fixture_dates[-1] if fixture_dates else None,
        validation_periods_covered=tuple(validation), test_periods_covered=tuple(test), quota=quota,
        reason_codes=tuple(reasons), response_receipts=tuple(receipts), normalized_events=tuple(events), normalized_quotes=tuple(quotes),
    )
    return CoverageProbeReport(**raw, report_fingerprint=sha256_fingerprint(raw))


def _request_count(adapter: HistoricalOddsProviderPort) -> int:
    return int(getattr(getattr(adapter, "client", None), "request_count", 0))


def _date(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
