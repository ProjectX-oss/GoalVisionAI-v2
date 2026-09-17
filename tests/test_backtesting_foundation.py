import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

from app.backtesting import (
    BacktestMetricsService,
    EvaluationOutcome,
    HistoricalEvaluationRecord,
    WalkForwardEvaluator,
    WalkForwardFoldResult,
    WalkForwardWindow,
    WalkForwardWindowProvider,
)


PREDICTION_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def record(
    fixture_id: int = 1,
    probability: str = "0.60",
    odds: str = "2.00",
    closing_odds: str | None = "1.80",
    outcome: EvaluationOutcome = EvaluationOutcome.WON,
    profit_loss: str = "1.00",
    prediction_timestamp: datetime = PREDICTION_AT,
) -> HistoricalEvaluationRecord:
    return HistoricalEvaluationRecord(
        fixture_id=fixture_id,
        competition="Premier League",
        kickoff_datetime=prediction_timestamp + timedelta(hours=3),
        prediction_timestamp=prediction_timestamp,
        feature_timestamp=prediction_timestamp - timedelta(minutes=10),
        odds_timestamp=prediction_timestamp - timedelta(minutes=5),
        market="Match Winner",
        selection="Home",
        model_probability=Decimal(probability),
        offered_odds=Decimal(odds),
        closing_odds=(Decimal(closing_odds) if closing_odds is not None else None),
        result="2-1",
        outcome=outcome,
        profit_loss=Decimal(profit_loss),
    )


class BacktestMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BacktestMetricsService()

    def test_zero_bets_returns_neutral_metrics(self):
        metrics = self.service.evaluate(())

        self.assertEqual(metrics.total_bets, 0)
        self.assertEqual(metrics.wins, 0)
        self.assertEqual(metrics.losses, 0)
        self.assertEqual(metrics.voids, 0)
        self.assertEqual(metrics.hit_rate, Decimal("0"))
        self.assertEqual(metrics.roi, Decimal("0"))
        self.assertEqual(metrics.total_profit, Decimal("0"))
        self.assertEqual(metrics.average_odds, Decimal("0"))
        self.assertEqual(metrics.maximum_drawdown, Decimal("0"))
        self.assertEqual(metrics.brier_score, Decimal("0"))
        self.assertEqual(metrics.log_loss, Decimal("0"))
        self.assertIsNone(metrics.average_clv)
        self.assertIsNone(metrics.positive_clv_percentage)
        self.assertEqual(metrics.average_probability, Decimal("0"))

    def test_only_void_bets_are_excluded_from_scoring(self):
        metrics = self.service.evaluate((
            record(outcome=EvaluationOutcome.VOID, profit_loss="0"),
            record(
                fixture_id=2,
                outcome=EvaluationOutcome.VOID,
                profit_loss="0",
            ),
        ))

        self.assertEqual(metrics.total_bets, 2)
        self.assertEqual(metrics.voids, 2)
        self.assertEqual(metrics.hit_rate, Decimal("0"))
        self.assertEqual(metrics.roi, Decimal("0"))
        self.assertEqual(metrics.brier_score, Decimal("0"))
        self.assertEqual(metrics.log_loss, Decimal("0"))

    def test_complete_metric_set_uses_one_unit_roi(self):
        records = (
            record(probability="0.80", odds="2.00", profit_loss="1.00"),
            record(
                fixture_id=2,
                probability="0.25",
                odds="3.00",
                closing_odds="3.50",
                outcome=EvaluationOutcome.LOST,
                profit_loss="-1.00",
                prediction_timestamp=PREDICTION_AT + timedelta(days=1),
            ),
            record(
                fixture_id=3,
                probability="0.50",
                odds="4.00",
                outcome=EvaluationOutcome.VOID,
                profit_loss="0",
                prediction_timestamp=PREDICTION_AT + timedelta(days=2),
            ),
        )

        metrics = self.service.evaluate(records)

        self.assertEqual(metrics.total_bets, 3)
        self.assertEqual((metrics.wins, metrics.losses, metrics.voids), (1, 1, 1))
        self.assertEqual(metrics.hit_rate, Decimal("0.5"))
        self.assertEqual(metrics.roi, Decimal("0"))
        self.assertEqual(metrics.total_profit, Decimal("0.00"))
        self.assertEqual(metrics.average_odds, Decimal("3.00"))
        self.assertEqual(
            metrics.average_probability,
            Decimal(
                "0.51666666666666666666666666666666666666666666666667"
            ),
        )
        self.assertEqual(metrics.brier_score, Decimal("0.05125"))

    def test_probability_close_to_zero_has_finite_log_loss(self):
        metrics = self.service.evaluate((record(probability="0.000000001"),))

        self.assertTrue(metrics.log_loss.is_finite())
        self.assertGreater(metrics.log_loss, Decimal("20"))
        self.assertEqual(metrics.brier_score, Decimal("0.999999998000000001"))

    def test_probability_close_to_one_has_small_log_loss(self):
        metrics = self.service.evaluate((record(probability="0.999999999"),))

        self.assertTrue(metrics.log_loss.is_finite())
        self.assertGreater(metrics.log_loss, Decimal("0"))
        self.assertLess(metrics.log_loss, Decimal("0.00000001"))
        self.assertEqual(metrics.brier_score, Decimal("0.000000000000000001"))

    def test_impossible_outcome_at_exact_probability_has_infinite_log_loss(self):
        losing = record(
            probability="1",
            outcome=EvaluationOutcome.LOST,
            profit_loss="-1",
        )

        self.assertEqual(
            self.service.evaluate((losing,)).log_loss,
            Decimal("Infinity"),
        )

    def test_missing_closing_odds_are_not_invented(self):
        metrics = self.service.evaluate((record(closing_odds=None),))

        self.assertIsNone(metrics.average_clv)
        self.assertIsNone(metrics.positive_clv_percentage)

    def test_positive_clv(self):
        metrics = self.service.evaluate((record(odds="2.20", closing_odds="2.00"),))

        self.assertEqual(metrics.average_clv, Decimal("0.10"))
        self.assertEqual(metrics.positive_clv_percentage, Decimal("100"))

    def test_negative_clv(self):
        metrics = self.service.evaluate((record(odds="1.80", closing_odds="2.00"),))

        self.assertEqual(metrics.average_clv, Decimal("-0.10"))
        self.assertEqual(metrics.positive_clv_percentage, Decimal("0"))

    def test_mixed_clv_ignores_only_missing_values(self):
        metrics = self.service.evaluate((
            record(odds="2.20", closing_odds="2.00"),
            record(fixture_id=2, odds="1.80", closing_odds="2.00"),
            record(fixture_id=3, closing_odds=None),
        ))

        self.assertEqual(metrics.average_clv, Decimal("0.00"))
        self.assertEqual(metrics.positive_clv_percentage, Decimal("50.0"))

    def test_maximum_drawdown_uses_prediction_time_order(self):
        records = (
            record(
                fixture_id=4,
                profit_loss="3",
                prediction_timestamp=PREDICTION_AT + timedelta(days=3),
            ),
            record(
                fixture_id=1,
                profit_loss="2",
                prediction_timestamp=PREDICTION_AT,
            ),
            record(
                fixture_id=3,
                outcome=EvaluationOutcome.LOST,
                profit_loss="-2",
                prediction_timestamp=PREDICTION_AT + timedelta(days=2),
            ),
            record(
                fixture_id=2,
                outcome=EvaluationOutcome.LOST,
                profit_loss="-1",
                prediction_timestamp=PREDICTION_AT + timedelta(days=1),
            ),
        )

        self.assertEqual(
            self.service.evaluate(records).maximum_drawdown,
            Decimal("3"),
        )

    def test_repeatability_is_independent_of_input_iteration_order(self):
        first = record(fixture_id=1)
        second = record(
            fixture_id=2,
            outcome=EvaluationOutcome.LOST,
            profit_loss="-1",
            prediction_timestamp=PREDICTION_AT + timedelta(days=1),
        )

        expected = self.service.evaluate((first, second))
        self.assertEqual(expected, self.service.evaluate((second, first)))
        self.assertEqual(expected, self.service.evaluate(iter((first, second))))

    def test_repeatability_is_independent_of_callers_decimal_context(self):
        records = (record(odds="2.20", closing_odds="1.90"),)
        expected = self.service.evaluate(records)

        with localcontext() as context:
            context.prec = 8
            actual = self.service.evaluate(records)

        self.assertEqual(actual, expected)


class HistoricalEvaluationValidationTests(unittest.TestCase):
    def test_invalid_probabilities_are_rejected(self):
        for probability in ("-0.01", "1.01", "NaN", "Infinity"):
            with self.subTest(probability=probability), self.assertRaises(ValueError):
                record(probability=probability)

    def test_decimal_fields_reject_binary_float_inputs(self):
        with self.assertRaises(TypeError):
            replace(record(), model_probability=0.6)

    def test_feature_timestamp_after_prediction_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Feature timestamp"):
            replace(
                record(),
                feature_timestamp=PREDICTION_AT + timedelta(microseconds=1),
            )

    def test_odds_timestamp_after_prediction_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Odds timestamp"):
            replace(
                record(),
                odds_timestamp=PREDICTION_AT + timedelta(microseconds=1),
            )

    def test_timestamps_equal_to_prediction_are_allowed(self):
        value = replace(
            record(),
            feature_timestamp=PREDICTION_AT,
            odds_timestamp=PREDICTION_AT,
        )

        self.assertEqual(value.feature_timestamp, value.prediction_timestamp)
        self.assertEqual(value.odds_timestamp, value.prediction_timestamp)

    def test_naive_timestamps_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Prediction timestamp"):
            replace(
                record(),
                prediction_timestamp=PREDICTION_AT.replace(tzinfo=None),
            )

    def test_prediction_after_kickoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "after kickoff"):
            replace(record(), kickoff_datetime=PREDICTION_AT - timedelta(seconds=1))

    def test_outcome_and_profit_loss_must_be_consistent(self):
        invalid = (
            (EvaluationOutcome.WON, "0"),
            (EvaluationOutcome.LOST, "0"),
            (EvaluationOutcome.VOID, "1"),
        )
        for outcome, profit_loss in invalid:
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                record(outcome=outcome, profit_loss=profit_loss)


class WalkForwardPrimitiveTests(unittest.TestCase):
    def test_non_overlapping_window_is_valid(self):
        window = WalkForwardWindow(
            training_start=PREDICTION_AT,
            training_end=PREDICTION_AT + timedelta(days=30),
            evaluation_start=PREDICTION_AT + timedelta(days=30),
            evaluation_end=PREDICTION_AT + timedelta(days=37),
        )

        self.assertEqual(window.training_end, window.evaluation_start)

    def test_overlapping_future_window_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            WalkForwardWindow(
                training_start=PREDICTION_AT,
                training_end=PREDICTION_AT + timedelta(days=31),
                evaluation_start=PREDICTION_AT + timedelta(days=30),
                evaluation_end=PREDICTION_AT + timedelta(days=37),
            )

    def test_protocols_are_runtime_pluggable(self):
        class Provider:
            def windows(self):
                return ()

        class Evaluator:
            def evaluate(self, records, window):
                return WalkForwardFoldResult(
                    window,
                    BacktestMetricsService().evaluate(records),
                )

        self.assertIsInstance(Provider(), WalkForwardWindowProvider)
        self.assertIsInstance(Evaluator(), WalkForwardEvaluator)


if __name__ == "__main__":
    unittest.main()
