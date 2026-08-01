import asyncio
import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.official_prediction_candidate_registry import (
    CandidateLifecycleState,
    OfficialPredictionCandidateValidator,
    OfficialPredictionCandidateVersion,
    SQLiteOfficialPredictionCandidateRepository,
    DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY,
)
from app.official_prediction_orchestration import (
    OfficialCandidateFingerprint,
    OfficialPredictionCandidateAssembler,
    OfficialPredictionOrchestrationOutcome,
    OfficialPredictionOrchestrationService,
    OfficialPredictionPublicationResult,
    OrchestrationStatus,
    PublisherResultStatus,
    SQLiteOfficialPublicationStateReader,
    SQLiteOrchestrationHistoryRepository,
)
from app.official_prediction_pipeline import (
    CandidateState,
    CandidateStateVerification,
    DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY,
    OfficialPredictionPipelineCommand,
    OfficialPredictionPipelineService,
    PipelinePublicationState,
    PipelineStage,
    PipelineStageEvent,
    PipelineStatus,
    PublicationStateVerification,
    ExistingMessagePreviewAdapter,
    ExistingPreapprovedOrchestrationAdapter,
    ExistingPublicationStateAdapter,
    PersistedQualityGateAdapter,
    SQLiteCandidateRegistryStateAdapter,
    request_fingerprint,
    run_official_prediction_pipeline_batch,
    SQLiteOfficialPredictionPipelineRepository,
)
from app.publication_quality_gate import (
    DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY,
    OfficialPublicationQualityGate,
    SQLiteQualityGateEvaluationRepository,
)
from app.official_prediction_publication import (
    ApprovedPublicReasoning,
    DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY,
    OfficialPredictionDestination,
    OfficialPredictionMessageBuilder,
    OfficialPredictionPublicFacts,
    SQLiteAtomicPredictionPublicationRepository,
    build_official_prediction_publisher_adapter,
)
from app.quality_gate import QualityGateStatus
from app.risk_management import RiskAssessmentDecision, RiskProductScope
from tests.test_official_prediction_candidate_registry import command as registry_command
from tests.test_official_prediction_orchestration import NOW, prediction, publication, request
from tests.test_official_prediction_publication import stake


PROVENANCE = (
    ("assessment_fingerprint", "assessment-fp"),
    ("bankroll_snapshot_identity", "bankroll-1"),
    ("calibrated_assembly_fingerprint", "calibrated-fp"),
    ("calibrated_assembly_id", "calibrated-1"),
    ("calibration_set_id", "calibration-set-1"),
    ("exposure_snapshot_identity", "exposure-1"),
    ("inference_id", "inference-1"),
    ("model_input_id", "model-input-1"),
    ("bookmaker_id", "bookmaker-a"),
    ("odds_fingerprint", "odds-fp"),
    ("odds_record_id", "odds-1"),
    ("preparation_request_fingerprint", "preparation-fp"),
    ("risk_fingerprint", "risk-fp"),
    ("selection_decision_id", "selection-1"),
    ("selection_fingerprint", "selection-fp"),
    ("selected_value_assessment_id", "assessment-1"),
)


def candidate():
    prepared = OfficialPredictionCandidateValidator(
        DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY
    ).prepare(registry_command(provenance=PROVENANCE))
    return OfficialPredictionCandidateVersion("candidate-1", 1, prepared)


def pipeline_command(**changes):
    item = candidate()
    assembly = request(prediction=prediction(
        registry_candidate_id=item.registry_candidate_id,
        registry_content_fingerprint=item.content_fingerprint,
    ))
    values = {
        "candidate": item,
        "assembly_request": assembly,
        "pipeline_request_identity": "pipeline-request-1",
        "candidate_id": item.registry_candidate_id,
        "candidate_version": 1,
        "candidate_fingerprint": item.content_fingerprint,
        "candidate_lifecycle_status": CandidateLifecycleState.READY,
        "match_id": "101",
        "kickoff_timestamp": NOW + timedelta(hours=1),
        "bankroll_scope": RiskProductScope.OFFICIAL,
        "destination_scope": RiskProductScope.OFFICIAL,
        "normalized_market": "MATCH WINNER",
        "normalized_selection": "HOME",
        "normalized_line": None,
        "preparation_execution_id": "preparation-execution-1",
        "selection_decision_id": "selection-1",
        "selected_value_assessment_id": "assessment-1",
        "model_input_id": "model-input-1",
        "inference_id": "inference-1",
        "calibrated_assembly_id": "calibrated-1",
        "calibration_set_id": "calibration-set-1",
        "odds_snapshot_identity": "odds-1",
        "bookmaker_provider_identity": "bookmaker-a",
        "odds_fingerprint": "odds-fp",
        "calibrated_assembly_fingerprint": "calibrated-fp",
        "selection_fingerprint": "selection-fp",
        "value_assessment_fingerprint": "assessment-fp",
        "risk_fingerprint": "risk-fp",
        "candidate_preparation_fingerprint": "preparation-fp",
        "bookmaker_odds": Decimal("1.80"),
        "calibrated_probability": Decimal("0.60"),
        "fair_odds": Decimal("1.6666666667"),
        "implied_probability": Decimal("0.5555555556"),
        "expected_value": Decimal("0.080"),
        "value_classification": "VALUE",
        "freshness": "FRESH",
        "risk_outcome": RiskAssessmentDecision.ELIGIBLE,
        "stake_recommendation": stake(),
        "internal_stake_percentage": Decimal("0.02"),
        "stake_amount": Decimal("20.00"),
        "bankroll_snapshot_identity": "bankroll-1",
        "exposure_snapshot_identity": "exposure-1",
        "quality_gate_evaluation_timestamp": NOW,
        "pipeline_execution_timestamp": NOW,
        "publication_effective_timestamp": NOW,
        "pipeline_policy_version": DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY.version,
        "metadata_version": "v1",
    }
    values.update(changes)
    return OfficialPredictionPipelineCommand(**values)


class CandidateStates:
    def __init__(self, state=CandidateState.READY):
        self.state = state

    def verify(self, command):
        return CandidateStateVerification(self.state, command.candidate, self.state is CandidateState.READY, fingerprint=command.candidate_fingerprint)


class PublicationStates:
    def __init__(self, *states):
        self.states = list(states or (PipelinePublicationState.NOT_PUBLISHED,))
        self.calls = 0

    def verify(self, command):
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        return PublicationStateVerification(
            state, NOW,
            publication_event_id="publication-event-1" if state is PipelinePublicationState.PUBLISHED else None,
            publication_fingerprint="publication-fp" if state is PipelinePublicationState.PUBLISHED else None,
            message_fingerprint="message-fp" if state is PipelinePublicationState.PUBLISHED else None,
            claim_identity="claim-1" if state is PipelinePublicationState.PUBLISHED else None,
            telegram_message_reference="42" if state is PipelinePublicationState.PUBLISHED else None,
        )


class Gate:
    def __init__(self, decision=QualityGateStatus.APPROVED):
        self.calls = 0
        self.decision = decision
        self.gate = OfficialPublicationQualityGate(
            DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY
        )
        self.evaluations = {}

    @property
    def policy_version(self):
        return DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY.version

    def evaluate_once(self, candidate):
        self.calls += 1
        evaluation = self.gate.evaluate(candidate)
        evaluation = replace(evaluation, final_decision=self.decision)
        self.evaluations[evaluation.evaluation_id] = evaluation
        return evaluation

    def load(self, evaluation_id):
        return self.evaluations.get(evaluation_id)


class Orchestration:
    def __init__(self, status=OrchestrationStatus.PUBLISHED):
        self.status = status
        self.calls = 0

    async def prepare_and_publish_preapproved(self, request, gate):
        self.calls += 1
        return OfficialPredictionOrchestrationOutcome(
            "orchestration-1", request.prediction.prediction_id, "orchestration-candidate-fp",
            gate.evaluation_id, self.status, (), (), "claim-1" if self.status is OrchestrationStatus.PUBLISHED else None,
            request.evaluation_timestamp, request.dry_run, gate.policy_version, request.prediction.model_version,
        )


class Preview:
    def __init__(self):
        self.calls = 0

    def build_preview(self, request, gate, orchestration):
        self.calls += 1
        return SimpleNamespace(message_fingerprint="preview-message-fp")


class MemoryRepository:
    def __init__(self):
        self.values = {}
        self.stages = {}

    def find_by_request_identity(self, identity):
        return self.values.get(identity)

    def append_pipeline_execution(self, execution, stage_events=()):
        existing = self.values.get(execution.pipeline_request_identity)
        if existing is not None:
            return existing
        self.values[execution.pipeline_request_identity] = execution
        self.stages[execution.pipeline_execution_id] = stage_events
        return execution

    def find_latest_for_candidate(self, candidate_id):
        values = [item for item in self.values.values() if item.candidate_id == candidate_id]
        return values[-1] if values else None


def service(publication_states=None, orchestration=None, gate=None):
    gate = gate or Gate()
    orchestrator = orchestration or Orchestration()
    preview = Preview()
    repository = MemoryRepository()
    value = OfficialPredictionPipelineService(
        DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY,
        CandidateStates(), publication_states or PublicationStates(PipelinePublicationState.NOT_PUBLISHED, PipelinePublicationState.PUBLISHED),
        gate, orchestrator, preview, repository, OfficialPredictionCandidateAssembler(),
    )
    return value, gate, orchestrator, preview, repository


class OfficialPredictionPipelineTests(unittest.TestCase):
    def test_approved_candidate_publishes_once_and_replays_terminal_result(self):
        value, gate, orchestration, _, _ = service()
        command = pipeline_command()
        first = asyncio.run(value.execute(command))
        second = asyncio.run(value.execute(command))
        self.assertEqual(first.final_status, PipelineStatus.PUBLISHED)
        self.assertEqual(first, second)
        self.assertEqual(gate.calls, 1)
        self.assertEqual(orchestration.calls, 1)
        self.assertEqual(first.message_fingerprint, "message-fp")

    def test_validation_failure_prevents_gate_and_orchestration(self):
        value, gate, orchestration, _, _ = service()
        outcome = asyncio.run(value.execute(pipeline_command(bookmaker_odds=Decimal("1.59"))))
        self.assertIn(outcome.final_status, {
            PipelineStatus.REJECTED_INVALID_REQUEST,
            PipelineStatus.REJECTED_PROVENANCE,
        })
        self.assertEqual(gate.calls, 0)
        self.assertEqual(orchestration.calls, 0)

    def test_candidate_state_fails_closed_before_gate(self):
        value, gate, orchestration, _, _ = service()
        value._candidate_states = CandidateStates(CandidateState.SUPERSEDED)
        outcome = asyncio.run(value.execute(pipeline_command()))
        self.assertEqual(outcome.final_status, PipelineStatus.REJECTED_CANDIDATE_STATE)
        self.assertEqual(gate.calls, 0)
        self.assertEqual(orchestration.calls, 0)

    def test_published_active_claim_and_retry_protection(self):
        for state, expected in (
            (PipelinePublicationState.PUBLISHED, PipelineStatus.IDEMPOTENT_EXISTING),
            (PipelinePublicationState.ACTIVE_CLAIM, PipelineStatus.PUBLICATION_IN_PROGRESS),
            (PipelinePublicationState.FAILED_RETRYABLE, PipelineStatus.RETRY_REQUIRED),
            (PipelinePublicationState.INDETERMINATE, PipelineStatus.RETRY_REQUIRED),
            (PipelinePublicationState.UNKNOWN, PipelineStatus.RETRY_REQUIRED),
        ):
            with self.subTest(state=state):
                value, gate, _, _, _ = service(PublicationStates(state))
                outcome = asyncio.run(value.execute(pipeline_command()))
                self.assertEqual(outcome.final_status, expected)
                self.assertEqual(gate.calls, 0)

    def test_explicit_retry_can_continue(self):
        value, gate, orchestration, _, _ = service(PublicationStates(PipelinePublicationState.FAILED_RETRYABLE, PipelinePublicationState.PUBLISHED))
        outcome = asyncio.run(value.execute(pipeline_command(retry=True)))
        self.assertEqual(outcome.final_status, PipelineStatus.PUBLISHED)
        self.assertEqual(gate.calls, 1)
        self.assertEqual(orchestration.calls, 1)

    def test_retry_reuses_verified_approved_gate(self):
        states = PublicationStates(
            PipelinePublicationState.NOT_PUBLISHED,
            PipelinePublicationState.FAILED_RETRYABLE,
            PipelinePublicationState.FAILED_RETRYABLE,
            PipelinePublicationState.PUBLISHED,
        )
        orchestrator = Orchestration(OrchestrationStatus.RETRYABLE_PUBLICATION_FAILURE)
        value, gate, _, _, _ = service(states, orchestrator)
        first = asyncio.run(value.execute(pipeline_command()))
        self.assertEqual(first.quality_gate_status, QualityGateStatus.APPROVED.value)
        orchestrator.status = OrchestrationStatus.PUBLISHED
        second = asyncio.run(value.execute(pipeline_command(
            pipeline_request_identity="pipeline-request-retry",
            retry=True,
        )))
        self.assertEqual(second.final_status, PipelineStatus.PUBLISHED)
        self.assertEqual(gate.calls, 1)

    def test_dry_run_builds_preview_without_publication(self):
        value, gate, orchestration, preview, _ = service(
            PublicationStates(PipelinePublicationState.NOT_PUBLISHED),
            Orchestration(OrchestrationStatus.APPROVED_NOT_PUBLISHED),
        )
        outcome = asyncio.run(value.execute(pipeline_command(dry_run=True)))
        self.assertEqual(outcome.final_status, PipelineStatus.DRY_RUN_COMPLETED)
        self.assertEqual(outcome.message_fingerprint, "preview-message-fp")
        self.assertEqual(gate.calls, orchestration.calls, 1)
        self.assertEqual(preview.calls, 1)

    def test_gate_rejection_and_review_never_orchestrate(self):
        for decision, expected in (
            (QualityGateStatus.REJECTED, PipelineStatus.NO_PUBLICATION_QUALITY_GATE_REJECTED),
            (QualityGateStatus.REVIEW_REQUIRED, PipelineStatus.NO_PUBLICATION_REVIEW_REQUIRED),
        ):
            with self.subTest(decision=decision):
                gate = Gate(decision)
                value, _, orchestration, preview, _ = service(gate=gate)
                outcome = asyncio.run(value.execute(pipeline_command()))
                self.assertEqual(outcome.final_status, expected)
                self.assertEqual(gate.calls, 1)
                self.assertEqual(orchestration.calls, 0)
                self.assertEqual(preview.calls, 0)

    def test_request_fingerprint_stability_and_material_changes(self):
        command = pipeline_command()
        self.assertEqual(request_fingerprint(command), request_fingerprint(command))
        self.assertNotEqual(request_fingerprint(command), request_fingerprint(replace(command, retry=True)))
        self.assertNotEqual(request_fingerprint(command), request_fingerprint(replace(command, pipeline_execution_timestamp=NOW + timedelta(seconds=1))))

    def test_request_identity_conflict_stops_second_gate(self):
        value, gate, _, _, _ = service()
        asyncio.run(value.execute(pipeline_command()))
        outcome = asyncio.run(value.execute(pipeline_command(retry=True)))
        self.assertEqual(outcome.final_status, PipelineStatus.CONFLICT)
        self.assertEqual(gate.calls, 1)

    def test_existing_orchestration_accepts_verified_preapproval_without_gate_reexecution(self):
        database = Database(":memory:")
        try:
            class NeverGate:
                policy = DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY
                calls = 0

                def evaluate(self, candidate):
                    self.calls += 1
                    raise AssertionError("preapproved path must not evaluate the gate")

            class StateReader:
                def get(self, prediction_id, match_id, evaluated_at):
                    return publication(observed_at=evaluated_at)

            class AtomicPublisher:
                enabled = True

                def __init__(self):
                    self.calls = 0

                async def publish(self, approved):
                    self.calls += 1
                    return OfficialPredictionPublicationResult(PublisherResultStatus.PUBLISHED, "claim-1")

            gate_engine = OfficialPublicationQualityGate(DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY)
            assembled = OfficialPredictionCandidateAssembler().assemble(request(), publication())
            evaluation = SQLiteQualityGateEvaluationRepository(database).append(gate_engine.evaluate(assembled.gate_candidate))
            never_gate = NeverGate()
            publisher = AtomicPublisher()
            orchestration_service = OfficialPredictionOrchestrationService(
                OfficialPredictionCandidateAssembler(), OfficialCandidateFingerprint(), never_gate,
                SQLiteQualityGateEvaluationRepository(database, migrate=False),
                SQLiteOrchestrationHistoryRepository(database, migrate=False), StateReader(), publisher,
            )
            outcome = asyncio.run(orchestration_service.prepare_and_publish_preapproved(request(), evaluation))
            self.assertEqual(outcome.final_status, OrchestrationStatus.PUBLISHED)
            self.assertEqual(never_gate.calls, 0)
            self.assertEqual(publisher.calls, 1)
        finally:
            database.close()

    def test_complete_sqlite_atomic_publication_integration(self):
        database = Database(":memory:")
        try:
            candidates = SQLiteOfficialPredictionCandidateRepository(database)
            registered = candidates.register_candidate_version(candidate().prepared).candidate
            assembly_request = request(prediction=prediction(
                registry_candidate_id=registered.registry_candidate_id,
                registry_content_fingerprint=registered.content_fingerprint,
            ))

            class Facts:
                def get(self, approved):
                    return OfficialPredictionPublicFacts(
                        approved.assembly.prediction_id,
                        approved.assembly.match_id,
                        approved.orchestration_id,
                        approved.quality_gate_evaluation.evaluation_id,
                        approved.candidate_fingerprint,
                        approved.assembly.gate_candidate.model_version,
                        approved.quality_gate_evaluation.policy_version,
                        "Premier League", "Home FC", "Away FC",
                        RiskProductScope.OFFICIAL,
                        RiskAssessmentDecision.ELIGIBLE,
                        stake(),
                        ApprovedPublicReasoning(("Home side has strong recent form.",)),
                    )

            class Telegram:
                def __init__(self):
                    self.calls = 0

                async def send_message(self, chat_id, text, parse_mode=None):
                    self.calls += 1
                    return 42

            telegram = Telegram()
            facts = Facts()
            destination = OfficialPredictionDestination(RiskProductScope.OFFICIAL, "official-channel")
            publisher = build_official_prediction_publisher_adapter(
                database, telegram, facts, destination, lambda: NOW
            )
            state_reader = SQLiteOfficialPublicationStateReader(database)
            gate_engine = OfficialPublicationQualityGate(DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY)
            gate_repository = SQLiteQualityGateEvaluationRepository(database, migrate=False)
            orchestration_service = OfficialPredictionOrchestrationService(
                OfficialPredictionCandidateAssembler(), OfficialCandidateFingerprint(), gate_engine,
                gate_repository, SQLiteOrchestrationHistoryRepository(database, migrate=False),
                state_reader, publisher,
            )
            publication_events = SQLiteAtomicPredictionPublicationRepository(database, migrate=False)
            pipeline_service = OfficialPredictionPipelineService(
                DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY,
                SQLiteCandidateRegistryStateAdapter(candidates),
                ExistingPublicationStateAdapter(state_reader, publication_events),
                PersistedQualityGateAdapter(gate_engine, gate_repository),
                ExistingPreapprovedOrchestrationAdapter(orchestration_service),
                ExistingMessagePreviewAdapter(
                    OfficialPredictionCandidateAssembler(), state_reader,
                    OfficialPredictionMessageBuilder(DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY),
                    facts, destination,
                ),
                SQLiteOfficialPredictionPipelineRepository(database, migrate=False),
            )
            command = pipeline_command(
                candidate=registered,
                candidate_id=registered.registry_candidate_id,
                candidate_fingerprint=registered.content_fingerprint,
                assembly_request=assembly_request,
            )
            outcome = asyncio.run(pipeline_service.execute(command))
            replay = asyncio.run(pipeline_service.execute(command))
            self.assertEqual(outcome.final_status, PipelineStatus.PUBLISHED)
            self.assertEqual(replay, outcome)
            self.assertEqual(telegram.calls, 1)
            self.assertEqual(len(gate_repository.history_for_prediction("prediction-1")), 1)
            self.assertEqual(len(publication_events.history("prediction-1")), 2)
        finally:
            database.close()

    def test_bounded_manual_batch_is_deterministic(self):
        value, _, _, _, _ = service()
        commands = (
            pipeline_command(pipeline_request_identity="request-2", candidate_id="candidate-2", candidate=replace(candidate(), registry_candidate_id="candidate-2"), assembly_request=replace(request(prediction=prediction(registry_candidate_id="candidate-2", registry_content_fingerprint=candidate().content_fingerprint)))),
            pipeline_command(),
        )
        # The second synthetic identity intentionally fails command/candidate content
        # verification, but the runner still isolates it and returns both outcomes.
        summary = asyncio.run(run_official_prediction_pipeline_batch(value, commands, DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY))
        self.assertEqual(summary.selected_count, 2)
        self.assertEqual(len(summary.outcomes), 2)


class OfficialPredictionPipelineMigrationTests(unittest.TestCase):
    def test_fresh_v22_schema_and_append_only_guards(self):
        database = Database(":memory:")
        try:
            MigrationManager(database.connection).migrate()
            versions = tuple(row[0] for row in database.connection.execute("SELECT version FROM schema_migrations ORDER BY version"))
            self.assertEqual(versions, tuple(range(1, 37)))
            tables = {row[0] for row in database.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("official_prediction_pipeline_executions", tables)
            self.assertIn("official_prediction_pipeline_stage_events", tables)
            self.assertEqual(MIGRATIONS[-1].version, 36)
        finally:
            database.close()

    def test_v21_to_v22_upgrade(self):
        database = Database(":memory:")
        try:
            original = tuple(MIGRATIONS)
            from app.database import migrations as module
            module.MIGRATIONS = tuple(item for item in original if item.version <= 21)
            MigrationManager(database.connection).migrate()
            module.MIGRATIONS = original
            MigrationManager(database.connection).migrate()
            self.assertEqual(database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 36)
        finally:
            module.MIGRATIONS = original
            database.close()

    def test_import_and_factory_have_no_execution_side_effect(self):
        import app.official_prediction_pipeline as pipeline
        self.assertFalse(pipeline.DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY.scheduling_enabled)
        self.assertFalse(pipeline.DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY.startup_execution_enabled)

    def test_repository_round_trip_queries_and_append_only_history(self):
        database = Database(":memory:")
        try:
            registered = SQLiteOfficialPredictionCandidateRepository(database).register_candidate_version(candidate().prepared).candidate
            memory_service, _, _, _, _ = service()
            base = asyncio.run(memory_service.execute(pipeline_command()))
            execution = replace(
                base,
                candidate_id=registered.registry_candidate_id,
                candidate_version=registered.candidate_version,
                candidate_fingerprint=registered.content_fingerprint,
                final_status=PipelineStatus.REJECTED_CANDIDATE_STATE,
                quality_gate_evaluation_id=None,
                quality_gate_status=None,
                quality_gate_fingerprint=None,
                orchestration_id=None,
                orchestration_status=None,
                orchestration_fingerprint=None,
                publication_event_id=None,
                publication_status=None,
                publication_fingerprint=None,
                publication_claim_identity=None,
                message_fingerprint=None,
                telegram_message_reference=None,
                pipeline_execution_id="pipeline-execution-round-trip",
                pipeline_fingerprint="pipeline-fingerprint-round-trip",
            )
            stage = PipelineStageEvent(
                "pipeline-stage-round-trip", execution.pipeline_execution_id, 1,
                PipelineStage.REQUEST_VALIDATION, "COMPLETED", None, None, (),
                (("stage", "REQUEST_VALIDATION"),), NOW,
            )
            repository = SQLiteOfficialPredictionPipelineRepository(database, migrate=False)
            stored = repository.append_pipeline_execution(execution, (stage,))
            self.assertEqual(stored, execution)
            self.assertEqual(repository.find_by_pipeline_fingerprint(execution.pipeline_fingerprint), execution)
            self.assertEqual(repository.load_execution_with_stages(execution.pipeline_execution_id).stages, (stage,))
            self.assertEqual(repository.list_executions_for_candidate(registered.registry_candidate_id), (execution,))
            with self.assertRaises(sqlite3.IntegrityError):
                database.connection.execute("UPDATE official_prediction_pipeline_executions SET match_id='x'")
            database.connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                database.connection.execute("DELETE FROM official_prediction_pipeline_stage_events")
        finally:
            database.close()


if __name__ == "__main__":
    unittest.main()
