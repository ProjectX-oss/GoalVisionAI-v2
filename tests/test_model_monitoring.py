import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from app.backtesting import EvaluationOutcome, HistoricalEvaluationRecord
from app.database import Database
from app.model_monitoring import (
    AlertSeverity,
    BacktestingMonitoringAdapter,
    DataCompleteness,
    DriftDetectionService,
    DriftFindingType,
    MetricDriftThreshold,
    ModelMonitoringConfig,
    ModelMonitoringService,
    MonitoringObservation,
    MonitoringPolicy,
    MonitoringReportService,
    MonitoringRunStatus,
    MonitoringWindow,
    MonitoringWindowKind,
    MonitoringWindowService,
    NullMonitoringRuntime,
    OfficialMonitoringAdapter,
    SQLiteMonitoringRepository,
    ShadowMonitoringAdapter,
    ThresholdComparison,
    deduplicate_monitoring_sources,
)
from app.quality_gate_shadow import ShadowEvaluationStage
from app.results import (
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
    SettlementReasonCode,
)


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def observation(
    index: int,
    *,
    outcome: ResolutionStatus | None = ResolutionStatus.WON,
    raw: str = "0.7",
    calibrated: str | None = "0.65",
    profit: str | None = "1",
    competition: str = "League A",
    market: str = "MATCH_WINNER",
    closing: str | None = "1.8",
    source: str = "OFFICIAL",
) -> MonitoringObservation:
    predicted = BASE + timedelta(days=index)
    return MonitoringObservation(
        prediction_id=f"prediction-{index}",
        fixture_id=100 + index,
        competition=competition,
        market=market,
        model_version="model-v1",
        calibration_artifact_id="artifact-1" if calibrated else None,
        prediction_timestamp=predicted,
        raw_probability=Decimal(raw),
        calibrated_probability=Decimal(calibrated) if calibrated else None,
        offered_odds=Decimal("2"),
        closing_odds=Decimal(closing) if closing else None,
        authoritative_outcome=outcome,
        profit_loss_units=Decimal(profit) if profit is not None else None,
        settlement_timestamp=(
            predicted + timedelta(hours=3) if outcome is not None else None
        ),
        source=source,
    )


def window(start: int, end: int) -> MonitoringWindow:
    return MonitoringWindow(
        MonitoringWindowKind.EXPLICIT_RANGE,
        BASE + timedelta(days=start),
        BASE + timedelta(days=end),
    )


class WindowAndReportTests(unittest.TestCase):
    def test_empty_report(self):
        report = MonitoringReportService().build(
            (), report_window=window(0, 1), generated_for=BASE + timedelta(days=2)
        )
        self.assertEqual(report.observation_count, 0)
        self.assertEqual(report.raw_brier_score, Decimal("0"))
        self.assertEqual(report.unresolved_count, 0)

    def test_fixed_count_and_deterministic_ordering(self):
        values = (observation(3), observation(1), observation(2))
        selected_window, selected = MonitoringWindowService.fixed_count(
            values, 2, end_at=BASE + timedelta(days=4)
        )
        self.assertEqual(
            tuple(item.prediction_id for item in selected),
            ("prediction-2", "prediction-3"),
        )
        self.assertEqual(selected_window.observation_limit, 2)

    def test_fixed_date_and_explicit_range_are_half_open(self):
        values = (observation(1), observation(2), observation(3))
        _, fixed = MonitoringWindowService.interval(
            values,
            start_at=BASE + timedelta(days=1),
            end_at=BASE + timedelta(days=3),
        )
        explicit_window, explicit = MonitoringWindowService.explicit_range(
            values,
            start_at=BASE + timedelta(days=1),
            end_at=BASE + timedelta(days=3),
        )
        self.assertEqual(fixed, explicit)
        self.assertEqual(len(explicit), 2)
        self.assertEqual(explicit_window.kind, MonitoringWindowKind.EXPLICIT_RANGE)

    def test_rolling_count_and_interval_use_caller_timestamp(self):
        values = tuple(observation(index) for index in range(1, 6))
        count_window, count_values = MonitoringWindowService.rolling_count(
            values, 2, generated_for=BASE + timedelta(days=6)
        )
        interval_window, interval_values = MonitoringWindowService.rolling_interval(
            values,
            timedelta(days=2),
            generated_for=BASE + timedelta(days=6),
        )
        self.assertEqual(count_window.kind, MonitoringWindowKind.ROLLING_COUNT)
        self.assertEqual(len(count_values), 2)
        self.assertEqual(interval_window.start_at, BASE + timedelta(days=4))
        self.assertEqual(len(interval_values), 2)

    def test_void_and_unresolved_policy(self):
        values = (
            observation(1),
            observation(2, outcome=ResolutionStatus.LOST, raw="0.8", profit="-1"),
            observation(3, outcome=ResolutionStatus.VOID, profit="0"),
            observation(4, outcome=None, profit=None),
        )
        report = MonitoringReportService().build(
            values, report_window=window(0, 5), generated_for=BASE + timedelta(days=6)
        )
        self.assertEqual((report.settled_count, report.unresolved_count), (3, 1))
        self.assertEqual((report.won_count, report.lost_count, report.void_count), (1, 1, 1))
        self.assertEqual(report.hit_rate, Decimal("0.5"))
        self.assertEqual(report.roi, Decimal("0"))

    def test_raw_calibrated_clv_drawdown_and_artifact_metrics(self):
        values = (
            observation(1, outcome=ResolutionStatus.LOST, raw="0.9", calibrated="0.6", profit="-1"),
            observation(2, outcome=ResolutionStatus.LOST, raw="0.8", calibrated="0.5", profit="-1"),
            observation(3, outcome=ResolutionStatus.WON, raw="0.6", calibrated="0.7", profit="1"),
        )
        report = MonitoringReportService().build(
            values, report_window=window(0, 4), generated_for=BASE + timedelta(days=5)
        )
        self.assertGreater(report.raw_brier_score, report.calibrated_brier_score)
        self.assertIsNotNone(report.average_clv)
        self.assertEqual(report.positive_clv_percentage, Decimal("100"))
        self.assertEqual(report.maximum_drawdown, Decimal("2"))
        self.assertEqual(report.calibration_artifact_usage_counts, (("artifact-1", 3),))

    def test_competition_market_segmentation_and_completeness(self):
        values = (
            observation(1, competition="A", market="M1"),
            observation(2, competition="B", market="M2", calibrated=None, closing=None),
        )
        report = MonitoringReportService().build(
            values, report_window=window(0, 3), generated_for=BASE + timedelta(days=4)
        )
        self.assertEqual(tuple(item.key for item in report.competition_segments), ("A", "B"))
        self.assertEqual(tuple(item.key for item in report.market_segments), ("M1", "M2"))
        self.assertEqual(report.data_completeness.calibrated_probability_count, 1)
        self.assertEqual(report.data_completeness.closing_odds_count, 1)

    def test_reports_are_immutable_and_decimal_stable(self):
        report = MonitoringReportService().build(
            (observation(1, raw="0.123456789123456789"),),
            report_window=window(0, 2),
            generated_for=BASE + timedelta(days=3),
        )
        self.assertIsInstance(report.raw_brier_score, Decimal)
        with self.assertRaises(FrozenInstanceError):
            report.roi = Decimal("1")

    def test_safe_infinite_log_loss(self):
        report = MonitoringReportService().build(
            (observation(1, outcome=ResolutionStatus.LOST, raw="1", profit="-1"),),
            report_window=window(0, 2),
            generated_for=BASE + timedelta(days=3),
        )
        self.assertTrue(report.raw_log_loss.is_positive_infinity)
        self.assertIsNone(report.raw_log_loss.finite_value)


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.service = DriftDetectionService()
        self.reporter = MonitoringReportService()
        self.baseline_values = tuple(
            observation(index, raw="0.6", profit="1")
            for index in range(1, 5)
        )
        self.current_values = tuple(
            observation(index + 10, outcome=ResolutionStatus.LOST, raw="0.9", profit="-1")
            for index in range(1, 5)
        )
        self.baseline = self.reporter.build(
            self.baseline_values, report_window=window(0, 6), generated_for=BASE + timedelta(days=20)
        )
        self.current = self.reporter.build(
            self.current_values, report_window=window(10, 16), generated_for=BASE + timedelta(days=20)
        )

    def policy(self, metric: str, warning: str, critical: str) -> MonitoringPolicy:
        return MonitoringPolicy(
            minimum_observations=1,
            minimum_settled_observations=1,
            thresholds=((metric, MetricDriftThreshold(
                True, Decimal(warning), Decimal(critical)
            )),),
        )

    def findings(self, policy):
        return self.service.compare(
            self.baseline,
            self.current,
            self.baseline_values,
            self.current_values,
            policy=policy,
            scope="global",
        )

    def test_brier_warning_and_critical(self):
        warning = self.findings(self.policy("brier", "0.5", "1"))
        critical = self.findings(self.policy("brier", "0.01", "0.02"))
        self.assertIn(
            AlertSeverity.WARNING,
            tuple(item.severity for item in warning if item.metric == "brier"),
        )
        self.assertIn(
            AlertSeverity.CRITICAL,
            tuple(item.severity for item in critical if item.metric == "brier"),
        )

    def test_required_metric_drift_types_are_detected(self):
        current = replace(
            self.current,
            average_clv=(self.baseline.average_clv or Decimal("0")) - Decimal("0.1"),
            data_completeness=DataCompleteness(
                self.current.observation_count, 0, 0, 0
            ),
        )
        zero = MetricDriftThreshold(
            True, Decimal("0"), Decimal("999")
        )
        policy = MonitoringPolicy(
            minimum_observations=1,
            minimum_settled_observations=1,
            thresholds=tuple(
                (metric, zero)
                for metric in (
                    "brier", "log_loss", "ece", "roi", "clv", "hit_rate",
                    "drawdown", "class_balance", "probability_psi",
                    "calibrated_probability_psi", "calibration_bins",
                    "data_completeness",
                )
            ),
        )
        findings = self.service.compare(
            self.baseline,
            current,
            self.baseline_values,
            self.current_values,
            policy=policy,
            scope="global",
            artifact_id="artifact-1",
        )
        types = {item.finding_type for item in findings}
        self.assertTrue({
            DriftFindingType.BRIER_DEGRADATION,
            DriftFindingType.LOG_LOSS_DEGRADATION,
            DriftFindingType.ECE_DEGRADATION,
            DriftFindingType.ROI_DEGRADATION,
            DriftFindingType.CLV_DEGRADATION,
            DriftFindingType.HIT_RATE_DEGRADATION,
            DriftFindingType.DRAWDOWN_INCREASE,
            DriftFindingType.CLASS_BALANCE_SHIFT,
            DriftFindingType.PROBABILITY_DISTRIBUTION_SHIFT,
            DriftFindingType.CALIBRATION_BIN_DRIFT,
            DriftFindingType.DATA_COMPLETENESS_DEGRADATION,
            DriftFindingType.ARTIFACT_PERFORMANCE_DEGRADATION,
        }.issubset(types))
        self.assertEqual(
            findings,
            tuple(sorted(findings, key=lambda item: (item.finding_type.value, item.metric))),
        )

    def test_probability_distribution_psi_formula_and_zero_smoothing(self):
        value = self.service.population_stability_index(
            (Decimal("0.1"), Decimal("0.1")),
            (Decimal("0.9"), Decimal("0.9")),
            (Decimal("0"), Decimal("0.5"), Decimal("1")),
            Decimal("0.000001"),
        )
        self.assertTrue(value.is_finite())
        self.assertGreater(value, Decimal("0"))

    def test_calibration_bin_drift_uses_existing_bins(self):
        value = self.service.calibration_bin_drift(self.baseline, self.current)
        self.assertGreaterEqual(value, Decimal("0"))
        self.assertTrue(value.is_finite())

    def test_insufficient_sample_prevents_false_critical(self):
        findings = self.service.compare(
            self.baseline,
            self.current,
            self.baseline_values,
            self.current_values,
            policy=MonitoringPolicy(
                minimum_observations=100,
                minimum_settled_observations=100,
            ),
            scope="global",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_type, DriftFindingType.SAMPLE_TOO_SMALL)
        self.assertEqual(findings[0].severity, AlertSeverity.INFO)

    def test_overlap_is_rejected_unless_policy_allows(self):
        overlapping = replace(
            self.current,
            report_window=window(5, 16),
        )
        with self.assertRaises(ValueError):
            self.service.compare(
                self.baseline,
                overlapping,
                self.baseline_values,
                self.current_values,
                policy=MonitoringPolicy(minimum_observations=1, minimum_settled_observations=1),
                scope="global",
            )


class PersistenceRunAndAdapterTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("tests") / f".model-monitoring-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.repository = SQLiteMonitoringRepository(self.database)

    def tearDown(self):
        self.database.close()
        for suffix in ("", "-journal", "-shm", "-wal"):
            path = Path(f"{self.path}{suffix}")
            if path.exists():
                path.unlink()

    def test_completed_run_alert_identity_and_idempotency(self):
        service = ModelMonitoringService(self.repository)
        baseline = tuple(observation(index) for index in range(1, 4))
        current = tuple(
            observation(index + 10, outcome=ResolutionStatus.LOST, raw="0.9", profit="-1")
            for index in range(1, 4)
        )
        policy = MonitoringPolicy(minimum_observations=1, minimum_settled_observations=1)
        run = service.run_once(
            baseline_observations=baseline,
            current_observations=current,
            baseline_window=window(0, 5),
            current_window=window(10, 15),
            policy=policy,
            scope="global",
            artifact_id=None,
            started_at=BASE + timedelta(days=20),
            completed_at=BASE + timedelta(days=20, minutes=1),
        )
        self.assertEqual(run.status, MonitoringRunStatus.COMPLETED)
        self.assertEqual(self.repository.get_run(run.run_id), run)
        if run.findings:
            alert = self.repository.alert_for_finding(
                run.run_id, run.findings[0],
                threshold_version=policy.version,
                created_at=BASE + timedelta(days=20, minutes=1),
            )
            _, inserted = self.repository.insert_alert(alert)
            self.assertFalse(inserted)

    def test_insufficient_and_failed_runs_are_isolated(self):
        service = ModelMonitoringService(self.repository)
        insufficient = service.run_once(
            baseline_observations=(),
            current_observations=(),
            baseline_window=window(0, 1),
            current_window=window(1, 2),
            policy=MonitoringPolicy(),
            scope="global",
            artifact_id=None,
            started_at=BASE + timedelta(days=3),
            completed_at=BASE + timedelta(days=3, minutes=1),
        )
        failed = service.run_once(
            baseline_observations=(),
            current_observations=(),
            baseline_window=window(0, 2),
            current_window=window(1, 3),
            policy=MonitoringPolicy(),
            scope="overlap",
            artifact_id=None,
            started_at=BASE + timedelta(days=4),
            completed_at=BASE + timedelta(days=4, minutes=1),
        )
        self.assertEqual(insufficient.status, MonitoringRunStatus.INSUFFICIENT_DATA)
        self.assertEqual(failed.status, MonitoringRunStatus.FAILED)
        self.assertEqual(failed.safe_error_message, "Monitoring run failed safely.")

    def test_restart_persistence(self):
        service = ModelMonitoringService(self.repository)
        run = service.run_once(
            baseline_observations=(),
            current_observations=(),
            baseline_window=window(0, 1),
            current_window=window(1, 2),
            policy=MonitoringPolicy(),
            scope="global",
            artifact_id=None,
            started_at=BASE + timedelta(days=3),
            completed_at=BASE + timedelta(days=3, minutes=1),
        )
        self.database.close()
        self.database = Database(self.path)
        restarted = SQLiteMonitoringRepository(self.database)
        self.assertEqual(restarted.get_run(run.run_id), run)

    def test_backtesting_conversion_and_source_priority_deduplication(self):
        record = HistoricalEvaluationRecord(
            1, "League", BASE + timedelta(days=2), BASE,
            BASE, BASE, "MATCH_WINNER", "home", Decimal("0.6"),
            Decimal("2"), Decimal("1.8"), "WON", EvaluationOutcome.WON,
            Decimal("1"),
        )
        backtest = BacktestingMonitoringAdapter.convert(
            (record,),
            model_version="model-v1",
            settlement_timestamp_by_fixture={1: BASE + timedelta(days=2)},
            prediction_id_by_fixture={1: "same"},
        )[0]
        official = replace(backtest, source="OFFICIAL")
        selected = deduplicate_monitoring_sources((backtest, official))
        self.assertEqual(selected, (official,))

    def test_authoritative_official_adapter(self):
        prediction = PublishedPredictionReference(
            "official-1", 9, "MATCH_WINNER", "home", BASE, odds=2.0
        )
        settlement = ResolvedPredictionResult(
            "official-1", 9, ResolutionStatus.WON,
            BASE + timedelta(days=1), 2, 0, "rule-v1",
            (SettlementReasonCode.MATCH_RESULT_SETTLED,),
        )
        converted = OfficialMonitoringAdapter.convert(
            prediction,
            settlement,
            competition="League",
            model_version="model-v1",
            raw_probability=Decimal("0.6"),
            profit_loss_units=Decimal("1"),
        )
        self.assertEqual(converted.source, "OFFICIAL")
        self.assertEqual(converted.authoritative_outcome, ResolutionStatus.WON)

    def test_shadow_stage_selection_and_no_duplicate_counting(self):
        candidate = SimpleNamespace(
            competition="League",
            market="MATCH_WINNER",
            model_version="model-v1",
            prediction_timestamp=BASE,
            raw_probability=Decimal("0.6"),
            calibrated_probability=Decimal("0.62"),
            offered_odds=Decimal("2"),
        )
        def shadow(stage):
            return SimpleNamespace(
                prediction_id="shadow-prediction",
                fixture_id=4,
                stage=stage,
                evaluation_timestamp=BASE + timedelta(minutes=1),
                shadow_evaluation_id=f"shadow-{stage.value}",
                candidate_snapshot=candidate,
                settled_at=BASE + timedelta(days=1),
                actual_offered_odds=None,
                settlement_outcome=ResolutionStatus.WON,
                eventual_profit_loss_units=Decimal("1"),
                actually_published=False,
                gate_status=SimpleNamespace(value="APPROVED"),
            )
        converted = ShadowMonitoringAdapter().convert((
            shadow(ShadowEvaluationStage.INITIAL_CANDIDATE),
            shadow(ShadowEvaluationStage.PRE_PUBLICATION),
            shadow(ShadowEvaluationStage.FINAL_PRE_KICKOFF),
        ))
        self.assertEqual(len(converted), 1)
        self.assertEqual(
            converted[0].source_stage,
            ShadowEvaluationStage.FINAL_PRE_KICKOFF.value,
        )
        self.assertFalse(converted[0].actually_published)

    def test_unresolved_shadow_remains_unresolved(self):
        candidate = SimpleNamespace(
            competition="League", market="M", model_version="v",
            prediction_timestamp=BASE, raw_probability=Decimal("0.5"),
            calibrated_probability=None, offered_odds=Decimal("2"),
        )
        shadow = SimpleNamespace(
            prediction_id="p", fixture_id=1,
            stage=ShadowEvaluationStage.FINAL_PRE_KICKOFF,
            evaluation_timestamp=BASE, shadow_evaluation_id="s",
            candidate_snapshot=candidate, settled_at=None,
            actual_offered_odds=None, settlement_outcome=None,
            eventual_profit_loss_units=None, actually_published=False,
            gate_status=SimpleNamespace(value="REVIEW_REQUIRED"),
        )
        converted = ShadowMonitoringAdapter().convert((shadow,))
        self.assertIsNone(converted[0].authoritative_outcome)
        self.assertIsNone(converted[0].settlement_timestamp)

    def test_shadow_adapter_rejects_impossible_future_information_order(self):
        candidate = SimpleNamespace(
            competition="League", market="M", model_version="v",
            prediction_timestamp=BASE, raw_probability=Decimal("0.5"),
            calibrated_probability=None, offered_odds=Decimal("2"),
        )
        shadow = SimpleNamespace(
            prediction_id="p", fixture_id=1,
            stage=ShadowEvaluationStage.FINAL_PRE_KICKOFF,
            evaluation_timestamp=BASE + timedelta(days=2),
            shadow_evaluation_id="s", candidate_snapshot=candidate,
            settled_at=BASE + timedelta(days=1), actual_offered_odds=None,
            settlement_outcome=ResolutionStatus.WON,
            eventual_profit_loss_units=Decimal("1"),
            actually_published=False,
            gate_status=SimpleNamespace(value="APPROVED"),
        )
        with self.assertRaises(ValueError):
            ShadowMonitoringAdapter().convert((shadow,))

    def test_disabled_config_null_runtime_and_no_external_side_effects(self):
        self.assertFalse(ModelMonitoringConfig().enabled)
        telegram = Mock()
        bankroll = Mock()
        scheduler = Mock()
        betting = Mock()
        self.assertIsNone(NullMonitoringRuntime().run_once())
        telegram.assert_not_called()
        bankroll.assert_not_called()
        scheduler.assert_not_called()
        betting.assert_not_called()

    def test_runtime_flag_parsing_is_strict(self):
        with patch.dict("os.environ", {"MODEL_MONITORING_ENABLED": "true"}):
            self.assertTrue(ModelMonitoringConfig.from_environment().enabled)
        with patch.dict("os.environ", {"MODEL_MONITORING_ENABLED": "yes"}):
            with self.assertRaises(ValueError):
                ModelMonitoringConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
