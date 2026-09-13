import asyncio
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from app.current_match_intelligence import (
    IntelligenceBudgetPolicy,
    RealMatchLabIntelligenceBridge,
    SQLiteCurrentMatchIntelligenceRepository,
    CurrentMatchIntelligenceService,
    future_feature_vector,
)
from app.current_match_intelligence.normalization import normalize_injuries
from app.current_match_intelligence.models import FieldProvenance
from app.current_match_intelligence.cli import _diagnostic
from app.current_match_intelligence.provider import ApiFootballCurrentMatchProvider
from app.database import Database


NOW = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=8)


def fixture():
    return {"response": [{
        "fixture": {"id": 500, "date": KICKOFF.isoformat(), "referee": "A. Ref",
                    "venue": {"id": 9, "name": "Ground", "city": "Berlin"},
                    "status": {"short": "NS"}},
        "league": {"id": 39, "name": "League", "country": "Country", "season": 2026,
                   "round": "Regular Season - 4"},
        "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 20, "name": "Away"}},
    }]}


def lineup(fixture_id=500):
    return {"response": [lineup_team(10, "Home", range(2, 13)),
                         lineup_team(20, "Away", range(21, 32))]}


def lineup_team(team_id, name, players):
    return {"team": {"id": team_id, "name": name}, "formation": "4-3-3",
            "startXI": [{"player": {"id": value, "name": f"P{value}", "pos": "M"}}
                         for value in players],
            "substitutes": [{"player": {"id": team_id * 100, "name": "Sub", "pos": "D"}}]}


def history(team_id, opponent_id, first_id):
    rows = []
    for index, days in enumerate((16, 10, 5)):
        home = index != 1
        teams = ({"home": {"id": team_id}, "away": {"id": opponent_id}}
                 if home else {"home": {"id": opponent_id}, "away": {"id": team_id}})
        goals = {"home": 2 if home else 0, "away": 1 if home else 1}
        rows.append({"fixture": {"id": first_id + index,
                                  "date": (KICKOFF - timedelta(days=days)).isoformat(),
                                  "status": {"short": "FT"}},
                     "league": {"name": "National Cup" if index == 2 else "League"},
                     "teams": teams, "goals": goals})
    return rows


def team_stats(team_id):
    return {"response": {"team": {"id": team_id},
        "fixtures": {"played": {"home": 4, "away": 4, "total": 8},
                     "wins": {"home": 3, "away": 1, "total": 4},
                     "draws": {"home": 1, "away": 1, "total": 2},
                     "loses": {"home": 0, "away": 2, "total": 2}},
        "goals": {"for": {"total": {"home": 8, "away": 4, "total": 12}},
                  "against": {"total": {"home": 2, "away": 5, "total": 7}}}}}


def odds():
    return {"response": [{"fixture": {"id": 500}, "update": NOW.isoformat(),
        "bookmakers": [{"id": 1, "name": "Book", "bets": [{"name": "Match Winner",
            "values": [{"value": "Home", "odd": "2.00"}, {"value": "Draw", "odd": "3.20"},
                       {"value": "Away", "odd": "3.80"}]}]}]}]}


def injuries():
    return {"response": [
        {"team": {"id": 10, "name": "Home"},
         "player": {"id": 1, "name": "P1", "type": "Missing Fixture", "reason": "Knee Injury"}},
        {"team": {"id": 20, "name": "Away"},
         "player": {"id": 21, "name": "P21", "type": "Missing Fixture", "reason": "Red Card Suspension"}},
    ]}


def fixture_statistics():
    return {"response": [
        {"team": {"id": 10}, "statistics": [
            {"type": "Total Shots", "value": 12}, {"type": "Shots on Goal", "value": 5},
            {"type": "Ball Possession", "value": "55%"}, {"type": "Corner Kicks", "value": 6},
            {"type": "Yellow Cards", "value": 2}, {"type": "expected_goals", "value": "1.42"}]},
        {"team": {"id": 20}, "statistics": [
            {"type": "Total Shots", "value": 8}, {"type": "Shots on Goal", "value": 3},
            {"type": "Ball Possession", "value": "45%"}, {"type": "Corner Kicks", "value": 3}]},
    ]}


class FakeProvider:
    def __init__(self, clock=NOW):
        self.calls = 0
        self.limit = 40
        self.metadata = {}
        self.clock = clock
        self.endpoints = []

    @property
    def request_count(self): return self.calls
    def restrict_requests(self, maximum_calls, *, daily_reserve=20): self.limit = min(self.limit, maximum_calls)
    def response_metadata(self): return self.metadata
    def _use(self, endpoint, value):
        if self.calls >= self.limit: raise RuntimeError("REQUEST_LIMIT")
        self.calls += 1
        self.endpoints.append(endpoint)
        self.metadata = {"endpoint": endpoint, "retrieved_at_utc": self.clock.isoformat()}
        return value
    async def fixture(self, fixture_id): return self._use("/fixtures", fixture())
    async def current_odds(self, fixture_id): return self._use("/odds", odds())
    async def injuries(self, fixture_id): return self._use("/injuries", injuries())
    async def team_statistics(self, team_id, league_id, season): return self._use("/teams/statistics", team_stats(team_id))
    async def last_matches(self, team_id, last=10, **_):
        return self._use("/fixtures", history(team_id, 99, 100 if team_id == 10 else 200))
    async def fixture_statistics(self, fixture_id): return self._use("/fixtures/statistics", fixture_statistics())
    async def lineup(self, fixture_id):
        if fixture_id == 500: return self._use("/fixtures/lineups", lineup())
        if fixture_id in {100, 101, 102}: return self._use("/fixtures/lineups", {"response": [lineup_team(10, "Home", range(1, 12))]})
        return self._use("/fixtures/lineups", {"response": [lineup_team(20, "Away", range(21, 32))]})


class CurrentMatchIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteCurrentMatchIntelligenceRepository(self.database)

    def tearDown(self): self.database.close()

    def collect(self, provider=None, *, budget=40, now=NOW):
        provider = provider or FakeProvider()
        result = asyncio.run(CurrentMatchIntelligenceService(
            self.repository, provider,
            budget=IntelligenceBudgetPolicy(maximum_api_calls=budget),
        ).collect(500, evaluated_at=now))
        return result, provider

    def test_lineup_freshness_is_independent_and_kickoff_sensitive(self):
        result, _ = self.collect()
        evidence = next(item for item in result.snapshot.freshness if item.signal == "confirmed_lineups")
        self.assertEqual((evidence.status.value, evidence.policy_seconds), ("FRESH", 1800))
        self.assertEqual(result.snapshot.field("feature.confirmed_starters_count_home").value, 11)
        self.assertEqual(result.snapshot.field("feature.missing_recent_starters_count_home").value, 1)
        self.assertEqual(
            result.snapshot.field("home.lineup.missing_recent_starters.1").value,
            "MISSING_FROM_CONFIRMED_XI",
        )
        later = FakeProvider(NOW + timedelta(minutes=31))
        self.collect(later, now=NOW + timedelta(minutes=31))
        self.assertIn("/fixtures/lineups", later.endpoints)
        self.assertNotIn("/injuries", later.endpoints)

    def test_injury_normalization_preserves_reason_and_explicit_suspension(self):
        p = FieldProvenance("API-FOOTBALL", "/injuries", NOW, None, "500")
        fields, injured_set, suspended_set = normalize_injuries(injuries(), identity={"home_team_id": 10, "away_team_id": 20}, provenance=p)
        values = {item.name: item.value for item in fields}
        self.assertEqual(values["home.availability.1.status"], "INJURED")
        self.assertEqual(values["away.availability.21.status"], "SUSPENDED")
        self.assertEqual(values["home.availability.1.reason"], "Knee Injury")
        self.assertEqual((injured_set["home"], suspended_set["away"]), ({"1"}, {"21"}))

    def test_rest_congestion_home_away_splits_and_real_statistics(self):
        snapshot = self.collect()[0].snapshot
        self.assertEqual(snapshot.field("feature.rest_days_home").value, 5)
        self.assertEqual(snapshot.field("feature.schedule_congestion_away").value, 1)
        self.assertEqual(
            snapshot.field("feature.home_recent_goals_for_per_match").value,
            "1.666666666666666666666666667",
        )
        self.assertEqual(snapshot.field("home.venue_recent.match_count").value, 2)
        self.assertEqual(snapshot.field("home.recent_shots_per_match").value, "12")
        self.assertEqual(snapshot.field("home.recent_xg_per_match").value, "1.42")

    def test_missing_data_remains_explicit(self):
        snapshot = self.collect()[0].snapshot
        self.assertIn("fixture.weather", snapshot.missing_data)
        self.assertIn("fixture.travel_context", snapshot.missing_data)
        self.assertNotIn("away.recent_shots_per_match", snapshot.missing_data)

    def test_empty_lineup_response_is_missing_not_fresh(self):
        class NoLineup(FakeProvider):
            async def lineup(self, fixture_id):
                if fixture_id == 500:
                    return self._use("/fixtures/lineups", {"response": []})
                return await super().lineup(fixture_id)

        snapshot = self.collect(NoLineup())[0].snapshot
        evidence = next(
            item for item in snapshot.freshness
            if item.signal == "confirmed_lineups"
        )
        self.assertEqual(evidence.status.value, "MISSING")
        self.assertIn("CONFIRMED_LINEUPS_NOT_AVAILABLE", snapshot.blockers)
        self.assertIsNone(snapshot.field("feature.lineup_continuity_home"))

    def test_cache_reuse_consumes_no_new_api_calls(self):
        first, first_provider = self.collect()
        second_provider = FakeProvider(NOW + timedelta(minutes=10))
        second, second_provider = self.collect(
            second_provider, now=NOW + timedelta(minutes=10)
        )
        self.assertGreater(first.api_calls_used, 0)
        self.assertEqual((second.api_calls_used, second_provider.calls), (0, 0))
        self.assertEqual(
            {x.name: x.value for x in first.snapshot.fields},
            {x.name: x.value for x in second.snapshot.fields},
        )

    def test_deterministic_replay_and_lab_bridge(self):
        snapshot = self.collect()[0].snapshot
        replay = self.repository.load(snapshot.snapshot_id)
        self.assertEqual(replay, snapshot)
        bridge = RealMatchLabIntelligenceBridge(self.repository)
        context = bridge.context_for_analysis("500", analysis_at=NOW)
        self.assertEqual(context["snapshot_id"], snapshot.snapshot_id)
        self.assertEqual(context["live_78_consumption"], "NOT_CONNECTED")
        self.assertEqual(future_feature_vector(replay), future_feature_vector(snapshot))

    def test_every_normalized_field_has_complete_provenance(self):
        snapshot = self.collect()[0].snapshot
        self.assertTrue(snapshot.fields)
        for field in snapshot.fields:
            self.assertTrue(field.provenance, field.name)
            for provenance in field.provenance:
                self.assertEqual(provenance.fixture_id, "500")
                self.assertTrue(provenance.provider)
                self.assertTrue(provenance.endpoint)
                self.assertIsNotNone(provenance.retrieved_at)

    def test_api_budget_is_enforced_before_required_stage(self):
        result, provider = self.collect(budget=7)
        self.assertEqual(provider.calls, 1)
        self.assertIn("INTELLIGENCE_REQUIRED_STAGE_BUDGET_INSUFFICIENT", result.snapshot.blockers)
        self.assertLessEqual(result.api_calls_used, 7)

    def test_append_only_persistence_rejects_mutation(self):
        snapshot = self.collect()[0].snapshot
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE current_match_intelligence_snapshots SET fixture_id='x' WHERE snapshot_id=?",
                (snapshot.snapshot_id,),
            )

    def test_diagnostic_exposes_every_required_section(self):
        value = _diagnostic(self.collect()[0].snapshot)
        self.assertTrue({"fixture", "retrieved_context", "missing_data", "freshness",
                         "api_calls", "normalized_features", "blockers", "provenance"}
                        <= value.keys())
        self.assertFalse(value["inference_executed"])
        self.assertEqual(value["telegram_sends"], 0)

    def test_new_api_football_adapter_endpoints_are_exact(self):
        class Response:
            def json(self): return {"response": []}

        class Client:
            request_count = 0
            def response_metadata(self): return {}
            async def _get(self, path, *, params):
                self.last = (path, params)
                return Response()

        client = Client(); adapter = ApiFootballCurrentMatchProvider(client)
        asyncio.run(adapter.lineup(500)); self.assertEqual(client.last, ("/fixtures/lineups", {"fixture": 500}))
        asyncio.run(adapter.injuries(500)); self.assertEqual(client.last, ("/injuries", {"fixture": 500}))
        asyncio.run(adapter.team_statistics(10, 39, 2026))
        self.assertEqual(client.last, ("/teams/statistics", {"team": 10, "league": 39, "season": 2026}))
        asyncio.run(adapter.fixture_statistics(100)); self.assertEqual(client.last, ("/fixtures/statistics", {"fixture": 100}))


if __name__ == "__main__":
    unittest.main()
