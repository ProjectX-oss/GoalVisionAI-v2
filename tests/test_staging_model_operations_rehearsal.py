import json
from dataclasses import replace
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.model_operations_rehearsal.safety import sha256_file
from app.staging_model_operations_rehearsal import (
    ArtifactMode,
    StagingRehearsalCommand,
    StagingRehearsalPolicy,
    StagingRehearsalPolicyError,
    canonical_json,
    format_human,
    run_staging_rehearsal,
)
from app.staging_model_operations_rehearsal.execution import (
    _sqlite_content_sha256,
)
from app.staging_model_operations_rehearsal.reporting import redact
from app.staging_real_artifact_chain import (
    build_real_artifact_chain,
    recent_calibration_rehearsal_profile,
)
from app.real_match_lab_analysis import (
    AnalysisStatus,
    SQLiteRealMatchLabRepository,
    build_real_match_lab_analysis_service,
    parse_input,
)
from datetime import datetime, timezone


SOURCE_COMMIT = "78f218632fafe4ceeab708b5dd92dbd1e48a890f"
TIMESTAMP = "20260725T120000Z"


class ControlledStagingRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = (
            Path("var")
            / "staging_rehearsal"
            / "tests"
            / uuid4().hex
        ).resolve()
        cls.root.mkdir(parents=True)
        cls.source = cls.root / "source.db"
        connection = sqlite3.connect(cls.source)
        try:
            with patch("app.database.migrations.MIGRATIONS", MIGRATIONS[:7]):
                MigrationManager(connection).migrate()
        finally:
            connection.close()
        cls.destination = cls.root / "authorized-run"
        cls.command = StagingRehearsalCommand(
            source_database=str(cls.source),
            destination_directory=str(cls.destination),
            environment="STAGING",
            scope="OFFICIAL_GLOBAL",
            timestamp=TIMESTAMP,
            source_commit=SOURCE_COMMIT,
            artifact_mode=ArtifactMode.REAL_ONLY,
        )
        cls.source_before = sha256_file(cls.source)
        cls.chain_profile = recent_calibration_rehearsal_profile(
            datetime(2026, 7, 31, 16, 16, 16, tzinfo=timezone.utc)
        )
        cls.outcome = run_staging_rehearsal(
            cls.command,
            chain_profile=cls.chain_profile,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_source_backup_and_disposable_copy_are_verified(self):
        self.assertEqual(self.outcome.source.sha256_before, self.source_before)
        self.assertEqual(self.outcome.source.sha256_after, self.source_before)
        self.assertEqual(self.outcome.source.backup_sha256, self.source_before)
        self.assertEqual(sha256_file(self.source), self.source_before)
        self.assertEqual(
            self.outcome.foundation_fingerprint,
            self.outcome.disposable_before_fingerprint,
        )

    def test_mandatory_preflight_and_final_audit_pass(self):
        preflight_json = tuple(
            item
            for item in self.outcome.preflight_audits
            if item.output_mode == "json"
        )
        self.assertEqual(len(preflight_json), 2)
        self.assertTrue(
            all(item.overall_status == "AUDIT_PASSED" for item in preflight_json)
        )
        self.assertTrue(
            all(
                item.staging_readiness == "STAGING_REHEARSAL_READY"
                for item in preflight_json
            )
        )
        final = next(
            item
            for item in self.outcome.final_audits
            if item.output_mode == "json"
        )
        self.assertEqual(final.overall_status, "AUDIT_PASSED")
        self.assertEqual(
            dict(final.summary_counts),
            {"BLOCKER": 0, "INFO": 0, "PASS": 35, "WARNING": 0},
        )

    def test_real_only_chain_is_explicit_complete_and_source_marked(self):
        self.assertFalse(self.outcome.fixture_fallback_used)
        self.assertFalse(self.outcome.artifact_inventory.used_fixture_fallback)
        self.assertTrue(self.outcome.real_artifact_chain_complete)
        self.assertEqual(self.outcome.artifact_mode, "REAL_ONLY")
        self.assertEqual(self.outcome.selected_artifact_mode, "REAL_ONLY")
        self.assertEqual(
            self.outcome.artifact_inventory.inventory_reason_codes,
            ("CONTROLLED_REAL_ARTIFACT_CHAIN_COMPLETE",),
        )
        manifest = (
            self.destination
            / f"goalvision_staging_rehearsal_{TIMESTAMP}.manifest.json"
        ).read_text(encoding="utf-8")
        self.assertIn("CONTROLLED_SYNTHETIC_STAGING_SOURCE", manifest)
        self.assertNotIn("FICTIONAL_", manifest)

    def test_real_chain_exact_replay_is_idempotent(self):
        controlled_source = (
            self.destination
            / f"controlled_real_artifact_source_{TIMESTAMP}.db"
        )
        database = Database(controlled_source)
        try:
            replay = build_real_artifact_chain(
                database,
                profile=self.chain_profile,
            )
        finally:
            database.close()
        self.assertEqual(
            replay.chain_fingerprint,
            self.outcome.real_artifact_chain_fingerprint,
        )
        self.assertEqual(replay.label, "CONTROLLED_SYNTHETIC_STAGING_SOURCE")

    def test_activation_rollback_and_resolver_sequence_are_exact(self):
        self.assertEqual(self.outcome.status, "STAGING_REHEARSAL_COMPLETED")
        self.assertEqual(
            self.outcome.resolver_sequence,
            self.outcome.generation_chain,
        )
        self.assertEqual(len(self.outcome.generation_chain), 3)
        statuses = {
            name: (status, exit_code)
            for name, status, exit_code in self.outcome.command_statuses
        }
        self.assertEqual(
            statuses["foundation-bootstrap"], ("BOOTSTRAP_EXECUTED", 0)
        )
        self.assertEqual(
            statuses["foundation-bootstrap-replay"], ("BOOTSTRAP_REJECTED", 6)
        )
        self.assertEqual(
            statuses["foundation-bootstrap-conflict"],
            ("BOOTSTRAP_REJECTED", 6),
        )
        self.assertEqual(
            statuses["foundation-prepare-activation"],
            ("ACTIVATION_PLAN_PREPARED", 0),
        )
        self.assertEqual(
            statuses["foundation-prepare-activation-replay"],
            ("ACTIVATION_PLAN_PREPARED", 0),
        )
        self.assertEqual(
            statuses["foundation-prepare-activation-conflict"],
            ("ACTIVATION_CONFLICT", 6),
        )
        self.assertEqual(statuses["execute-activation"], ("ACTIVATION_EXECUTED", 0))
        self.assertEqual(
            statuses["execute-activation-replay"],
            ("ACTIVATION_ALREADY_EXECUTED", 6),
        )
        self.assertEqual(
            statuses["execute-activation-conflict"], ("ACTIVATION_CONFLICT", 6)
        )

    def test_rolled_back_legacy_champion_is_stale_without_delivery(self):
        disposable = (
            self.destination
            / f"goalvision_staging_activation_rollback_{TIMESTAMP}.db"
        )
        raw = json.loads(
            Path("tests/fixtures/real_match_lab/valid.json").read_text(
                encoding="utf-8"
            )
        )
        raw["source_commit"] = SOURCE_COMMIT
        raw["collected_at"] = "2026-08-01T14:00:00Z"
        raw["source_updated_at"] = "2026-08-01T13:59:00Z"
        raw["data"]["home_availability"]["lineup_source_timestamp"] = (
            "2026-08-01T13:55:00Z"
        )
        raw["data"]["away_availability"]["lineup_source_timestamp"] = (
            "2026-08-01T13:54:00Z"
        )
        for odds in raw["odds"]:
            odds["captured_at"] = "2026-08-01T13:58:00Z"
        now = datetime(2026, 8, 1, 14, tzinfo=timezone.utc)
        command = parse_input(raw, now=now)
        database = Database(disposable)
        try:
            service = build_real_match_lab_analysis_service(database)
            record = service.analyze(command)
            diagnostic = None
            if record.status is AnalysisStatus.REJECTED:
                try:
                    service.engine.analyze(command, command.collected_at)
                except Exception as exc:
                    diagnostic = str(exc)
            deliveries = database.connection.execute(
                "SELECT COUNT(*) FROM real_match_lab_deliveries"
            ).fetchone()[0]
        finally:
            database.close()
        self.assertEqual(record.status, AnalysisStatus.REJECTED)
        self.assertIn("CALIBRATION_EVIDENCE_STALE", record.rejection_reasons)
        self.assertIn("CALIBRATION_EVIDENCE_STALE", diagnostic)
        self.assertIsNone(record.evidence)
        self.assertEqual(deliveries, 0)
        statuses = {
            name: (status, exit_code)
            for name, status, exit_code in self.outcome.command_statuses
        }
        self.assertEqual(
            statuses["execute-activation-wrong-confirmation"],
            ("CONFIRMATION_REJECTED", 2),
        )
        self.assertEqual(statuses["execute-rollback"], ("ROLLBACK_EXECUTED", 0))
        self.assertEqual(
            statuses["execute-rollback-replay"],
            ("ROLLBACK_ALREADY_EXECUTED", 6),
        )

    def test_final_counts_append_only_and_protected_boundaries(self):
        self.assertEqual(
            dict(self.outcome.final_counts),
            {
                "activation_executions": 1,
                "activation_plans": 1,
                "activation_requests": 1,
                "evidence_links": 30,
                "generations": 3,
                "registry_events": 5,
                "rollback_executions": 1,
                "rollback_plans": 1,
                "rollback_requests": 1,
            },
        )
        self.assertTrue(self.outcome.protected_state_unchanged)
        self.assertEqual(
            self.outcome.atomicity_checks,
            (
                "ACTIVATION_FAILURE_ATOMIC",
                "ACTIVATION_EXACT_RETRY_SUCCEEDED",
                "ROLLBACK_FAILURE_ATOMIC",
                "ROLLBACK_EXACT_RETRY_SUCCEEDED",
            ),
        )
        self.assertGreaterEqual(self.outcome.append_only_trigger_count, 184)
        self.assertEqual(self.outcome.foreign_key_violations, 0)
        disposable = (
            self.destination
            / f"goalvision_staging_activation_rollback_{TIMESTAMP}.db"
        )
        connection = sqlite3.connect(disposable)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(
                    "UPDATE model_champion_generations SET model_scope='BROKEN'"
                )
        finally:
            connection.close()

    def test_evidence_output_is_deterministic_redacted_and_path_free(self):
        first = canonical_json(self.outcome)
        second = canonical_json(self.outcome)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["evidence_fingerprint"], self.outcome.evidence_fingerprint)
        self.assertNotIn(str(self.root), first)
        self.assertIn("production activation remains unauthorized", format_human(self.outcome).lower())

    def test_content_fingerprint_ignores_migration_wall_clock_metadata(self):
        fingerprints = []
        for index, applied_at in enumerate(
            ("2026-07-25 12:00:00", "2026-07-25 12:01:00")
        ):
            path = self.root / f"logical-fingerprint-{index}.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """CREATE TABLE schema_migrations(
                           version INTEGER PRIMARY KEY,
                           applied_at TEXT NOT NULL
                       );
                       CREATE TABLE evidence(
                           evidence_id TEXT PRIMARY KEY,
                           value TEXT NOT NULL
                       );"""
                )
                connection.execute(
                    "INSERT INTO schema_migrations VALUES(?,?)",
                    (31, applied_at),
                )
                connection.execute(
                    "INSERT INTO evidence VALUES(?,?)",
                    ("evidence-1", "identical"),
                )
                connection.commit()
            finally:
                connection.close()
            fingerprints.append(_sqlite_content_sha256(path.resolve()))
        self.assertEqual(fingerprints[0], fingerprints[1])

    def test_production_outside_root_and_collision_reject(self):
        with self.assertRaises(StagingRehearsalPolicyError):
            run_staging_rehearsal(
                replace(self.command, environment="PRODUCTION")
            )
        policy = StagingRehearsalPolicy(
            approved_destination_roots=(self.root / "different-root",)
        )
        with self.assertRaises(StagingRehearsalPolicyError):
            run_staging_rehearsal(self.command, policy=policy)
        with self.assertRaises(StagingRehearsalPolicyError):
            run_staging_rehearsal(
                replace(
                    self.command,
                    destination_directory=str(self.source),
                )
            )

    def test_mandatory_preflight_refuses_append_only_blocker(self):
        broken = self.root / "missing-trigger.db"
        disposable = (
            self.destination
            / f"goalvision_staging_activation_rollback_{TIMESTAMP}.db"
        )
        shutil.copy2(disposable, broken)
        connection = sqlite3.connect(broken)
        try:
            connection.execute(
                "DROP TRIGGER model_activation_requests_no_update"
            )
            connection.commit()
        finally:
            connection.close()
        result = subprocess.run(
            (
                sys.executable,
                "-m",
                "app.model_activation_audit.cli",
                "preflight",
                "--database",
                str(broken),
                "--environment",
                "STAGING",
                "--scope",
                "OFFICIAL_GLOBAL",
                "--source-commit",
                SOURCE_COMMIT,
                "--generated-at",
                "2026-07-25T12:00:00Z",
                "--output",
                "json",
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        document = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(document["overall_status"], "AUDIT_BLOCKED")
        self.assertGreater(document["summary_counts"]["BLOCKER"], 0)

    def test_cli_help_is_inert_and_production_has_no_implicit_default(self):
        before = tuple(sorted(path.name for path in self.root.iterdir()))
        for arguments in (("--help",), ("run", "--help")):
            result = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "app.staging_model_operations_rehearsal.cli",
                    *arguments,
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("STAGING", result.stdout)
            self.assertNotIn("automatic", result.stdout.lower())
        self.assertEqual(before, tuple(sorted(path.name for path in self.root.iterdir())))

    def test_no_telegram_publication_runtime_scheduler_or_startup_integration(self):
        package = Path("app/staging_model_operations_rehearsal")
        content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in package.glob("*.py")
        ).lower()
        self.assertNotIn("telegram", content)
        self.assertNotIn("official_prediction", content)
        self.assertNotIn("scheduler", content)
        self.assertNotIn("worker", content)
        self.assertNotIn("runtimechampionresolver(", content)

    def test_secret_redaction(self):
        value = redact("bot_token=hidden password: private")
        self.assertNotIn("hidden", value)
        self.assertNotIn("private", value)
        self.assertEqual(value.count("[REDACTED]"), 2)


if __name__ == "__main__":
    unittest.main()
