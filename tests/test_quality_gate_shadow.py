import asyncio
import sqlite3
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.calibration import CalibrationScope
from app.core.application import GoalVisionApp
from app.database import Database, MigrationManager
from app.models import Match
from app.quality_gate import (
    DEFAULT_OFFICIAL_QUALITY_GATE_POLICY,
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
    InMemoryDuplicatePublicationChecker,
    PublicationCandidate,
    PublicationQualityGate,
    QualityGateContext,
    QualityGateStatus,
    RejectionReason,
    ReviewReason,
)
from app.quality_gate_shadow import (
    CURRENTLY_UNAVAILABLE_CONTEXT_FIELDS,
    DisabledQualityGateShadowObserver,
    PredictionShadowContextAdapter,
    QualityGateShadowEvaluationService,
    SQLiteShadowEvaluationRepository,
    ShadowComparisonReportService,
    ShadowEvaluationOutcome,
    ShadowEvaluationRequest,
    ShadowEvaluationStage,
    ShadowModeConfig,
    ShadowObservationFacts,
    ShadowSettlementEnrichmentService,
    ShadowSettlementFacts,
    build_quality_gate_shadow_observer,
)
from app.results import ResolutionStatus


PREDICTED_AT = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
EVALUATED_AT = PREDICTED_AT + timedelta(minutes=10)
KICKOFF_AT = PREDICTED_AT + timedelta(hours=2)
POLICY = DEFAULT_OFFICIAL_QUALITY_GATE_POLICY


def candidate(**changes) -> PublicationCandidate:
    values = {
        "prediction_id": "prediction-1",
        "fixture_id": 500,
        "competition": "Premier League",
        "kickoff_time": KICKOFF_AT,
        "prediction_timestamp": PREDICTED_AT,
        "market": "Match Winner",
        "selection": "Home",
        "raw_probability": Decimal("0.60"),
        "offered_odds": Decimal("2.00"),
        "odds_timestamp": PREDICTED_AT + timedelta(minutes=5),
        "calibrated_probability": Decimal("0.62"),
        "reference_odds": Decimal("1.95"),
        "expected_value": None,
        "model_version": "model-v1",
        "calibration_scope": CalibrationScope.global_scope(),
        "calibration_method": "platt",
        "calibration_sample_size": 200,
        "calibration_fit_timestamp": PREDICTED_AT - timedelta(minutes=20),
        "calibration_training_cutoff": PREDICTED_AT - timedelta(hours=1),
        "confidence_score": Decimal("0.80"),
        "uncertainty_score": Decimal("0.10"),
        "product_scope": "OFFICIAL",
    }
    values.update(changes)
    return PublicationCandidate(**values)


def evidence() -> tuple[EvidenceAssessment, ...]:
    return tuple(
        EvidenceAssessment(category=item, status=EvidenceStatus.AVAILABLE)
        for item in EvidenceCategory
    )


def context(**changes) -> QualityGateContext:
    values = {
        "evaluation_timestamp": EVALUATED_AT,
        "data_completeness_status": EvidenceStatus.AVAILABLE,
        "data_freshness_status": EvidenceStatus.AVAILABLE,
        "lineup_status": EvidenceStatus.AVAILABLE,
        "injury_data_status": EvidenceStatus.AVAILABLE,
        "market_consensus_probability": Decimal("0.58"),
        "market_disagreement": None,
        "current_exposure": Decimal("0.1"),
        "daily_exposure": Decimal("1"),
        "competition_exposure": Decimal("1"),
        "correlated_exposure": Decimal("0.5"),
        "sample_size": 200,
        "calibration_sample_size": 200,
        "evidence": evidence(),
    }
    values.update(changes)
    return QualityGateContext(**values)


def request(
    *,
    stage: ShadowEvaluationStage = ShadowEvaluationStage.INITIAL_CANDIDATE,
    value: PublicationCandidate | None = None,
    gate_context: QualityGateContext | None = None,
    published: bool = False,
    evaluation_id: str | None = None,
) -> ShadowEvaluationRequest:
    selected = value or candidate()
    return ShadowEvaluationRequest(
        shadow_evaluation_id=evaluation_id or f"shadow-{selected.prediction_id}-{stage.value}",
        stage=stage,
        candidate=selected,
        context=gate_context or context(),
        policy_version=POLICY.version,
        actually_published=published,
        actual_publication_timestamp=(EVALUATED_AT if published else None),
        actual_offered_odds=(selected.offered_odds if published else None),
        created_at=EVALUATED_AT,
    )


def gate() -> PublicationQualityGate:
    return PublicationQualityGate(
        policy=POLICY,
        duplicates=InMemoryDuplicatePublicationChecker(),
    )


class ShadowDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path("tests") / f".shadow-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.repository = SQLiteShadowEvaluationRepository(self.database)
        self.service = QualityGateShadowEvaluationService(gate(), self.repository)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        try:
            self.database.close()
        except sqlite3.ProgrammingError:
            pass
        for suffix in ("", "-journal", "-shm", "-wal"):
            path = Path(f"{self.path}{suffix}")
            if path.exists():
                path.unlink()


class ShadowEvaluationPersistenceTests(ShadowDatabaseTestCase):
    def test_approved_decision_is_recorded(self):
        result = self.service.evaluate(request())

        self.assertEqual(result.outcome, ShadowEvaluationOutcome.RECORDED)
        self.assertEqual(result.record.gate_status, QualityGateStatus.APPROVED)
        self.assertEqual(len(result.record.ordered_check_results), 11)
        self.assertEqual(result.record.calculated_expected_value, Decimal("0.2400"))

    def test_review_required_decision_is_recorded(self):
        result = self.service.evaluate(request(gate_context=context(
            lineup_status=EvidenceStatus.PARTIAL,
        )))

        self.assertEqual(result.record.gate_status, QualityGateStatus.REVIEW_REQUIRED)
        self.assertIn(ReviewReason.LINEUP_UNCONFIRMED, result.record.review_reasons)

    def test_rejected_decision_is_recorded(self):
        result = self.service.evaluate(request(value=candidate(
            offered_odds=Decimal("1.50"),
        )))

        self.assertEqual(result.record.gate_status, QualityGateStatus.REJECTED)
        self.assertIn(RejectionReason.ODDS_BELOW_MINIMUM, result.record.rejection_reasons)

    def test_multiple_ordered_reasons_round_trip(self):
        value = candidate(
            offered_odds=Decimal("1.50"),
            prediction_timestamp=KICKOFF_AT,
        )
        result = self.service.evaluate(request(value=value))

        self.assertGreaterEqual(len(result.record.rejection_reasons), 2)
        stored = self.repository.get(result.record.shadow_evaluation_id)
        self.assertEqual(stored.rejection_reasons, result.record.rejection_reasons)

    def test_candidate_and_context_snapshots_are_immutable(self):
        record = self.service.evaluate(request()).record

        with self.assertRaises(FrozenInstanceError):
            record.candidate_snapshot.selection = "Away"
        with self.assertRaises(FrozenInstanceError):
            record.context_snapshot.sample_size = 1

    def test_repeated_request_is_idempotent(self):
        first = self.service.evaluate(request())
        second = self.service.evaluate(request(evaluation_id="different-id"))

        self.assertEqual(first.outcome, ShadowEvaluationOutcome.RECORDED)
        self.assertEqual(second.outcome, ShadowEvaluationOutcome.EXISTING)
        self.assertEqual(first.record, second.record)

    def test_separate_evaluation_stages_are_allowed(self):
        initial = self.service.evaluate(request())
        pre_publication = self.service.evaluate(request(
            stage=ShadowEvaluationStage.PRE_PUBLICATION,
        ))

        self.assertEqual(initial.outcome, ShadowEvaluationOutcome.RECORDED)
        self.assertEqual(pre_publication.outcome, ShadowEvaluationOutcome.RECORDED)
        self.assertEqual(len(self.repository.by_prediction("prediction-1")), 2)

    def test_database_constraint_prevents_same_stage_duplicate(self):
        record = self.service.evaluate(request()).record
        values = SQLiteShadowEvaluationRepository._record_values(replace(
            record,
            shadow_evaluation_id="other-id",
        ))

        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                """
                INSERT INTO quality_gate_shadow_evaluations (
                    shadow_evaluation_id, prediction_id, fixture_id,
                    product_scope, evaluation_stage, policy_version,
                    evaluation_timestamp, candidate_snapshot, context_snapshot,
                    gate_status, check_results, rejection_reasons,
                    review_reasons,
                    evaluated_probability, probability_source,
                    calculated_expected_value, market_disagreement,
                    actually_published, actual_publication_timestamp,
                    actual_offered_odds, settlement_outcome,
                    eventual_profit_loss_units, settled_at, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                values,
            )

    def test_all_lookup_filters_are_supported(self):
        approved = self.service.evaluate(request(published=True)).record
        self.service.evaluate(request(
            stage=ShadowEvaluationStage.PRE_PUBLICATION,
            value=candidate(offered_odds=Decimal("1.50")),
        ))

        self.assertEqual(self.repository.get(approved.shadow_evaluation_id), approved)
        self.assertEqual(len(self.repository.by_prediction("prediction-1")), 2)
        self.assertEqual(len(self.repository.by_fixture(500)), 2)
        self.assertEqual(len(self.repository.query(
            PREDICTED_AT,
            KICKOFF_AT,
            gate_status=QualityGateStatus.APPROVED,
        )), 1)
        self.assertEqual(len(self.repository.query(
            PREDICTED_AT,
            KICKOFF_AT,
            actually_published=True,
        )), 1)

    def test_database_restart_preserves_complete_snapshots(self):
        expected = self.service.evaluate(request()).record
        self.database.close()
        self.database = Database(self.path)
        restarted = SQLiteShadowEvaluationRepository(self.database)

        self.assertEqual(restarted.get(expected.shadow_evaluation_id), expected)

    def test_gate_exception_is_safely_audited(self):
        broken_gate = Mock()
        broken_gate.evaluate.side_effect = RuntimeError("token=secret")
        service = QualityGateShadowEvaluationService(broken_gate, self.repository)

        result = service.evaluate(request())

        self.assertEqual(result.outcome, ShadowEvaluationOutcome.ERROR)
        self.assertNotIn("secret", result.error.safe_message)
        errors = self.repository.query_errors(PREDICTED_AT, KICKOFF_AT, POLICY.version)
        self.assertEqual(errors, (result.error,))

    def test_gate_exception_never_propagates(self):
        broken_gate = Mock()
        broken_gate.evaluate.side_effect = Exception("boom")

        result = QualityGateShadowEvaluationService(
            broken_gate,
            self.repository,
        ).evaluate(request())

        self.assertEqual(result.outcome, ShadowEvaluationOutcome.ERROR)


class ShadowSettlementTests(ShadowDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.record = self.service.evaluate(request()).record
        self.enrichment = ShadowSettlementEnrichmentService(self.repository)

    def facts(self, outcome: ResolutionStatus) -> ShadowSettlementFacts:
        profit = {
            ResolutionStatus.WON: Decimal("1.00"),
            ResolutionStatus.LOST: Decimal("-1.00"),
            ResolutionStatus.VOID: Decimal("0"),
        }[outcome]
        return ShadowSettlementFacts(outcome, profit, KICKOFF_AT + timedelta(hours=2))

    def test_won_lost_and_void_enrichment(self):
        for index, outcome in enumerate((
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        )):
            with self.subTest(outcome=outcome):
                value = candidate(
                    prediction_id=f"prediction-{index + 2}",
                    fixture_id=501 + index,
                )
                record = self.service.evaluate(request(value=value)).record
                enriched = self.enrichment.attach(
                    record.shadow_evaluation_id,
                    self.facts(outcome),
                )
                self.assertEqual(enriched.settlement_outcome, outcome)

    def test_settlement_is_idempotent(self):
        facts = self.facts(ResolutionStatus.WON)

        first = self.enrichment.attach(self.record.shadow_evaluation_id, facts)
        second = self.enrichment.attach(self.record.shadow_evaluation_id, facts)

        self.assertEqual(first, second)

    def test_conflicting_second_settlement_is_rejected(self):
        self.enrichment.attach(
            self.record.shadow_evaluation_id,
            self.facts(ResolutionStatus.WON),
        )

        with self.assertRaises(ValueError):
            self.enrichment.attach(
                self.record.shadow_evaluation_id,
                self.facts(ResolutionStatus.LOST),
            )

    def test_settlement_does_not_change_original_decision(self):
        enriched = self.enrichment.attach(
            self.record.shadow_evaluation_id,
            self.facts(ResolutionStatus.WON),
        )

        self.assertEqual(enriched.gate_status, self.record.gate_status)
        self.assertEqual(enriched.rejection_reasons, self.record.rejection_reasons)
        self.assertEqual(enriched.candidate_snapshot, self.record.candidate_snapshot)


class ShadowReportTests(ShadowDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.reports = ShadowComparisonReportService(self.repository)
        self.enrichment = ShadowSettlementEnrichmentService(self.repository)

    def report(self, policy_version: str = POLICY.version):
        return self.reports.build(
            PREDICTED_AT,
            KICKOFF_AT,
            policy_version,
            KICKOFF_AT,
        )

    def add(
        self,
        prediction_id: str,
        status: QualityGateStatus,
        outcome: ResolutionStatus | None,
        published: bool,
        offered_odds: Decimal = Decimal("2.00"),
    ):
        value = candidate(
            prediction_id=prediction_id,
            fixture_id=500 + int(prediction_id.rsplit("-", 1)[1]),
            offered_odds=(
                Decimal("1.50")
                if status is QualityGateStatus.REJECTED
                else offered_odds
            ),
            uncertainty_score=(
                Decimal("0.20")
                if status is QualityGateStatus.REVIEW_REQUIRED
                else Decimal("0.10")
            ),
        )
        record = self.service.evaluate(request(value=value, published=published)).record
        self.assertEqual(record.gate_status, status)
        if outcome is not None:
            profit = {
                ResolutionStatus.WON: Decimal("0.75"),
                ResolutionStatus.LOST: Decimal("-1"),
                ResolutionStatus.VOID: Decimal("0"),
            }[outcome]
            record = self.enrichment.attach(
                record.shadow_evaluation_id,
                ShadowSettlementFacts(
                    outcome,
                    profit,
                    KICKOFF_AT + timedelta(hours=2),
                ),
            )
        return record

    def test_empty_report(self):
        report = self.report()

        self.assertEqual(report.total_shadow_evaluations, 0)
        self.assertIsNone(report.hypothetical_approved_only.roi)
        self.assertEqual(report.rejection_reasons, ())

    def test_unsettled_records_are_counted_without_performance(self):
        self.add("prediction-1", QualityGateStatus.APPROVED, None, False)

        report = self.report()

        self.assertEqual(report.total_shadow_evaluations, 1)
        self.assertEqual(report.settlement_coverage_count, 0)

    def test_report_groups_counts_and_outcomes_by_gate_status(self):
        self.add("prediction-1", QualityGateStatus.APPROVED, ResolutionStatus.WON, True)
        self.add(
            "prediction-2",
            QualityGateStatus.REVIEW_REQUIRED,
            ResolutionStatus.LOST,
            False,
        )
        self.add("prediction-3", QualityGateStatus.REJECTED, ResolutionStatus.VOID, False)

        report = self.report()

        self.assertEqual((report.approved_count, report.review_required_count, report.rejected_count), (1, 1, 1))
        self.assertEqual(report.actually_published_count, 1)
        self.assertEqual(report.settlement_coverage_count, 3)
        self.assertEqual(tuple(item.performance.settled_count for item in report.by_gate_status), (1, 1, 1))

    def test_hypothetical_approved_only_uses_candidate_odds(self):
        self.add(
            "prediction-1",
            QualityGateStatus.APPROVED,
            ResolutionStatus.WON,
            False,
            Decimal("2.25"),
        )
        performance = self.report().hypothetical_approved_only

        self.assertTrue(performance.hypothetical)
        self.assertEqual(performance.profit_loss_units, Decimal("1.25"))
        self.assertEqual(performance.roi, Decimal("1.25"))

    def test_hypothetical_approved_and_review_excludes_rejected(self):
        self.add("prediction-1", QualityGateStatus.APPROVED, ResolutionStatus.WON, False)
        self.add("prediction-2", QualityGateStatus.REVIEW_REQUIRED, ResolutionStatus.LOST, False)
        self.add("prediction-3", QualityGateStatus.REJECTED, ResolutionStatus.WON, False)

        performance = self.report().hypothetical_approved_and_review

        self.assertEqual(performance.settled_count, 2)
        self.assertEqual(performance.profit_loss_units, Decimal("0.00"))

    def test_actual_published_uses_authoritative_profit_loss(self):
        self.add("prediction-1", QualityGateStatus.APPROVED, ResolutionStatus.WON, True)
        self.add("prediction-2", QualityGateStatus.APPROVED, ResolutionStatus.LOST, False)

        performance = self.report().actual_published_result

        self.assertFalse(performance.hypothetical)
        self.assertEqual(performance.total_records, 1)
        self.assertEqual(performance.profit_loss_units, Decimal("0.75"))

    def test_void_is_in_roi_denominator_and_excluded_from_hit_rate(self):
        self.add("prediction-1", QualityGateStatus.APPROVED, ResolutionStatus.WON, False)
        self.add("prediction-2", QualityGateStatus.APPROVED, ResolutionStatus.VOID, False)

        performance = self.report().hypothetical_approved_only

        self.assertEqual(performance.roi, Decimal("0.5"))
        self.assertEqual(performance.hit_rate, Decimal("1"))

    def test_reason_frequency_is_deterministic(self):
        for index in range(1, 3):
            self.add(f"prediction-{index}", QualityGateStatus.REJECTED, None, False)

        first = self.report()
        second = self.report()

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(item.reason for item in first.rejection_reasons),
            ("EXPECTED_VALUE_TOO_LOW", "ODDS_BELOW_MINIMUM"),
        )
        self.assertEqual(first.rejection_reasons[0].count, 2)

    def test_review_reason_frequency_is_reported(self):
        self.add(
            "prediction-1",
            QualityGateStatus.REVIEW_REQUIRED,
            None,
            False,
        )

        statistics = self.report().review_reasons

        self.assertEqual(statistics[0].reason, "EXCESSIVE_UNCERTAINTY")
        self.assertEqual(statistics[0].count, 1)

    def test_shadow_errors_are_counted_in_report(self):
        broken_gate = Mock()
        broken_gate.evaluate.side_effect = RuntimeError("safe failure")
        QualityGateShadowEvaluationService(
            broken_gate,
            self.repository,
        ).evaluate(request())

        self.assertEqual(self.report().error_count, 1)

    def test_date_range_and_policy_version_filters(self):
        self.add("prediction-1", QualityGateStatus.APPROVED, None, False)

        self.assertEqual(self.report("other-policy").total_shadow_evaluations, 0)
        outside = self.reports.build(
            KICKOFF_AT,
            KICKOFF_AT + timedelta(days=1),
            POLICY.version,
            KICKOFF_AT,
        )
        self.assertEqual(outside.total_shadow_evaluations, 0)

    def test_closing_reference_odds_are_never_used_hypothetically(self):
        value = candidate(reference_odds=Decimal("10"))
        record = self.service.evaluate(request(value=value)).record
        self.enrichment.attach(
            record.shadow_evaluation_id,
            ShadowSettlementFacts(
                ResolutionStatus.WON,
                Decimal("9"),
                KICKOFF_AT + timedelta(hours=2),
            ),
        )

        self.assertEqual(
            self.report().hypothetical_approved_only.profit_loss_units,
            Decimal("1.00"),
        )


class ShadowConfigurationAdapterAndRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path("tests") / f".shadow-runtime-{uuid4().hex}.db"
        self.addCleanup(self._cleanup)
        self.match = Match(
            fixture_id=500,
            league_id=39,
            league_name="Premier League",
            season=2026,
            home_team_id=1,
            home_team_name="Home",
            away_team_id=2,
            away_team_name="Away",
            kickoff=KICKOFF_AT,
            status="NS",
        )
        self.assessment = SimpleNamespace(prediction=SimpleNamespace(
            winner="Home",
            home_probability=60.0,
            away_probability=40.0,
            confidence="HIGH",
            rating_difference=20.0,
        ))

    def _cleanup(self) -> None:
        for suffix in ("", "-journal", "-shm", "-wal"):
            path = Path(f"{self.path}{suffix}")
            if path.exists():
                path.unlink()

    def facts(self) -> ShadowObservationFacts:
        return ShadowObservationFacts(
            offered_odds=Decimal("2"),
            odds_timestamp=PREDICTED_AT + timedelta(minutes=5),
            calibrated_probability=Decimal("0.62"),
            calibration_method="platt",
            calibration_scope=CalibrationScope.global_scope(),
            calibration_sample_size=200,
            calibration_fit_timestamp=PREDICTED_AT - timedelta(minutes=20),
            calibration_training_cutoff=PREDICTED_AT - timedelta(hours=1),
            model_version="model-v1",
            confidence_score=Decimal("0.8"),
            uncertainty_score=Decimal("0.1"),
            reference_odds=None,
            expected_value=None,
            data_completeness_status=EvidenceStatus.AVAILABLE,
            data_freshness_status=EvidenceStatus.AVAILABLE,
            lineup_status=EvidenceStatus.AVAILABLE,
            injury_data_status=EvidenceStatus.AVAILABLE,
            market_consensus_probability=Decimal("0.58"),
            market_disagreement=None,
            current_exposure=Decimal("0.1"),
            daily_exposure=Decimal("1"),
            competition_exposure=Decimal("1"),
            correlated_exposure=Decimal("0.5"),
            sample_size=200,
            context_calibration_sample_size=200,
            evidence=evidence(),
        )

    def test_feature_flag_defaults_false(self):
        self.assertFalse(ShadowModeConfig.from_environment({}).enabled)

    def test_feature_flag_strict_enabled_disabled_and_invalid(self):
        self.assertTrue(ShadowModeConfig.from_environment({
            "QUALITY_GATE_SHADOW_ENABLED": "true",
        }).enabled)
        self.assertFalse(ShadowModeConfig.from_environment({
            "QUALITY_GATE_SHADOW_ENABLED": "false",
        }).enabled)
        with self.assertRaises(ValueError):
            ShadowModeConfig.from_environment({
                "QUALITY_GATE_SHADOW_ENABLED": "yes",
            })

    def test_disabled_mode_performs_no_evaluation_or_persistence(self):
        observer = build_quality_gate_shadow_observer(ShadowModeConfig(
            enabled=False,
            database_path=self.path,
        ))

        result = observer.observe(self.match, self.assessment)

        self.assertIsInstance(observer, DisabledQualityGateShadowObserver)
        self.assertEqual(result.outcome, ShadowEvaluationOutcome.DISABLED)
        self.assertFalse(self.path.exists())

    def test_missing_runtime_data_remains_explicitly_missing(self):
        adaptation = PredictionShadowContextAdapter(POLICY.version).adapt(
            self.match,
            self.assessment,
            EVALUATED_AT,
        )

        self.assertIsNone(adaptation.request)
        self.assertEqual(
            adaptation.unavailable_fields,
            CURRENTLY_UNAVAILABLE_CONTEXT_FIELDS,
        )

    def test_enabled_mode_evaluates_complete_supplied_candidate(self):
        provider = SimpleNamespace(facts_for=lambda match, assessment: self.facts())
        observer = build_quality_gate_shadow_observer(
            ShadowModeConfig(True, self.path),
            facts=provider,
            clock=lambda: EVALUATED_AT,
        )

        result = observer.observe(self.match, self.assessment)
        observer.close()

        self.assertEqual(result.outcome, ShadowEvaluationOutcome.RECORDED)
        self.assertEqual(result.record.gate_status, QualityGateStatus.APPROVED)

    def test_enabled_mode_with_current_runtime_data_is_ineligible(self):
        observer = build_quality_gate_shadow_observer(
            ShadowModeConfig(True, self.path),
            clock=lambda: EVALUATED_AT,
        )

        result = observer.observe(self.match, self.assessment)
        observer.close()

        self.assertEqual(result.outcome, ShadowEvaluationOutcome.INELIGIBLE)
        database = Database(self.path)
        repository = SQLiteShadowEvaluationRepository(database)
        self.assertEqual(repository.by_fixture(500), ())
        database.close()

    def test_shadow_observer_failure_does_not_change_live_flow(self):
        application = GoalVisionApp.__new__(GoalVisionApp)
        application.football = SimpleNamespace(
            get_today_matches=AsyncMock(return_value=[self.match]),
            cached_team_form=lambda team_id: [],
        )
        application.history_collector = SimpleNamespace(collect=lambda data: [])
        application.standings = SimpleNamespace(load=AsyncMock())
        application.repository = SimpleNamespace(
            values={},
            save=lambda value: application.repository.values.__setitem__(value.team_id, value),
            get=lambda team_id: application.repository.values[team_id],
        )
        application.pipeline = SimpleNamespace(assess=Mock(return_value=self.assessment))
        application.telegram = SimpleNamespace(send_message=AsyncMock())
        application.shadow_observer = SimpleNamespace(
            observe=Mock(side_effect=RuntimeError("shadow failed")),
        )

        async def build_team(match, team_id, is_home):
            application.repository.save(SimpleNamespace(team_id=team_id))

        application.build_team = build_team

        asyncio.run(application._run())

        application.telegram.send_message.assert_not_awaited()
        application.pipeline.assess.assert_called_once()

    def test_live_publication_outcome_matches_with_shadow_on_and_off(self):
        disabled = build_quality_gate_shadow_observer(ShadowModeConfig(
            False,
            self.path,
        ))
        enabled = build_quality_gate_shadow_observer(
            ShadowModeConfig(True, self.path),
            clock=lambda: EVALUATED_AT,
        )

        disabled_result = self._run_application(disabled)
        enabled_result = self._run_application(enabled)
        enabled.close()

        self.assertEqual(disabled_result, enabled_result)
        self.assertEqual(disabled_result, (1, 0))

    def test_runtime_observation_has_no_telegram_bankroll_or_scheduling_effects(self):
        database = Database(self.path)
        repository = SQLiteShadowEvaluationRepository(database)
        service = QualityGateShadowEvaluationService(gate(), repository)

        with patch(
            "app.services.telegram_service.TelegramService.send_message",
            side_effect=AssertionError("telegram called"),
        ), patch(
            "app.bankroll.engine.OfficialBankrollSettlementEngine.settle",
            side_effect=AssertionError("bankroll called"),
        ), patch("asyncio.create_task", side_effect=AssertionError("scheduled")):
            result = service.evaluate(request())

        self.assertEqual(result.outcome, ShadowEvaluationOutcome.RECORDED)
        database.close()

    def _run_application(self, observer) -> tuple[int, int]:
        application = GoalVisionApp.__new__(GoalVisionApp)
        application.football = SimpleNamespace(
            get_today_matches=AsyncMock(return_value=[self.match]),
            cached_team_form=lambda team_id: [],
        )
        application.history_collector = SimpleNamespace(collect=lambda data: [])
        application.standings = SimpleNamespace(load=AsyncMock())
        values = {}
        application.repository = SimpleNamespace(
            save=lambda value: values.__setitem__(value.team_id, value),
            get=lambda team_id: values[team_id],
        )
        application.pipeline = SimpleNamespace(
            assess=Mock(return_value=self.assessment),
        )
        application.telegram = SimpleNamespace(send_message=AsyncMock())
        application.shadow_observer = observer

        async def build_team(match, team_id, is_home):
            application.repository.save(SimpleNamespace(team_id=team_id))

        application.build_team = build_team
        asyncio.run(application._run())
        return (
            application.pipeline.assess.call_count,
            application.telegram.send_message.await_count,
        )


class ShadowMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path("tests") / f".shadow-migration-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        self.database.close()
        if self.path.exists():
            self.path.unlink()

    def test_migration_four_is_idempotent_and_preserves_existing_data(self):
        self.database.connection.execute(
            "CREATE TABLE existing_history (value TEXT NOT NULL)"
        )
        self.database.connection.execute(
            "INSERT INTO existing_history VALUES ('keep-me')"
        )
        self.database.commit()

        MigrationManager(self.database.connection).migrate()
        MigrationManager(self.database.connection).migrate()

        versions = tuple(
            row["version"]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        tables = {
            row["name"]
            for row in self.database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertEqual(versions, tuple(range(1, 26)))
        self.assertIn("quality_gate_shadow_evaluations", tables)
        self.assertIn("quality_gate_shadow_errors", tables)
        self.assertEqual(
            self.database.connection.execute(
                "SELECT value FROM existing_history"
            ).fetchone()["value"],
            "keep-me",
        )


if __name__ == "__main__":
    unittest.main()
