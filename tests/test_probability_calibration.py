import unittest
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

from app.backtesting import (
    BacktestMetricsService,
    EvaluationOutcome,
    HistoricalEvaluationRecord,
    WalkForwardWindow,
)
from app.calibration import (
    CalibrationComparisonService,
    CalibrationFitMetadata,
    CalibrationFitRequest,
    CalibrationFittingNotImplemented,
    CalibrationFittingError,
    CalibrationObservation,
    CalibrationReportService,
    CalibrationResolutionRequest,
    CalibrationResolverConfig,
    CalibrationScope,
    CalibrationScopeKind,
    CalibrationScopeResolver,
    CalibrationTrainingWindow,
    CalibrationWalkForwardService,
    EqualWidthBinning,
    ExplicitBoundaryBinning,
    IdentityCalibrator,
    IsotonicCalibrator,
    PlattCalibrator,
)


NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)


def observation(
    observation_id: str = "obs-1",
    probability: str = "0.60",
    outcome: int = 1,
    timestamp: datetime = NOW,
    outcome_timestamp: datetime | None = None,
    competition: str = "Premier League",
    market: str = "Match Winner",
    odds_band: str | None = "1.80-2.19",
) -> CalibrationObservation:
    return CalibrationObservation(
        observation_id=observation_id,
        fixture_id=int("".join(filter(str.isdigit, observation_id)) or "1"),
        competition=competition,
        market=market,
        selection="Home",
        prediction_timestamp=timestamp,
        outcome_timestamp=outcome_timestamp or timestamp,
        raw_probability=Decimal(probability),
        binary_outcome=outcome,
        model_version="model-v1",
        odds_band=odds_band,
        confidence_band="HIGH",
    )


def scope(kind: CalibrationScopeKind, value: str = "") -> CalibrationScope:
    if kind is CalibrationScopeKind.GLOBAL:
        return CalibrationScope.global_scope()
    if kind is CalibrationScopeKind.IDENTITY:
        return CalibrationScope.identity_scope()
    if kind is CalibrationScopeKind.COMPETITION:
        return CalibrationScope(kind, competition=value or "Premier League")
    if kind is CalibrationScopeKind.MARKET:
        return CalibrationScope(kind, market=value or "Match Winner")
    if kind is CalibrationScopeKind.ODDS_BAND:
        return CalibrationScope(kind, odds_band=value or "1.80-2.19")
    return CalibrationScope(
        kind,
        competition="Premier League",
        market="Match Winner",
    )


def metadata(
    calibration_scope: CalibrationScope | None = None,
    count: int = 100,
    method: str = "identity",
) -> CalibrationFitMetadata:
    return CalibrationFitMetadata(
        fitted_at=NOW,
        training_window=CalibrationTrainingWindow(
            NOW - timedelta(days=30),
            NOW,
        ),
        observation_count=count,
        scope=calibration_scope or CalibrationScope.global_scope(),
        method_name=method,
        version="calibration-v1",
    )


def identity(
    calibration_scope: CalibrationScope,
    count: int = 100,
) -> IdentityCalibrator:
    return IdentityCalibrator(metadata(calibration_scope, count))


@dataclass(frozen=True, slots=True)
class ConstantCalibrator:
    metadata: CalibrationFitMetadata
    value: Decimal

    def calibrate(self, probability: Decimal) -> Decimal:
        return self.value


class CalibrationObservationTests(unittest.TestCase):
    def test_valid_binary_outcomes(self):
        self.assertEqual(observation(outcome=0).binary_outcome, 0)
        self.assertEqual(observation(outcome=1).binary_outcome, 1)

    def test_invalid_binary_outcomes_reject_void_like_values(self):
        for value in (-1, 2, None, "VOID", 1.0, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(observation(), binary_outcome=value)

    def test_invalid_probabilities(self):
        for value in ("-0.01", "1.01", "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                observation(probability=value)

    def test_probability_requires_decimal(self):
        with self.assertRaises(TypeError):
            replace(observation(), raw_probability=0.5)

    def test_probabilities_zero_and_one_are_valid(self):
        self.assertEqual(observation(probability="0").raw_probability, Decimal("0"))
        self.assertEqual(observation(probability="1").raw_probability, Decimal("1"))

    def test_outcome_timestamp_must_not_predate_prediction(self):
        with self.assertRaisesRegex(ValueError, "must not predate"):
            observation(outcome_timestamp=NOW - timedelta(seconds=1))

    def test_void_backtest_conversion_is_rejected(self):
        record = self._backtest(EvaluationOutcome.VOID, "0")

        with self.assertRaisesRegex(ValueError, "Void backtest"):
            CalibrationObservation.from_backtest_record(
                "void",
                record,
                NOW + timedelta(hours=3),
            )

    def test_decided_backtests_convert_to_binary_outcomes(self):
        won = CalibrationObservation.from_backtest_record(
            "won",
            self._backtest(EvaluationOutcome.WON, "1"),
            NOW + timedelta(hours=3),
        )
        lost = CalibrationObservation.from_backtest_record(
            "lost",
            self._backtest(EvaluationOutcome.LOST, "-1"),
            NOW + timedelta(hours=3),
        )

        self.assertEqual(won.binary_outcome, 1)
        self.assertEqual(lost.binary_outcome, 0)

    def test_scoring_matches_backtesting_brier_and_log_loss_definitions(self):
        records = (
            self._backtest(EvaluationOutcome.WON, "1"),
            replace(
                self._backtest(EvaluationOutcome.LOST, "-1"),
                fixture_id=2,
                model_probability=Decimal("0.6"),
            ),
        )
        observations = tuple(
            CalibrationObservation.from_backtest_record(
                f"obs-{index}",
                record,
                NOW + timedelta(hours=3),
            )
            for index, record in enumerate(records, start=1)
        )

        backtest = BacktestMetricsService().evaluate(records)
        calibration = CalibrationReportService().evaluate(observations)

        self.assertEqual(calibration.brier_score, backtest.brier_score)
        self.assertEqual(calibration.log_loss, backtest.log_loss)

    @staticmethod
    def _backtest(
        outcome: EvaluationOutcome,
        profit_loss: str,
    ) -> HistoricalEvaluationRecord:
        return HistoricalEvaluationRecord(
            fixture_id=1,
            competition="Premier League",
            kickoff_datetime=NOW + timedelta(hours=2),
            prediction_timestamp=NOW,
            feature_timestamp=NOW - timedelta(minutes=10),
            odds_timestamp=NOW - timedelta(minutes=5),
            market="Match Winner",
            selection="Home",
            model_probability=Decimal("0.6"),
            offered_odds=Decimal("2"),
            closing_odds=None,
            result="2-1",
            outcome=outcome,
            profit_loss=Decimal(profit_loss),
        )


class CalibrationBinningTests(unittest.TestCase):
    def test_equal_width_boundaries_include_zero_and_one(self):
        self.assertEqual(
            EqualWidthBinning(4).boundaries,
            tuple(map(Decimal, ("0", "0.25", "0.5", "0.75", "1"))),
        )

    def test_equal_width_boundary_assignment_is_right_sided(self):
        report = CalibrationReportService(EqualWidthBinning(4)).evaluate((
            observation("obs-1", "0", 0),
            observation("obs-2", "0.249", 0),
            observation("obs-3", "0.25", 0),
            observation("obs-4", "0.5", 1),
            observation("obs-5", "0.75", 1),
            observation("obs-6", "1", 1),
        ))

        self.assertEqual(tuple(item.observation_count for item in report.bins), (2, 1, 1, 2))

    def test_explicit_boundary_assignment(self):
        binning = ExplicitBoundaryBinning((
            Decimal("0"),
            Decimal("0.2"),
            Decimal("0.8"),
            Decimal("1"),
        ))
        report = CalibrationReportService(binning).evaluate((
            observation("obs-1", "0.2", 0),
            observation("obs-2", "0.8", 1),
            observation("obs-3", "1", 1),
        ))

        self.assertEqual(tuple(item.observation_count for item in report.bins), (0, 1, 2))

    def test_invalid_explicit_boundaries(self):
        invalid = (
            (Decimal("0.1"), Decimal("1")),
            (Decimal("0"), Decimal("0.8")),
            (Decimal("0"), Decimal("0.7"), Decimal("0.6"), Decimal("1")),
            (Decimal("0"), Decimal("0.5"), Decimal("0.5"), Decimal("1")),
            (Decimal("0"), Decimal("NaN"), Decimal("1")),
        )
        for boundaries in invalid:
            with self.subTest(boundaries=boundaries), self.assertRaises(ValueError):
                ExplicitBoundaryBinning(boundaries)

    def test_boundary_types_must_be_decimal(self):
        with self.assertRaises(TypeError):
            ExplicitBoundaryBinning((Decimal("0"), 0.5, Decimal("1")))

    def test_invalid_equal_width_bin_count(self):
        for count in (0, -1, 2.5, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                EqualWidthBinning(count)

    def test_empty_bins_are_retained_with_none_statistics(self):
        report = CalibrationReportService(EqualWidthBinning(3)).evaluate((
            observation(probability="0.1", outcome=0),
        ))

        self.assertEqual(len(report.bins), 3)
        self.assertEqual(report.bins[1].observation_count, 0)
        self.assertIsNone(report.bins[1].mean_predicted_probability)
        self.assertIsNone(report.bins[1].observed_success_rate)
        self.assertIsNone(report.bins[1].calibration_gap)


class CalibrationReportTests(unittest.TestCase):
    def test_empty_observations(self):
        report = CalibrationReportService(EqualWidthBinning(2)).evaluate(())

        self.assertEqual(report.total_observations, 0)
        self.assertEqual(report.mean_predicted_probability, Decimal("0"))
        self.assertEqual(report.observed_success_rate, Decimal("0"))
        self.assertEqual(report.brier_score, Decimal("0"))
        self.assertEqual(report.log_loss, Decimal("0"))
        self.assertEqual(report.expected_calibration_error, Decimal("0"))
        self.assertEqual(report.maximum_calibration_error, Decimal("0"))
        self.assertEqual(len(report.bins), 2)

    def test_one_observation(self):
        report = CalibrationReportService(EqualWidthBinning(2)).evaluate((
            observation(probability="0.8", outcome=1),
        ))

        self.assertEqual(report.total_observations, 1)
        self.assertEqual(report.mean_predicted_probability, Decimal("0.8"))
        self.assertEqual(report.observed_success_rate, Decimal("1"))
        self.assertEqual(report.brier_score, Decimal("0.04"))
        self.assertEqual(report.expected_calibration_error, Decimal("0.2"))
        self.assertEqual(report.maximum_calibration_error, Decimal("0.2"))

    def test_correct_probabilities_zero_and_one_have_zero_scores(self):
        report = CalibrationReportService().evaluate((
            observation("obs-1", "0", 0),
            observation("obs-2", "1", 1),
        ))

        self.assertEqual(report.brier_score, Decimal("0"))
        self.assertEqual(report.log_loss, Decimal("0"))

    def test_impossible_exact_probability_has_infinite_log_loss(self):
        report = CalibrationReportService().evaluate((
            observation(probability="0", outcome=1),
        ))

        self.assertEqual(report.log_loss, Decimal("Infinity"))

    def test_probabilities_near_zero_and_one_are_finite(self):
        report = CalibrationReportService().evaluate((
            observation("obs-1", "0.000000001", 0),
            observation("obs-2", "0.999999999", 1),
        ))

        self.assertTrue(report.log_loss.is_finite())
        self.assertEqual(report.brier_score, Decimal("0.000000000000000001"))

    def test_ece_and_maximum_calibration_error(self):
        service = CalibrationReportService(ExplicitBoundaryBinning((
            Decimal("0"), Decimal("0.5"), Decimal("1"),
        )))
        report = service.evaluate((
            observation("obs-1", "0.2", 0),
            observation("obs-2", "0.4", 1),
            observation("obs-3", "0.9", 1),
        ))

        self.assertEqual(report.bins[0].calibration_gap, Decimal("0.2"))
        self.assertEqual(report.bins[1].calibration_gap, Decimal("0.1"))
        self.assertEqual(
            report.expected_calibration_error,
            Decimal("0.16666666666666666666666666666666666666666666666667"),
        )
        self.assertEqual(report.maximum_calibration_error, Decimal("0.2"))

    def test_report_is_deterministic_across_order_and_decimal_context(self):
        values = (
            observation("obs-1", "0.333333", 0),
            observation("obs-2", "0.777777", 1),
        )
        service = CalibrationReportService(EqualWidthBinning(7))
        expected = service.evaluate(values)

        with localcontext() as context:
            context.prec = 6
            actual = service.evaluate(tuple(reversed(values)))

        self.assertEqual(actual, expected)

    def test_duplicate_observation_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "IDs must be unique"):
            CalibrationReportService().evaluate((observation(), observation()))


class CalibratorContractTests(unittest.TestCase):
    def test_identity_calibrator(self):
        calibrator = identity(CalibrationScope.global_scope())

        for value in (Decimal("0"), Decimal("0.42"), Decimal("1")):
            self.assertEqual(calibrator.calibrate(value), value)

    def test_identity_fit_exposes_immutable_metadata(self):
        training = (observation(timestamp=NOW - timedelta(days=1)),)
        request = CalibrationFitRequest(
            fitted_at=NOW,
            training_window=CalibrationTrainingWindow(
                NOW - timedelta(days=2),
                NOW - timedelta(hours=1),
            ),
            scope=CalibrationScope.global_scope(),
            version="identity-v2",
            target_prediction_timestamp=NOW + timedelta(hours=1),
            model_version="model-v1",
        )
        fitted = IdentityCalibrator.fit(training, request)

        self.assertEqual(fitted.metadata.observation_count, 1)
        self.assertEqual(fitted.metadata.method_name, "identity")
        self.assertEqual(fitted.metadata.scope, CalibrationScope.global_scope())
        self.assertEqual(fitted.metadata.model_version, "model-v1")
        with self.assertRaises(FrozenInstanceError):
            fitted.metadata.observation_count = 2

    def test_fit_rejects_future_observation(self):
        request = CalibrationFitRequest(
            fitted_at=NOW,
            training_window=CalibrationTrainingWindow(
                NOW - timedelta(days=2),
                NOW - timedelta(days=1),
            ),
            scope=CalibrationScope.global_scope(),
            version="identity-v1",
            target_prediction_timestamp=NOW,
        )

        with self.assertRaisesRegex(ValueError, "outside its training window"):
            IdentityCalibrator.fit((observation(timestamp=NOW),), request)

    def test_fit_rejects_outcome_unavailable_at_cutoff(self):
        request = CalibrationFitRequest(
            fitted_at=NOW,
            training_window=CalibrationTrainingWindow(
                NOW - timedelta(days=3),
                NOW - timedelta(days=1),
            ),
            scope=CalibrationScope.global_scope(),
            version="identity-v1",
            target_prediction_timestamp=NOW,
        )
        unavailable = observation(
            timestamp=NOW - timedelta(days=2),
            outcome_timestamp=NOW,
        )

        with self.assertRaisesRegex(ValueError, "unavailable at the cutoff"):
            IdentityCalibrator.fit((unavailable,), request)

    def test_fit_request_rejects_non_strict_target_cutoff(self):
        with self.assertRaisesRegex(ValueError, "strictly earlier"):
            CalibrationFitRequest(
                fitted_at=NOW,
                training_window=CalibrationTrainingWindow(
                    NOW - timedelta(days=1), NOW,
                ),
                scope=CalibrationScope.global_scope(),
                version="identity-v1",
                target_prediction_timestamp=NOW,
            )

    def test_fit_rejects_scope_mismatch(self):
        request = CalibrationFitRequest(
            fitted_at=NOW,
            training_window=CalibrationTrainingWindow(
                NOW - timedelta(days=2), NOW,
            ),
            scope=scope(CalibrationScopeKind.COMPETITION, "La Liga"),
            version="identity-v1",
        )

        with self.assertRaisesRegex(ValueError, "does not match"):
            IdentityCalibrator.fit((observation(),), request)

    def test_fit_rejects_model_version_mismatch(self):
        request = CalibrationFitRequest(
            fitted_at=NOW,
            training_window=CalibrationTrainingWindow(
                NOW - timedelta(days=1), NOW,
            ),
            scope=CalibrationScope.global_scope(),
            version="identity-v1",
            model_version="model-v2",
        )

        with self.assertRaisesRegex(ValueError, "model version"):
            IdentityCalibrator.fit((observation(),), request)

    def test_platt_and_isotonic_reject_unsupported_small_sample(self):
        request = CalibrationFitRequest(
            fitted_at=NOW,
            training_window=CalibrationTrainingWindow(NOW, NOW),
            scope=CalibrationScope.global_scope(),
            version="foundation-v1",
        )
        values = (observation(),)

        for calibrator in (PlattCalibrator(), IsotonicCalibrator()):
            with self.subTest(method=calibrator.method_name), self.assertRaises(
                CalibrationFittingError
            ):
                calibrator.fit(values, request)


class CalibrationScopeResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = CalibrationResolutionRequest(
            competition="Premier League",
            market="Match Winner",
            odds_band="1.80-2.19",
        )
        self.identity = IdentityCalibrator.fallback(NOW)

    def test_scope_fallback_order(self):
        ordered_scopes = (
            scope(CalibrationScopeKind.COMPETITION_MARKET),
            scope(CalibrationScopeKind.MARKET),
            scope(CalibrationScopeKind.COMPETITION),
            scope(CalibrationScopeKind.ODDS_BAND),
            scope(CalibrationScopeKind.GLOBAL),
        )
        for expected_index in range(len(ordered_scopes)):
            with self.subTest(expected=ordered_scopes[expected_index]):
                resolver = CalibrationScopeResolver(
                    tuple(identity(item) for item in ordered_scopes[expected_index:]),
                    self.identity,
                )
                result = resolver.resolve(self.request)
                self.assertEqual(result.scope_used, ordered_scopes[expected_index])

    def test_insufficient_segment_falls_back(self):
        specific = identity(scope(CalibrationScopeKind.COMPETITION_MARKET), 9)
        market = identity(scope(CalibrationScopeKind.MARKET), 10)
        resolver = CalibrationScopeResolver(
            (specific, market),
            self.identity,
            CalibrationResolverConfig(minimum_observations=10),
        )

        result = resolver.resolve(self.request)

        self.assertEqual(result.scope_used.kind, CalibrationScopeKind.MARKET)
        self.assertTrue(result.used_fallback)

    def test_scope_specific_minimum_override(self):
        specific = identity(scope(CalibrationScopeKind.COMPETITION_MARKET), 20)
        resolver = CalibrationScopeResolver(
            (specific,),
            self.identity,
            CalibrationResolverConfig(
                minimum_observations=10,
                scope_overrides=((CalibrationScopeKind.COMPETITION_MARKET, 25),),
            ),
        )

        self.assertEqual(
            resolver.resolve(self.request).scope_used.kind,
            CalibrationScopeKind.IDENTITY,
        )

    def test_unsupported_segments_use_identity(self):
        resolver = CalibrationScopeResolver((), self.identity)

        result = resolver.resolve(self.request)

        self.assertEqual(result.scope_used.kind, CalibrationScopeKind.IDENTITY)
        self.assertIs(result.calibrator, self.identity)


class CalibrationComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        reports = CalibrationReportService(EqualWidthBinning(2))
        self.service = CalibrationComparisonService(reports)
        self.values = (
            observation("obs-1", "0.9", 0),
            observation("obs-2", "0.1", 1),
        )

    def test_identity_comparison_does_not_claim_improvement(self):
        calibration_scope = CalibrationScope.global_scope()
        result = self.service.compare(
            self.values,
            identity(calibration_scope),
            calibration_scope,
        )

        self.assertEqual(result.brier_improvement, Decimal("0"))
        self.assertEqual(result.log_loss_improvement, Decimal("0"))
        self.assertFalse(result.brier_improved)
        self.assertFalse(result.log_loss_improved)

    def test_raw_versus_calibrated_metrics(self):
        calibration_scope = CalibrationScope.global_scope()
        calibrator = ConstantCalibrator(
            metadata(calibration_scope, method="constant-test"),
            Decimal("0.5"),
        )

        result = self.service.compare(self.values, calibrator, calibration_scope)

        self.assertEqual(result.raw_brier_score, Decimal("0.81"))
        self.assertEqual(result.calibrated_brier_score, Decimal("0.25"))
        self.assertEqual(result.brier_improvement, Decimal("0.56"))
        self.assertTrue(result.brier_improved)
        self.assertTrue(result.log_loss_improved)
        self.assertEqual(result.calibration_method, "constant-test")
        self.assertEqual(result.scope_used, calibration_scope)
        self.assertEqual(result.observation_count, 2)

    def test_worse_calibration_is_not_claimed_as_better(self):
        calibration_scope = CalibrationScope.global_scope()
        values = (
            observation("obs-1", "0.8", 1),
            observation("obs-2", "0.2", 0),
        )
        calibrator = ConstantCalibrator(
            metadata(calibration_scope, method="constant-test"),
            Decimal("0.5"),
        )

        result = self.service.compare(values, calibrator, calibration_scope)

        self.assertLess(result.brier_improvement, 0)
        self.assertLess(result.log_loss_improvement, 0)
        self.assertFalse(result.brier_improved)
        self.assertFalse(result.log_loss_improved)


class CalibrationWalkForwardTests(unittest.TestCase):
    def setUp(self) -> None:
        reports = CalibrationReportService(EqualWidthBinning(2))
        self.service = CalibrationWalkForwardService(
            CalibrationComparisonService(reports)
        )
        self.window = WalkForwardWindow(
            training_start=NOW - timedelta(days=3),
            training_end=NOW - timedelta(days=1),
            evaluation_start=NOW - timedelta(days=1),
            evaluation_end=NOW + timedelta(days=2),
        )

    def test_training_is_earlier_and_target_is_isolated(self):
        values = (
            observation("target-2", timestamp=NOW + timedelta(hours=1)),
            observation("train-1", timestamp=NOW - timedelta(days=2)),
            observation(
                "unsettled-1",
                timestamp=NOW - timedelta(days=2),
                outcome_timestamp=NOW,
            ),
            observation("cutoff-1", timestamp=NOW - timedelta(days=1)),
            observation("target-1", timestamp=NOW),
        )

        folds = self.service.evaluate(
            values,
            (self.window,),
            IdentityCalibrator,
            CalibrationScope.global_scope(),
            "walk-v1",
        )

        fold = folds[0]
        self.assertEqual(fold.training_observation_ids, ("train-1", "cutoff-1"))
        self.assertEqual(fold.target_observation_ids, ("target-1", "target-2"))
        self.assertTrue(
            set(fold.training_observation_ids).isdisjoint(fold.target_observation_ids)
        )
        self.assertEqual(fold.fit_metadata.observation_count, 2)

    def test_duplicate_target_timestamps_use_observation_id_order(self):
        values = (
            observation("target-2", timestamp=NOW),
            observation("target-1", timestamp=NOW),
            observation("train-1", timestamp=NOW - timedelta(days=2)),
        )

        fold = self.service.evaluate(
            values,
            (self.window,),
            IdentityCalibrator,
            CalibrationScope.global_scope(),
            "walk-v1",
        )[0]

        self.assertEqual(fold.target_observation_ids, ("target-1", "target-2"))

    def test_windows_are_evaluated_in_deterministic_order(self):
        later = WalkForwardWindow(
            training_start=NOW - timedelta(days=2),
            training_end=NOW + timedelta(days=1),
            evaluation_start=NOW + timedelta(days=2),
            evaluation_end=NOW + timedelta(days=3),
        )

        folds = self.service.evaluate(
            (),
            (later, self.window),
            IdentityCalibrator,
            CalibrationScope.global_scope(),
            "walk-v1",
        )

        self.assertEqual(tuple(item.window for item in folds), (self.window, later))

    def test_overlapping_evaluation_windows_are_rejected(self):
        overlapping = WalkForwardWindow(
            training_start=NOW - timedelta(days=4),
            training_end=NOW - timedelta(days=2),
            evaluation_start=NOW,
            evaluation_end=NOW + timedelta(days=3),
        )

        with self.assertRaisesRegex(ValueError, "must not overlap"):
            self.service.evaluate(
                (),
                (self.window, overlapping),
                IdentityCalibrator,
                CalibrationScope.global_scope(),
                "walk-v1",
            )


if __name__ == "__main__":
    unittest.main()
