import asyncio
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.official_prediction_orchestration import (
    AssemblyReason,
    BankrollScopeRecord,
    CandidateAssemblyError,
    ConfirmedOfficialPublisherError,
    ExposureEvaluationRecord,
    IndeterminateOfficialPublisherError,
    ModelHealthRecord,
    OfficialCandidateAssemblyRequest,
    OfficialCandidateFingerprint,
    OfficialPredictionCandidateAssembler,
    OfficialPredictionFacts,
    OfficialPredictionOrchestrationService,
    OfficialPredictionPublicationResult,
    OrchestrationStatus,
    PublicationDeliveryState,
    PublicationStateRecord,
    PublisherResultStatus,
    RiskEvaluationRecord,
    SQLiteOfficialPublicationStateReader,
    SQLiteOrchestrationHistoryRepository,
    build_official_prediction_orchestration_service,
)
from app.probability_calibration import (
    CalibrationMethod,
    CalibrationMetricSummary,
    ProbabilityCalibrationReport,
)
from app.publication_quality_gate import (
    ConfidenceLevel,
    ExposureDecision,
    FactStatus,
    LineupStatus,
    MarketAvailability,
    ModelHealthStatus,
    OfficialPublicationQualityGate,
    OfficialQualityGatePolicy,
    SQLiteQualityGateEvaluationRepository,
)
from app.risk_management import RiskAssessmentDecision, RiskProductScope


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)


def calibration(
    run_id: str = "calibration-1",
    *,
    timestamp: datetime = NOW - timedelta(minutes=3),
    model_version: str = "model-v1",
    raw_probability: Decimal = Decimal("0.62"),
    calibrated_probability: Decimal = Decimal("0.60"),
    method: CalibrationMethod = CalibrationMethod.PLATT,
) -> ProbabilityCalibrationReport:
    return ProbabilityCalibrationReport(
        calibration_run_id=run_id,
        raw_probability=raw_probability,
        calibrated_probability=calibrated_probability,
        delta=calibrated_probability - raw_probability,
        calibration_method=method,
        metric_summary=CalibrationMetricSummary(
            observation_count=200,
            brier_score=Decimal("0.15"),
            log_loss=Decimal("0.50"),
            expected_calibration_error=Decimal("0.03"),
            maximum_calibration_error=Decimal("0.08"),
            reliability_bins=(),
        ),
        confidence_histogram=(),
        timestamp=timestamp,
        model_version=model_version,
        calibration_version="calibration-v1",
    )


def prediction(**changes) -> OfficialPredictionFacts:
    values = {
        "prediction_id": "prediction-1",
        "match_id": "101",
        "model_version": "model-v1",
        "market": "MATCH_WINNER",
        "selection": "HOME",
        "market_line": None,
        "raw_probability": Decimal("0.62"),
        "decimal_odds": Decimal("1.80"),
        "odds_timestamp": NOW - timedelta(minutes=2),
        "expected_value": Decimal("0.080"),
        "confidence": ConfidenceLevel.HIGH,
        "prediction_timestamp": NOW - timedelta(minutes=10),
        "kickoff_timestamp": NOW + timedelta(hours=1),
        "core_data_timestamp": NOW - timedelta(minutes=5),
        "supporting_data_status": FactStatus.AVAILABLE,
        "market_availability": MarketAvailability.AVAILABLE,
        "lineup_status": LineupStatus.CONFIRMED,
        "injury_status": FactStatus.AVAILABLE,
    }
    values.update(changes)
    return OfficialPredictionFacts(**values)


def health(
    record_id: str = "health-1",
    *,
    checked_at: datetime = NOW - timedelta(minutes=1),
    model_version: str = "model-v1",
) -> ModelHealthRecord:
    return ModelHealthRecord(
        record_id,
        model_version,
        ModelHealthStatus.HEALTHY,
        checked_at,
    )


def risk(
    evaluation_id: str = "risk-1",
    *,
    evaluated_at: datetime = NOW - timedelta(minutes=2),
    **changes,
) -> RiskEvaluationRecord:
    values = {
        "evaluation_id": evaluation_id,
        "prediction_id": "prediction-1",
        "match_id": "101",
        "model_version": "model-v1",
        "market": "MATCH_WINNER",
        "selection": "HOME",
        "market_line": None,
        "bankroll_scope": RiskProductScope.OFFICIAL,
        "decision": RiskAssessmentDecision.ELIGIBLE,
        "evaluated_at": evaluated_at,
    }
    values.update(changes)
    return RiskEvaluationRecord(**values)


def exposure(
    evaluation_id: str = "exposure-1",
    *,
    evaluated_at: datetime = NOW - timedelta(minutes=2),
    **changes,
) -> ExposureEvaluationRecord:
    values = {
        "evaluation_id": evaluation_id,
        "prediction_id": "prediction-1",
        "match_id": "101",
        "model_version": "model-v1",
        "market": "MATCH_WINNER",
        "selection": "HOME",
        "market_line": None,
        "bankroll_scope": RiskProductScope.OFFICIAL,
        "decision": ExposureDecision.CLEAR,
        "evaluated_at": evaluated_at,
    }
    values.update(changes)
    return ExposureEvaluationRecord(**values)


def request(**changes) -> OfficialCandidateAssemblyRequest:
    values = {
        "prediction": prediction(),
        "calibration_records": (calibration(),),
        "model_health_records": (health(),),
        "risk_evaluations": (risk(),),
        "exposure_evaluations": (exposure(),),
        "bankroll": BankrollScopeRecord(
            "official-bankroll-1",
            RiskProductScope.OFFICIAL,
            NOW - timedelta(minutes=2),
        ),
        "evaluation_timestamp": NOW,
        "dry_run": False,
    }
    values.update(changes)
    return OfficialCandidateAssemblyRequest(**values)


def publication(
    state: PublicationDeliveryState = PublicationDeliveryState.NEVER_ATTEMPTED,
    **changes,
) -> PublicationStateRecord:
    values = {
        "prediction_id": "prediction-1",
        "match_id": "101",
        "state": state,
        "observed_at": NOW,
        "attempt_reference": None,
    }
    values.update(changes)
    return PublicationStateRecord(**values)


class CandidateAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.assembler = OfficialPredictionCandidateAssembler()

    def test_successful_candidate_assembly_and_decimal_ev_verification(self):
        assembled = self.assembler.assemble(request(), publication())

        self.assertEqual(assembled.prediction_id, "prediction-1")
        self.assertEqual(assembled.match_id, "101")
        self.assertEqual(assembled.verified_expected_value, Decimal("0.0800"))
        self.assertEqual(
            assembled.gate_candidate.expected_value,
            Decimal("0.080"),
        )

    def test_missing_required_facts_fail_closed(self):
        with self.assertRaises(CandidateAssemblyError) as caught:
            self.assembler.assemble(
                request(calibration_records=()),
                publication(),
            )
        self.assertEqual(
            caught.exception.reasons,
            (AssemblyReason.NO_VALID_CALIBRATION_RECORD,),
        )

    def test_mismatched_prediction_and_match_ids_fail(self):
        for changes, expected in (
            ({"risk_evaluations": (risk(prediction_id="other"),)}, AssemblyReason.RISK_IDENTITY_MISMATCH),
            ({"exposure_evaluations": (exposure(match_id="999"),)}, AssemblyReason.EXPOSURE_IDENTITY_MISMATCH),
        ):
            with self.subTest(expected=expected), self.assertRaises(CandidateAssemblyError) as caught:
                self.assembler.assemble(request(**changes), publication())
            self.assertEqual(caught.exception.reasons, (expected,))

    def test_model_version_mismatch_and_no_valid_calibration(self):
        with self.assertRaises(CandidateAssemblyError) as caught:
            self.assembler.assemble(
                request(calibration_records=(calibration(model_version="model-v2"),)),
                publication(),
            )
        self.assertEqual(
            caught.exception.reasons,
            (AssemblyReason.CALIBRATION_MODEL_VERSION_MISMATCH,),
        )

        with self.assertRaises(CandidateAssemblyError) as future:
            self.assembler.assemble(
                request(calibration_records=(calibration(timestamp=NOW + timedelta(seconds=1)),)),
                publication(),
            )
        self.assertEqual(
            future.exception.reasons,
            (AssemblyReason.NO_VALID_CALIBRATION_RECORD,),
        )

    def test_explicit_identity_calibration_is_accepted(self):
        identity = calibration(method=CalibrationMethod.IDENTITY)
        assembled = self.assembler.assemble(
            request(calibration_records=(identity,)),
            publication(),
        )
        self.assertEqual(assembled.calibration_method, "identity")

    def test_calibration_selection_is_newest_with_deterministic_tie_break(self):
        older = calibration("older", timestamp=NOW - timedelta(minutes=4))
        tied_a = calibration("a", timestamp=NOW - timedelta(minutes=1))
        tied_b = calibration("b", timestamp=NOW - timedelta(minutes=1))
        future = calibration("future", timestamp=NOW + timedelta(seconds=1))

        assembled = self.assembler.assemble(
            request(calibration_records=(future, tied_a, older, tied_b)),
            publication(),
        )
        self.assertEqual(assembled.calibration_run_id, "b")

    def test_risk_and_exposure_selection_are_deterministic(self):
        assembled = self.assembler.assemble(
            request(
                risk_evaluations=(
                    risk("risk-old", evaluated_at=NOW - timedelta(minutes=4)),
                    risk("risk-a", evaluated_at=NOW - timedelta(minutes=1)),
                    risk("risk-b", evaluated_at=NOW - timedelta(minutes=1)),
                ),
                exposure_evaluations=(
                    exposure("exp-b", evaluated_at=NOW - timedelta(minutes=1)),
                    exposure("exp-a", evaluated_at=NOW - timedelta(minutes=1)),
                ),
            ),
            publication(),
        )
        self.assertEqual(assembled.risk_evaluation_id, "risk-b")
        self.assertEqual(assembled.exposure_evaluation_id, "exp-b")

    def test_wrong_bankroll_scope_and_inconsistent_market_fail(self):
        wrong = BankrollScopeRecord(
            "combo-bank",
            RiskProductScope.COMBO,
            NOW - timedelta(minutes=1),
        )
        with self.assertRaises(CandidateAssemblyError) as caught:
            self.assembler.assemble(request(bankroll=wrong), publication())
        self.assertEqual(caught.exception.reasons, (AssemblyReason.WRONG_BANKROLL_SCOPE,))

        with self.assertRaises(CandidateAssemblyError) as market_error:
            self.assembler.assemble(
                request(risk_evaluations=(risk(market="TOTALS"),)),
                publication(),
            )
        self.assertEqual(
            market_error.exception.reasons,
            (AssemblyReason.RISK_IDENTITY_MISMATCH,),
        )

    def test_unsupported_market_fails_during_assembly(self):
        with self.assertRaises(CandidateAssemblyError) as caught:
            self.assembler.assemble(
                request(prediction=prediction(market="CORRECT_SCORE", selection="2-1")),
                publication(),
            )
        self.assertEqual(
            caught.exception.reasons,
            (AssemblyReason.UNSUPPORTED_MARKET_FACTS,),
        )

    def test_candidate_fingerprint_is_deterministic_material_and_order_independent(self):
        fingerprint = OfficialCandidateFingerprint()
        first_request = request(
            calibration_records=(
                calibration("old", timestamp=NOW - timedelta(minutes=4)),
                calibration("selected", timestamp=NOW - timedelta(minutes=1)),
            )
        )
        second_request = replace(
            first_request,
            calibration_records=tuple(reversed(first_request.calibration_records)),
        )
        first = self.assembler.assemble(first_request, publication())
        second = self.assembler.assemble(second_request, publication())

        self.assertEqual(fingerprint.generate(first), fingerprint.generate(second))
        changed_request = replace(
            first_request,
            prediction=replace(
                first_request.prediction,
                decimal_odds=Decimal("1.81"),
                expected_value=Decimal("0.086"),
            ),
        )
        changed = self.assembler.assemble(changed_request, publication())
        self.assertNotEqual(fingerprint.generate(first), fingerprint.generate(changed))


class StateReader:
    def __init__(self, value: PublicationStateRecord | None = None):
        self.value = value or publication()
        self.calls = 0

    def get(self, prediction_id, match_id, evaluated_at):
        self.calls += 1
        return replace(
            self.value,
            prediction_id=prediction_id,
            match_id=match_id,
            observed_at=evaluated_at,
        )


class Publisher:
    def __init__(
        self,
        result: OfficialPredictionPublicationResult | None = None,
        *,
        enabled: bool = True,
        error: Exception | None = None,
        events: list[str] | None = None,
    ):
        self._enabled = enabled
        self.result = result or OfficialPredictionPublicationResult(
            PublisherResultStatus.PUBLISHED,
            "attempt-1",
        )
        self.error = error
        self.calls = []
        self.events = events

    @property
    def enabled(self):
        return self._enabled

    async def publish(self, candidate):
        self.calls.append(candidate)
        if self.events is not None:
            self.events.append("publish")
        if self.error is not None:
            raise self.error
        return self.result


class EventGateRepository:
    def __init__(self, delegate, events):
        self.delegate = delegate
        self.events = events

    def append(self, evaluation):
        self.events.append("gate-persisted")
        return self.delegate.append(evaluation)

    def get(self, evaluation_id):
        return self.delegate.get(evaluation_id)


class FailingGateRepository:
    def append(self, evaluation):
        raise ValueError("database unavailable")

    def get(self, evaluation_id):
        return None


class BrokenGate:
    policy = OfficialQualityGatePolicy()

    def evaluate(self, candidate):
        raise RuntimeError("gate error")


class OrchestrationServiceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.gate_repository = SQLiteQualityGateEvaluationRepository(self.database)
        self.history = SQLiteOrchestrationHistoryRepository(self.database, migrate=False)
        self.state = StateReader()
        self.publisher = Publisher()

    def tearDown(self):
        self.database.close()

    def service(self, *, gate=None, gate_repository=None, publisher=None):
        return OfficialPredictionOrchestrationService(
            OfficialPredictionCandidateAssembler(),
            OfficialCandidateFingerprint(),
            gate or OfficialPublicationQualityGate(OfficialQualityGatePolicy()),
            gate_repository or self.gate_repository,
            self.history,
            self.state,
            publisher or self.publisher,
        )

    def execute(self, value=None, **service_changes):
        return asyncio.run(
            self.service(**service_changes).prepare_and_publish_official_prediction(
                value or request()
            )
        )

    def test_approved_candidate_reaches_publisher_after_gate_persistence(self):
        events = []
        publisher = Publisher(events=events)
        gate_repository = EventGateRepository(self.gate_repository, events)

        outcome = self.execute(publisher=publisher, gate_repository=gate_repository)

        self.assertEqual(outcome.final_status, OrchestrationStatus.PUBLISHED)
        self.assertEqual(events, ["gate-persisted", "publish"])
        self.assertEqual(len(publisher.calls), 1)
        self.assertIsNotNone(outcome.quality_gate_evaluation_id)

    def test_rejected_and_review_required_never_reach_publisher(self):
        rejected_request = request(
            prediction=prediction(
                decimal_odds=Decimal("1.50"),
                expected_value=Decimal("-0.10"),
            )
        )
        rejected = self.execute(rejected_request)
        self.assertEqual(rejected.final_status, OrchestrationStatus.REJECTED)

        review_request = request(
            risk_evaluations=(risk(decision=RiskAssessmentDecision.REVIEW_REQUIRED),)
        )
        review = self.execute(review_request)
        self.assertEqual(review.final_status, OrchestrationStatus.REVIEW_REQUIRED)
        self.assertEqual(self.publisher.calls, [])

    def test_gate_evaluation_and_repository_failures_prevent_publication(self):
        broken = self.execute(gate=BrokenGate())
        self.assertEqual(broken.final_status, OrchestrationStatus.ASSEMBLY_FAILED)
        self.assertIn(
            AssemblyReason.QUALITY_GATE_EVALUATION_FAILED.value,
            broken.ordered_reason_codes,
        )

        failed = self.execute(gate_repository=FailingGateRepository())
        self.assertEqual(failed.final_status, OrchestrationStatus.ASSEMBLY_FAILED)
        self.assertIn(
            AssemblyReason.QUALITY_GATE_PERSISTENCE_FAILED.value,
            failed.ordered_reason_codes,
        )
        self.assertEqual(self.publisher.calls, [])

    def test_assembly_failure_prevents_publication(self):
        outcome = self.execute(request(calibration_records=()))
        self.assertEqual(outcome.final_status, OrchestrationStatus.ASSEMBLY_FAILED)
        self.assertEqual(self.publisher.calls, [])

    def test_dry_run_persists_gate_and_never_invokes_publisher(self):
        outcome = self.execute(request(dry_run=True))

        self.assertEqual(
            outcome.final_status,
            OrchestrationStatus.APPROVED_NOT_PUBLISHED,
        )
        self.assertTrue(outcome.dry_run)
        self.assertEqual(self.publisher.calls, [])
        self.assertIsNotNone(outcome.quality_gate_evaluation_id)

    def test_disabled_publisher_is_explicit_approved_not_published(self):
        publisher = Publisher(enabled=False)
        outcome = self.execute(publisher=publisher)
        self.assertEqual(
            outcome.final_status,
            OrchestrationStatus.APPROVED_NOT_PUBLISHED,
        )
        self.assertIn(
            AssemblyReason.PUBLISHER_DISABLED.value,
            outcome.ordered_reason_codes,
        )

    def test_duplicate_published_and_active_claim_are_blocked(self):
        for state in (
            PublicationDeliveryState.PUBLISHED,
            PublicationDeliveryState.CLAIMED,
            PublicationDeliveryState.ATTEMPTING,
        ):
            with self.subTest(state=state):
                self.state.value = publication(state)
                outcome = self.execute()
                self.assertEqual(
                    outcome.final_status,
                    OrchestrationStatus.DUPLICATE_BLOCKED,
                )
        self.assertEqual(self.publisher.calls, [])

    def test_confirmed_failed_publication_follows_retry_path(self):
        self.state.value = publication(
            PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE
        )
        self.publisher.result = OfficialPredictionPublicationResult(
            PublisherResultStatus.PUBLISHED,
            "retry-attempt-2",
        )
        outcome = self.execute()
        self.assertEqual(outcome.final_status, OrchestrationStatus.PUBLISHED)
        self.assertEqual(len(self.publisher.calls), 1)

    def test_indeterminate_state_never_resends(self):
        self.state.value = publication(
            PublicationDeliveryState.INDETERMINATE_FAILURE,
            attempt_reference="attempt-unknown",
        )
        outcome = self.execute()
        self.assertEqual(
            outcome.final_status,
            OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
        )
        self.assertEqual(self.publisher.calls, [])

    def test_publisher_result_and_exception_failures_are_mapped(self):
        cases = (
            (
                Publisher(
                    OfficialPredictionPublicationResult(
                        PublisherResultStatus.RETRYABLE_FAILURE,
                        "attempt-failed",
                    )
                ),
                OrchestrationStatus.RETRYABLE_PUBLICATION_FAILURE,
            ),
            (
                Publisher(
                    error=ConfirmedOfficialPublisherError(
                        "confirmed failure",
                        "confirmed-ref",
                    )
                ),
                OrchestrationStatus.RETRYABLE_PUBLICATION_FAILURE,
            ),
            (
                Publisher(
                    error=IndeterminateOfficialPublisherError(
                        "unknown after send",
                        "unknown-ref",
                    )
                ),
                OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
            ),
            (
                Publisher(error=RuntimeError("unexpected")),
                OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
            ),
        )
        for publisher, expected in cases:
            with self.subTest(expected=expected):
                database = Database(":memory:")
                service = build_official_prediction_orchestration_service(
                    database,
                    publisher,
                    publication_states=StateReader(),
                )
                outcome = asyncio.run(
                    service.prepare_and_publish_official_prediction(request())
                )
                self.assertEqual(outcome.final_status, expected)
                database.close()

    def test_publisher_duplicate_result_is_mapped(self):
        publisher = Publisher(
            OfficialPredictionPublicationResult(
                PublisherResultStatus.DUPLICATE_BLOCKED,
                "existing-attempt",
            )
        )
        outcome = self.execute(publisher=publisher)
        self.assertEqual(outcome.final_status, OrchestrationStatus.DUPLICATE_BLOCKED)

    def test_identical_repeat_is_idempotent_and_changed_candidate_appends(self):
        service = self.service()
        first = asyncio.run(service.prepare_and_publish_official_prediction(request()))
        second = asyncio.run(service.prepare_and_publish_official_prediction(request()))

        self.assertEqual(first, second)
        self.assertEqual(len(self.publisher.calls), 1)
        self.assertEqual(len(self.history.history_for_prediction("prediction-1")), 1)

        changed = request(
            prediction=prediction(
                decimal_odds=Decimal("1.81"),
                expected_value=Decimal("0.086"),
            )
        )
        third = asyncio.run(service.prepare_and_publish_official_prediction(changed))
        self.assertNotEqual(first.candidate_fingerprint, third.candidate_fingerprint)
        self.assertEqual(len(self.history.history_for_prediction("prediction-1")), 2)


class OrchestrationPersistenceTests(unittest.TestCase):
    def test_fresh_migration_eleven_and_append_only_guards(self):
        database = Database(":memory:")
        MigrationManager(database.connection).migrate()
        versions = tuple(
            row[0]
            for row in database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 23)))

        service = build_official_prediction_orchestration_service(
            database,
            Publisher(enabled=False),
            publication_states=StateReader(),
        )
        outcome = asyncio.run(
            service.prepare_and_publish_official_prediction(request())
        )
        repository = SQLiteOrchestrationHistoryRepository(database, migrate=False)
        stored = repository.get(outcome.orchestration_id)
        self.assertIsNotNone(stored)
        for statement in (
            "UPDATE official_prediction_orchestrations SET final_status='REJECTED'",
            "DELETE FROM official_prediction_orchestrations",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                database.connection.execute(statement)
        database.close()

    def test_upgrade_from_v10_applies_only_next_migration(self):
        database = Database(":memory:")
        database.connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS[:10]:
            for statement in migration.statements:
                database.connection.execute(statement)
            database.connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'existing')",
                (migration.version,),
            )
        MigrationManager(database.connection).migrate()

        versions = tuple(
            row[0]
            for row in database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 23)))
        self.assertIsNotNone(
            database.connection.execute(
                "SELECT name FROM sqlite_master WHERE name='official_prediction_orchestrations'"
            ).fetchone()
        )
        database.close()

    def test_sqlite_state_reader_observes_published_prediction(self):
        database = Database(":memory:")
        reader = SQLiteOfficialPublicationStateReader(database)
        database.connection.execute(
            """
            INSERT INTO published_predictions (
                prediction_id, fixture_id, market, pick, published_at,
                settlement_status
            ) VALUES ('prediction-1', 101, 'MATCH_WINNER', 'HOME', ?, 'PENDING')
            """,
            ((NOW - timedelta(minutes=1)).isoformat(),),
        )
        state = reader.get("prediction-1", "101", NOW)
        self.assertEqual(state.state, PublicationDeliveryState.PUBLISHED)
        database.close()


if __name__ == "__main__":
    unittest.main()
