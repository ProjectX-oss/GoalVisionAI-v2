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


class H2HEngineTests(unittest.TestCase):

    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def fixture(
        self,
        fixture_id: int,
        home_goals: int,
        away_goals: int,
        days_ago: int,
        status: str = "FT",
        home_team_id: int = 1,
        away_team_id: int = 2,
    ) -> HistoricalMatch:
        return HistoricalMatch(
            fixture_id=fixture_id,
            league_id=39,
            season=2026,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_goals=home_goals,
            away_goals=away_goals,
            kickoff=self.now - timedelta(days=days_ago),
            status=status,
        )

    def test_empty_history_returns_neutral_strength(self):
        engine = H2HEngine()

        self.assertEqual(engine.strength_for(1, 2, []), 0.5)

    def test_one_finished_match_is_evaluated(self):
        engine = H2HEngine(minimum_confidence=0.0)

        strength = engine.strength_for(1, 2, [self.fixture(1, 2, 0, 1)])

        self.assertEqual(strength, 1.0)

    def test_multiple_matches_are_evaluated_for_requested_team(self):
        engine = H2HEngine(minimum_confidence=0.0)
        fixtures = [
            self.fixture(1, 2, 0, 1),
            self.fixture(2, 1, 1, 2),
            self.fixture(3, 0, 2, 3),
            self.fixture(4, 4, 1, 4, home_team_id=2, away_team_id=1),
            self.fixture(5, 3, 0, 5, status="NS"),
        ]

        strength = engine.strength_for(1, 2, fixtures)

        self.assertEqual(strength, 0.55)

    def test_recent_matches_receive_more_weight(self):
        engine = H2HEngine(minimum_confidence=0.0)
        recent_win = self.fixture(1, 2, 0, 1)
        older_loss = self.fixture(2, 0, 2, 10)

        strength = engine.strength_for(1, 2, [older_loss, recent_win])

        self.assertEqual(strength, 0.666667)

    def test_duplicate_fixtures_are_ignored(self):
        engine = H2HEngine(minimum_confidence=0.0)
        win = self.fixture(1, 2, 0, 1)
        loss = self.fixture(2, 0, 1, 2)

        strength = engine.strength_for(1, 2, [win, win, loss])

        self.assertEqual(strength, 0.666667)

    def test_strength_is_always_normalized(self):
        engine = H2HEngine(max_history=2, minimum_confidence=0.0)
        wins = [
            self.fixture(1, 10, 0, 1),
            self.fixture(2, 8, 0, 2),
            self.fixture(3, 6, 0, 3),
        ]

        strength = engine.strength_for(1, 2, wins)

        self.assertGreaterEqual(strength, 0.0)
        self.assertLessEqual(strength, 1.0)

    def test_insufficient_history_is_reduced_toward_neutral(self):
        engine = H2HEngine(max_history=10, minimum_confidence=0.5)

        strength = engine.strength_for(1, 2, [self.fixture(1, 2, 0, 1)])

        self.assertEqual(strength, 0.6)

    def test_pipeline_retains_h2h_engine_without_using_it(self):
        h2h = H2HEngine()
        h2h.strength_for = Mock(return_value=1.0)
        pipeline = PredictionPipeline(
            LeagueStrengthEngine({}, default_strength=0.5),
            h2h,
            RestDaysEngine(),
            QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG),
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

        self.assertIs(pipeline.h2h, h2h)
        h2h.strength_for.assert_not_called()


if __name__ == "__main__":
    unittest.main()
