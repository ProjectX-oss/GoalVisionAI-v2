import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.explanations import (
    DEFAULT_EXPLANATION_CONFIG,
    PredictionExplanation,
    PredictionExplanationEngine,
)
from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import HistoricalMatch, Match, Prediction
from app.quality_score import (
    DEFAULT_QUALITY_SCORE_CONFIG,
    QualityScoreEngine,
    QualitySignals,
)
from app.rest_days import RestDaysEngine


class PredictionExplanationTests(unittest.TestCase):

    def setUp(self) -> None:
        self.kickoff = datetime.now(timezone.utc)
        self.league_strength = LeagueStrengthEngine({39: 1.0}, 0.5)
        self.h2h = H2HEngine(minimum_confidence=0.0)
        self.rest_days = RestDaysEngine(maximum_rest_days=10)
        self.quality_score = QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG)
        self.engine = PredictionExplanationEngine(
            DEFAULT_EXPLANATION_CONFIG,
            self.league_strength,
            self.h2h,
            self.rest_days,
        )
        self.match = Match(
            fixture_id=1,
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

    @staticmethod
    def context(
        form: float,
        attack: float,
        defense: float,
        momentum: float,
        venue: float,
        standings: float,
        home: bool,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            rating=SimpleNamespace(
                form=form,
                attack=attack,
                defense=defense,
                momentum=momentum,
            ),
            strength=SimpleNamespace(
                home=venue if home else 0.0,
                away=venue if not home else 0.0,
            ),
            features=SimpleNamespace(league_position=standings),
        )

    def history(self, home_wins: bool | None, equal_rest: bool = False):
        if home_wins is None:
            h2h_goals = (1, 1)
        else:
            h2h_goals = (2, 0) if home_wins else (0, 2)
        away_days = 7 if equal_rest else (3 if home_wins else 8)
        home_days = 7 if equal_rest else (8 if home_wins else 3)
        return (
            HistoricalMatch(
                1, 39, 2026, 1, 2,
                h2h_goals[0], h2h_goals[1],
                self.kickoff - timedelta(days=20), "FT",
            ),
            HistoricalMatch(
                2, 39, 2026, 1, 91, 1, 0,
                self.kickoff - timedelta(days=home_days), "FT",
            ),
            HistoricalMatch(
                3, 39, 2026, 92, 2, 1, 0,
                self.kickoff - timedelta(days=away_days), "FT",
            ),
        )

    @staticmethod
    def complete_signals(conflict: float = 0.0) -> QualitySignals:
        return QualitySignals(
            recent_form=1.0,
            league_strength=1.0,
            standings=1.0,
            h2h=0.3,
            rest_days=1.0,
            home_away=1.0,
            attack=1.0,
            defense=1.0,
            conflicting_signal_penalty=conflict,
        )

    def explain(
        self,
        prediction: Prediction,
        home: SimpleNamespace,
        away: SimpleNamespace,
        signals: QualitySignals,
        history=None,
    ) -> PredictionExplanation:
        quality = self.quality_score.evaluate(signals)
        return self.engine.explain(
            match=self.match,
            prediction=prediction,
            quality_score=quality,
            quality_signals=signals,
            home=home,
            away=away,
            h2h_history=history,
            rest_history=history,
        )

    def test_strong_home_advantage(self):
        prediction = Prediction("Home", 70.0, 30.0, "HIGH", 40.0)
        home = self.context(85, 80, 78, 70, 80, 0.9, home=True)
        away = self.context(40, 45, 50, 40, 35, 0.4, home=False)

        explanation = self.explain(
            prediction,
            home,
            away,
            self.complete_signals(),
            self.history(home_wins=True),
        )

        self.assertTrue(any("Home" in factor for factor in explanation.positive_factors))
        self.assertIn("FORM_HOME_ADVANTAGE", explanation.reason_codes)
        self.assertIn("H2H_HOME_ADVANTAGE", explanation.reason_codes)

    def test_strong_away_advantage(self):
        prediction = Prediction("Away", 30.0, 70.0, "HIGH", 40.0)
        home = self.context(35, 40, 45, 40, 30, 0.3, home=True)
        away = self.context(82, 85, 80, 75, 85, 0.9, home=False)

        explanation = self.explain(
            prediction,
            home,
            away,
            self.complete_signals(),
            self.history(home_wins=False),
        )

        self.assertTrue(any("Away" in factor for factor in explanation.positive_factors))
        self.assertIn("ATTACK_AWAY_ADVANTAGE", explanation.reason_codes)
        self.assertIn("H2H_AWAY_ADVANTAGE", explanation.reason_codes)

    def test_conflicting_signals_are_a_risk(self):
        prediction = Prediction("Home", 55.0, 45.0, "MEDIUM", 10.0)
        home = self.context(80, 40, 75, 40, 70, 0.8, home=True)
        away = self.context(45, 85, 50, 80, 40, 0.4, home=False)

        explanation = self.explain(
            prediction,
            home,
            away,
            self.complete_signals(conflict=0.5),
            self.history(home_wins=True),
        )

        self.assertIn(
            "Supporting indicators point in different directions.",
            explanation.risk_factors,
        )
        self.assertIn("SIGNALS_CONFLICT", explanation.reason_codes)

    def test_missing_data_is_reported_without_facts(self):
        prediction = Prediction("Home", 50.0, 50.0, "LOW", 0.0)
        neutral = self.context(50, 50, 50, 50, 50, 0.5, home=True)
        away = self.context(50, 50, 50, 50, 50, 0.5, home=False)
        signals = QualitySignals(league_strength=1.0)

        explanation = self.explain(prediction, neutral, away, signals)

        self.assertIn("recent form", explanation.missing_data)
        self.assertIn("head-to-head history", explanation.missing_data)
        self.assertIn("Critical supporting data is missing.", explanation.risk_factors)

    def test_neutral_evidence_has_no_directional_claim(self):
        prediction = Prediction("Home", 50.0, 50.0, "LOW", 0.0)
        home = self.context(50, 50, 50, 50, 50, 0.5, home=True)
        away = self.context(50, 50, 50, 50, 50, 0.5, home=False)

        explanation = self.explain(
            prediction,
            home,
            away,
            self.complete_signals(),
            self.history(home_wins=None, equal_rest=True),
        )

        self.assertIn("no clear supporting advantage", explanation.short_summary)

    def test_output_is_deterministic(self):
        prediction = Prediction("Home", 60.0, 40.0, "HIGH", 20.0)
        home = self.context(75, 70, 72, 65, 70, 0.8, home=True)
        away = self.context(45, 50, 48, 50, 40, 0.4, home=False)
        history = self.history(home_wins=True)

        first = self.explain(prediction, home, away, self.complete_signals(), history)
        second = self.explain(prediction, home, away, self.complete_signals(), history)

        self.assertEqual(first, second)

    def test_explanation_contains_no_unavailable_odds_or_statistics(self):
        prediction = Prediction("Home", 55.0, 45.0, "MEDIUM", 10.0)
        home = self.context(60, 60, 60, 60, 60, 0.6, home=True)
        away = self.context(50, 50, 50, 50, 50, 0.5, home=False)

        explanation = self.explain(
            prediction,
            home,
            away,
            QualitySignals(league_strength=1.0),
        )
        rendered = repr(explanation).lower()

        self.assertNotIn("odds", rendered)
        self.assertNotIn("profit", rendered)
        self.assertNotIn("guarantee", rendered)


if __name__ == "__main__":
    unittest.main()
