import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import HistoricalMatch, TeamRating
from app.pipeline import PredictionPipeline
from app.quality_score import (
    DEFAULT_QUALITY_SCORE_CONFIG,
    QualityScoreEngine,
)
from app.rest_days import RestDaysEngine


class RestDaysEngineTests(unittest.TestCase):

    def setUp(self) -> None:
        self.fixture_date = datetime.now(timezone.utc)

    def fixture(
        self,
        fixture_id: int,
        team_id: int,
        days_ago: float,
        status: str = "FT",
    ) -> HistoricalMatch:
        return HistoricalMatch(
            fixture_id=fixture_id,
            league_id=39,
            season=2026,
            home_team_id=team_id,
            away_team_id=99,
            home_goals=0,
            away_goals=0,
            kickoff=self.fixture_date - timedelta(days=days_ago),
            status=status,
        )

    def test_no_history_returns_neutral_advantage(self):
        engine = RestDaysEngine()

        advantage = engine.advantage_for(1, 2, self.fixture_date, [])

        self.assertEqual(advantage, 0.5)

    def test_same_rest_returns_neutral_advantage(self):
        engine = RestDaysEngine(maximum_rest_days=10)
        fixtures = [self.fixture(1, 1, 5), self.fixture(2, 2, 5)]

        advantage = engine.advantage_for(1, 2, self.fixture_date, fixtures)

        self.assertEqual(advantage, 0.5)

    def test_more_home_rest_produces_home_advantage(self):
        engine = RestDaysEngine(maximum_rest_days=10)
        fixtures = [self.fixture(1, 1, 8), self.fixture(2, 2, 4)]

        advantage = engine.advantage_for(1, 2, self.fixture_date, fixtures)

        self.assertEqual(advantage, 0.7)

    def test_more_away_rest_produces_away_advantage(self):
        engine = RestDaysEngine(maximum_rest_days=10)
        fixtures = [self.fixture(1, 1, 4), self.fixture(2, 2, 8)]

        advantage = engine.advantage_for(1, 2, self.fixture_date, fixtures)

        self.assertEqual(advantage, 0.3)

    def test_long_breaks_are_capped(self):
        engine = RestDaysEngine(maximum_rest_days=10)
        fixtures = [self.fixture(1, 1, 100), self.fixture(2, 2, 20)]

        advantage = engine.advantage_for(1, 2, self.fixture_date, fixtures)

        self.assertEqual(advantage, 0.5)

    def test_output_is_normalized(self):
        engine = RestDaysEngine(maximum_rest_days=10)
        fixtures = [self.fixture(1, 1, 20), self.fixture(2, 2, 0.1)]

        advantage = engine.advantage_for(1, 2, self.fixture_date, fixtures)

        self.assertGreaterEqual(advantage, 0.0)
        self.assertLessEqual(advantage, 1.0)

    def test_unfinished_matches_are_ignored(self):
        engine = RestDaysEngine(maximum_rest_days=10)
        fixtures = [
            self.fixture(1, 1, 8),
            self.fixture(2, 1, 1, status="NS"),
            self.fixture(3, 2, 4),
        ]

        advantage = engine.advantage_for(1, 2, self.fixture_date, fixtures)

        self.assertEqual(advantage, 0.7)

    def test_pipeline_retains_rest_engine_without_using_it(self):
        rest_days = RestDaysEngine()
        rest_days.advantage_for = Mock(return_value=1.0)
        pipeline = PredictionPipeline(
            LeagueStrengthEngine({}, default_strength=0.5),
            H2HEngine(),
            rest_days,
            QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG),
            Mock(),
        )
        match = SimpleNamespace(
            home_team_name="Home",
            away_team_name="Away",
        )
        home = SimpleNamespace(
            rating=TeamRating(60.0, 60.0, 60.0, 60.0, 60.0)
        )
        away = SimpleNamespace(
            rating=TeamRating(40.0, 40.0, 40.0, 40.0, 40.0)
        )

        pipeline.predict(match, home, away)

        self.assertIs(pipeline.rest_days, rest_days)
        rest_days.advantage_for.assert_not_called()


if __name__ == "__main__":
    unittest.main()
