"""Executable, dependency-injectable manual Official operations CLI.

Importing this module is inert. Production/staging transports and destination
verification must be supplied by existing application infrastructure to
``main``; this package never resolves Telegram credentials itself.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from app.database import Database, MigrationManager

from .commands import (
    PRODUCTION_TOKEN, PUBLISH_TOKEN, RETRY_TOKEN, execute_fixture_sync,
    retry_persisted_execution_sync,
)
from .diagnostics import run_official_pipeline_diagnostics
from .exceptions import (
    ConfirmationError, DatabaseSafetyError, DestinationVerificationError,
    FixtureValidationError, MaterializationError, OfficialPredictionOperationsError,
)
from .factory import (
    DestinationVerificationPort, OperationsEnvironment, open_operations_database,
    resolve_database_path,
)
from .recovery import analyze_execution_recovery
from .serialization import canonical_value
from .summaries import OperationsExitCode, OperationsResult
from .validation import load_official_fixture, parse_utc_timestamp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goalvision-official-operations", description="Controlled manual Official prediction operations (never scheduled).")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-fixture", help="Validate one signed fixture without database writes or gate execution.")
    validate.add_argument("--fixture", required=True)
    validate.add_argument("--json-output", action="store_true")

    dry = sub.add_parser("dry-run-fixture", help="Run the real persisted pipeline through deterministic message preview only.")
    _fixture_execution_arguments(dry)
    dry.add_argument("--environment", required=True, choices=("fixture",))

    publish = sub.add_parser("publish-fixture", help="Publish through the existing atomic adapter with exact confirmations.")
    _fixture_execution_arguments(publish)
    publish.add_argument("--environment", required=True, choices=("staging", "production"))
    publish.add_argument("--confirm-publish", required=True)
    publish.add_argument("--confirm-environment")
    publish.add_argument("--expected-candidate-id", required=True)
    publish.add_argument("--expected-match-id", required=True)
    publish.add_argument("--expected-destination", required=True)

    inspect_execution = sub.add_parser("inspect-execution", help="Read one execution and its immutable stage events.")
    _database_arguments(inspect_execution, allow_create=False)
    identity = inspect_execution.add_mutually_exclusive_group(required=True)
    identity.add_argument("--execution-id")
    identity.add_argument("--request-id")
    inspect_execution.add_argument("--json-output", action="store_true")

    inspect_candidate = sub.add_parser("inspect-candidate", help="Read candidate lifecycle, provenance, gate, orchestration, and publication evidence.")
    _database_arguments(inspect_candidate, allow_create=False)
    inspect_candidate.add_argument("--candidate-id", required=True)
    inspect_candidate.add_argument("--candidate-version", type=int)
    inspect_candidate.add_argument("--json-output", action="store_true")

    retry = sub.add_parser("retry-execution", help="Analyze and explicitly retry only a verified retryable execution.")
    _database_arguments(retry, allow_create=False)
    retry.add_argument("--execution-id", required=True)
    retry.add_argument("--retry", required=True, action="store_true")
    retry.add_argument("--execution-time", required=True, type=_timestamp_argument)
    retry.add_argument("--publication-time", required=True, type=_timestamp_argument)
    retry.add_argument("--confirm-retry", required=True)
    retry.add_argument("--json-output", action="store_true")

    listing = sub.add_parser("list-retry-required", help="List a bounded set of retry-required executions.")
    _database_arguments(listing, allow_create=False)
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--match-id")
    listing.add_argument("--candidate-id")
    listing.add_argument("--json-output", action="store_true")

    smoke = sub.add_parser("smoke-startup", help="Prove that startup/import performs zero gate, pipeline, claim, or send actions.")
    smoke.add_argument("--json-output", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    telegram: object | None = None,
    destination_verifier: DestinationVerificationPort | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args, telegram=telegram, destination_verifier=destination_verifier)
    except FixtureValidationError as exc:
        result = _error(args.command, "FIXTURE_VALIDATION_FAILED", OperationsExitCode.FIXTURE_VALIDATION_FAILURE, exc)
    except (DatabaseSafetyError, ConfirmationError, DestinationVerificationError) as exc:
        result = _error(args.command, "SAFETY_CHECK_FAILED", OperationsExitCode.INVALID_ARGUMENTS, exc)
    except MaterializationError as exc:
        result = _error(args.command, "UPSTREAM_MATERIALIZATION_REJECTED", OperationsExitCode.PROVENANCE_OR_CANDIDATE_REJECTION, exc)
    except OfficialPredictionOperationsError as exc:
        result = _error(args.command, "OPERATIONS_FAILED", OperationsExitCode.PUBLICATION_FAILURE, exc)
    except Exception as exc:
        result = _error(args.command, "INTERNAL_FAILURE", OperationsExitCode.INTERNAL_FAILURE, exc)
    print(result.to_json() if getattr(args, "json_output", False) else result.to_human())
    return int(result.exit_code)


def _dispatch(args: argparse.Namespace, *, telegram: object | None, destination_verifier: DestinationVerificationPort | None) -> OperationsResult:
    if args.command == "validate-fixture":
        fixture = load_official_fixture(args.fixture)
        return OperationsResult(
            command=args.command, success=True, final_status="VALID",
            fixture_id=fixture.fixture_id,
            details={"fixture_fingerprint": fixture.fixture_fingerprint, "schema": fixture.payload["metadata"]["schema_version"]},
        )
    if args.command in {"dry-run-fixture", "publish-fixture"}:
        publish = args.command == "publish-fixture"
        fixture = load_official_fixture(args.fixture)
        path = resolve_database_path(args.database, create_database=args.create_database, publish=publish)
        database = open_operations_database(path)
        try:
            return execute_fixture_sync(
                fixture, database, database_path=path,
                environment=OperationsEnvironment(args.environment),
                execution_time=args.execution_time, quality_gate_time=args.quality_gate_time,
                publication_time=args.publication_time, request_id=args.request_id,
                dry_run=not publish, telegram=telegram,
                destination_verifier=destination_verifier,
                expected_candidate_id=getattr(args, "expected_candidate_id", None),
                expected_match_id=getattr(args, "expected_match_id", None),
                expected_destination=getattr(args, "expected_destination", None),
                confirm_publish=getattr(args, "confirm_publish", None),
                confirm_environment=getattr(args, "confirm_environment", None),
            )
        finally:
            database.close()
    if args.command == "smoke-startup":
        database = Database(":memory:")
        try:
            MigrationManager(database.connection).migrate()
            counts = {
                "pipeline_executions": database.connection.execute("SELECT COUNT(*) FROM official_prediction_pipeline_executions").fetchone()[0],
                "gate_executions": database.connection.execute("SELECT COUNT(*) FROM official_quality_gate_evaluations").fetchone()[0],
                "orchestrations": database.connection.execute("SELECT COUNT(*) FROM official_prediction_orchestrations").fetchone()[0],
                "publication_claims": database.connection.execute("SELECT COUNT(*) FROM official_prediction_publication_events WHERE status='CLAIMED'").fetchone()[0],
                "telegram_sends": 0,
            }
        finally:
            database.close()
        healthy = not any(counts.values())
        return OperationsResult(command=args.command, success=healthy, final_status="HEALTHY" if healthy else "UNSAFE_STARTUP_ACTIVITY", exit_code=0 if healthy else 10, details=counts)

    path = resolve_database_path(args.database, create_database=False, publish=False)
    database = Database(path)
    try:
        if args.command == "inspect-execution":
            return _inspect_execution(database, path, args)
        if args.command == "inspect-candidate":
            return _inspect_candidate(database, path, args)
        if args.command == "list-retry-required":
            return _list_retry_required(database, path, args)
        if args.command == "retry-execution":
            analysis = analyze_execution_recovery(database, args.execution_id)
            if args.confirm_retry != RETRY_TOKEN:
                raise ConfirmationError("Exact retry confirmation token is required.")
            if not analysis.retry_safe or analysis.resend_forbidden:
                return OperationsResult(
                    command=args.command, success=False, final_status=analysis.classification.value,
                    exit_code=int(OperationsExitCode.RETRY_OR_IN_PROGRESS), execution_id=args.execution_id,
                    reason_codes=analysis.reason_codes, database_path=str(path), retry=True,
                    details=canonical_value(analysis),
                )
            if telegram is None or destination_verifier is None:
                raise ConfirmationError("Safe retry requires injected transport and destination verification from application infrastructure.")
            return retry_persisted_execution_sync(
                database, database_path=path, execution_id=args.execution_id,
                execution_time=args.execution_time, publication_time=args.publication_time,
                confirm_retry=args.confirm_retry, telegram=telegram,
                destination_verifier=destination_verifier,
            )
    finally:
        database.close()
    raise AssertionError("Unknown command dispatch.")


def _inspect_execution(database: Database, path: Path, args: argparse.Namespace) -> OperationsResult:
    from app.official_prediction_pipeline import SQLiteOfficialPredictionPipelineRepository
    repository = SQLiteOfficialPredictionPipelineRepository(database, migrate=False)
    execution = repository.load_pipeline_execution(args.execution_id) if args.execution_id else repository.find_by_request_identity(args.request_id)
    if execution is None:
        return OperationsResult(command=args.command, success=False, final_status="EXECUTION_NOT_FOUND", exit_code=4, request_id=args.request_id, execution_id=args.execution_id, database_path=str(path), reason_codes=("EXECUTION_NOT_FOUND",))
    stored = repository.load_execution_with_stages(execution.pipeline_execution_id)
    diagnostics = run_official_pipeline_diagnostics(database, execution_id=execution.pipeline_execution_id)
    return OperationsResult(
        command=args.command, success=True, final_status=execution.final_status.value,
        request_id=execution.pipeline_request_identity, execution_id=execution.pipeline_execution_id,
        candidate_id=execution.candidate_id, candidate_version=execution.candidate_version,
        match_id=execution.match_id, gate_status=execution.quality_gate_status,
        orchestration_status=execution.orchestration_status, publication_status=execution.publication_status,
        message_fingerprint=execution.message_fingerprint, reason_codes=execution.ordered_reason_codes,
        database_path=str(path), dry_run=execution.dry_run, retry=execution.retry,
        details={"execution": execution, "stages": stored.stages, "diagnostics": diagnostics},
    )


def _inspect_candidate(database: Database, path: Path, args: argparse.Namespace) -> OperationsResult:
    from app.official_prediction_candidate_registry import SQLiteOfficialPredictionCandidateRepository
    repository = SQLiteOfficialPredictionCandidateRepository(database, migrate=False)
    candidate = repository.find_candidate_by_id(args.candidate_id)
    if candidate is None or (args.candidate_version is not None and candidate.candidate_version != args.candidate_version):
        return OperationsResult(command=args.command, success=False, final_status="CANDIDATE_NOT_FOUND", exit_code=4, candidate_id=args.candidate_id, database_path=str(path), reason_codes=("CANDIDATE_NOT_FOUND",))
    connection = database.connection
    lifecycle = connection.execute("SELECT event_type,reason_code,event_timestamp FROM official_prediction_candidate_lifecycle_events WHERE registry_candidate_id=? ORDER BY event_sequence", (args.candidate_id,)).fetchall()
    pipeline = connection.execute("SELECT pipeline_execution_id,quality_gate_evaluation_id,quality_gate_status,orchestration_id,orchestration_status,publication_event_id,publication_status,final_pipeline_status FROM official_prediction_pipeline_executions WHERE candidate_id=? ORDER BY pipeline_execution_timestamp", (args.candidate_id,)).fetchall()
    diagnostics = run_official_pipeline_diagnostics(database, candidate_id=args.candidate_id)
    return OperationsResult(
        command=args.command, success=True, final_status=repository.current_state(args.candidate_id).value,
        candidate_id=args.candidate_id, candidate_version=candidate.candidate_version,
        match_id=candidate.match_id, database_path=str(path),
        details={"candidate": candidate, "provenance": dict(candidate.prepared.provenance), "lifecycle": tuple(dict(row) for row in lifecycle), "pipeline_linkage": tuple(dict(row) for row in pipeline), "diagnostics": diagnostics},
    )


def _list_retry_required(database: Database, path: Path, args: argparse.Namespace) -> OperationsResult:
    if args.limit < 1 or args.limit > 100:
        raise DatabaseSafetyError("--limit must be between 1 and 100.")
    clauses = ["""(
        (
            (e.final_pipeline_status='RETRY_REQUIRED' AND COALESCE(e.publication_state_result,'')!='INDETERMINATE')
            OR e.publication_status='FAILED_RETRYABLE'
        )
        AND COALESCE((
            SELECT publication.status
            FROM official_prediction_candidate_versions AS candidate
            JOIN official_prediction_publication_events AS publication
              ON publication.prediction_id=candidate.prediction_id
            WHERE candidate.registry_candidate_id=e.candidate_id
            ORDER BY publication.attempt_number DESC,publication.event_sequence DESC
            LIMIT 1
        ),'') NOT IN ('CLAIMED','INDETERMINATE','PUBLISHED')
    )"""]
    params: list[object] = []
    if args.match_id:
        clauses.append("e.match_id=?"); params.append(args.match_id)
    if args.candidate_id:
        clauses.append("e.candidate_id=?"); params.append(args.candidate_id)
    params.append(args.limit)
    rows = database.connection.execute(
        "SELECT e.pipeline_execution_id,e.pipeline_request_identity,e.candidate_id,e.candidate_version,e.match_id,e.final_pipeline_status,e.pipeline_execution_timestamp FROM official_prediction_pipeline_executions AS e WHERE " + " AND ".join(clauses) + " ORDER BY e.pipeline_execution_timestamp,e.pipeline_execution_id LIMIT ?",
        tuple(params),
    ).fetchall()
    retryable: list[dict[str, object]] = []
    for row in rows:
        analysis = analyze_execution_recovery(database, row["pipeline_execution_id"])
        if not analysis.retry_safe or analysis.resend_forbidden:
            continue
        item = dict(row)
        item["recovery_classification"] = analysis.classification.value
        retryable.append(item)
    return OperationsResult(command=args.command, success=True, final_status="LISTED", database_path=str(path), details={"limit": args.limit, "count": len(retryable), "executions": tuple(retryable)})


def _fixture_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fixture", required=True)
    _database_arguments(parser, allow_create=True)
    parser.add_argument("--execution-time", required=True, type=_timestamp_argument)
    parser.add_argument("--quality-gate-time", required=True, type=_timestamp_argument)
    parser.add_argument("--publication-time", required=True, type=_timestamp_argument)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("--verbose", action="store_true")


def _database_arguments(parser: argparse.ArgumentParser, *, allow_create: bool) -> None:
    parser.add_argument("--database", required=True)
    if allow_create:
        parser.add_argument("--create-database", action="store_true")


def _timestamp_argument(value: str) -> datetime:
    try:
        return parse_utc_timestamp(value, "CLI timestamp")
    except FixtureValidationError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _error(command: str, status: str, code: OperationsExitCode, exc: Exception) -> OperationsResult:
    return OperationsResult(command=command, success=False, final_status=status, exit_code=int(code), reason_codes=(type(exc).__name__.upper(),), details={"error": str(exc)})


if __name__ == "__main__":
    sys.exit(main())
