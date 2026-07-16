import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.calibration import (
    CalibrationFallbackFittingService,
    CalibrationFitRequest,
    CalibrationFittingError,
    CalibrationFittingPolicy,
    CalibrationMethodSelectionService,
    CalibrationNonConvergenceError,
    CalibrationObservation,
    CalibrationResolutionRequest,
    CalibrationScope,
    CalibrationScopeKind,
    CalibrationSelectionMetric,
    CalibrationSelectionPolicy,
    CalibrationTrainingWindow,
    CalibrationWalkForwardService,
    CalibrationComparisonService,
    CalibrationReportService,
    CalibratorSerializer,
    FittedIsotonicCalibrator,
    FittedPlattCalibrator,
    IdentityCalibrator,
    IsotonicCalibrator,
    IsotonicFittingConfig,
    PlattCalibrator,
    PlattFittingConfig,
)
from app.backtesting import WalkForwardWindow


NOW = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
START = NOW - timedelta(days=30)
CUTOFF = NOW - timedelta(days=1)


def obs(
    index: int,
    probability: str,
    outcome: int,
    *,
    timestamp: datetime | None = None,
    outcome_timestamp: datetime | None = None,
    competition: str = "Premier League",
    market: str = "Match Winner",
) -> CalibrationObservation:
    prediction = timestamp or START + timedelta(hours=index)
    return CalibrationObservation(
        observation_id=f"obs-{index:03d}",
        fixture_id=index + 1,
        competition=competition,
        market=market,
        selection="Home",
        prediction_timestamp=prediction,
        outcome_timestamp=outcome_timestamp or prediction + timedelta(minutes=1),
        raw_probability=Decimal(probability),
        binary_outcome=outcome,
        model_version="model-v1",
        odds_band="all",
    )


def request(
    scope: CalibrationScope | None = None,
    *,
    target: datetime | None = NOW,
    maximum_end: datetime = CUTOFF,
) -> CalibrationFitRequest:
    return CalibrationFitRequest(
        fitted_at=maximum_end,
        training_window=CalibrationTrainingWindow(START, maximum_end),
        scope=scope or CalibrationScope.global_scope(),
        version="fit-v1",
        target_prediction_timestamp=target,
        model_version="model-v1",
    )


def policy(total=4, positive=1, negative=1, single_class=False):
    return CalibrationFittingPolicy(
        global_minimum=total,
        market_minimum=total,
        competition_minimum=total,
        competition_market_minimum=total,
        odds_band_minimum=total,
        minimum_positive=positive,
        minimum_negative=negative,
        allow_single_class_isotonic=single_class,
    )


def mixed():
    return (
        obs(1, "0.10", 0),
        obs(2, "0.25", 0),
        obs(3, "0.70", 1),
        obs(4, "0.90", 1),
    )


def validation_copy(values):
    return tuple(
        replace(
            item,
            observation_id=f"val-{item.observation_id}",
            fixture_id=item.fixture_id + 100,
            prediction_timestamp=NOW + timedelta(hours=item.fixture_id),
            outcome_timestamp=NOW + timedelta(hours=item.fixture_id, minutes=1),
        )
        for item in values
    )


class PlattFittingTests(unittest.TestCase):
    def test_normal_mixed_fit_is_deterministic_and_in_range(self):
        trainer = PlattCalibrator(policy=policy())
        first = trainer.fit(mixed(), request())
        second = trainer.fit(tuple(reversed(mixed())), request())
        self.assertEqual(first, second)
        self.assertIsInstance(first, FittedPlattCalibrator)
        self.assertTrue(first.fit_data.converged)
        for value in ("0", "0.2", "0.5", "0.8", "1"):
            calibrated = first.calibrate(Decimal(value))
            self.assertTrue(Decimal("0") <= calibrated <= Decimal("1"))

    def test_zero_one_inputs_are_clipped_and_finite(self):
        fitted = PlattCalibrator(policy=policy()).fit(
            (
                obs(1, "0", 0),
                obs(2, "0.2", 0),
                obs(3, "0.8", 1),
                obs(4, "1", 1),
            ),
            request(),
        )
        self.assertTrue(fitted.calibrate(Decimal("0")).is_finite())
        self.assertTrue(fitted.calibrate(Decimal("1")).is_finite())
        self.assertEqual(fitted.fit_data.clipping_epsilon, Decimal("0.000001"))

    def test_identical_probabilities_fit_intercept_with_regularization(self):
        values = tuple(
            obs(index, "0.5", outcome)
            for index, outcome in enumerate((0, 1, 0, 1), start=1)
        )
        fitted = PlattCalibrator(policy=policy()).fit(values, request())
        self.assertTrue(fitted.fit_data.final_objective.is_finite())
        self.assertEqual(fitted.calibrate(Decimal("0.5")), Decimal("0.5"))

    def test_single_class_outcomes_are_rejected(self):
        for outcome in (0, 1):
            values = tuple(obs(index, "0.5", outcome) for index in range(1, 5))
            with self.subTest(outcome=outcome), self.assertRaises(
                CalibrationFittingError
            ):
                PlattCalibrator(policy=policy()).fit(values, request())

    def test_complete_separation_is_stabilized_by_regularization(self):
        fitted = PlattCalibrator(
            PlattFittingConfig(regularization=Decimal("0.1")),
            policy(),
        ).fit(mixed(), request())
        self.assertTrue(fitted.fit_data.a.is_finite())
        self.assertGreater(fitted.fit_data.a, 0)

    def test_forced_non_convergence_is_typed(self):
        trainer = PlattCalibrator(
            PlattFittingConfig(
                maximum_iterations=1,
                convergence_tolerance=Decimal("1e-30"),
            ),
            policy(),
        )
        with self.assertRaises(CalibrationNonConvergenceError):
            trainer.fit(mixed(), request())

    def test_metadata_and_parameters_are_immutable(self):
        fitted = PlattCalibrator(policy=policy()).fit(mixed(), request())
        self.assertEqual(fitted.metadata.positive_outcome_count, 2)
        self.assertEqual(fitted.metadata.negative_outcome_count, 2)
        self.assertEqual(fitted.metadata.training_cutoff, CUTOFF)
        self.assertTrue(fitted.diagnostics.production_eligible)
        self.assertTrue(fitted.diagnostics.training_brier_score.is_finite())
        with self.assertRaises(FrozenInstanceError):
            fitted.fit_data.a = Decimal("2")

    def test_serialization_round_trip_preserves_predictions_and_metadata(self):
        fitted = PlattCalibrator(policy=policy()).fit(mixed(), request())
        serializer = CalibratorSerializer()
        restored = serializer.deserialize(serializer.serialize(fitted))
        self.assertEqual(restored, fitted)
        self.assertEqual(
            restored.calibrate(Decimal("0.37")),
            fitted.calibrate(Decimal("0.37")),
        )


class IsotonicFittingTests(unittest.TestCase):
    def test_normal_fit_is_monotonic_and_deterministic(self):
        trainer = IsotonicCalibrator(policy=policy())
        first = trainer.fit(mixed(), request())
        second = trainer.fit(tuple(reversed(mixed())), request())
        self.assertEqual(first, second)
        values = tuple(first.calibrate(Decimal(value)) for value in ("0", "0.2", "0.5", "0.8", "1"))
        self.assertEqual(values, tuple(sorted(values)))

    def test_repeated_probabilities_group_mixed_outcomes(self):
        values = (
            obs(1, "0.3", 0),
            obs(2, "0.3", 1),
            obs(3, "0.8", 1),
            obs(4, "0.8", 1),
        )
        fitted = IsotonicCalibrator(policy=policy()).fit(values, request())
        self.assertEqual(fitted.calibrate(Decimal("0.3")), Decimal("0.5"))

    def test_one_unique_probability_is_supported_with_both_classes(self):
        values = tuple(
            obs(index, "0.5", outcome)
            for index, outcome in enumerate((0, 1, 0, 1), start=1)
        )
        fitted = IsotonicCalibrator(policy=policy()).fit(values, request())
        self.assertEqual(fitted.fit_data.breakpoints, (Decimal("0.5"),))
        self.assertEqual(fitted.calibrate(Decimal("0.1")), Decimal("0.5"))
        self.assertEqual(fitted.calibrate(Decimal("0.9")), Decimal("0.5"))

    def test_single_class_policy_rejects_by_default_and_can_explicitly_allow(self):
        values = tuple(obs(index, "0.5", 0) for index in range(1, 5))
        with self.assertRaises(CalibrationFittingError):
            IsotonicCalibrator(policy=policy()).fit(values, request())
        fitted = IsotonicCalibrator(
            policy=policy(single_class=True)
        ).fit(values, request())
        self.assertEqual(fitted.calibrate(Decimal("0.5")), Decimal("0"))

    def test_right_continuous_step_prediction_and_extrapolation(self):
        fitted = IsotonicCalibrator(policy=policy()).fit(mixed(), request())
        self.assertEqual(
            fitted.calibrate(fitted.fit_data.breakpoints[0]),
            fitted.fit_data.fitted_values[0],
        )
        between = (
            fitted.fit_data.breakpoints[0] + fitted.fit_data.breakpoints[1]
        ) / 2
        self.assertEqual(
            fitted.calibrate(between),
            fitted.fit_data.fitted_values[1],
        )
        self.assertEqual(
            fitted.calibrate(Decimal("0")),
            fitted.fit_data.fitted_values[0],
        )
        self.assertEqual(
            fitted.calibrate(Decimal("1")),
            fitted.fit_data.fitted_values[-1],
        )

    def test_optional_output_clipping(self):
        fitted = IsotonicCalibrator(
            IsotonicFittingConfig(output_epsilon=Decimal("0.01")),
            policy(),
        ).fit(mixed(), request())
        self.assertTrue(
            all(Decimal("0.01") <= value <= Decimal("0.99") for value in fitted.fit_data.fitted_values)
        )

    def test_metadata_is_immutable_and_serializes_losslessly(self):
        fitted = IsotonicCalibrator(policy=policy()).fit(mixed(), request())
        with self.assertRaises(FrozenInstanceError):
            fitted.fit_data.breakpoints = ()
        serializer = CalibratorSerializer()
        self.assertEqual(
            serializer.deserialize(serializer.serialize(fitted)),
            fitted,
        )


class PolicyFallbackWalkForwardTests(unittest.TestCase):
    def test_insufficient_total_positive_and_negative_samples(self):
        cases = (
            (mixed()[:2], "total"),
            (tuple(obs(i, "0.5", int(i == 1)) for i in range(1, 5)), "positive"),
            (tuple(obs(i, "0.5", int(i != 1)) for i in range(1, 5)), "negative"),
        )
        strict = policy(total=4, positive=2, negative=2)
        for values, label in cases:
            with self.subTest(label=label), self.assertRaises(CalibrationFittingError):
                PlattCalibrator(policy=strict).fit(values, request())

    def test_narrow_scope_falls_back_to_global_then_identity(self):
        values = mixed()
        service = CalibrationFallbackFittingService()
        resolution = CalibrationResolutionRequest("La Liga", "Match Winner")
        fitted = service.fit(
            values,
            resolution,
            request(),
            IsotonicCalibrator(policy=policy()),
        )
        self.assertEqual(
            fitted.scope_used,
            CalibrationScope(CalibrationScopeKind.MARKET, market="Match Winner"),
        )
        self.assertEqual(
            tuple(attempt.scope.kind.value for attempt in fitted.attempts),
            ("COMPETITION_MARKET", "MARKET"),
        )
        identity = service.fit(
            values[:1],
            resolution,
            request(),
            IsotonicCalibrator(policy=policy()),
        )
        self.assertEqual(identity.scope_used, CalibrationScope.identity_scope())

    def test_walk_forward_excludes_target_and_future_outcome(self):
        reports = CalibrationReportService()
        service = CalibrationWalkForwardService(
            CalibrationComparisonService(reports)
        )
        window = WalkForwardWindow(
            START,
            CUTOFF,
            NOW,
            NOW + timedelta(days=1),
        )
        training = mixed()
        target = obs(20, "0.6", 1, timestamp=NOW)
        future_outcome = obs(
            21,
            "0.4",
            0,
            timestamp=START + timedelta(days=2),
            outcome_timestamp=NOW,
        )
        fold = service.evaluate(
            training + (target, future_outcome),
            (window,),
            PlattCalibrator(policy=policy()),
            CalibrationScope.global_scope(),
            "walk-fit-v1",
            "model-v1",
        )[0]
        self.assertNotIn("obs-020", fold.training_observation_ids)
        self.assertNotIn("obs-021", fold.training_observation_ids)
        self.assertEqual(fold.target_observation_ids, ("obs-020",))
        self.assertEqual(fold.scope_used, CalibrationScope.global_scope())
        self.assertEqual(fold.fit_version, "walk-fit-v1")
        self.assertEqual(len(fold.calibrated_targets), 1)

    def test_repeated_walk_forward_is_deterministic(self):
        reports = CalibrationReportService()
        service = CalibrationWalkForwardService(CalibrationComparisonService(reports))
        window = WalkForwardWindow(START, CUTOFF, NOW, NOW + timedelta(days=1))
        values = mixed() + (obs(20, "0.6", 1, timestamp=NOW),)
        trainer = IsotonicCalibrator(policy=policy())
        first = service.evaluate(values, (window,), trainer, CalibrationScope.global_scope(), "v1")
        second = service.evaluate(tuple(reversed(values)), (window,), trainer, CalibrationScope.global_scope(), "v1")
        self.assertEqual(first, second)


class SelectionSerializationSafetyTests(unittest.TestCase):
    def test_identity_wins_metric_tie(self):
        service = CalibrationMethodSelectionService(
            policy=CalibrationSelectionPolicy(
                primary_metric=CalibrationSelectionMetric.BRIER_SCORE
            )
        )
        training = tuple(
            obs(index, "0.5", outcome)
            for index, outcome in enumerate((0, 1, 0, 1), start=1)
        )
        selection = service.select(
            training,
            validation_copy(training),
            request(target=None),
            PlattCalibrator(policy=policy()),
            IsotonicCalibrator(policy=policy()),
        )
        self.assertIn(selection.selected_method, {"identity", "platt", "isotonic"})
        tied = tuple(
            item for item in selection.evaluations
            if item.brier_score == selection.evaluations[0].brier_score
        )
        if len(tied) > 1:
            self.assertEqual(selection.selected_method, "identity")

    def test_platt_selected_when_validation_mapping_is_reversed(self):
        training = (
            obs(1, "0.1", 1), obs(2, "0.2", 1),
            obs(3, "0.8", 0), obs(4, "0.9", 0),
        )
        validation = validation_copy(training)
        selection = CalibrationMethodSelectionService().select(
            training, validation, request(target=None),
            PlattCalibrator(policy=policy()),
            IsotonicCalibrator(policy=policy()),
        )
        self.assertEqual(selection.selected_method, "platt")

    def test_isotonic_selected_for_step_process(self):
        training = (
            obs(1, "0.1", 0), obs(2, "0.2", 0),
            obs(3, "0.4", 0), obs(4, "0.6", 1),
            obs(5, "0.8", 1), obs(6, "0.9", 1),
        )
        validation = validation_copy(training)
        selection = CalibrationMethodSelectionService().select(
            training, validation, request(target=None),
            PlattCalibrator(policy=policy(total=4)),
            IsotonicCalibrator(policy=policy(total=4)),
        )
        self.assertEqual(selection.selected_method, "isotonic")

    def test_infinite_log_loss_has_json_safe_domain_representation(self):
        selection = CalibrationMethodSelectionService().select(
            mixed(),
            (obs(30, "0", 1), obs(31, "1", 0)),
            request(target=None),
            PlattCalibrator(policy=policy()),
            IsotonicCalibrator(policy=policy()),
        )
        identity = selection.evaluations[0]
        self.assertTrue(identity.log_loss.is_positive_infinity)
        self.assertIsNone(identity.log_loss.finite_value)

    def test_malformed_and_unknown_serialization_are_rejected(self):
        serializer = CalibratorSerializer()
        with self.assertRaises(ValueError):
            serializer.deserialize({"serialization_version": "future"})
        payload = serializer.serialize(
            PlattCalibrator(policy=policy()).fit(mixed(), request())
        )
        del payload["parameters"]["a"]
        with self.assertRaises(ValueError):
            serializer.deserialize(payload)

    def test_no_network_telegram_bankroll_scheduling_or_live_changes(self):
        with (
            patch("telegram.Bot.send_message") as telegram,
            patch("app.bankroll.engine.OfficialBankrollSettlementEngine.settle") as bankroll,
        ):
            fitted = PlattCalibrator(policy=policy()).fit(mixed(), request())
            fitted.calibrate(Decimal("0.5"))
        telegram.assert_not_called()
        bankroll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
