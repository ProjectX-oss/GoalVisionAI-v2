import asyncio
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.current_odds_forward_test.cli import main as cli_main
from app.current_odds_forward_test.discovery import discover_current_fixture
from app.current_odds_forward_test.evidence import build_discovery_efficiency_evidence
from app.current_odds_forward_test.efficiency import (
    CapabilityCacheError,
    CompetitionCapabilityCache,
    RunDataCache,
    plan_candidate,
)
from app.real_match_lab_analysis.fingerprint import canonical_json
from tests.test_api_football_adaptive_discovery import (
    FakeProvider,
    NOW,
    fixture,
    odds,
)


def capabilities(*, odds_available=True, fixture_available=True):
    return {
        "response": [{
            "league": {"id": 179, "name": "Premiership", "type": "League"},
            "country": {"name": "Scotland"},
            "seasons": [{
                "year": 2026, "start": "2026-01-01", "end": "2026-12-31",
                "current": True,
                "coverage": {
                    "fixtures": {
                        "events": fixture_available, "lineups": fixture_available,
                        "statistics_fixtures": fixture_available,
                    },
                    "standings": True, "injuries": True,
                    "odds": odds_available,
                },
            }],
        }],
    }


class CostProvider(FakeProvider):
    def __init__(self, *args, histories=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._leagues = capabilities()
        self.histories = histories or {}
        self.history_calls = []

    async def last_matches(self, team_id, **kwargs):
        self.history_calls.append((team_id, kwargs.get("league_id"), kwargs.get("season")))
        rows = self.histories.get(team_id, [])
        self._record("/fixtures", {"team": team_id, "league": kwargs.get("league_id"), "season": kwargs.get("season"), "last": 5}, len(rows))
        return rows

    async def account_status(self):
        self._record("/status", {}, 1)
        return {"response": {"subscription": {"active": True}}}

    async def close(self):
        return None


def history(identifier):
    return [{"fixture": {"id": identifier, "status": {"short": "FT"}}}]


class CapabilityCacheTests(unittest.TestCase):
    def cache_path(self, name):
        path = Path("var") / f"test_{name}_capabilities.json"
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_capability_cache_is_timestamped_fingerprinted_and_secret_free(self):
        cache = CompetitionCapabilityCache.from_provider_payload(capabilities(), retrieved_at_utc=NOW)
        self.assertEqual(cache.get(179, 2026).standings, True)
        self.assertTrue(cache.get(179, 2026).odds)
        document = cache.as_document()
        self.assertEqual(document["cache_fingerprint"], cache.cache_fingerprint)
        self.assertNotIn("api_key", canonical_json(document).casefold())

    def test_persisted_cache_reuse_and_freshness_invalidation(self):
        cache = CompetitionCapabilityCache.from_provider_payload(capabilities(), retrieved_at_utc=NOW)
        path = self.cache_path("freshness")
        cache.save(path)
        self.assertEqual(CompetitionCapabilityCache.load(path, now=NOW), cache)
        self.assertIsNone(CompetitionCapabilityCache.load(path, now=NOW + timedelta(hours=7)))

    def test_cache_conflict_and_fingerprint_tampering_fail_closed(self):
        payload = capabilities()
        conflict = json.loads(json.dumps(payload["response"][0]))
        conflict["seasons"][0]["coverage"]["odds"] = False
        payload["response"].append(conflict)
        with self.assertRaisesRegex(CapabilityCacheError, "CONFLICT"):
            CompetitionCapabilityCache.from_provider_payload(payload, retrieved_at_utc=NOW)
        cache = CompetitionCapabilityCache.from_provider_payload(capabilities(), retrieved_at_utc=NOW)
        path = self.cache_path("tamper")
        cache.save(path)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["records"][0]["odds"] = False
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(CapabilityCacheError, "FINGERPRINT"):
            CompetitionCapabilityCache.load(path, now=NOW)

    def test_run_cache_reuses_context_and_invalidates_stale_values(self):
        cache = RunDataCache()
        team_key = (1, 179, 2026, NOW.isoformat())
        standing_key = (179, 2026)
        cache.save_team_history(team_key, history(1), retrieved_at=NOW)
        cache.save_standings(standing_key, {"table": []}, retrieved_at=NOW)
        self.assertIsNotNone(cache.team_history(team_key, now=NOW))
        self.assertIsNotNone(cache.standings(standing_key, now=NOW))
        self.assertIsNone(cache.team_history(team_key, now=NOW + timedelta(minutes=16)))
        self.assertIsNone(cache.standings(standing_key, now=NOW + timedelta(minutes=16)))
        self.assertIsNone(cache.team_history((1, 999, 2026, NOW.isoformat()), now=NOW))

    def test_optional_context_caches_are_freshness_and_identity_bound(self):
        cache = RunDataCache()
        cache.save_season_aggregate((1, 179, 2026), {"played": 10}, retrieved_at=NOW)
        cache.save_injuries((100, 1), [], retrieved_at=NOW)
        cache.save_lineup(100, {"available": False}, retrieved_at=NOW)
        self.assertIsNotNone(cache.season_aggregate((1, 179, 2026), now=NOW))
        self.assertIsNone(cache.season_aggregate((1, 179, 2025), now=NOW))
        self.assertIsNotNone(cache.injuries((100, 1), now=NOW + timedelta(hours=3)))
        self.assertIsNone(cache.injuries((100, 1), now=NOW + timedelta(hours=5)))
        self.assertIsNotNone(cache.lineup(100, now=NOW + timedelta(minutes=30)))
        self.assertIsNone(cache.lineup(100, now=NOW + timedelta(hours=2)))


class PlannerAndDiscoveryTests(unittest.TestCase):
    def discover(self, client, **kwargs):
        return asyncio.run(discover_current_fixture(
            client, now=NOW, horizon_days=1, maximum_api_calls=10, **kwargs
        ))

    def test_full_cost_estimation_and_no_partial_candidate_when_unfunded(self):
        candidate = {
            "home_team_id": 10, "away_team_id": 11,
            "competition_id": 179, "season": 2026,
        }
        plan = plan_candidate(candidate, RunDataCache(), cutoff=NOW, request_count=8, effective_call_limit=10)
        self.assertEqual(plan.status, "CANDIDATE_SKIPPED_QUOTA")
        self.assertEqual((plan.baseline_calls, plan.odds_calls, plan.total_mandatory_calls), (2, 1, 3))
        client = CostProvider({"2026-08-01": [fixture(1)]}, histories={10: history(10), 11: history(11)})
        value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1, maximum_api_calls=2))
        self.assertEqual(client.history_calls, [])
        self.assertEqual(value["terminal_result"], "DISCOVERY_QUOTA_INSUFFICIENT")

    def test_fresh_odds_precede_home_baseline_failure(self):
        client = CostProvider({"2026-08-01": [fixture(1)]}, {1: odds(1)})
        value = self.discover(client)
        self.assertEqual(client.history_calls, [(10, 179, 2026)])
        self.assertEqual(client.odds_calls, [1])
        trace = value["request_cost_report"][0]
        self.assertEqual(trace["calls"]["team_history"], 1)
        self.assertEqual(trace["calls"]["odds"], 1)
        self.assertEqual(trace["result"], "CANDIDATE_SKIPPED_BASELINE")
        self.assertTrue(all(cost == 0 for name, cost in trace["calls"].items() if name not in {"team_history", "odds", "retries"}))

    def test_provider_plan_error_is_preserved_in_candidate_cost_trace(self):
        class Restricted(CostProvider):
            async def last_matches(self, team_id, **kwargs):
                self.history_calls.append((team_id, kwargs.get("league_id"), kwargs.get("season")))
                errors = {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}
                self._record("/fixtures", {"team": team_id}, 0, errors)
                return []
        value = self.discover(Restricted({"2026-08-01": [fixture(1)]}, {1: odds(1)}))
        trace = value["request_cost_report"][0]
        self.assertEqual(trace["rejection_reason"], "API_FOOTBALL_PLAN_RESTRICTED")
        self.assertIn("2022 to 2024", trace["provider_errors"]["HOME_TEAM_HISTORY"]["plan"])

    def test_team_history_reuse_reduces_second_candidate_cost(self):
        first = fixture(1)
        second = fixture(2)
        second["teams"]["home"]["id"] = 10
        client = CostProvider(
            {"2026-08-01": [first, second]}, {1: odds(1), 2: odds(2)},
            histories={10: history(10), 11: [], 21: history(21)},
        )
        value = self.discover(client)
        self.assertEqual(value["selected_fixture"]["provider_fixture_id"], 2)
        self.assertEqual([item[0] for item in client.history_calls], [10, 11, 21])
        self.assertIn("HOME_TEAM_HISTORY", value["request_cost_report"][1]["cache_hits"])

    def test_fixture_response_prefilter_rejects_no_odds_without_deep_calls(self):
        client = CostProvider({"2026-08-01": [fixture(1)]})
        client._leagues = capabilities(odds_available=False)
        value = self.discover(client)
        self.assertEqual(client.history_calls, [])
        self.assertEqual(client.odds_calls, [])
        self.assertEqual(value["skip_reasons"]["NO_ODDS_CAPABILITY"], 1)
        self.assertGreaterEqual(value["candidates_prefiltered"], 1)

    def test_fixture_response_prefilter_rejects_no_fixture_coverage(self):
        client = CostProvider({"2026-08-01": [fixture(1)]})
        client._leagues = capabilities(fixture_available=False)
        value = self.discover(client)
        self.assertEqual(client.history_calls, [])
        self.assertIn("NO_FIXTURE_COVERAGE", value["skip_reasons"])

    def test_fixture_response_prefilter_rejects_same_team_identity(self):
        row = fixture(1)
        row["teams"]["away"] = dict(row["teams"]["home"])
        client = CostProvider({"2026-08-01": [row]})
        value = self.discover(client)
        self.assertEqual(client.history_calls, [])
        self.assertIn("MALFORMED_FIXTURE_IDENTITY", value["skip_reasons"])

    def test_priority_precedes_earlier_nonpriority_without_model_output(self):
        low = fixture(2, league_id=999, league_name="Senior League", kickoff="2026-08-01T17:00:00+00:00")
        high = fixture(1, kickoff="2026-08-01T18:00:00+00:00")
        client = CostProvider(
            {"2026-08-01": [low, high]}, {1: odds(1)},
            histories={10: history(10), 11: history(11)},
        )
        client._leagues["response"].append({
            "league": {"id": 999, "name": "Senior League", "type": "League"},
            "country": {"name": "Country"},
            "seasons": [{"year": 2026, "start": "2026-01-01", "end": "2026-12-31", "current": True, "coverage": {"fixtures": {"events": True}, "odds": True}}],
        })
        value = self.discover(client)
        self.assertEqual(value["selected_fixture"]["provider_fixture_id"], 1)
        self.assertFalse(value["inference_executed"])

    def test_capability_cache_hit_uses_status_not_leagues(self):
        cache = CompetitionCapabilityCache.from_provider_payload(capabilities(), retrieved_at_utc=NOW)
        path = Path("var/test_discovery_hit_capabilities.json")
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        cache.save(path)
        client = CostProvider({"2026-08-01": []})
        value = self.discover(client, capability_cache_path=path)
        self.assertEqual(value["capability_cache"]["status"], "HIT")
        self.assertEqual(value["stage_request_costs"][0]["stage"], "QUOTA_REFRESH_CAPABILITY_CACHE_HIT")

    def test_cost_report_is_deterministic_for_equivalent_inputs(self):
        def execute():
            client = CostProvider({"2026-08-01": [fixture(1)]})
            return self.discover(client)["request_cost_report"]
        self.assertEqual(execute(), execute())

    def test_safety_and_no_duplicate_odds_call_remain_explicit(self):
        row = fixture(1)
        client = CostProvider(
            {"2026-08-01": [row], "2026-08-02": [row]}, {1: {"response": []}},
            histories={10: history(10), 11: history(11)},
        )
        value = self.discover(client)
        self.assertEqual(client.odds_calls, [1])
        self.assertEqual((value["telegram_sends"], value["delivery_records"], value["official_publications"]), (0, 0, 0))


class EfficiencyCliTests(unittest.TestCase):
    def test_canonical_evidence_fingerprint_and_committed_artifact(self):
        expected = build_discovery_efficiency_evidence()
        artifact = Path("docs/rehearsals/api_football_discovery_efficiency_2026-08-01.json")
        self.assertEqual(json.loads(artifact.read_text(encoding="utf-8")), expected)
        self.assertEqual(expected["evidence_fingerprint"], "e54eb842e738efab28d86bdc79417a6b3ca616af0b6a734672e60db645e69267")

    def test_request_cost_cli_supports_human_and_json(self):
        class FakeClient(CostProvider):
            def __init__(self, **_):
                super().__init__({"2026-08-01": []})

        for output in ("human", "json"):
            stream = io.StringIO()
            cache = Path(f"var/test_cli_{output}_capabilities.json")
            cache.unlink(missing_ok=True)
            self.addCleanup(cache.unlink, missing_ok=True)
            with patch("app.football.client.FootballClient", FakeClient), redirect_stdout(stream):
                code = cli_main([
                    "inspect-discovery-request-costs", "--output", output,
                    "--horizon-days", "1", "--capability-cache", str(cache),
                ])
            self.assertEqual(code, 0)
            self.assertIn("goalvision-api-football-request-cost-report-v1", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
