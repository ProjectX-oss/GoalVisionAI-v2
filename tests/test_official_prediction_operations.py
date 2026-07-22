import contextlib
import io
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.database import Database
from app.official_prediction_operations import (
    DestinationVerification, DestinationVerificationState,
    NoSendTelegramTransport, OperationsEnvironment, StaticDestinationVerifier,
    analyze_execution_recovery, build_active_claim_fixture,
    build_below_minimum_ev_fixture, build_below_minimum_odds_fixture,
    build_indeterminate_publication_fixture, build_quality_gate_rejected_fixture,
    build_retryable_publication_failure_fixture, build_review_required_fixture,
    build_stale_odds_fixture, build_superseded_candidate_fixture,
    build_valid_official_fixture, execute_fixture_sync,
    retry_persisted_execution_sync, run_official_pipeline_diagnostics,
    validate_official_fixture,
)
from app.official_prediction_operations.cli import build_parser, main
from app.official_prediction_operations.exceptions import (
    ConfirmationError, DatabaseSafetyError, DestinationVerificationError,
    FixtureValidationError,
)
from app.official_prediction_operations.factory import resolve_database_path
from app.official_prediction_operations.serialization import sha256_fingerprint
from app.official_prediction_publication import ConfirmedTelegramDeliveryError


UTC = timezone.utc
EXECUTION = datetime(2026, 8, 1, 12, 10, tzinfo=UTC)
GATE = datetime(2026, 8, 1, 12, 9, tzinfo=UTC)
PUBLICATION = datetime(2026, 8, 1, 12, 11, tzinfo=UTC)
SAMPLES = Path("tests/fixtures/official_prediction_pipeline")


class RecordingTelegram:
    def __init__(self, *, fail=False, indeterminate=False):
        self.calls = 0
        self.fail = fail
        self.indeterminate = indeterminate

    async def send_message(self, chat_id, text, parse_mode=None):
        self.calls += 1
        if self.fail:
            raise ConfirmedTelegramDeliveryError("not delivered")
        if self.indeterminate:
            raise RuntimeError("delivery unknown")
        return 42


def verifier(environment=OperationsEnvironment.STAGING, identity="fixture-official-channel"):
    return StaticDestinationVerifier(DestinationVerification(
        DestinationVerificationState.VERIFIED,
        identity,
        "TELEGRAM_CHANNEL",
        environment,
        True,
        "Fictional Official Test Channel",
    ))


def resign(value):
    value = deepcopy(value)
    value["metadata"].pop("fixture_fingerprint", None)
    value["metadata"]["fixture_fingerprint"] = sha256_fingerprint(value)
    return value


class FixtureSchemaTests(unittest.TestCase):
    def test_all_builders_are_deterministic_and_validate(self):
        builders = (
            build_valid_official_fixture, build_quality_gate_rejected_fixture,
            build_review_required_fixture, build_stale_odds_fixture,
            build_below_minimum_odds_fixture, build_below_minimum_ev_fixture,
            build_superseded_candidate_fixture,
            build_retryable_publication_failure_fixture,
            build_active_claim_fixture, build_indeterminate_publication_fixture,
        )
        for builder in builders:
            with self.subTest(builder=builder.__name__):
                first = builder()
                self.assertEqual(first, builder())
                self.assertEqual(validate_official_fixture(first).fixture_id, first["metadata"]["fixture_id"])

    def test_every_checked_in_sample_validates_and_contains_no_secret_or_url(self):
        names = {
            "valid_dry_run.json", "quality_gate_rejected.json", "review_required.json",
            "stale_odds.json", "retryable_send_failure.json", "active_claim.json",
            "indeterminate_post_send.json",
        }
        self.assertEqual({path.name for path in SAMPLES.glob("*.json")}, names)
        for path in SAMPLES.glob("*.json"):
            raw = path.read_text(encoding="utf-8")
            fixture = validate_official_fixture(json.loads(raw))
            self.assertTrue(fixture.payload["metadata"]["non_production"])
            self.assertNotIn("http://", raw.lower())
            self.assertNotIn("https://", raw.lower())
            self.assertNotIn("bot_token", raw.lower())

    def test_schema_version_sections_decimals_timestamps_and_fingerprint_fail_closed(self):
        base = build_valid_official_fixture()
        cases = []
        value = deepcopy(base); value["metadata"]["schema_version"] = "v2"; cases.append(value)
        value = deepcopy(base); value.pop("risk"); cases.append(value)
        value = deepcopy(base); value["odds"]["decimal_odds"] = "NaN"; cases.append(resign(value))
        value = deepcopy(base); value["match"]["kickoff_utc"] = "2026-08-01T15:00:00+02:00"; cases.append(resign(value))
        value = deepcopy(base); value["metadata"]["fixture_fingerprint"] = "0" * 64; cases.append(value)
        for value in cases:
            with self.subTest(value=value["metadata"].get("schema_version")), self.assertRaises(FixtureValidationError):
                validate_official_fixture(value)

    def test_credentials_urls_and_arbitrary_objects_are_rejected(self):
        value = deepcopy(build_valid_official_fixture())
        value["risk"]["api_token"] = "not-a-real-token"
        with self.assertRaises(FixtureValidationError):
            validate_official_fixture(value)
        value = deepcopy(build_valid_official_fixture())
        value["metadata"]["description"] = "https://affiliate.invalid"
        with self.assertRaises(FixtureValidationError):
            validate_official_fixture(value)
        value = deepcopy(build_valid_official_fixture())
        value["metadata"]["description"] = object()
        with self.assertRaises(FixtureValidationError):
            validate_official_fixture(value)


class DatabaseAndCliSafetyTests(unittest.TestCase):
    def test_database_path_is_explicit_bounded_and_publish_refuses_memory(self):
        with self.assertRaises(DatabaseSafetyError):
            resolve_database_path("", create_database=False, publish=False)
        with self.assertRaises(DatabaseSafetyError):
            resolve_database_path("prod", create_database=False, publish=False)
        with self.assertRaises(DatabaseSafetyError):
            resolve_database_path(":memory:", create_database=False, publish=True)
        directory = Path("tests") / f".official-operations-path-{uuid4().hex}"
        directory.mkdir()
        try:
            missing = directory / "fixture.db"
            with self.assertRaises(DatabaseSafetyError):
                resolve_database_path(str(missing), create_database=False, publish=False)
            self.assertEqual(resolve_database_path(str(missing), create_database=True, publish=False), missing.resolve())
            with self.assertRaises(DatabaseSafetyError):
                resolve_database_path(str(directory), create_database=False, publish=False)
        finally:
            directory.rmdir()

    def test_parser_requires_arguments_and_rejects_unknown_arguments(self):
        parser = build_parser()
        for argv in (("dry-run-fixture",), ("validate-fixture", "--unknown")):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                parser.parse_args(argv)
            self.assertEqual(caught.exception.code, 2)

    def test_invalid_timestamp_is_argparse_exit_two(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            build_parser().parse_args((
                "dry-run-fixture", "--fixture", "x", "--database", "x",
                "--environment", "fixture", "--execution-time", "now",
                "--quality-gate-time", "now", "--publication-time", "now",
                "--request-id", "x",
            ))
        self.assertEqual(caught.exception.code, 2)

    def test_validate_cli_json_has_stable_schema(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("validate-fixture", "--fixture", str(SAMPLES / "valid_dry_run.json"), "--json-output"))
        value = json.loads(output.getvalue())
        self.assertEqual((code, value["schema"], value["final_status"]), (0, "goalvision_official_operations_result_v1", "VALID"))

    def test_publish_refuses_fixture_environment_and_missing_exact_token(self):
        parser = build_parser()
        common = (
            "publish-fixture", "--fixture", str(SAMPLES / "valid_dry_run.json"),
            "--database", "fixture.db", "--execution-time", "2026-08-01T12:10:00Z",
            "--quality-gate-time", "2026-08-01T12:09:00Z", "--publication-time", "2026-08-01T12:11:00Z",
            "--request-id", "x", "--confirm-publish", "yes",
            "--expected-candidate-id", "x", "--expected-match-id", "500100",
            "--expected-destination", "fixture-official-channel",
        )
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args((*common, "--environment", "fixture"))


class EndToEndOperationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path("tests") / f".official-operations-{uuid4().hex}"
        self.directory.mkdir()
        self.path = self.directory / "operations.db"
        self.database = Database(self.path)

    def tearDown(self):
        self.database.close()
        if self.path.exists():
            self.path.unlink()
        self.directory.rmdir()

    def execute(self, fixture, *, request="fixture-request-1", dry_run=True, telegram=None, environment=None):
        fixture = validate_official_fixture(fixture)
        values = dict(
            database_path=self.path,
            environment=environment or (OperationsEnvironment.FIXTURE if dry_run else OperationsEnvironment.STAGING),
            execution_time=EXECUTION, quality_gate_time=GATE,
            publication_time=PUBLICATION, request_id=request, dry_run=dry_run,
        )
        if not dry_run:
            values.update(
                telegram=telegram, destination_verifier=verifier(),
                expected_candidate_id=fixture.candidate_id,
                expected_match_id=fixture.match_id,
                expected_destination=fixture.destination_identity,
                confirm_publish="YES_PUBLISH_OFFICIAL",
            )
        return execute_fixture_sync(fixture, self.database, **values)

    def test_real_dry_run_traverses_every_upstream_boundary_without_claim_or_send(self):
        result = self.execute(build_valid_official_fixture())
        self.assertEqual(result.final_status, "DRY_RUN_COMPLETED")
        self.assertEqual(result.gate_status, "APPROVED")
        self.assertEqual(result.orchestration_status, "APPROVED_NOT_PUBLISHED")
        self.assertIsNotNone(result.message_fingerprint)
        for table in (
            "match_data_snapshot_versions", "match_feature_sets", "model_input_vectors",
            "prediction_inference_results", "calibrated_market_probability_assemblies",
            "market_value_assessments", "official_prediction_selection_decisions",
            "official_candidate_preparation_executions", "official_prediction_candidate_versions",
            "official_quality_gate_evaluations", "official_prediction_orchestrations",
            "official_prediction_pipeline_executions",
        ):
            self.assertGreater(self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM official_prediction_publication_events").fetchone()[0], 0)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM official_quality_gate_evaluations").fetchone()[0], 1)

    def test_dry_run_replay_is_idempotent_and_sends_zero(self):
        first = self.execute(build_valid_official_fixture())
        second = self.execute(build_valid_official_fixture())
        self.assertEqual(first.execution_id, second.execution_id)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM official_prediction_pipeline_executions").fetchone()[0], 1)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM official_prediction_publication_events").fetchone()[0], 0)

    def test_publish_claims_sends_finalizes_once_and_replay_does_not_resend(self):
        telegram = RecordingTelegram()
        first = self.execute(build_valid_official_fixture(), request="publish-1", dry_run=False, telegram=telegram)
        second = self.execute(build_valid_official_fixture(), request="publish-1", dry_run=False, telegram=telegram)
        self.assertEqual((first.final_status, second.final_status, telegram.calls), ("PUBLISHED", "PUBLISHED", 1))
        statuses = [row[0] for row in self.database.connection.execute("SELECT status FROM official_prediction_publication_events ORDER BY event_sequence")]
        self.assertEqual(statuses, ["CLAIMED", "PUBLISHED"])

    def test_publish_confirmation_identity_and_destination_mismatches_block_before_send(self):
        fixture = validate_official_fixture(build_valid_official_fixture())
        for change in (
            {"confirm_publish": "yes"}, {"expected_candidate_id": "wrong"},
            {"expected_match_id": "999"}, {"expected_destination": "wrong"},
        ):
            with self.subTest(change=change):
                telegram = RecordingTelegram()
                values = dict(
                    database_path=self.path, environment=OperationsEnvironment.STAGING,
                    execution_time=EXECUTION, quality_gate_time=GATE,
                    publication_time=PUBLICATION, request_id="blocked-" + next(iter(change)),
                    dry_run=False, telegram=telegram, destination_verifier=verifier(),
                    expected_candidate_id=fixture.candidate_id, expected_match_id=fixture.match_id,
                    expected_destination=fixture.destination_identity,
                    confirm_publish="YES_PUBLISH_OFFICIAL",
                )
                values.update(change)
                with self.assertRaises((ConfirmationError, DestinationVerificationError)):
                    execute_fixture_sync(fixture, self.database, **values)
                self.assertEqual(telegram.calls, 0)

    def test_production_requires_additional_exact_confirmation(self):
        fixture = validate_official_fixture(build_valid_official_fixture())
        telegram = RecordingTelegram()
        with self.assertRaises(ConfirmationError):
            execute_fixture_sync(
                fixture, self.database, database_path=self.path,
                environment=OperationsEnvironment.PRODUCTION,
                execution_time=EXECUTION, quality_gate_time=GATE,
                publication_time=PUBLICATION, request_id="prod-blocked", dry_run=False,
                telegram=telegram, destination_verifier=verifier(OperationsEnvironment.PRODUCTION),
                expected_candidate_id=fixture.candidate_id, expected_match_id=fixture.match_id,
                expected_destination=fixture.destination_identity,
                confirm_publish="YES_PUBLISH_OFFICIAL",
            )
        self.assertEqual(telegram.calls, 0)
        with self.assertRaises(ConfirmationError):
            execute_fixture_sync(
                fixture, self.database, database_path=self.path,
                environment=OperationsEnvironment.PRODUCTION,
                execution_time=EXECUTION, quality_gate_time=GATE,
                publication_time=PUBLICATION, request_id="prod-non-production-blocked", dry_run=False,
                telegram=telegram, destination_verifier=verifier(OperationsEnvironment.PRODUCTION),
                expected_candidate_id=fixture.candidate_id, expected_match_id=fixture.match_id,
                expected_destination=fixture.destination_identity,
                confirm_publish="YES_PUBLISH_OFFICIAL", confirm_environment="PRODUCTION_OFFICIAL",
            )
        production_payload = resign(fixture.payload)
        production_payload["metadata"]["non_production"] = False
        production_fixture = validate_official_fixture(resign(production_payload))
        published = execute_fixture_sync(
            production_fixture, self.database, database_path=self.path,
            environment=OperationsEnvironment.PRODUCTION,
            execution_time=EXECUTION, quality_gate_time=GATE,
            publication_time=PUBLICATION, request_id="prod-controlled", dry_run=False,
            telegram=telegram, destination_verifier=verifier(OperationsEnvironment.PRODUCTION),
            expected_candidate_id=production_fixture.candidate_id,
            expected_match_id=production_fixture.match_id,
            expected_destination=production_fixture.destination_identity,
            confirm_publish="YES_PUBLISH_OFFICIAL", confirm_environment="PRODUCTION_OFFICIAL",
        )
        self.assertEqual((published.final_status, telegram.calls), ("PUBLISHED", 1))

    def test_gate_rejection_review_superseded_active_and_indeterminate_send_zero(self):
        cases = (
            (build_quality_gate_rejected_fixture, "NO_PUBLICATION_QUALITY_GATE_REJECTED"),
            (build_review_required_fixture, "NO_PUBLICATION_REVIEW_REQUIRED"),
            (build_superseded_candidate_fixture, "REJECTED_CANDIDATE_STATE"),
            (build_active_claim_fixture, "PUBLICATION_IN_PROGRESS"),
            (build_indeterminate_publication_fixture, "RETRY_REQUIRED"),
        )
        for index, (builder, expected) in enumerate(cases):
            with self.subTest(builder=builder.__name__):
                database = Database(":memory:")
                fixture = validate_official_fixture(builder())
                result = execute_fixture_sync(
                    fixture, database, database_path=Path(":memory:"),
                    environment=OperationsEnvironment.FIXTURE,
                    execution_time=EXECUTION, quality_gate_time=GATE,
                    publication_time=PUBLICATION, request_id=f"state-{index}", dry_run=True,
                )
                self.assertEqual(result.final_status, expected)
                self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM official_prediction_publication_events").fetchone()[0], 0)
                database.close()

    def test_confirmed_send_failure_is_retryable_and_reuses_approved_gate(self):
        failing = RecordingTelegram(fail=True)
        failed = self.execute(build_retryable_publication_failure_fixture(), request="retryable-1", dry_run=False, telegram=failing)
        self.assertEqual((failed.final_status, failing.calls), ("PUBLICATION_SEND_FAILED", 1))
        analysis = analyze_execution_recovery(self.database, failed.execution_id)
        self.assertEqual(analysis.classification.value, "RETRYABLE_SEND_FAILURE")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("list-retry-required", "--database", str(self.path), "--limit", "20", "--json-output"))
        listing = json.loads(output.getvalue())
        self.assertEqual((code, listing["details"]["count"]), (0, 1))
        self.assertEqual(listing["details"]["executions"][0]["pipeline_execution_id"], failed.execution_id)
        self.assertEqual(listing["details"]["executions"][0]["recovery_classification"], "RETRYABLE_SEND_FAILURE")
        successful = RecordingTelegram()
        retried = retry_persisted_execution_sync(
            self.database, database_path=self.path, execution_id=failed.execution_id,
            execution_time=datetime(2026, 8, 1, 12, 12, tzinfo=UTC),
            publication_time=datetime(2026, 8, 1, 12, 13, tzinfo=UTC),
            confirm_retry="YES_RETRY_OFFICIAL", telegram=successful,
            destination_verifier=verifier(),
        )
        self.assertEqual((retried.final_status, successful.calls), ("PUBLISHED", 1))
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM official_quality_gate_evaluations").fetchone()[0], 1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("list-retry-required", "--database", str(self.path), "--limit", "20", "--json-output"))
        listing = json.loads(output.getvalue())
        self.assertEqual((code, listing["details"]["count"]), (0, 0))

    def test_indeterminate_send_is_never_retryable(self):
        telegram = RecordingTelegram(indeterminate=True)
        failed = self.execute(build_valid_official_fixture(), request="uncertain-1", dry_run=False, telegram=telegram)
        self.assertEqual(failed.final_status, "PUBLICATION_FINALIZATION_FAILED")
        analysis = analyze_execution_recovery(self.database, failed.execution_id)
        self.assertEqual(analysis.classification.value, "INDETERMINATE_POST_SEND")
        self.assertTrue(analysis.resend_forbidden)

    def test_retry_listing_excludes_indeterminate_fixture_history(self):
        result = self.execute(build_indeterminate_publication_fixture(), request="uncertain-fixture-1")
        self.assertEqual(result.final_status, "RETRY_REQUIRED")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("list-retry-required", "--database", str(self.path), "--limit", "20", "--json-output"))
        listing = json.loads(output.getvalue())
        self.assertEqual((code, listing["details"]["count"]), (0, 0))

    def test_diagnostics_are_read_only_and_healthy(self):
        result = self.execute(build_valid_official_fixture())
        before = self.database.connection.total_changes
        diagnostics = run_official_pipeline_diagnostics(self.database, execution_id=result.execution_id)
        self.assertTrue(diagnostics.healthy, diagnostics.reason_codes)
        self.assertEqual(self.database.connection.total_changes, before)

    def test_diagnostics_detect_missing_stage_broken_gate_and_invalid_lifecycle(self):
        result = self.execute(build_valid_official_fixture())
        self.database.connection.execute("DROP TRIGGER official_pipeline_stage_events_no_delete")
        self.database.connection.execute(
            "DELETE FROM official_prediction_pipeline_stage_events WHERE pipeline_execution_id=? AND stage_order=6",
            (result.execution_id,),
        )
        diagnostics = run_official_pipeline_diagnostics(self.database, execution_id=result.execution_id)
        self.assertIn("STAGE_EVENT_COMPLETENESS", diagnostics.reason_codes)

        self.database.connection.execute("DROP TRIGGER official_quality_gate_no_delete")
        self.database.connection.commit()
        self.database.connection.execute("PRAGMA foreign_keys=OFF")
        self.database.connection.execute(
            "DELETE FROM official_quality_gate_evaluations WHERE evaluation_id=(SELECT quality_gate_evaluation_id FROM official_prediction_pipeline_executions WHERE pipeline_execution_id=?)",
            (result.execution_id,),
        )
        diagnostics = run_official_pipeline_diagnostics(self.database, execution_id=result.execution_id)
        self.assertIn("GATE_EVALUATION_LINKAGE", diagnostics.reason_codes)
        self.database.connection.commit()

        from app.official_prediction_candidate_registry import SQLiteOfficialPredictionCandidateRepository
        candidates = SQLiteOfficialPredictionCandidateRepository(self.database, migrate=False)
        candidates.invalidate_candidate(result.candidate_id, "DIAGNOSTIC_TEST", PUBLICATION)
        diagnostics = run_official_pipeline_diagnostics(self.database, candidate_id=result.candidate_id)
        self.assertIn("CANDIDATE_LIFECYCLE", diagnostics.reason_codes)

    def test_empty_database_diagnostics_and_recovery_fail_closed_without_writes(self):
        empty = Database(":memory:")
        before = empty.connection.total_changes
        diagnostics = run_official_pipeline_diagnostics(empty, execution_id="missing")
        analysis = analyze_execution_recovery(empty, "missing")
        self.assertFalse(diagnostics.healthy)
        self.assertEqual(analysis.classification.value, "INVALID_HISTORY")
        self.assertTrue(analysis.resend_forbidden)
        self.assertEqual(empty.connection.total_changes, before)
        empty.close()


class DocumentationAndStartupTests(unittest.TestCase):
    def test_runbook_contains_all_sections_tokens_and_emergency_guards(self):
        path = Path("docs/OFFICIAL_PREDICTION_OPERATIONS_RUNBOOK.md")
        text = path.read_text(encoding="utf-8")
        for number in range(1, 26):
            self.assertIn(f"## {number}.", text)
        for token in ("YES_PUBLISH_OFFICIAL", "PRODUCTION_OFFICIAL", "YES_RETRY_OFFICIAL"):
            self.assertIn(token, text)
        for phrase in ("Preserve the database", "do not delete", "Never manually mark an uncertain send as failed"):
            self.assertIn(phrase.lower(), text.lower())
        self.assertNotIn("APScheduler", text)
        self.assertNotIn("Celery", text)

    def test_operations_import_and_cli_import_have_no_execution_side_effects(self):
        database = Database(":memory:")
        from app.database import MigrationManager
        MigrationManager(database.connection).migrate()
        before = tuple(database.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in (
            "official_prediction_pipeline_executions", "official_quality_gate_evaluations",
            "official_prediction_orchestrations", "official_prediction_publication_events",
        ))
        import app.official_prediction_operations as operations
        import app.official_prediction_operations.cli as cli
        self.assertIsNotNone((operations, cli))
        after = tuple(database.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in (
            "official_prediction_pipeline_executions", "official_quality_gate_evaluations",
            "official_prediction_orchestrations", "official_prediction_publication_events",
        ))
        self.assertEqual(before, after)
        database.close()

    def test_smoke_startup_reports_all_zero(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("smoke-startup", "--json-output"))
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["final_status"], "HEALTHY")
        self.assertFalse(any(result["details"].values()))


if __name__ == "__main__":
    unittest.main()
