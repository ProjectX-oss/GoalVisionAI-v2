import json
import hashlib
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.model_activation_audit.formatting import format_human, format_json, redact
from app.model_activation_audit.models import (
    AuditCheck,
    AuditSeverity,
    AuditStatus,
    StagingReadiness,
)
from app.model_activation_audit.policy import assess_staging_readiness
from app.model_activation_audit.repository import ReadOnlyAuditRepository
from app.model_activation_audit.service import ModelActivationAuditService
from app.model_operations_rehearsal.execution import (
    execute_activation_rollback_rehearsal,
)


SOURCE_COMMIT = "5ad132885b876d59b3e4c1f7f811980e77784b5e"
GENERATED_AT = "2026-07-25T00:30:00Z"


class ModelActivationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path("var") / "test_model_activation_audit" / uuid4().hex
        cls.root.mkdir(parents=True)
        source = cls.root / "source.db"
        source.write_bytes(b"")
        timestamp = "20260725T020000Z"
        cls.rehearsal = execute_activation_rollback_rehearsal(
            source_database=source,
            destination_directory=cls.root,
            timestamp=timestamp,
        )
        cls.database = (
            cls.root / f"goalvision_activation_rollback_{timestamp}.db"
        )
        cls.source = source

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def audit(self, database=None):
        repository = ReadOnlyAuditRepository(str(database or self.database))
        try:
            return ModelActivationAuditService(repository).audit(
                source_commit=SOURCE_COMMIT,
                generated_timestamp_utc=GENERATED_AT,
                environment="LAB",
                scope="OFFICIAL_GLOBAL",
            )
        finally:
            repository.close()

    def corrupt_copy(self, name, statements):
        target = self.root / f"{name}-{uuid4().hex}.db"
        shutil.copy2(self.database, target)
        connection = sqlite3.connect(target)
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            for statement in statements:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()
        return target

    def check(self, report, check_id):
        return next(item for item in report.checks if item.check_id == check_id)

    def test_audit_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "app.model_activation_audit.cli", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("read-only", result.stdout)
        self.assertNotIn("execute-activation", result.stdout)

    def test_human_json_success_and_deterministic_fingerprint(self):
        first = self.audit()
        second = self.audit()
        self.assertEqual(first.overall_status, AuditStatus.AUDIT_PASSED)
        self.assertEqual(
            first.staging_readiness,
            StagingReadiness.STAGING_REHEARSAL_READY,
        )
        self.assertEqual(first.audit_fingerprint, second.audit_fingerprint)
        self.assertIn("AUDIT_PASSED", format_human(first))
        document = json.loads(format_json(first))
        self.assertEqual(document["schema_version"], first.schema_version)
        self.assertEqual(document["audit_fingerprint"], first.audit_fingerprint)

    def test_schema_success_and_deterministic_severity_counts(self):
        report = self.audit()
        self.assertEqual(self.check(report, "schema.version").severity, AuditSeverity.PASS)
        self.assertEqual(
            dict(report.summary_counts),
            {"PASS": 35, "INFO": 0, "WARNING": 0, "BLOCKER": 0},
        )

    def test_missing_table_is_blocker(self):
        target = self.corrupt_copy(
            "missing-table",
            (
                "DROP TRIGGER model_activation_evidence_links_no_update",
                "DROP TRIGGER model_activation_evidence_links_no_delete",
                "DROP TABLE model_activation_evidence_links",
            ),
        )
        report = self.audit(target)
        self.assertEqual(report.overall_status, AuditStatus.AUDIT_BLOCKED)
        self.assertEqual(self.check(report, "schema.tables").severity, AuditSeverity.BLOCKER)

    def test_missing_trigger_is_blocker(self):
        target = self.corrupt_copy(
            "missing-trigger",
            ("DROP TRIGGER model_activation_plans_no_update",),
        )
        self.assertEqual(
            self.check(self.audit(target), "schema.append_only_triggers").severity,
            AuditSeverity.BLOCKER,
        )

    def test_duplicate_active_generation_is_blocker(self):
        class DuplicateGenerationRepository(ReadOnlyAuditRepository):
            def scalar(self, sql, parameters=()):
                if "GROUP BY model_scope,generation_number" in sql:
                    return 1
                return super().scalar(sql, parameters)

        repository = DuplicateGenerationRepository(str(self.database))
        try:
            report = ModelActivationAuditService(repository).audit(
                source_commit=SOURCE_COMMIT,
                generated_timestamp_utc=GENERATED_AT,
                environment="LAB",
                scope="OFFICIAL_GLOBAL",
            )
        finally:
            repository.close()
        self.assertEqual(
            self.check(report, "registry.current_enforcement").severity,
            AuditSeverity.BLOCKER,
        )

    def test_broken_generation_chain_is_blocker(self):
        target = self.corrupt_copy(
            "broken-chain",
            (
                "DROP TRIGGER model_champion_generations_no_update",
                """UPDATE model_champion_generations
                   SET previous_champion_generation_id=NULL
                   WHERE generation_number=2""",
            ),
        )
        self.assertEqual(
            self.check(self.audit(target), "registry.generation_chain").severity,
            AuditSeverity.BLOCKER,
        )

    def test_orphan_registry_event_is_blocker(self):
        target = self.corrupt_copy(
            "orphan-event",
            (
                """INSERT INTO model_champion_registry_events VALUES
                   ('orphan','OFFICIAL_GLOBAL','missing',99,'INITIAL_REGISTERED',
                    'test','2026-08-02T00:00:00Z','orphan-fingerprint')""",
            ),
        )
        self.assertEqual(
            self.check(self.audit(target), "registry.events_referential").severity,
            AuditSeverity.BLOCKER,
        )

    def test_missing_activation_and_shadow_evidence_are_blockers(self):
        target = self.corrupt_copy(
            "missing-evidence",
            (
                "DROP TRIGGER model_activation_evidence_links_no_delete",
                "DELETE FROM model_activation_evidence_links",
            ),
        )
        report = self.audit(target)
        self.assertEqual(
            self.check(report, "activation.shadow_evidence").severity,
            AuditSeverity.BLOCKER,
        )

    def test_invalid_promotion_outcome_is_blocker(self):
        target = self.corrupt_copy(
            "invalid-promotion",
            (
                "DROP TRIGGER model_comparison_recommendations_no_update",
                """UPDATE model_comparison_recommendations
                   SET recommendation='KEEP_CHAMPION'
                   WHERE recommendation='PROMOTE_CHALLENGER'""",
            ),
        )
        self.assertEqual(
            self.check(self.audit(target), "activation.promotion").severity,
            AuditSeverity.BLOCKER,
        )

    def test_rollback_target_and_generation_semantics(self):
        report = self.audit()
        self.assertEqual(self.check(report, "rollback.target_validity").severity, AuditSeverity.PASS)
        self.assertEqual(self.check(report, "rollback.generation_semantics").severity, AuditSeverity.PASS)

    def test_resolver_match_and_mismatch_blocker(self):
        report = self.audit()
        self.assertEqual(self.check(report, "resolver.fail_closed").severity, AuditSeverity.PASS)
        target = self.corrupt_copy(
            "artifact-mismatch",
            (
                "DROP TRIGGER model_champion_generations_no_update",
                """UPDATE model_champion_generations
                   SET generation_snapshot=replace(
                     generation_snapshot,
                     'historical_training_features_v1',
                     'corrupt-feature-schema')
                   WHERE generation_number=2""",
            ),
        )
        self.assertEqual(
            self.check(self.audit(target), "activation.artifact_provenance").severity,
            AuditSeverity.BLOCKER,
        )

    def test_cli_confirmation_no_yes_no_telegram_and_no_startup_path(self):
        report = self.audit()
        for check_id in (
            "cli.confirmations",
            "cli.no_side_effect_integrations",
            "resolver.runtime_unwired",
        ):
            self.assertEqual(self.check(report, check_id).severity, AuditSeverity.PASS)

    def test_rehearsal_hash_atomicity_and_runbook_guidance(self):
        self.assertEqual(
            self.rehearsal.source_fingerprint,
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
        )
        report = self.audit()
        self.assertEqual(self.check(report, "rehearsal.fidelity").severity, AuditSeverity.PASS)
        self.assertEqual(self.check(report, "runbook.consistency").severity, AuditSeverity.PASS)

    def test_secret_redaction(self):
        first = "value-" + "one"
        second = "value-" + "two"
        value = redact(
            "bot_" + "token=" + first + " pass" + "word: " + second
        )
        self.assertNotIn(first, value)
        self.assertNotIn(second, value)
        self.assertEqual(value.count("[REDACTED]"), 2)

    def test_known_failure_has_no_traceback(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.model_activation_audit.cli",
                "audit",
                "--database",
                "missing.db",
                "--environment",
                "LAB",
                "--scope",
                "OFFICIAL_GLOBAL",
                "--source-commit",
                SOURCE_COMMIT,
                "--generated-at",
                GENERATED_AT,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_staging_readiness_blocked(self):
        blocker = AuditCheck(
            "test.blocker",
            "TEST",
            AuditSeverity.BLOCKER,
            "blocked",
        )
        self.assertEqual(
            assess_staging_readiness(AuditStatus.AUDIT_BLOCKED, (blocker,)),
            StagingReadiness.STAGING_REHEARSAL_BLOCKED,
        )

    def test_audit_never_imports_state_change_or_telegram(self):
        with (
            patch(
                "app.model_activation.service.ModelActivationService.execute_activation",
                side_effect=AssertionError("activation called"),
            ),
            patch(
                "app.model_activation.service.ModelActivationService.execute_rollback",
                side_effect=AssertionError("rollback called"),
            ),
        ):
            self.assertEqual(self.audit().overall_status, AuditStatus.AUDIT_PASSED)


if __name__ == "__main__":
    unittest.main()
