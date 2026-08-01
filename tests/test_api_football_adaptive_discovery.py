import asyncio
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from app.current_odds_forward_test.cli import main as cli_main
from app.current_odds_forward_test.discovery import (
    _competition_catalog,
    _fixture_identity,
    _fixture_rejection,
    _ordered_candidates,
    discover_current_fixture,
)
from app.current_odds_forward_test.evidence import build_adaptive_fixture_discovery_evidence
from app.current_odds_forward_test.input import CurrentOddsValidationError, normalize_api_football_current_odds
from app.current_odds_forward_test.provider import diagnose_fixture_discovery, resolve_current_competitions
from app.football.client import FootballClient, FootballRequestLimitError
from app.football.quota import FootballQuotaError, FootballQuotaReport


NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def league_payload(*, include_priority=True):
    rows = []
    if include_priority:
        rows.append(league(179, "Premiership", "Scotland", 2026))
    rows.append(league(999, "Senior League", "Country", 2026))
    return {"response": rows}


def league(identifier, name, country, season, *, start="2026-01-01", end="2026-12-31", current=True, kind="League"):
    return {"league": {"id": identifier, "name": name, "type": kind}, "country": {"name": country}, "seasons": [{"year": season, "start": start, "end": end, "current": current, "coverage": {"fixtures": {"events": True}, "odds": True}}]}


def fixture(identifier=1, *, league_id=179, league_name="Premiership", kickoff="2026-08-01T18:00:00+00:00", status="NS", home="Home", away="Away", season=2026):
    return {"fixture": {"id": identifier, "date": kickoff, "status": {"short": status}}, "league": {"id": league_id, "name": league_name, "season": season}, "teams": {"home": {"id": identifier * 10, "name": home}, "away": {"id": identifier * 10 + 1, "name": away}}}


def odds(identifier=1, *, updated=None, markets=3):
    values = [{"value": name, "odd": odd} for name, odd in (("Home", "2.10"), ("Draw", "3.20"), ("Away", "3.10"))][:markets]
    return {"response": [{"fixture": {"id": identifier}, "update": updated, "bookmakers": [{"id": 1, "name": "Book", "bets": [{"name": "Match Winner", "values": values}]}]}]}


class FakeProvider:
    def __init__(self, fixtures_by_date=None, odds_by_fixture=None, *, include_priority=True, daily=99, minute=10):
        self.calls = 0
        self.odds_calls = []
        self._metadata = {}
        self._fixtures = fixtures_by_date or {}
        self._odds = odds_by_fixture or {}
        self._leagues = league_payload(include_priority=include_priority)
        self.daily = daily
        self.minute = minute

    @property
    def request_count(self): return self.calls
    def quota_snapshot(self): return {"interpretation_status": "NORMALIZED", "daily_remaining": self.daily, "minute_remaining": self.minute}
    def response_metadata(self): return dict(self._metadata)
    def _record(self, endpoint, query, results=0, errors=None):
        self.calls += 1; self._metadata = {"endpoint": endpoint, "method": "GET", "query": query, "http_status": 200, "errors": [] if errors is None else errors, "results": results, "paging": {"current": 1, "total": 1}, "quota": self.quota_snapshot()}
    async def leagues(self, **_): self._record("/leagues", {"current": "true"}, len(self._leagues["response"])); return self._leagues
    async def fixtures_by_date(self, day, **_):
        rows = self._fixtures.get(day, []); self._record("/fixtures", {"date": day, "timezone": "UTC"}, len(rows)); return {"response": rows}
    async def last_matches(self, *_args, **_kwargs): self._record("/fixtures", {"last": 5}, 5); return [{"fixture": {"id": i}} for i in range(5)]
    async def current_odds(self, fixture_id): self.odds_calls.append(fixture_id); self._record("/odds", {"fixture": fixture_id}, 1); return self._odds.get(fixture_id, {"response": []})


class QuotaAndClientTests(unittest.TestCase):
    def test_quota_headers_have_exact_provider_meanings(self):
        report = FootballQuotaReport.from_headers({"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "93", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "4"})
        self.assertEqual((report.daily_limit, report.daily_remaining), (100, 93)); self.assertEqual((report.minute_limit, report.minute_remaining), (10, 4)); self.assertEqual(report.interpretation_status, "NORMALIZED")

    def test_ambiguous_quota_and_reserve_fail_closed(self):
        ambiguous = FootballQuotaReport.from_headers({})
        with self.assertRaisesRegex(FootballQuotaError, "AMBIGUOUS"): ambiguous.require_capacity(additional_calls=1, daily_reserve=20)
        low = FootballQuotaReport.from_headers({"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "20", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"})
        with self.assertRaisesRegex(FootballQuotaError, "INSUFFICIENT"): low.require_capacity(additional_calls=1, daily_reserve=20)
        minute_low = FootballQuotaReport.from_headers({"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "90", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "1"})
        with self.assertRaisesRegex(FootballQuotaError, "INSUFFICIENT"): minute_low.require_capacity(additional_calls=2, daily_reserve=20)

    def test_client_preserves_query_errors_paging_and_never_headers_secret(self):
        class FakeHTTP:
            async def get(self, path, params):
                request = httpx.Request("GET", "https://example.invalid")
                return httpx.Response(200, request=request, headers={"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "90", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"}, json={"errors": {"from": "needs league"}, "results": 0, "paging": {"current": 1, "total": 1}, "response": []})
            async def aclose(self): pass
        client = FootballClient(api_key="not-a-real-key", request_limit=1); asyncio.run(client._client.aclose()); client._client = FakeHTTP()
        asyncio.run(client.fixtures_between("2026-08-01", "2026-08-08", league_id=179, season=2026)); metadata = client.response_metadata(); asyncio.run(client.close())
        self.assertEqual(metadata["query"]["timezone"], "UTC"); self.assertEqual(metadata["errors"], {"from": "needs league"}); self.assertEqual(metadata["paging"]["total"], 1); self.assertNotIn("not-a-real-key", json.dumps(metadata))

    def test_unscoped_date_range_is_rejected_before_network(self):
        client = FootballClient(api_key="not-a-real-key")
        with self.assertRaisesRegex(ValueError, "RANGE_REQUIRES_LEAGUE_AND_SEASON"):
            asyncio.run(client.fixtures_between("2026-08-01", "2026-08-08"))
        asyncio.run(client.close())

    def test_request_limit_includes_real_attempts(self):
        class FakeHTTP:
            async def get(self, path, params): return httpx.Response(200, request=httpx.Request("GET", "https://example.invalid"), headers={}, json={})
            async def aclose(self): pass
        client = FootballClient(api_key="fake", request_limit=1); asyncio.run(client._client.aclose()); client._client = FakeHTTP(); asyncio.run(client.account_status())
        with self.assertRaises(FootballRequestLimitError): asyncio.run(client.account_status())
        asyncio.run(client.close())


class CompetitionAndFilteringTests(unittest.TestCase):
    def test_current_season_resolution_and_stale_season_rejection(self):
        payload = {"response": [league(39, "Premier League", "England", 2025, start="2025-08-01", end="2026-05-31"), league(179, "Premiership", "Scotland", 2026)]}
        resolved = resolve_current_competitions(payload, observed_at=NOW); premier = next(item for item in resolved if item["provider_league_id"] == 39); scotland = next(item for item in resolved if item["provider_league_id"] == 179)
        self.assertEqual(premier["reason_code"], "STALE_HARD_CODED_CURRENT_SEASON_REJECTED"); self.assertEqual(scotland["current_season"], 2026); self.assertTrue(scotland["odds_coverage"])

    def test_league_id_and_empty_priority_fallback_catalog(self):
        payload = league_payload(include_priority=False); catalog = _competition_catalog(payload, NOW.date())
        self.assertIn(999, catalog); self.assertEqual(catalog[999]["season"], 2026)

    def test_exclusions_and_safe_kickoff(self):
        catalog = {179: {"type": "League", "season": 2026}}
        cases = [
            (fixture(home="Club U21"), "EXCLUDED_FIXTURE_CLASS"),
            (fixture(home="Club Reserves"), "EXCLUDED_FIXTURE_CLASS"),
            (fixture(league_name="Friendlies Clubs"), "EXCLUDED_FIXTURE_CLASS"),
            (fixture(kickoff="2026-08-01T09:00:00+00:00"), "ALREADY_STARTED"),
            (fixture(status="PST"), "NOT_UPCOMING_OR_POSTPONED"),
            (fixture(kickoff="2026-08-01T10:30:00+00:00"), "KICKOFF_TOO_CLOSE"),
        ]
        for raw, expected in cases:
            with self.subTest(expected=expected): self.assertEqual(_fixture_rejection(_fixture_identity(raw), NOW, 60, catalog), expected)

    def test_deterministic_order_is_kickoff_priority_then_id(self):
        catalog = {179: {"type": "League", "season": 2026}, 999: {"type": "League", "season": 2026}}
        rows = [fixture(9, league_id=999, league_name="Senior League"), fixture(8, league_id=179), fixture(7, league_id=179)]
        values = _ordered_candidates(rows, now=NOW, minimum_lead_minutes=60, catalog=catalog, priority={179: 0}, priority_only=False, skipped={})
        self.assertEqual([item["provider_fixture_id"] for item in values], [7, 8, 9])


class AdaptiveDiscoveryTests(unittest.TestCase):
    def run_discovery(self, client, **kwargs):
        return asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1, maximum_api_calls=10, **kwargs))

    def test_priority_stage_first_eligible_and_no_model_based_selection(self):
        rows = [fixture(2, kickoff="2026-08-01T19:00:00+00:00"), fixture(1, kickoff="2026-08-01T18:00:00+00:00")]
        client = FakeProvider({"2026-08-01": rows}, {1: odds(1), 2: odds(2)})
        value = self.run_discovery(client)
        self.assertEqual(value["selected_fixture"]["provider_fixture_id"], 1); self.assertEqual(client.odds_calls, [1]); self.assertFalse(value["inference_executed"])

    def test_all_supported_professional_fallback_when_priority_empty(self):
        client = FakeProvider({"2026-08-01": [fixture(5, league_id=999, league_name="Senior League")]}, {5: odds(5)}, include_priority=False)
        value = self.run_discovery(client)
        self.assertEqual(value["selected_fixture"]["provider_fixture_id"], 5); self.assertEqual(value["discovery_stages"][-1]["stage"], "ALL_SUPPORTED_PROFESSIONAL_SENIOR_NEXT_7_DAYS")

    def test_missing_odds_skips_without_duplicate_request(self):
        row = fixture(3); client = FakeProvider({"2026-08-01": [row], "2026-08-02": [row]}, {})
        value = self.run_discovery(client)
        self.assertIsNone(value["selected_fixture"]); self.assertEqual(client.odds_calls, [3]); self.assertEqual(value["skip_reasons"]["CURRENT_ODDS_UNAVAILABLE"], 1)

    def test_insufficient_markets_and_malformed_odds_skip(self):
        for payload, reason in ((odds(1, markets=2), "INSUFFICIENT_SUPPORTED_MARKETS"), (odds(1), "MALFORMED_ODDS")):
            if reason == "MALFORMED_ODDS": payload["response"][0]["bookmakers"][0]["bets"][0]["values"][0]["odd"] = "bad"
            with self.subTest(reason=reason):
                value = self.run_discovery(FakeProvider({"2026-08-01": [fixture(1)]}, {1: payload}))
                self.assertIn(reason, value["skip_reasons"])

    def test_stale_odds_and_fixture_identity_mismatch_are_rejected(self):
        stale = odds(1, updated="2026-08-01T09:00:00+00:00")
        value = self.run_discovery(FakeProvider({"2026-08-01": [fixture(1)]}, {1: stale})); self.assertIn("STALE_CURRENT_ODDS", value["skip_reasons"])
        with self.assertRaisesRegex(CurrentOddsValidationError, "IDENTITY_MISMATCH"):
            normalize_api_football_current_odds(odds(2), fixture_id="1", kickoff_utc="2026-08-01T18:00:00+00:00", retrieved_at_utc="2026-08-01T10:00:00+00:00", source_selected_at_utc="2026-08-01T09:59:00+00:00")

    def test_missing_odds_fixture_identity_is_rejected(self):
        payload = odds(1)
        del payload["response"][0]["fixture"]
        with self.assertRaisesRegex(CurrentOddsValidationError, "IDENTITY_MISSING"):
            normalize_api_football_current_odds(
                payload, fixture_id="1", kickoff_utc="2026-08-01T18:00:00+00:00",
                retrieved_at_utc="2026-08-01T10:00:00+00:00",
                source_selected_at_utc="2026-08-01T09:59:00+00:00",
            )

    def test_candidate_and_api_call_limits_fail_closed(self):
        rows = [fixture(i, kickoff=f"2026-08-01T{12 + i % 10:02d}:00:00+00:00") for i in range(1, 20)]
        value = asyncio.run(discover_current_fixture(FakeProvider({"2026-08-01": rows}), now=NOW, horizon_days=1, maximum_candidates=2, maximum_api_calls=6))
        self.assertLessEqual(value["fixtures_inspected"], 2); self.assertLessEqual(value["api_call_count"], 6)

    def test_quota_ambiguity_and_reserve_enforced_before_fixture_calls(self):
        client = FakeProvider(daily=20)
        value = self.run_discovery(client, daily_quota_reserve=20)
        self.assertEqual(value["terminal_result"], "DISCOVERY_QUOTA_INSUFFICIENT"); self.assertEqual(value["api_call_count"], 1)

    def test_zero_network_safety_counters_and_odds_before_any_inference(self):
        client = FakeProvider({"2026-08-01": [fixture(1)]}, {1: odds(1)}); value = self.run_discovery(client)
        self.assertTrue(value["selected_fixture"]["odds_snapshot_fingerprint"]); self.assertFalse(value["inference_executed"]); self.assertEqual((value["telegram_sends"], value["delivery_records"], value["official_publications"]), (0, 0, 0))


class DiagnosticTests(unittest.TestCase):
    def test_adaptive_evidence_is_canonical_and_committed(self):
        expected = build_adaptive_fixture_discovery_evidence()
        artifact = Path("docs/rehearsals/api_football_fixture_discovery_fix_2026-08-01.json")
        self.assertEqual(json.loads(artifact.read_text(encoding="utf-8")), expected)
        self.assertEqual(expected["evidence_fingerprint"], "b9f945bce5c0086e339e9ef3f723a7054adcfa5e6f3b61f4690b30c31376f06e")

    def test_zero_result_diagnosis_preserves_redacted_query_metadata(self):
        class DiagnosticFake(FakeProvider):
            async def account_status(self): self._record("/status", {}, 1); return {"response": {"subscription": {"active": True}}}
            async def fixtures_between(self, start, end, **kwargs): self._record("/fixtures", {"from": start, "to": end, **({"timezone": kwargs["timezone_name"]} if "timezone_name" in kwargs else {})}, 0, {"from": "needs another parameter"}); return {"errors": {"from": "needs another parameter"}, "results": 0, "response": []}
            async def fixtures_by_date(self, day, **_): self._record("/fixtures", {"date": day, "timezone": "UTC"}, 10); return {"response": [fixture(1)] * 10}
            async def _get(self, path, params): self._record(path, params, 0, {"from": "needs another parameter"}); return httpx.Response(200, request=httpx.Request("GET", "https://example.invalid"), json={"errors": {"from": "needs another parameter"}, "results": 0, "response": []})
        value = asyncio.run(diagnose_fixture_discovery(DiagnosticFake(), now=NOW, daily_reserve=20))
        self.assertEqual(value["previous_zero_result_cause"]["code"], "PROVIDER_QUERY_REJECTED"); self.assertEqual(value["previous_request"]["query"], {"from": "2026-08-01", "to": "2026-08-08"}); self.assertNotIn("api_key", json.dumps(value).casefold())

    def test_cli_json_and_human_provider_quota_output(self):
        class FakeClient:
            def __init__(self, **_): pass
            async def account_status(self): return {"response": {}}
            def quota_snapshot(self): return {"interpretation_status": "NORMALIZED", "daily_limit": 100}
            async def close(self): pass
        for output in ("json", "human"):
            stream = io.StringIO()
            with patch("app.football.client.FootballClient", FakeClient), redirect_stdout(stream): code = cli_main(["inspect-provider-quota", "--output", output])
            self.assertEqual(code, 0); self.assertIn("NORMALIZED", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
