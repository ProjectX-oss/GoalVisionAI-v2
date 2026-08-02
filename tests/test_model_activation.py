import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.model_activation import (
    ActivationEvidence, ActivationExecutionCommand, ActivationPlan,
    ActivationNotEligibleError,
    ActivationRequest, ActivationStatus, ActivationStalePlanError,
    ActivationValidation, ChampionResolution, GenerationReason,
    ModelActivationPolicy, RollbackExecutionCommand, RollbackPlan,
    RollbackRequest, RuntimeArtifactReference, RuntimeChampionResolver,
    ModelActivationService,
    SQLiteModelActivationRepository, ValidationStatus, canonical_json,
    sha256_fingerprint,
)
from app.model_activation.validation import evaluate_evidence

UTC = timezone.utc
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def artifact(name):
    return RuntimeArtifactReference(
        model_artifact_id=f"model-{name}", model_artifact_fingerprint=f"model-fp-{name}",
        preprocessing_fingerprint=f"pre-fp-{name}",
        calibration_artifact_set_id=f"cal-{name}",
        calibration_artifact_set_fingerprint=f"cal-fp-{name}",
        feature_schema_version="historical_training_features_v1",
        feature_schema_fingerprint="schema-fp",
        target_contract_version="official_prediction_targets_v1",
        probability_contract_version="canonical-11-target-contract-v1",
        runtime_compatibility_version="probability-calibration-v1",
    )


def evidence(count=30):
    base = ActivationEvidence(
        settled_count=count, observation_days=Decimal("14"),
        agreement_ratio=Decimal(".8"), critical_disagreement_ratio=Decimal(".05"),
        predictive_degradation=Decimal("0"), calibration_degradation=Decimal("0"),
        betting_performance_degradation=Decimal("0"),
        drawdown_deterioration=Decimal("0"),
        evidence_completeness=Decimal("1"), shadow_execution_ids=(),
        shadow_execution_fingerprints=(), shadow_settlement_fingerprints=(),
        evidence_fingerprint="pending",
    )
    return replace(base, evidence_fingerprint=sha256_fingerprint(base))


def request(current, challenger):
    return ActivationRequest(
        activation_request_id="activate-1", activation_name="Promote B",
        model_scope="OFFICIAL_GLOBAL",
        current_champion_generation_id=current.champion_generation_id,
        current_champion_generation_fingerprint=current.generation_fingerprint,
        current_champion=current.artifact, challenger=challenger,
        comparison_run_id="comparison-1", comparison_run_fingerprint="comparison-fp",
        challenger_candidate_id="candidate-1", recommendation_id="recommendation-1",
        recommendation_fingerprint="recommendation-fp",
        evidence_cutoff_timestamp_utc=NOW, requested_timestamp_utc=NOW,
        activation_reason="Reviewed shadow evidence", operator_identity="operator-1",
    )


def activation_plan(current, challenger, suffix="1"):
    req = replace(request(current, challenger), activation_request_id=f"activate-{suffix}")
    ev = evidence()
    validation = ActivationValidation(
        f"validation-{suffix}", "EVIDENCE", "ALL_GATES", ValidationStatus.PASS,
        "{}", f"validation-fp-{suffix}", 0,
    )
    request_fp = sha256_fingerprint(req)
    core = (request_fp, current.generation_fingerprint, ev.evidence_fingerprint, suffix)
    plan_fp = sha256_fingerprint(core)
    return ActivationPlan(
        f"activation-plan-{suffix}", req, request_fp, current.generation_number,
        current.generation_fingerprint, (validation,), ev, "{}",
        "2026-08-01T12:00:00Z", plan_fp,
    )


def rollback_plan(current, target):
    req = RollbackRequest(
        "rollback-1", "Rollback incident", "OFFICIAL_GLOBAL",
        current.champion_generation_id, current.generation_fingerprint,
        target.champion_generation_id, "Model incident", "INC-1", "operator-1", NOW,
    )
    validation = ActivationValidation(
        "rollback-validation", "ROLLBACK", "TARGET_RUNTIME_COMPATIBLE",
        ValidationStatus.PASS, "{}", "rollback-validation-fp", 0,
    )
    request_fp = sha256_fingerprint(req)
    plan_fp = sha256_fingerprint((request_fp, current.generation_fingerprint, target.generation_fingerprint))
    return RollbackPlan(
        "rollback-plan-1", req, request_fp, current.generation_number,
        current.generation_fingerprint, target, (validation,), "{}",
        "2026-08-01T12:00:00Z", plan_fp,
    )


class ModelActivationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteModelActivationRepository(self.database)
        self.database.connection.execute("PRAGMA foreign_keys=OFF")
        self.initial = self.repository.bootstrap_champion(
            "OFFICIAL_GLOBAL", artifact("a"), NOW, "Existing production champion", "operator-1",
        )

    def service(self):
        return ModelActivationService(
            self.repository, object(), object(), object(), object(),
            ModelActivationPolicy(),
        )

    def test_service_valid_prepare_and_execute_only_switches_at_execution(self):
        service = self.service()
        req = request(self.initial, artifact("b"))
        with (
            patch("app.model_activation.service.verify_promotion"),
            patch("app.model_activation.service.verify_runtime_artifact"),
            patch("app.model_activation.service.build_activation_evidence", return_value=evidence()),
        ):
            prepared = service.prepare_activation(req)
            self.assertEqual(prepared.status, ActivationStatus.ACTIVATION_PLAN_PREPARED)
            self.assertEqual(self.repository.resolve_current_champion("OFFICIAL_GLOBAL"), self.initial)
            executed = service.execute_activation(ActivationExecutionCommand(
                "execute-service-1", prepared.plan_id, prepared.plan_fingerprint,
                NOW, "operator-1",
            ))
        self.assertEqual(executed.status, ActivationStatus.ACTIVATION_EXECUTED)
        self.assertEqual(executed.champion_generation.artifact, artifact("b"))

    def test_service_missing_promotion_or_insufficient_shadow_is_not_eligible(self):
        service = self.service()
        req = request(self.initial, artifact("b"))
        with patch(
            "app.model_activation.service.verify_promotion",
            side_effect=ActivationNotEligibleError("missing promotion"),
        ):
            missing = service.prepare_activation(req)
        self.assertEqual(missing.status, ActivationStatus.ACTIVATION_NOT_ELIGIBLE)
        with (
            patch("app.model_activation.service.verify_promotion"),
            patch("app.model_activation.service.verify_runtime_artifact"),
            patch("app.model_activation.service.build_activation_evidence", return_value=evidence(29)),
        ):
            insufficient = service.prepare_activation(req)
        self.assertEqual(insufficient.status, ActivationStatus.ACTIVATION_NOT_ELIGIBLE)

    def test_service_manual_rollback_is_two_stage(self):
        activation = activation_plan(self.initial, artifact("b"))
        self.repository.append_activation_plan(activation)
        promoted, _ = self.repository.execute_activation(activation, "execute-1", NOW, "operator-1")
        service = self.service()
        req = RollbackRequest(
            "rollback-service-1", "Incident rollback", "OFFICIAL_GLOBAL",
            promoted.champion_generation_id, promoted.generation_fingerprint,
            self.initial.champion_generation_id, "Observed incident", "INC-2",
            "operator-1", NOW,
        )
        with patch("app.model_activation.service.verify_runtime_artifact"):
            prepared = service.prepare_rollback(req)
            self.assertEqual(prepared.status, ActivationStatus.ROLLBACK_PLAN_PREPARED)
            self.assertEqual(self.repository.resolve_current_champion("OFFICIAL_GLOBAL"), promoted)
            executed = service.execute_rollback(RollbackExecutionCommand(
                "rollback-service-execute-1", prepared.plan_id,
                prepared.plan_fingerprint, NOW, "operator-1",
            ))
        self.assertEqual(executed.status, ActivationStatus.ROLLBACK_EXECUTED)
        self.assertEqual(executed.champion_generation.artifact, self.initial.artifact)

    def test_prepare_plan_persistence_has_no_runtime_effect(self):
        plan = activation_plan(self.initial, artifact("b"))
        self.repository.append_activation_plan(plan)
        self.assertEqual(self.repository.resolve_current_champion("OFFICIAL_GLOBAL"), self.initial)
        loaded = self.repository.load_activation_plan(plan.activation_plan_id)
        self.assertEqual(loaded.activation_plan_fingerprint, plan.activation_plan_fingerprint)
        self.assertEqual(loaded.evidence, plan.evidence)

    def test_valid_activation_and_duplicate_execution_are_atomic_and_idempotent(self):
        plan = activation_plan(self.initial, artifact("b"))
        self.repository.append_activation_plan(plan)
        generation, replay = self.repository.execute_activation(plan, "execute-1", NOW, "operator-1")
        self.assertFalse(replay)
        self.assertEqual(generation.generation_number, 2)
        self.assertEqual(generation.artifact, artifact("b"))
        self.assertEqual(generation.activation_reason, GenerationReason.APPROVED_ACTIVATION)
        replayed, replay = self.repository.execute_activation(plan, "execute-1", NOW, "operator-1")
        self.assertTrue(replay)
        self.assertEqual(replayed, generation)
        self.assertEqual(len(self.repository.list_generations("OFFICIAL_GLOBAL")), 2)

    def test_concurrent_pending_plan_and_stale_plan_are_rejected(self):
        first = activation_plan(self.initial, artifact("b"), "1")
        conflicting = activation_plan(self.initial, artifact("c"), "2")
        self.repository.append_activation_plan(first)
        with self.assertRaises(Exception):
            self.repository.append_activation_plan(conflicting)
        stale = replace(first, expected_registry_fingerprint="stale-registry")
        with self.assertRaises(ActivationStalePlanError):
            self.repository.execute_activation(stale, "execute-2", NOW, "operator-1")

    def test_manual_rollback_appends_new_generation_and_preserves_failed_champion(self):
        activation = activation_plan(self.initial, artifact("b"))
        self.repository.append_activation_plan(activation)
        promoted, _ = self.repository.execute_activation(activation, "execute-1", NOW, "operator-1")
        plan = rollback_plan(promoted, self.initial)
        self.repository.append_rollback_plan(plan)
        rolled_back, replay = self.repository.execute_rollback(plan, "rollback-execute-1", NOW, "operator-1")
        self.assertFalse(replay)
        self.assertEqual(rolled_back.generation_number, 3)
        self.assertEqual(rolled_back.artifact, self.initial.artifact)
        self.assertEqual(rolled_back.previous_champion_generation_id, promoted.champion_generation_id)
        self.assertEqual(len(self.repository.list_generations("OFFICIAL_GLOBAL")), 3)

    def test_database_failure_rolls_back_generation_and_never_loses_champion(self):
        plan = activation_plan(self.initial, artifact("b"))
        self.repository.append_activation_plan(plan)
        self.database.connection.execute(
            """CREATE TRIGGER fail_activation_event BEFORE INSERT ON model_champion_registry_events
               WHEN NEW.event_type='CHAMPION_ACTIVATED'
               BEGIN SELECT RAISE(ABORT,'injected failure'); END"""
        )
        with self.assertRaises(Exception):
            self.repository.execute_activation(plan, "execute-1", NOW, "operator-1")
        self.assertEqual(self.repository.resolve_current_champion("OFFICIAL_GLOBAL"), self.initial)
        self.assertEqual(len(self.repository.list_generations("OFFICIAL_GLOBAL")), 1)

    def test_append_only_triggers_reject_mutation(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.database.connection.execute(
                "UPDATE model_champion_generations SET model_scope='changed' WHERE champion_generation_id=?",
                (self.initial.champion_generation_id,),
            )
        with self.assertRaises(sqlite3.DatabaseError):
            self.database.connection.execute(
                "DELETE FROM model_champion_generations WHERE champion_generation_id=?",
                (self.initial.champion_generation_id,),
            )

    def test_runtime_resolver_is_read_only_and_fails_closed(self):
        resolver = RuntimeChampionResolver(self.repository, object(), object(), ModelActivationPolicy())
        with patch("app.model_activation.source_verification.verify_runtime_artifact", return_value=(object(), object())):
            outcome = resolver.resolve("OFFICIAL_GLOBAL")
        self.assertEqual(outcome.status, ActivationStatus.CHAMPION_RESOLVED)
        self.assertEqual(outcome.champion_generation, self.initial)
        invalid = resolver.resolve("UNINITIALIZED")
        self.assertEqual(invalid.status, ActivationStatus.CHAMPION_STATE_INVALID)
        self.assertIsNone(invalid.champion_generation)

    def test_conservative_evidence_policy_rejects_partial_samples(self):
        with self.assertRaises(Exception):
            evaluate_evidence(evidence(29), ModelActivationPolicy())
        validations = evaluate_evidence(evidence(30), ModelActivationPolicy())
        self.assertTrue(all(item.status is ValidationStatus.PASS for item in validations))


class ModelActivationMigrationTests(unittest.TestCase):
    def test_fresh_v31_migration_and_immutable_tables(self):
        database = Database(":memory:")
        MigrationManager(database.connection).migrate()
        self.assertEqual(database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 40)
        tables = database.connection.execute(
            """SELECT name FROM sqlite_master WHERE type='table' AND
               (name LIKE 'model_activation_%' OR name LIKE 'model_rollback_%' OR name LIKE 'model_champion_%')"""
        ).fetchall()
        triggers = database.connection.execute(
            """SELECT name FROM sqlite_master WHERE type='trigger' AND
               (name LIKE 'model_activation_%' OR name LIKE 'model_rollback_%' OR name LIKE 'model_champion_%')"""
        ).fetchall()
        self.assertEqual(len(tables), 10)
        self.assertEqual(len(triggers), 20)

    def test_v30_upgrades_to_v31_without_rewriting_history(self):
        database = Database(":memory:")
        connection = database.connection
        connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS[:-1]:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations VALUES (?, 'prior')", (migration.version,))
        connection.commit()
        MigrationManager(connection).migrate()
        versions = tuple(row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version"))
        self.assertEqual(versions, tuple(range(1, 41)))


if __name__ == "__main__":
    unittest.main()
