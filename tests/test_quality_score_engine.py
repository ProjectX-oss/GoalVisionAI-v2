import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import TeamRating
from app.pipeline import PredictionPipeline
from app.quality_score import (
    DEFAULT_QUALITY_SCORE_CONFIG,
    QualityScoreEngine,
    QualitySignal,
    QualitySignals,
)
from app.rest_days import RestDaysEngine


class QualityScoreEngineTests(unittest.TestCase):

    def setUp(self) -> None:
        self.engine = QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG)

    @staticmethod
    def complete_signals(**changes: float | None) -> QualitySignals:
        values: dict[str, float | None] = {
            "recent_form": 1.0,
            "league_strength": 1.0,
            "standings": 1.0,
            "h2h": 1.0,
            "rest_days": 1.0,
            "home_away": 1.0,
            "attack": 1.0,
            "defense": 1.0,
            "conflicting_signal_penalty": 0.0,
            "missing_data_penalty": 0.0,
        }
        values.update(changes)
        return QualitySignals(**values)

    def test_complete_high_quality_data_scores_100(self):
        result = self.engine.evaluate(self.complete_signals())

        self.assertEqual(result.score, 100)
        self.assertEqual(result.completeness, 1.0)
        self.assertEqual(result.consistency, 1.0)
        self.assertEqual(result.missing_signals, ())
        self.assertEqual(result.reason_codes, ("DATA_COMPLETE",))

    def test_empty_data_scores_zero(self):
        result = self.engine.evaluate(QualitySignals())

        self.assertEqual(result.score, 0)
        self.assertEqual(result.completeness, 0.0)
        self.assertEqual(result.available_signals, ())
        self.assertEqual(result.missing_signals, tuple(QualitySignal))

    def test_partial_data_has_partial_completeness(self):
        signals = QualitySignals(
            recent_form=0.8,
            standings=0.7,
            attack=0.9,
            defense=0.9,
        )

        result = self.engine.evaluate(signals)

        self.assertGreater(result.score, 0)
        self.assertLess(result.score, 100)
        self.assertGreater(result.completeness, 0.0)
        self.assertLess(result.completeness, 1.0)
        self.assertIn("DATA_PARTIAL", result.reason_codes)

    def test_conflicting_signals_reduce_consistency_and_score(self):
        baseline = self.engine.evaluate(self.complete_signals())
        conflicting = self.engine.evaluate(
            self.complete_signals(conflicting_signal_penalty=0.8)
        )

        self.assertLess(conflicting.score, baseline.score)
        self.assertEqual(conflicting.consistency, 0.2)
        self.assertIn("SIGNALS_CONFLICT", conflicting.reason_codes)

    def test_missing_critical_signal_penalizes_more(self):
        missing_critical = self.engine.evaluate(
            self.complete_signals(standings=None)
        )
        missing_noncritical = self.engine.evaluate(
            self.complete_signals(h2h=None)
        )

        self.assertLess(missing_critical.score, missing_noncritical.score)
        self.assertIn(
            "CRITICAL_DATA_MISSING",
            missing_critical.reason_codes,
        )

    def test_score_is_normalized_for_valid_inputs(self):
        results = (
            self.engine.evaluate(QualitySignals()),
            self.engine.evaluate(self.complete_signals()),
            self.engine.evaluate(
                self.complete_signals(
                    conflicting_signal_penalty=1.0,
                    missing_data_penalty=1.0,
                )
            ),
        )

        for result in results:
            self.assertGreaterEqual(result.score, 0)
            self.assertLessEqual(result.score, 100)

    def test_invalid_configuration_is_rejected(self):
        invalid_config = replace(
            DEFAULT_QUALITY_SCORE_CONFIG,
            signal_weights={QualitySignal.RECENT_FORM: 1.0},
        )

        with self.assertRaises(ValueError):
            QualityScoreEngine(invalid_config)

    def test_invalid_signal_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate(QualitySignals(recent_form=1.1))

    def test_same_input_produces_same_result(self):
        signals = self.complete_signals(
            h2h=0.6,
            conflicting_signal_penalty=0.2,
        )

        self.assertEqual(
            self.engine.evaluate(signals),
            self.engine.evaluate(signals),
        )

    def test_pipeline_retains_quality_engine_without_using_it(self):
        quality_score = QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG)
        quality_score.evaluate = Mock()
        pipeline = PredictionPipeline(
            LeagueStrengthEngine({}, default_strength=0.5),
            H2HEngine(),
            RestDaysEngine(),
            quality_score,
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

        before = pipeline.predict(match, home, away)
        after = pipeline.predict(match, home, away)

        self.assertEqual(before, after)
        self.assertIs(pipeline.quality_score, quality_score)
        quality_score.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
