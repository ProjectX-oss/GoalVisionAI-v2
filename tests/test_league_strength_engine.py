import unittest
from types import SimpleNamespace

from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import TeamRating
from app.pipeline import PredictionPipeline
from app.rest_days import RestDaysEngine


class LeagueStrengthEngineTests(unittest.TestCase):

    def test_returns_configured_normalized_strength(self):
        engine = LeagueStrengthEngine(
            ratings={39: 0.95},
            default_strength=0.5,
        )

        self.assertEqual(engine.strength_for(39), 0.95)

    def test_returns_injected_default_for_unknown_league(self):
        engine = LeagueStrengthEngine(
            ratings={},
            default_strength=0.4,
        )

        self.assertEqual(engine.strength_for(999), 0.4)

    def test_rejects_strength_outside_normalized_range(self):
        with self.assertRaises(ValueError):
            LeagueStrengthEngine(
                ratings={39: 1.01},
                default_strength=0.5,
            )

    def test_rejects_non_integer_league_id(self):
        with self.assertRaises(TypeError):
            LeagueStrengthEngine(
                ratings={"39": 0.95},
                default_strength=0.5,
            )

    def test_pipeline_retains_injected_engine_without_using_it(self):
        low_strength = LeagueStrengthEngine(
            ratings={39: 0.1},
            default_strength=0.5,
        )
        high_strength = LeagueStrengthEngine(
            ratings={39: 1.0},
            default_strength=0.5,
        )
        low_pipeline = PredictionPipeline(
            low_strength,
            H2HEngine(),
            RestDaysEngine(),
        )
        high_pipeline = PredictionPipeline(
            high_strength,
            H2HEngine(),
            RestDaysEngine(),
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

        low_prediction = low_pipeline.predict(match, home, away)
        high_prediction = high_pipeline.predict(match, home, away)

        self.assertIs(low_pipeline.league_strength, low_strength)
        self.assertEqual(low_prediction, high_prediction)


if __name__ == "__main__":
    unittest.main()
