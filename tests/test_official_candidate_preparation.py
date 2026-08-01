import sqlite3
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.official_candidate_preparation import (
    DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY,
    CandidatePreparationMappingError,
    CandidatePreparationConflictError,
    CandidatePreparationReason,
    CandidatePreparationStatus,
    OfficialBankrollPreparationContext,
    OfficialCandidatePreparationCommand,
    OfficialCandidatePreparationService,
    OfficialCandidateRegistrationFacts,
    OfficialExposurePreparationContext,
    SQLiteOfficialCandidatePreparationRepository,
    bankroll_context_fingerprint,
    build_official_candidate_preparation_service,
    exposure_context_fingerprint,
    prepare_official_candidate,
)
from app.official_prediction_candidate_registry import (
    CandidatePublicationGuardState,
    CandidateRegistrationStatus,
    OfficialPredictionCandidateRegistrationOutcome,
    OfficialPredictionReasoningFact,
    ReasoningFactType,
    SQLiteOfficialPredictionCandidateRepository,
    build_official_prediction_candidate_registry,
)
from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import (
    BankrollStateSnapshot,
    ExposureSnapshot,
    RiskAssessmentDecision,
    RiskAssessmentService,
    RiskProductScope,
    DEFAULT_OFFICIAL_RISK_POLICY,
)
from tests import test_official_prediction_selection as selection_fixture


class Guard:
    def state(self, prediction_id, match_id, evaluated_at):
        return CandidatePublicationGuardState.UNPUBLISHED


class CountingRisk:
    def __init__(self, mode="actual"):
        self.mode = mode
        self.calls = []
        self.actual = RiskAssessmentService(DEFAULT_OFFICIAL_RISK_POLICY)

    def assess(self, request, context):
        self.calls.append((request, context))
        if self.mode == "failure":
            raise RuntimeError("risk unavailable")
        audit = self.actual.assess(request, context)
        if self.mode == "review":
            return replace(audit, final_decision=RiskAssessmentDecision.REVIEW_REQUIRED)
        if self.mode == "ineligible":
            return replace(audit, final_decision=RiskAssessmentDecision.INELIGIBLE, recommendation=None)
        if self.mode == "reduced":
            return replace(audit, final_decision=RiskAssessmentDecision.REDUCED_STAKE)
        if self.mode == "malformed":
            return replace(audit, prediction_id="wrong-selection")
        return audit


class CountingRegistry:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    def register_candidate(self, command):
        self.calls.append(command)
        return self.delegate.register_candidate(command)


class StaticRegistry:
    def __init__(self, status):
        self.status = status
        self.calls = []

    def register_candidate(self, command):
        self.calls.append(command)
        return OfficialPredictionCandidateRegistrationOutcome(
            registry_candidate_id=None,
            prediction_id=command.prediction_id,
            match_id=command.match_id,
            logical_identity_fingerprint=None,
            candidate_content_fingerprint=None,
            candidate_version=None,
            final_status=self.status,
            ordered_reason_codes=(self.status.value,),
            explanations=("Registry terminal outcome.",),
            previous_candidate_id=None,
            registration_timestamp=command.registration_timestamp,
            model_version=command.model_version,
            market_identity=None,
        )


class PreexistingRegistry:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    def register_candidate(self, command):
        self.calls.append(command)
        self.delegate.register_candidate(command)
        return self.delegate.register_candidate(command)


class OfficialCandidatePreparationTests(unittest.TestCase):
    def setUp(self):
        self.selection_fixture = selection_fixture.OfficialPredictionSelectionTests()
        self.selection_fixture.setUp()
        outcome = self.selection_fixture.select()
        self.selection = outcome.decision
        self.database = self.selection_fixture.upstream.database
        self.preparations = SQLiteOfficialCandidatePreparationRepository(self.database)
        self.candidates = SQLiteOfficialPredictionCandidateRepository(self.database)
        registry = build_official_prediction_candidate_registry(
            self.database, publication_guard=Guard()
        )
        self.risk = CountingRisk()
        self.registry = CountingRegistry(registry)
        self.service = self.make_service(self.risk, self.registry)
        self.counter = 0

    def tearDown(self):
        self.selection_fixture.tearDown()

    def make_service(self, risk, registry):
        return OfficialCandidatePreparationService(
            repository=self.preparations,
            selections=self.selection_fixture.repository,
            assessments=self.selection_fixture.repository,
            risk_service=risk,
            candidate_registry=registry,
            candidate_lifecycle=self.candidates,
            policy=DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY,
        )

    def command(self, **changes):
        self.counter += 1
        selected_at = self.selection.selection_timestamp
        risk_at = selected_at + timedelta(seconds=10)
        prepared_at = selected_at + timedelta(seconds=20)
        state = BankrollStateSnapshot(
            product_scope=RiskProductScope.OFFICIAL,
            currency="EUR",
            opening_bankroll=Decimal("10000"),
            current_bankroll=Decimal("10000"),
            peak_bankroll=Decimal("10000"),
            current_drawdown_amount=Decimal("0"),
            current_drawdown_percentage=Decimal("0"),
            consecutive_wins=0,
            consecutive_losses=0,
            settled_bet_count=200,
            unsettled_exposure=Decimal("0"),
            snapshot_timestamp=selected_at,
            authoritative_source_reference="official-bankroll-ledger-v1",
        )
        bank = OfficialBankrollPreparationContext(
            snapshot_identity="official-bankroll-snapshot-1",
            fingerprint="",
            match_id=self.selection.match_id,
            kickoff_timestamp=self.selection.kickoff_timestamp,
            available_bankroll=Decimal("10000"),
            reserved_exposure=Decimal("0"),
            state=state,
        )
        bank = replace(bank, fingerprint=bankroll_context_fingerprint(bank))
        exposure = OfficialExposurePreparationContext(
            snapshot_identity="official-exposure-snapshot-1",
            fingerprint="",
            match_id=self.selection.match_id,
            kickoff_timestamp=self.selection.kickoff_timestamp,
            snapshot=ExposureSnapshot(
                product_scope=RiskProductScope.OFFICIAL,
                positions=(),
                snapshot_timestamp=selected_at,
                authoritative_source_reference="official-exposure-ledger-v1",
            ),
        )
        exposure = replace(
            exposure, fingerprint=exposure_context_fingerprint(exposure)
        )
        facts = OfficialCandidateRegistrationFacts(
            fixture_id=500,
            source_event_id="source-event-500",
            odds_source_id="book-a",
            competition_id="premier-league",
            competition_name="Premier League",
            home_team_id="home-team",
            home_team_name="Home FC",
            away_team_id="away-team",
            away_team_name="Away FC",
            raw_model_probability=Decimal("0.55"),
            core_match_data_timestamp=selected_at,
            lineup_status=LineupStatus.MISSING,
            lineup_data_timestamp=None,
            injury_suspension_status=FactStatus.MISSING,
            injury_suspension_data_timestamp=None,
            confidence_level=ConfidenceLevel.HIGH,
            public_reasoning_facts=(
                OfficialPredictionReasoningFact(
                    ReasoningFactType.MARKET_STATISTICAL_EVIDENCE,
                    "The calibrated model probability exceeds the supplied market baseline.",
                    "selection-history-v1",
                ),
            ),
            source_data_version="feature-snapshot-v1",
            supporting_data_status=FactStatus.AVAILABLE,
            market_availability=MarketAvailability.AVAILABLE,
            model_confidence=Decimal("0.75"),
            uncertainty=Decimal("0.15"),
            calibration_sample_size=200,
            model_sample_size=200,
            team_ids=("away-team", "home-team"),
            market_family="match-result",
            model_name="goalvision-model",
            calibration_artifact_references=(self.selection.calibration_set_fingerprint,),
        )
        values = dict(
            integration_request_identity=f"candidate-preparation-request-{self.counter}",
            selection=self.selection,
            bankroll=bank,
            exposure=exposure,
            candidate_facts=facts,
            risk_assessment_timestamp=risk_at,
            candidate_preparation_timestamp=prepared_at,
            bankroll_scope=RiskProductScope.OFFICIAL,
            destination_scope=RiskProductScope.OFFICIAL,
            integration_policy_version=DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY.version,
            source_run_identity="official-run-1",
            metadata=(("source_stage", "official-selection"),),
        )
        values.update(changes)
        return OfficialCandidatePreparationCommand(**values)

    def test_eligible_registers_once_preserves_stake_and_provenance(self):
        result = prepare_official_candidate(self.service, self.command())
        self.assertEqual(result.final_status, CandidatePreparationStatus.CANDIDATE_REGISTERED)
        self.assertEqual(len(self.risk.calls), 1)
        self.assertEqual(len(self.registry.calls), 1)
        self.assertIsNone(self.risk.calls[0][0].quality_gate_status)
        self.assertEqual(self.risk.calls[0][0].assessment_phase.value, "PRE_PUBLICATION_GATE")
        self.assertEqual(result.stake_recommendation.final_stake, Decimal("100.00"))
        candidate = self.candidates.find_candidate_by_id(result.registry_candidate_id)
        provenance = dict(candidate.prepared.provenance)
        self.assertEqual(provenance["selection_fingerprint"], self.selection.selection_fingerprint)
        self.assertEqual(provenance["risk_assessment_id"], result.risk_assessment_id)
        self.assertEqual(provenance["stake_amount"], "100.00")

    def test_reduced_stake_is_preserved_exactly(self):
        risk = CountingRisk("reduced")
        service = self.make_service(risk, self.registry)
        result = service.prepare_official_candidate(self.command())
        self.assertEqual(result.risk_outcome, RiskAssessmentDecision.REDUCED_STAKE)
        self.assertEqual(result.stake_recommendation, risk.calls and self.preparations.load_execution_with_risk_snapshot(result.integration_execution_id).risk_snapshot.audit.recommendation)

    def test_review_and_ineligible_never_call_registry(self):
        for mode, status in (
            ("review", CandidatePreparationStatus.NO_REGISTRATION_REVIEW_REQUIRED),
            ("ineligible", CandidatePreparationStatus.NO_REGISTRATION_INELIGIBLE),
        ):
            with self.subTest(mode=mode):
                registry = StaticRegistry(CandidateRegistrationStatus.REGISTERED)
                risk = CountingRisk(mode)
                result = self.make_service(risk, registry).prepare_official_candidate(self.command())
                self.assertEqual(result.final_status, status)
                self.assertEqual(len(risk.calls), 1)
                self.assertEqual(registry.calls, [])
                self.assertIsNone(result.registry_candidate_id)
                with self.assertRaises(CandidatePreparationMappingError):
                    self.make_service(risk, registry).quality_gate_handoff(
                        result.integration_execution_id
                    )
        self.assertEqual(len(self.preparations.list_no_registration_decisions()), 2)

    def test_risk_failure_and_malformed_result_never_call_registry(self):
        for mode, status in (
            ("failure", CandidatePreparationStatus.RISK_EXECUTION_FAILED),
            ("malformed", CandidatePreparationStatus.REJECTED_INVALID_RISK_RESULT),
        ):
            with self.subTest(mode=mode):
                registry = StaticRegistry(CandidateRegistrationStatus.REGISTERED)
                result = self.make_service(CountingRisk(mode), registry).prepare_official_candidate(self.command())
                self.assertEqual(result.final_status, status)
                self.assertEqual(registry.calls, [])

    def test_invalid_provenance_and_scope_fail_before_risk(self):
        bad_bank = replace(self.command().bankroll, fingerprint="0" * 64)
        result = self.service.prepare_official_candidate(self.command(bankroll=bad_bank))
        self.assertEqual(result.final_status, CandidatePreparationStatus.REJECTED_PROVENANCE)
        result = self.service.prepare_official_candidate(self.command(destination_scope=RiskProductScope.LIVE))
        self.assertEqual(result.final_status, CandidatePreparationStatus.REJECTED_SCOPE)
        self.assertEqual(self.risk.calls, [])

    def test_no_selection_and_tampered_selection_fail_before_risk(self):
        no_selection = self.selection_fixture.select(()).decision
        result = self.service.prepare_official_candidate(
            self.command(selection=no_selection)
        )
        self.assertEqual(result.final_status, CandidatePreparationStatus.REJECTED_INVALID_REQUEST)
        tampered = replace(self.selection, selection_fingerprint="0" * 64)
        result = self.service.prepare_official_candidate(
            self.command(selection=tampered)
        )
        self.assertEqual(result.final_status, CandidatePreparationStatus.REJECTED_PROVENANCE)
        self.assertEqual(self.risk.calls, [])

    def test_factory_has_no_execution_side_effect(self):
        before = self.database.connection.execute(
            "SELECT COUNT(*) FROM official_candidate_preparation_executions"
        ).fetchone()[0]
        built = build_official_candidate_preparation_service(
            preparation_repository=self.preparations,
            selection_repository=self.selection_fixture.repository,
            value_assessment_repository=self.selection_fixture.repository,
            risk_service=self.risk,
            candidate_registry=self.registry,
            candidate_lifecycle=self.candidates,
            policy=DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY,
        )
        after = self.database.connection.execute(
            "SELECT COUNT(*) FROM official_candidate_preparation_executions"
        ).fetchone()[0]
        self.assertIsNotNone(built)
        self.assertEqual((before, after), (0, 0))

    def test_status_contract_is_exact(self):
        self.assertEqual(
            tuple(item.value for item in CandidatePreparationStatus),
            (
                "CANDIDATE_REGISTERED", "IDEMPOTENT_EXISTING",
                "NO_REGISTRATION_INELIGIBLE", "NO_REGISTRATION_REVIEW_REQUIRED",
                "REJECTED_INVALID_REQUEST", "REJECTED_PROVENANCE", "REJECTED_SCOPE",
                "REJECTED_INVALID_RISK_RESULT", "RISK_EXECUTION_FAILED",
                "CANDIDATE_REGISTRATION_REJECTED", "ALREADY_PUBLISHED",
                "CORRECTION_REQUIRED", "CONFLICT", "PERSISTENCE_FAILURE",
            ),
        )

    def test_exact_retry_does_not_repeat_risk_or_registry(self):
        command = self.command()
        first = self.service.prepare_official_candidate(command)
        second = self.service.prepare_official_candidate(command)
        self.assertEqual(first.final_status, CandidatePreparationStatus.CANDIDATE_REGISTERED)
        self.assertEqual(second.final_status, CandidatePreparationStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(len(self.risk.calls), 1)
        self.assertEqual(len(self.registry.calls), 1)
        self.assertEqual(first.integration_execution_id, second.integration_execution_id)

    def test_request_identity_conflict_fails_before_second_risk_call(self):
        command = self.command()
        self.service.prepare_official_candidate(command)
        changed = replace(command, metadata=(("source_stage", "changed"),))
        result = self.service.prepare_official_candidate(changed)
        self.assertEqual(result.final_status, CandidatePreparationStatus.CONFLICT)
        self.assertEqual(len(self.risk.calls), 1)

    def test_registry_terminal_status_mapping(self):
        expected = {
            CandidateRegistrationStatus.REJECTED_INVALID: CandidatePreparationStatus.CANDIDATE_REGISTRATION_REJECTED,
            CandidateRegistrationStatus.REJECTED_SCOPE: CandidatePreparationStatus.REJECTED_SCOPE,
            CandidateRegistrationStatus.ALREADY_PUBLISHED: CandidatePreparationStatus.ALREADY_PUBLISHED,
            CandidateRegistrationStatus.CORRECTION_REQUIRED: CandidatePreparationStatus.CORRECTION_REQUIRED,
            CandidateRegistrationStatus.CONFLICT: CandidatePreparationStatus.CONFLICT,
            CandidateRegistrationStatus.PERSISTENCE_FAILURE: CandidatePreparationStatus.PERSISTENCE_FAILURE,
        }
        for registry_status, integration_status in expected.items():
            with self.subTest(status=registry_status):
                registry = StaticRegistry(registry_status)
                result = self.make_service(CountingRisk(), registry).prepare_official_candidate(self.command())
                self.assertEqual(result.final_status, integration_status)
                self.assertEqual(len(registry.calls), 1)

    def test_registry_idempotent_existing_maps_without_service_retry(self):
        delegate = build_official_prediction_candidate_registry(
            self.database, publication_guard=Guard()
        )
        registry = PreexistingRegistry(delegate)
        service = self.make_service(CountingRisk(), registry)
        result = service.prepare_official_candidate(self.command())
        self.assertEqual(
            result.final_status,
            CandidatePreparationStatus.IDEMPOTENT_EXISTING,
        )
        self.assertEqual(len(registry.calls), 1)
        self.assertIsNotNone(result.registry_candidate_id)
        self.assertEqual(
            service.quality_gate_handoff(result.integration_execution_id).candidate.registry_candidate_id,
            result.registry_candidate_id,
        )

    def test_persistence_queries_risk_snapshot_and_immutability(self):
        result = self.service.prepare_official_candidate(self.command())
        stored = self.preparations.load_execution_with_risk_snapshot(result.integration_execution_id)
        self.assertEqual(stored.execution, result.execution)
        self.assertEqual(stored.risk_snapshot.audit.recommendation, result.stake_recommendation)
        self.assertEqual(self.preparations.find_by_integration_fingerprint(result.integration_fingerprint), result.execution)
        self.assertEqual(self.preparations.list_executions_for_selection(self.selection.selection_decision_id), (result.execution,))
        self.assertEqual(self.preparations.list_executions_for_match(self.selection.match_id), (result.execution,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("UPDATE official_candidate_preparation_executions SET match_id = 'x'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("DELETE FROM official_candidate_preparation_risk_snapshots")

    def test_risk_snapshot_failure_rolls_back_execution(self):
        result = self.service.prepare_official_candidate(self.command())
        stored = self.preparations.load_execution_with_risk_snapshot(
            result.integration_execution_id
        )
        execution = replace(
            stored.execution,
            integration_execution_id="candidate-preparation-rollback-test",
            integration_request_identity="candidate-preparation-rollback-request",
            preparation_request_fingerprint="1" * 64,
            integration_fingerprint="2" * 64,
        )
        with self.assertRaises(CandidatePreparationConflictError):
            self.preparations.append_preparation_execution(
                execution,
                stored.risk_snapshot,
            )
        self.assertIsNone(
            self.preparations.load_preparation_execution(
                "candidate-preparation-rollback-test"
            )
        )

    def test_quality_gate_handoff_is_typed_and_does_not_run_gate(self):
        result = self.service.prepare_official_candidate(self.command())
        handoff = self.service.quality_gate_handoff(result.integration_execution_id)
        self.assertEqual(handoff.candidate.registry_candidate_id, result.registry_candidate_id)
        self.assertEqual(handoff.risk_evaluation.evaluation_id, result.risk_assessment_id)
        self.assertEqual(handoff.bankroll.reference_id, "official-bankroll-snapshot-1")

    def test_quality_gate_handoff_rejects_non_ready_lifecycle(self):
        first = self.service.prepare_official_candidate(self.command())
        second = self.service.prepare_official_candidate(self.command())
        self.assertEqual(
            second.ordered_reason_codes,
            (CandidatePreparationReason.CANDIDATE_SUPERSEDED_PREVIOUS,),
        )
        with self.assertRaises(CandidatePreparationMappingError):
            self.service.quality_gate_handoff(first.integration_execution_id)
        self.candidates.invalidate_candidate(
            second.registry_candidate_id,
            "INVALID_TEST_PROVENANCE",
            second.candidate_preparation_timestamp + timedelta(seconds=1),
        )
        with self.assertRaises(CandidatePreparationMappingError):
            self.service.quality_gate_handoff(second.integration_execution_id)

    def test_quality_gate_handoff_rejects_withdrawn_candidate(self):
        result = self.service.prepare_official_candidate(self.command())
        self.candidates.withdraw_candidate(
            result.registry_candidate_id,
            "WITHDRAWN_FOR_TEST",
            result.candidate_preparation_timestamp + timedelta(seconds=1),
        )
        with self.assertRaises(CandidatePreparationMappingError):
            self.service.quality_gate_handoff(result.integration_execution_id)

    def test_models_are_immutable_and_repeatable(self):
        command = self.command()
        with self.assertRaises(FrozenInstanceError):
            command.integration_request_identity = "changed"
        first = self.service.prepare_official_candidate(command)
        stored = self.preparations.load_execution_with_risk_snapshot(first.integration_execution_id)
        self.assertEqual(first.integration_fingerprint, stored.execution.integration_fingerprint)


class CandidatePreparationMigrationTests(unittest.TestCase):
    def test_fresh_v21_and_v20_upgrade(self):
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 37)
        tables = {row[0] for row in fresh.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("official_candidate_preparation_executions", tables)
        self.assertIn("official_candidate_preparation_risk_snapshots", tables)
        columns = {row[1] for row in fresh.connection.execute("PRAGMA table_info(official_prediction_candidate_versions)")}
        self.assertIn("provenance_snapshot", columns)
        upgrade = Database(":memory:")
        upgrade.connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS:
            if migration.version > 20:
                break
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 37)
        fresh.close()
        upgrade.close()


if __name__ == "__main__":
    unittest.main()
