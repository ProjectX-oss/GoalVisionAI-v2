import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from uuid import uuid4

from app.database import Database
from app.model_operations_rehearsal.execution import (
    ACTIVATION_EXECUTED_AT,
    ACTIVATION_EXECUTION_REQUEST_ID,
    EXECUTION_LABEL,
    FOUNDATION_PLAN_ID,
    ROLLBACK_EXECUTED_AT,
    ROLLBACK_EXECUTION_REQUEST_ID,
    ROLLBACK_PREPARED_AT,
    ROLLBACK_REQUEST_ID,
    ExecutionRehearsalError,
    SubprocessModelOperationsRunner,
    _validate_prepared_foundation,
    execute_activation_rollback_rehearsal,
    inspect_rehearsal_state,
)


class ModelOperationsExecutionRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = (
            Path("var")
            / "test_model_operations_execution_rehearsal"
            / uuid4().hex
        )
        cls.root.mkdir(parents=True)
        cls.source = cls.root / "source.db"
        cls.source.write_bytes(b"")
        cls.timestamp = "20260725T010000Z"
        cls.report = execute_activation_rollback_rehearsal(
            source_database=cls.source,
            destination_directory=cls.root,
            timestamp=cls.timestamp,
        )
        cls.foundation = (
            cls.root
            / f"goalvision_lab_rehearsal_{cls.timestamp}.db"
        )
        cls.disposable = (
            cls.root
            / f"goalvision_activation_rollback_{cls.timestamp}.db"
        )
        cls.runner = SubprocessModelOperationsRunner()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_disposable_copy_and_starting_invariants(self):
        self.assertEqual(
            self.report.foundation_fingerprint,
            self.report.disposable_before_fingerprint,
        )
        state = inspect_rehearsal_state(self.foundation)
        self.assertEqual(state["schema_version"], 36)
        self.assertEqual(state["foreign_key_violations"], 0)
        self.assertEqual(len(state["generations"]), 1)
        self.assertEqual(
            state["pending_activation_plans"][0]["activation_plan_id"],
            FOUNDATION_PLAN_ID,
        )
        self.assertEqual(state["activation_execution_count"], 0)
        self.assertEqual(state["rollback_request_count"], 0)
        self.assertEqual(state["rollback_plan_count"], 0)
        self.assertEqual(state["rollback_execution_count"], 0)
        self.assertEqual(state["validation_statuses"], ("PASS",) * 9)

    def test_complete_transition_chain_is_exact_and_idempotent(self):
        self.assertEqual(len(self.report.generation_chain), 3)
        self.assertEqual(
            self.report.resolver_sequence,
            self.report.generation_chain,
        )
        self.assertEqual(
            self.report.registry_event_types,
            (
                "INITIAL_REGISTERED",
                "RETIRED_BY_ACTIVATION",
                "CHAMPION_ACTIVATED",
                "RETIRED_BY_ROLLBACK",
                "CHAMPION_ROLLED_BACK",
            ),
        )
        self.assertEqual(
            self.report.final_counts,
            {
                "generations": 3,
                "activation_requests": 1,
                "activation_plans": 1,
                "activation_executions": 1,
                "rollback_requests": 1,
                "rollback_plans": 1,
                "rollback_executions": 1,
                "registry_events": 5,
                "evidence_links": 30,
            },
        )
        statuses = {
            item.name: (
                item.parsed_json["status"]
                if item.parsed_json is not None
                else None
            )
            for item in self.report.commands
        }
        self.assertEqual(statuses["execute-activation"], "ACTIVATION_EXECUTED")
        self.assertEqual(
            statuses["execute-activation-replay"],
            "ACTIVATION_ALREADY_EXECUTED",
        )
        self.assertEqual(
            statuses["execute-activation-conflict"],
            "ACTIVATION_CONFLICT",
        )
        self.assertEqual(statuses["execute-rollback"], "ROLLBACK_EXECUTED")
        self.assertEqual(
            statuses["execute-rollback-replay"],
            "ROLLBACK_ALREADY_EXECUTED",
        )
        self.assertEqual(
            statuses["execute-rollback-conflict"],
            "ROLLBACK_CONFLICT",
        )

    def test_confirmation_failures_are_nonzero_and_do_not_duplicate_state(self):
        captures = {
            item.name: item for item in self.report.commands
        }
        for name in (
            "execute-activation-wrong-confirmation",
            "execute-rollback-wrong-confirmation",
        ):
            self.assertEqual(captures[name].exit_code, 2)
            self.assertEqual(
                captures[name].parsed_json["status"],
                "CONFIRMATION_REJECTED",
            )
            self.assertNotIn("Traceback", captures[name].stdout)
        final = inspect_rehearsal_state(self.disposable)
        self.assertEqual(final["activation_execution_count"], 1)
        self.assertEqual(final["rollback_execution_count"], 1)
        self.assertEqual(len(final["generations"]), 3)

    def test_resolver_artifact_sequence_and_generation_links(self):
        database = Database(str(self.disposable))
        try:
            rows = tuple(
                dict(row)
                for row in database.connection.execute(
                    """SELECT generation_number,model_artifact_id,
                              calibration_artifact_set_id,
                              previous_champion_generation_id,
                              generation_snapshot
                       FROM model_champion_generations
                       ORDER BY generation_number"""
                )
            )
        finally:
            database.close()
        self.assertEqual(rows[0]["model_artifact_id"], rows[2]["model_artifact_id"])
        self.assertEqual(
            rows[0]["calibration_artifact_set_id"],
            rows[2]["calibration_artifact_set_id"],
        )
        self.assertNotEqual(rows[0]["model_artifact_id"], rows[1]["model_artifact_id"])
        self.assertEqual(
            rows[1]["previous_champion_generation_id"],
            self.report.initial_generation_id,
        )
        self.assertEqual(
            rows[2]["previous_champion_generation_id"],
            self.report.activated_generation_id,
        )
        initial = json.loads(rows[0]["generation_snapshot"])["artifact"]
        activated = json.loads(rows[1]["generation_snapshot"])["artifact"]
        rolled_back = json.loads(rows[2]["generation_snapshot"])["artifact"]
        for field in (
            "model_artifact_id",
            "model_artifact_fingerprint",
            "preprocessing_fingerprint",
            "calibration_artifact_set_id",
            "calibration_artifact_set_fingerprint",
            "feature_schema_version",
            "feature_schema_fingerprint",
            "target_contract_version",
            "probability_contract_version",
            "runtime_compatibility_version",
        ):
            self.assertEqual(initial[field], rolled_back[field])
        self.assertNotEqual(
            activated["model_artifact_id"],
            rolled_back["model_artifact_id"],
        )

    def test_append_only_guards_and_protected_state(self):
        self.assertGreaterEqual(self.report.append_only_trigger_count, 184)
        self.assertEqual(self.report.foreign_key_violations, 0)
        self.assertTrue(self.report.protected_state_unchanged)
        copy = self.root / "append-only-copy.db"
        shutil.copy2(self.disposable, copy)
        database = Database(str(copy))
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                database.connection.execute(
                    """UPDATE model_champion_generations
                       SET model_scope='CHANGED'"""
                )
            database.connection.rollback()
            with self.assertRaises(sqlite3.DatabaseError):
                database.connection.execute(
                    "DELETE FROM model_rollback_executions"
                )
            database.connection.rollback()
        finally:
            database.close()

    def test_starting_state_validation_fails_closed(self):
        copy = self.root / "invalid-foundation.db"
        shutil.copy2(self.foundation, copy)
        database = Database(str(copy))
        try:
            database.connection.execute(
                "DELETE FROM schema_migrations WHERE version=36"
            )
            database.connection.commit()
        finally:
            database.close()
        state = inspect_rehearsal_state(copy)
        manifest_path = self.foundation.with_suffix(".manifest.json")
        from app.model_operations_rehearsal.fixtures import LabFixtureManifest
        from app.model_activation import RuntimeArtifactReference

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw["champion"] = RuntimeArtifactReference(**raw["champion"])
        raw["challenger"] = RuntimeArtifactReference(**raw["challenger"])
        manifest = LabFixtureManifest(**raw)
        with self.assertRaises(ExecutionRehearsalError):
            _validate_prepared_foundation(state, manifest)

    def test_report_redacts_paths_and_has_no_telegram_or_secrets(self):
        output = self.report.as_json()
        self.assertNotIn(str(self.root.resolve()), output)
        self.assertNotIn("BOT_TOKEN", output)
        self.assertNotIn("api.telegram.org", output)
        self.assertIn("<DISPOSABLE_DB>", output)
        self.assertTrue(self.report.protected_state_unchanged)
        source = Path(
            "app/model_operations_rehearsal/execution.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("lab_telegram", source)
        self.assertNotIn("telegram", source.lower())

    def test_rehearsal_cli_help_is_inert(self):
        before = tuple(sorted(path.name for path in self.root.iterdir()))
        for arguments in (
            ("--help",),
            ("execute-activation-rollback-rehearsal", "--help"),
        ):
            completed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "app.model_operations_rehearsal.cli",
                    *arguments,
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertNotIn("Traceback", completed.stdout)
            self.assertEqual(completed.stderr, "")
        after = tuple(sorted(path.name for path in self.root.iterdir()))
        self.assertEqual(before, after)

    def test_read_only_human_and_json_outputs_are_deterministic(self):
        common = self._common(self.disposable)
        first_human = self.runner.run(
            "deterministic-human-1",
            ("show-champion", *common, "--output", "human"),
            expect_exit=0,
            json_output=False,
        )
        second_human = self.runner.run(
            "deterministic-human-2",
            ("show-champion", *common, "--output", "human"),
            expect_exit=0,
            json_output=False,
        )
        first_json = self.runner.run(
            "deterministic-json-1",
            ("show-champion", *common, "--output", "json"),
            expect_exit=0,
            json_output=True,
        )
        second_json = self.runner.run(
            "deterministic-json-2",
            ("show-champion", *common, "--output", "json"),
            expect_exit=0,
            json_output=True,
        )
        self.assertEqual(first_human.stdout, second_human.stdout)
        self.assertEqual(first_json.stdout, second_json.stdout)

    def test_activation_transaction_failure_rolls_back_and_retry_succeeds(self):
        copy = self.root / "activation-atomicity.db"
        shutil.copy2(self.foundation, copy)
        database = Database(str(copy))
        try:
            database.connection.execute(
                """CREATE TRIGGER rehearsal_fail_activation_execution
                   BEFORE INSERT ON model_activation_executions
                   BEGIN SELECT RAISE(ABORT,'injected activation failure'); END"""
            )
            database.connection.commit()
        finally:
            database.close()
        arguments = self._activation_execution_arguments(copy)
        failed = self.runner.run(
            "atomic-activation-failure",
            arguments,
            expect_exit=6,
            json_output=True,
        )
        self.assertEqual(failed.parsed_json["status"], "ACTIVATION_REJECTED")
        state = inspect_rehearsal_state(copy)
        self.assertEqual(len(state["generations"]), 1)
        self.assertEqual(state["activation_execution_count"], 0)
        self.assertEqual(len(state["registry_events"]), 1)
        database = Database(str(copy))
        try:
            database.connection.execute(
                "DROP TRIGGER rehearsal_fail_activation_execution"
            )
            database.connection.commit()
        finally:
            database.close()
        retried = self.runner.run(
            "atomic-activation-retry",
            arguments,
            expect_exit=0,
            json_output=True,
        )
        self.assertEqual(retried.parsed_json["status"], "ACTIVATION_EXECUTED")
        state = inspect_rehearsal_state(copy)
        self.assertEqual(len(state["generations"]), 2)
        self.assertEqual(state["activation_execution_count"], 1)

    def test_rollback_transaction_failure_rolls_back_and_retry_succeeds(self):
        copy = self.root / "rollback-atomicity.db"
        shutil.copy2(self.foundation, copy)
        activation = self.runner.run(
            "rollback-atomicity-activation",
            self._activation_execution_arguments(copy),
            expect_exit=0,
            json_output=True,
        )
        active = activation.parsed_json["details"]["new_champion_generation"]
        prepared = self.runner.run(
            "rollback-atomicity-prepare",
            self._rollback_prepare_arguments(copy, active),
            expect_exit=0,
            json_output=True,
        )
        plan_id = prepared.parsed_json["details"]["rollback_plan_id"]
        plan_fingerprint = prepared.parsed_json["details"][
            "rollback_plan_fingerprint"
        ]
        database = Database(str(copy))
        try:
            database.connection.execute(
                """CREATE TRIGGER rehearsal_fail_rollback_execution
                   BEFORE INSERT ON model_rollback_executions
                   BEGIN SELECT RAISE(ABORT,'injected rollback failure'); END"""
            )
            database.connection.commit()
        finally:
            database.close()
        arguments = self._rollback_execution_arguments(
            copy,
            plan_id,
            plan_fingerprint,
        )
        failed = self.runner.run(
            "atomic-rollback-failure",
            arguments,
            expect_exit=6,
            json_output=True,
        )
        self.assertEqual(failed.parsed_json["status"], "ROLLBACK_REJECTED")
        state = inspect_rehearsal_state(copy)
        self.assertEqual(len(state["generations"]), 2)
        self.assertEqual(state["rollback_execution_count"], 0)
        self.assertEqual(len(state["registry_events"]), 3)
        database = Database(str(copy))
        try:
            database.connection.execute(
                "DROP TRIGGER rehearsal_fail_rollback_execution"
            )
            database.connection.commit()
        finally:
            database.close()
        retried = self.runner.run(
            "atomic-rollback-retry",
            arguments,
            expect_exit=0,
            json_output=True,
        )
        self.assertEqual(retried.parsed_json["status"], "ROLLBACK_EXECUTED")
        state = inspect_rehearsal_state(copy)
        self.assertEqual(len(state["generations"]), 3)
        self.assertEqual(state["rollback_execution_count"], 1)

    def _activation_execution_arguments(self, database):
        state = inspect_rehearsal_state(database)
        plan = state["pending_activation_plans"][0]
        return (
            "execute-activation",
            *self._common(database),
            "--output",
            "json",
            "--execution-request-id",
            ACTIVATION_EXECUTION_REQUEST_ID,
            "--plan-id",
            plan["activation_plan_id"],
            "--plan-fingerprint",
            plan["activation_plan_fingerprint"],
            "--executed-at",
            ACTIVATION_EXECUTED_AT,
            "--operator",
            EXECUTION_LABEL,
            "--confirm",
            "ACTIVATE_CHAMPION",
        )

    def _rollback_prepare_arguments(self, database, active):
        foundation = inspect_rehearsal_state(self.foundation)
        initial = foundation["generations"][0]
        return (
            "prepare-rollback",
            *self._common(database),
            "--output",
            "json",
            "--request-id",
            ROLLBACK_REQUEST_ID,
            "--name",
            f"{EXECUTION_LABEL} rollback preparation",
            "--current-generation-id",
            active["champion_generation_id"],
            "--current-generation-fingerprint",
            active["generation_fingerprint"],
            "--target-generation-id",
            initial["champion_generation_id"],
            "--reason",
            f"{EXECUTION_LABEL} controlled rollback",
            "--incident-reference",
            "FICTIONAL-LAB-INCIDENT-001",
            "--operator",
            EXECUTION_LABEL,
            "--requested-at",
            ROLLBACK_PREPARED_AT,
        )

    def _rollback_execution_arguments(
        self,
        database,
        plan_id,
        plan_fingerprint,
    ):
        return (
            "execute-rollback",
            *self._common(database),
            "--output",
            "json",
            "--execution-request-id",
            ROLLBACK_EXECUTION_REQUEST_ID,
            "--plan-id",
            plan_id,
            "--plan-fingerprint",
            plan_fingerprint,
            "--executed-at",
            ROLLBACK_EXECUTED_AT,
            "--operator",
            EXECUTION_LABEL,
            "--confirm",
            "ROLLBACK_CHAMPION",
        )

    @staticmethod
    def _common(database):
        return (
            "--database",
            str(Path(database).resolve()),
            "--environment",
            "lab",
            "--scope",
            "OFFICIAL_GLOBAL",
        )


if __name__ == "__main__":
    unittest.main()
