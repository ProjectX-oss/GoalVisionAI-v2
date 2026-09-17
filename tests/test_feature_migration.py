import unittest

from app.models import FeatureVector, FormSnapshot, TeamStrength
from app.pipeline import TeamBuilder
from app.prediction import RatingEngine, TeamStrengthEngine


class FeatureMigrationTests(unittest.TestCase):

    def test_rating_engine_accepts_team_strength(self):
        strength = TeamStrength(
            attack=60.0,
            defense=70.0,
            form=80.0,
            momentum=50.0,
            home=75.0,
            away=40.0,
            goal_difference=55.0,
            clean_sheet=30.0,
            failed_to_score=85.0,
            league_position=90.0,
            home_points=65.0,
            away_points=45.0,
            recent_goal_difference=60.0,
            recent_points=70.0,
        )

        rating = RatingEngine().calculate(strength, is_home=True)

        self.assertEqual(rating.form, strength.form)
        self.assertEqual(rating.attack, strength.attack)
        self.assertGreater(rating.total, 0.0)

    def test_team_strength_maps_feature_vector_fields(self):
        features = FeatureVector(
            team_id=1,
            form=0.8,
            attack=0.6,
            defense=0.7,
            momentum=0.5,
            home_strength=0.75,
            away_strength=0.4,
            win_rate=0.8,
            points_per_game=0.7,
            goals_for=2.0,
            goals_against=1.0,
            goal_difference=0.5,
            league_position=0.9,
            rest_days=0.0,
            clean_sheet_rate=0.3,
            failed_to_score_rate=0.15,
            home_points_per_game=0.65,
            away_points_per_game=0.45,
            recent_goal_difference=0.2,
            recent_points_per_game=0.7,
        )

        strength = TeamStrengthEngine().calculate(features)

        self.assertEqual(strength.home, 75.0)
        self.assertEqual(strength.away, 40.0)
        self.assertEqual(strength.failed_to_score, 85.0)

    def test_team_builder_completes_feature_to_rating_pipeline(self):
        snapshot = FormSnapshot(
            team_id=1,
            games=0,
            wins=0,
            draws=0,
            losses=0,
            goals_for=0,
            goals_against=0,
            goal_difference=0,
            home_games=0,
            away_games=0,
            home_wins=0,
            home_draws=0,
            home_losses=0,
            away_wins=0,
            away_draws=0,
            away_losses=0,
            clean_sheets=0,
            failed_to_score=0,
            points=0,
            attack=0.0,
            defense=0.0,
            win_rate=0.0,
            momentum=0.0,
        )

        builder = TeamBuilder()
        builder.form.analyze = lambda team_id, history: snapshot

        context = builder.build(1, history=[], table=None, is_home=True)

        self.assertEqual(context.team_id, 1)
        self.assertEqual(context.features.team_id, 1)
        self.assertIsInstance(context.strength, TeamStrength)
        self.assertEqual(context.rating.form, 0.0)


if __name__ == "__main__":
    unittest.main()
