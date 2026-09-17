import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.collector import HistoryCollector
from app.core.application import GoalVisionApp
from app.explanations import (
    DEFAULT_EXPLANATION_CONFIG,
    PredictionExplanationEngine,
)
from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import HistoricalMatch, LeagueTable, Match
from app.pipeline import (
    PredictionAssessment,
    PredictionPipeline,
    PredictionSupportingData,
)
from app.quality_score import (
    DEFAULT_QUALITY_SCORE_CONFIG,
    QualityScoreEngine,
    QualitySignal,
)
from app.rest_days import RestDaysEngine


class PredictionAssessmentTests(unittest.TestCase):

    def setUp(self) -> None:
        self.kickoff = datetime.now(timezone.utc)
        league_strength = LeagueStrengthEngine(
            ratings={39: 1.0},
            default_strength=0.5,
        )
        h2h = H2HEngine()
        rest_days = RestDaysEngine()
        self.pipeline = PredictionPipeline(
            league_strength=league_strength,
            h2h=h2h,
            rest_days=rest_days,
            quality_score=QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG),
            explanations=PredictionExplanationEngine(
                config=DEFAULT_EXPLANATION_CONFIG,
                league_strength=league_strength,
                h2h=h2h,
                rest_days=rest_days,
            ),
        )
        self.match = Match(
            fixture_id=500,
            league_id=39,
            league_name="Premier League",
            season=2026,
            home_team_id=1,
            home_team_name="Home",
            away_team_id=2,
            away_team_name="Away",
            kickoff=self.kickoff,
            status="NS",
        )

    def raw_history(self, team_id: int, home: bool) -> list[dict]:
        fixtures = []
        for index in range(5):
            home_id = team_id if home else 100 + index
            away_id = 100 + index if home else team_id
            fixtures.append({
                "teams": {
                    "home": {"id": home_id},
                    "away": {"id": away_id},
                },
                "goals": {"home": 2, "away": 1},
            })
        return fixtures

    def table(self) -> dict[int, LeagueTable]:
        return {
            1: LeagueTable(1, 1, 20, 45, 14, 3, 3, 40, 15, 25),
            2: LeagueTable(2, 2, 20, 42, 13, 3, 4, 36, 18, 18),
        }

    def contexts(self, with_standings: bool = True):
        table = self.table() if with_standings else None
        home = self.pipeline.build_team(
            team_id=1,
            history=self.raw_history(1, home=True),
            table=table,
            is_home=True,
        )
        away = self.pipeline.build_team(
            team_id=2,
            history=self.raw_history(2, home=False),
            table=table,
            is_home=False,
        )
        return home, away

    def historical(
        self,
        fixture_id: int,
        home_team_id: int,
        away_team_id: int,
        days_ago: int,
    ) -> HistoricalMatch:
        return HistoricalMatch(
            fixture_id=fixture_id,
            league_id=39,
            season=2026,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_goals=2,
            away_goals=1,
            kickoff=self.kickoff - timedelta(days=days_ago),
            status="FT",
        )

    def complete_support(self) -> PredictionSupportingData:
        history = (
            self.historical(1, 1, 2, 10),
            self.historical(2, 1, 91, 3),
            self.historical(3, 92, 2, 4),
        )
        return PredictionSupportingData(
            h2h_history=history,
            rest_history=history,
            metadata=(("source", "test_history"),),
        )

    def test_complete_supporting_data_builds_typed_assessment(self):
        home, away = self.contexts()

        assessment = self.pipeline.assess(
            self.match,
            home,
            away,
            self.complete_support(),
        )

        self.assertIsInstance(assessment, PredictionAssessment)
        self.assertEqual(assessment.quality_score.completeness, 1.0)
        self.assertEqual(assessment.quality_score.missing_signals, ())
        self.assertIs(assessment.home_context, home)
        self.assertIs(assessment.away_context, away)

    def test_partial_supporting_data_is_reported(self):
        home, away = self.contexts()

        assessment = self.pipeline.assess(self.match, home, away)

        self.assertLess(assessment.quality_score.completeness, 1.0)
        self.assertIn(QualitySignal.H2H, assessment.quality_score.missing_signals)
        self.assertIn(
            QualitySignal.REST_DAYS,
            assessment.quality_score.missing_signals,
        )

    def test_missing_standings_is_reported(self):
        home, away = self.contexts(with_standings=False)

        assessment = self.pipeline.assess(
            self.match,
            home,
            away,
            self.complete_support(),
        )

        self.assertIn(
            QualitySignal.STANDINGS,
            assessment.quality_score.missing_signals,
        )

    def test_missing_h2h_is_reported(self):
        home, away = self.contexts()
        support = self.complete_support()

        assessment = self.pipeline.assess(
            self.match,
            home,
            away,
            PredictionSupportingData(rest_history=support.rest_history),
        )

        self.assertIn(QualitySignal.H2H, assessment.quality_score.missing_signals)

    def test_missing_rest_history_is_reported(self):
        home, away = self.contexts()
        support = self.complete_support()

        assessment = self.pipeline.assess(
            self.match,
            home,
            away,
            PredictionSupportingData(h2h_history=support.h2h_history),
        )

        self.assertIn(
            QualitySignal.REST_DAYS,
            assessment.quality_score.missing_signals,
        )

    def test_assessment_is_deterministic(self):
        home, away = self.contexts()
        support = self.complete_support()

        first = self.pipeline.assess(self.match, home, away, support)
        second = self.pipeline.assess(self.match, home, away, support)

        self.assertEqual(first, second)

    def test_assessment_does_not_change_prediction(self):
        home, away = self.contexts()
        prediction = self.pipeline.predict(self.match, home, away)

        assessment = self.pipeline.assess(
            self.match,
            home,
            away,
            self.complete_support(),
        )

        self.assertEqual(assessment.prediction, prediction)

    def test_assessment_calculates_prediction_once(self):
        home, away = self.contexts()
        original_predict = self.pipeline.engine.predict
        self.pipeline.engine.predict = Mock(side_effect=original_predict)

        assessment = self.pipeline.assess(
            self.match,
            home,
            away,
            self.complete_support(),
        )

        self.assertEqual(assessment.prediction.winner, "Home")
        self.pipeline.engine.predict.assert_called_once()

    def test_cached_raw_history_is_converted_to_typed_support(self):
        raw_fixture = {
            "fixture": {
                "id": 10,
                "date": (self.kickoff - timedelta(days=3)).isoformat(),
                "status": {"short": "FT"},
            },
            "league": {"id": 39, "season": 2026},
            "teams": {"home": {"id": 1}, "away": {"id": 2}},
            "goals": {"home": 2, "away": 1},
        }
        application = GoalVisionApp.__new__(GoalVisionApp)
        application.history_collector = HistoryCollector()
        application.football = SimpleNamespace(
            cached_team_form=lambda team_id: [raw_fixture] if team_id == 1 else []
        )

        support = application._supporting_data(self.match)

        self.assertIsNotNone(support.h2h_history)
        self.assertIsInstance(support.h2h_history[0], HistoricalMatch)
        self.assertEqual(support.h2h_history, support.rest_history)


if __name__ == "__main__":
    unittest.main()
