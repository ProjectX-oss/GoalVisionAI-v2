import sqlite3
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.calibration import CalibrationFittingPolicy, CalibrationObservation
from app.database import Database
from app.probability_calibration import (
    CalibrationMethod,
    CalibrationRunAlreadyExistsError,
    ProbabilityCalibrationConfig,
    ProbabilityCalibrationEngine,
    ProbabilityCalibrationRequest,
    SQLiteProbabilityCalibrationRepository,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
MODEL_VERSION = "model-v1"


def observation(
    index: int,
    probability: str,
    outcome: int,
) -> CalibrationObservation:
    predicted_at = BASE + timedelta(hours=index)
    return CalibrationObservation(
        observation_id=f"observation-{index}",
        fixture_id=index + 1,
        competition="Test League",
        market="MATCH_WINNER",
        selection="home",
        prediction_timestamp=predicted_at,
        outcome_timestamp=predicted_at + timedelta(minutes=30),
        raw_probability=Decimal(probability),
        binary_outcome=outcome,
        model_version=MODEL_VERSION,
    )


HISTORY = (
    observation(0, "0.10", 0),
    observation(1, "0.20", 0),
    observation(2, "0.30", 1),
    observation(3, "0.40", 0),
    observation(4, "0.60", 1),
    observation(5, "0.70", 0),
    observation(6, "0.80", 1),
    observation(7, "0.90", 1),
)


def config(method: CalibrationMethod) -> ProbabilityCalibrationConfig:
    policy = CalibrationFittingPolicy(
        global_minimum=4,
        market_minimum=4,
        competition_minimum=4,
        competition_market_minimum=4,
        odds_band_minimum=4,
        minimum_positive=2,
        minimum_negative=2,
    )
    return ProbabilityCalibrationConfig(method=method, fitting_policy=policy)


def request(
    probability: str = "0.65",
    *,
    run_id: str = "run-1",
    history: tuple[CalibrationObservation, ...] = HISTORY,
) -> ProbabilityCalibrationRequest:
    return ProbabilityCalibrationRequest(
        calibration_run_id=run_id,
        raw_probability=Decimal(probability),
        historical_data=history,
        timestamp=BASE + timedelta(days=1),
        model_version=MODEL_VERSION,
    )


class ProbabilityCalibrationEngineTests(unittest.TestCase):
    def test_identity_calibration_and_immutable_report(self):
        report = ProbabilityCalibrationEngine(
            config(CalibrationMethod.IDENTITY)
        ).calibrate(request())

        self.assertEqual(report.calibrated_probability, Decimal("0.65"))
        self.assertEqual(report.delta, Decimal("0.00"))
        self.assertEqual(report.calibration_method, CalibrationMethod.IDENTITY)
        self.assertEqual(report.metric_summary.observation_count, len(HISTORY))
        with self.assertRaises(FrozenInstanceError):
            report.delta = Decimal("0")

    def test_identity_without_history_is_supported_and_clamped(self):
        report = ProbabilityCalibrationEngine().calibrate(
            request("0", history=())
        )

        self.assertEqual(report.calibrated_probability, Decimal("0.001"))
        self.assertEqual(report.metric_summary.observation_count, 0)
        self.assertEqual(len(report.metric_summary.reliability_bins), 10)
        self.assertEqual(len(report.confidence_histogram), 10)

    def test_platt_scaling_is_fitted_and_bounded(self):
        report = ProbabilityCalibrationEngine(
            config(CalibrationMethod.PLATT)
        ).calibrate(request())

        self.assertEqual(report.calibration_method, CalibrationMethod.PLATT)
        self.assertTrue(
            Decimal("0.001")
            <= report.calibrated_probability
            <= Decimal("0.999")
        )
        self.assertNotEqual(report.calibrated_probability, report.raw_probability)

    def test_isotonic_regression_is_fitted_and_bounded(self):
        report = ProbabilityCalibrationEngine(
            config(CalibrationMethod.ISOTONIC)
        ).calibrate(request())

        self.assertEqual(report.calibration_method, CalibrationMethod.ISOTONIC)
        self.assertTrue(
            Decimal("0.001")
            <= report.calibrated_probability
            <= Decimal("0.999")
        )

    def test_all_methods_preserve_probability_ordering(self):
        values = ("0", "0.1", "0.3", "0.5", "0.7", "0.9", "1")
        for method in CalibrationMethod:
            engine = ProbabilityCalibrationEngine(config(method))
            outputs = tuple(
                engine.calibrate(request(value, run_id=f"{method.value}-{value}"))
                .calibrated_probability
                for value in values
            )
            with self.subTest(method=method):
                self.assertEqual(outputs, tuple(sorted(outputs)))

    def test_boundary_probabilities_are_clamped_for_every_method(self):
        for method in CalibrationMethod:
            engine = ProbabilityCalibrationEngine(config(method))
            low = engine.calibrate(request("0", run_id=f"{method.value}-low"))
            high = engine.calibrate(request("1", run_id=f"{method.value}-high"))
            with self.subTest(method=method):
                self.assertGreaterEqual(low.calibrated_probability, Decimal("0.001"))
                self.assertLessEqual(high.calibrated_probability, Decimal("0.999"))

    def test_identity_metric_correctness_reliability_and_histogram(self):
        history = (
            observation(10, "0.25", 0),
            observation(11, "0.75", 1),
        )
        report = ProbabilityCalibrationEngine(
            ProbabilityCalibrationConfig(
                method=CalibrationMethod.IDENTITY,
                reliability_bin_count=2,
                confidence_bin_count=2,
            )
        ).calibrate(request(history=history))
        metrics = report.metric_summary

        self.assertEqual(metrics.brier_score, Decimal("0.0625"))
        self.assertAlmostEqual(metrics.log_loss, -Decimal("0.75").ln(), places=27)
        self.assertEqual(metrics.expected_calibration_error, Decimal("0.25"))
        self.assertEqual(metrics.maximum_calibration_error, Decimal("0.25"))
        self.assertEqual(
            tuple(item.observation_count for item in metrics.reliability_bins),
            (1, 1),
        )
        self.assertEqual(
            tuple(item.observation_count for item in report.confidence_histogram),
            (1, 1),
        )
        self.assertEqual(
            tuple(item.observation_fraction for item in report.confidence_histogram),
            (Decimal("0.5"), Decimal("0.5")),
        )

    def test_repeatability_is_exact_and_input_order_independent(self):
        engine = ProbabilityCalibrationEngine(config(CalibrationMethod.PLATT))
        first = engine.calibrate(request())
        second = engine.calibrate(request(history=tuple(reversed(HISTORY))))

        self.assertEqual(first, second)

    def test_fitted_methods_require_history(self):
        for method in (CalibrationMethod.PLATT, CalibrationMethod.ISOTONIC):
            with self.subTest(method=method), self.assertRaises(ValueError):
                ProbabilityCalibrationEngine(config(method)).calibrate(
                    request(history=())
                )

    def test_future_or_wrong_model_history_is_rejected(self):
        future = observation(1, "0.5", 1)
        future = CalibrationObservation(
            future.observation_id,
            future.fixture_id,
            future.competition,
            future.market,
            future.selection,
            BASE + timedelta(days=2),
            BASE + timedelta(days=2, minutes=30),
            future.raw_probability,
            future.binary_outcome,
            future.model_version,
        )
        with self.assertRaises(ValueError):
            request(history=(future,))
        with self.assertRaises(ValueError):
            ProbabilityCalibrationRequest(
                calibration_run_id="wrong-model",
                raw_probability=Decimal("0.5"),
                historical_data=HISTORY,
                timestamp=BASE + timedelta(days=1),
                model_version="different-model",
            )


class ProbabilityCalibrationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteProbabilityCalibrationRepository(self.database)
        self.report = ProbabilityCalibrationEngine(
            config(CalibrationMethod.ISOTONIC)
        ).calibrate(request())

    def tearDown(self):
        self.database.close()

    def test_migration_nine_creates_append_only_history(self):
        versions = tuple(
            row[0]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 42)))
        columns = {
            row[1]
            for row in self.database.connection.execute(
                "PRAGMA table_info(probability_calibration_history)"
            )
        }
        self.assertTrue(
            {
                "calibration_run_id",
                "raw_probability",
                "calibrated_probability",
                "brier_score",
                "reliability_bins",
                "confidence_histogram",
            }.issubset(columns)
        )

    def test_report_round_trip_is_lossless(self):
        self.repository.append(self.report)

        self.assertEqual(
            self.repository.get(self.report.calibration_run_id),
            self.report,
        )
        self.assertEqual(
            self.repository.history_for_model(MODEL_VERSION),
            (self.report,),
        )

    def test_duplicate_run_never_overwrites_history(self):
        self.repository.append(self.report)

        with self.assertRaises(CalibrationRunAlreadyExistsError):
            self.repository.append(self.report)
        self.assertEqual(self.repository.get("run-1"), self.report)

    def test_database_rejects_updates_and_deletes(self):
        self.repository.append(self.report)

        for statement in (
            "UPDATE probability_calibration_history SET delta = '0'",
            "DELETE FROM probability_calibration_history",
        ):
            with self.subTest(statement=statement), self.assertRaises(
                sqlite3.IntegrityError
            ):
                self.database.connection.execute(statement)


if __name__ == "__main__":
    unittest.main()
