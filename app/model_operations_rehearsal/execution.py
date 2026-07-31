"""Subprocess-driven activation and rollback rehearsal on a disposable DB."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, Sequence

from app.database import Database

from .fixtures import LabFixtureManifest, seed_lab_fixture
from .safety import (
    RehearsalSafetyError,
    create_rehearsal_database_copies,
    resolve_database_source,
    sha256_file,
)


SCOPE = "OFFICIAL_GLOBAL"
FOUNDATION_PLAN_ID = (
    "activation-plan-"
    "52de46d3503b82ba317fd1aebf3b4d63439561b66f94336510f7f6f7131dfcac"
)
EXECUTION_LABEL = "FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY"
ACTIVATION_EXECUTION_REQUEST_ID = (
    "fictional-lab-execution-rehearsal-activation-1"
)
ROLLBACK_REQUEST_ID = "fictional-lab-execution-rehearsal-rollback-1"
ROLLBACK_EXECUTION_REQUEST_ID = (
    "fictional-lab-execution-rehearsal-rollback-execution-1"
)
ACTIVATION_EXECUTED_AT = "2026-08-01T14:00:00Z"
ROLLBACK_PREPARED_AT = "2026-08-01T15:00:00Z"
ROLLBACK_EXECUTED_AT = "2026-08-01T16:00:00Z"

_ACTIVATION_TABLES = (
    "model_activation_requests",
    "model_activation_plans",
    "model_activation_validations",
    "model_activation_evidence_links",
    "model_activation_executions",
    "model_rollback_requests",
    "model_rollback_plans",
    "model_rollback_executions",
    "model_champion_generations",
    "model_champion_registry_events",
)


class ExecutionRehearsalError(RuntimeError):
    """Raised when any rehearsal command or invariant fails closed."""


@dataclass(frozen=True, slots=True)
class ExecutionRehearsalProfile:
    environment: str = "lab"
    scope: str = SCOPE
    fixture_label: str = "FICTIONAL_LAB_REHEARSAL_ONLY"
    execution_label: str = EXECUTION_LABEL
    operator: str = "codex-lab-rehearsal"
    activation_prepare_request_id: str = "lab-rehearsal-activation-prepare-1"
    activation_execution_request_id: str = ACTIVATION_EXECUTION_REQUEST_ID
    rollback_request_id: str = ROLLBACK_REQUEST_ID
    rollback_execution_request_id: str = ROLLBACK_EXECUTION_REQUEST_ID
    incident_reference: str = "FICTIONAL-LAB-INCIDENT-001"
    bootstrap_timestamp: str = "2026-07-24T23:10:00Z"
    activation_requested_at: str = "2026-08-01T13:00:00Z"
    activation_executed_at: str = ACTIVATION_EXECUTED_AT
    rollback_prepared_at: str = ROLLBACK_PREPARED_AT
    rollback_executed_at: str = ROLLBACK_EXECUTED_AT
    expected_plan_id: str | None = FOUNDATION_PLAN_ID
    foundation_prefix: str = "goalvision_lab_rehearsal"
    disposable_prefix: str = "goalvision_activation_rollback"


DEFAULT_EXECUTION_REHEARSAL_PROFILE = ExecutionRehearsalProfile()


@dataclass(frozen=True, slots=True)
class CommandCapture:
    name: str
    arguments: tuple[str, ...]
    exit_code: int
    stdout: str
    parsed_json: dict | None


@dataclass(frozen=True, slots=True)
class ExecutionRehearsalReport:
    label: str
    source_database_name: str
    foundation_database_name: str
    disposable_database_name: str
    source_fingerprint: str
    foundation_fingerprint: str
    disposable_before_fingerprint: str
    disposable_after_fingerprint: str
    initial_generation_id: str
    activation_plan_id: str
    activation_plan_fingerprint: str
    activation_execution_fingerprint: str
    activated_generation_id: str
    rollback_plan_id: str
    rollback_plan_fingerprint: str
    rollback_execution_fingerprint: str
    rollback_generation_id: str
    resolver_sequence: tuple[str, str, str]
    generation_chain: tuple[str, ...]
    registry_event_types: tuple[str, ...]
    final_counts: dict[str, int]
    commands: tuple[CommandCapture, ...]
    protected_state_unchanged: bool
    append_only_trigger_count: int
    foreign_key_violations: int

    def as_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2)


class SubprocessModelOperationsRunner:
    """Runs the real operator CLI in a fresh Python process."""

    def __init__(self, *, python_executable: str | None = None) -> None:
        self._python = python_executable or sys.executable

    def run(
        self,
        name: str,
        arguments: Sequence[str],
        *,
        expect_exit: int | tuple[int, ...],
        json_output: bool,
    ) -> CommandCapture:
        command = (
            self._python,
            "-m",
            "app.model_operations.cli",
            *arguments,
        )
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        expected = (
            (expect_exit,) if isinstance(expect_exit, int) else expect_exit
        )
        if completed.returncode not in expected:
            raise ExecutionRehearsalError(
                f"{name} returned {completed.returncode}; expected {expected}; "
                f"stdout={completed.stdout.strip()!r}; stderr={completed.stderr.strip()!r}."
            )
        if completed.stderr.strip():
            raise ExecutionRehearsalError(
                f"{name} unexpectedly wrote to stderr."
            )
        output = completed.stdout.strip()
        parsed = None
        if json_output:
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError as exc:
                raise ExecutionRehearsalError(
                    f"{name} did not return valid JSON."
                ) from exc
        return CommandCapture(
            name=name,
            arguments=tuple(arguments),
            exit_code=completed.returncode,
            stdout=output,
            parsed_json=parsed,
        )


def execute_activation_rollback_rehearsal(
    *,
    source_database: Path,
    destination_directory: Path,
    timestamp: str,
    runner: SubprocessModelOperationsRunner | None = None,
    profile: ExecutionRehearsalProfile = DEFAULT_EXECUTION_REHEARSAL_PROFILE,
    fixture_seed: Callable[[Database], LabFixtureManifest] = seed_lab_fixture,
    pre_bootstrap_hook: Callable[[Path], None] | None = None,
    pre_execution_hook: Callable[[Path], None] | None = None,
    final_hook: Callable[[Path], None] | None = None,
) -> ExecutionRehearsalReport:
    """Build a prepared foundation, copy it, then exercise the real CLI."""
    runner = runner or SubprocessModelOperationsRunner()
    source = resolve_database_source(explicit=source_database)
    source_fingerprint = sha256_file(source)
    copies = create_rehearsal_database_copies(
        source,
        destination_directory,
        timestamp=timestamp,
        rehearsal_prefix=profile.foundation_prefix,
    )
    foundation = copies.rehearsal
    manifest_path = foundation.with_suffix(".manifest.json")
    disposable = (
        destination_directory.resolve()
        / f"{profile.disposable_prefix}_{timestamp}.db"
    )
    result_path = disposable.with_suffix(".result.json")
    if disposable.exists() or result_path.exists():
        raise RehearsalSafetyError(
            "The disposable execution rehearsal destination already exists."
        )
    try:
        manifest, foundation_commands = _seed_and_prepare_foundation(
            foundation,
            manifest_path,
            runner,
            profile,
            fixture_seed,
            pre_bootstrap_hook,
        )
        foundation_state = inspect_rehearsal_state(foundation)
        _validate_prepared_foundation(
            foundation_state,
            manifest,
            expected_plan_id=profile.expected_plan_id,
        )
        if pre_execution_hook is not None:
            pre_execution_hook(foundation)
        foundation_fingerprint = sha256_file(foundation)
        shutil.copy2(foundation, disposable)
        disposable_before = sha256_file(disposable)
        if disposable_before != foundation_fingerprint:
            raise ExecutionRehearsalError(
                "Disposable database differs from its prepared foundation."
            )
        report = _run_disposable_rehearsal(
            disposable,
            source,
            source_fingerprint,
            foundation,
            foundation_fingerprint,
            disposable_before,
            manifest,
            runner,
            profile,
            foundation_commands,
        )
        if final_hook is not None:
            final_hook(disposable)
        result_path.write_text(report.as_json() + "\n", encoding="utf-8")
        return report
    except Exception:
        disposable.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
        raise


def verify_atomic_failure_recovery(
    *,
    foundation: Path,
    destination_directory: Path,
    profile: ExecutionRehearsalProfile = DEFAULT_EXECUTION_REHEARSAL_PROFILE,
    runner: SubprocessModelOperationsRunner | None = None,
) -> tuple[str, ...]:
    """Inject activation/rollback persistence failures on fresh disposable copies."""
    runner = runner or SubprocessModelOperationsRunner()
    activation_copy = destination_directory / "activation_atomicity.db"
    rollback_copy = destination_directory / "rollback_atomicity.db"
    if activation_copy.exists() or rollback_copy.exists():
        raise ExecutionRehearsalError("Atomicity copy already exists.")
    shutil.copy2(foundation, activation_copy)
    shutil.copy2(foundation, rollback_copy)
    _create_failure_trigger(
        activation_copy,
        "rehearsal_fail_activation_execution",
        "model_activation_executions",
    )
    activation_arguments = _activation_arguments_for(activation_copy, profile)
    failed_activation = runner.run(
        "atomic-activation-failure",
        activation_arguments,
        expect_exit=6,
        json_output=True,
    )
    _expect_status(failed_activation, "ACTIVATION_REJECTED")
    state = inspect_rehearsal_state(activation_copy)
    if (
        len(state["generations"]) != 1
        or state["activation_execution_count"] != 0
        or len(state["registry_events"]) != 1
    ):
        raise ExecutionRehearsalError("Activation failure left partial state.")
    _drop_trigger(activation_copy, "rehearsal_fail_activation_execution")
    retried_activation = runner.run(
        "atomic-activation-retry",
        activation_arguments,
        expect_exit=0,
        json_output=True,
    )
    _expect_status(retried_activation, "ACTIVATION_EXECUTED")

    activated = runner.run(
        "rollback-atomicity-activation",
        _activation_arguments_for(rollback_copy, profile),
        expect_exit=0,
        json_output=True,
    ).parsed_json["details"]["new_champion_generation"]
    initial = inspect_rehearsal_state(foundation)["generations"][0]
    prepared = runner.run(
        "rollback-atomicity-prepare",
        (
            "prepare-rollback",
            *_common(rollback_copy, output="json", profile=profile),
            "--request-id",
            profile.rollback_request_id,
            "--name",
            f"{profile.execution_label} rollback atomicity",
            "--current-generation-id",
            activated["champion_generation_id"],
            "--current-generation-fingerprint",
            activated["generation_fingerprint"],
            "--target-generation-id",
            initial["champion_generation_id"],
            "--reason",
            f"{profile.execution_label} rollback atomicity",
            "--incident-reference",
            profile.incident_reference,
            "--operator",
            profile.execution_label,
            "--requested-at",
            profile.rollback_prepared_at,
        ),
        expect_exit=0,
        json_output=True,
    )
    plan_id = prepared.parsed_json["details"]["rollback_plan_id"]
    plan_fingerprint = prepared.parsed_json["details"][
        "rollback_plan_fingerprint"
    ]
    _create_failure_trigger(
        rollback_copy,
        "rehearsal_fail_rollback_execution",
        "model_rollback_executions",
    )
    rollback_arguments = (
        "execute-rollback",
        *_common(rollback_copy, output="json", profile=profile),
        "--execution-request-id",
        profile.rollback_execution_request_id,
        "--plan-id",
        plan_id,
        "--plan-fingerprint",
        plan_fingerprint,
        "--executed-at",
        profile.rollback_executed_at,
        "--operator",
        profile.execution_label,
        "--confirm",
        "ROLLBACK_CHAMPION",
    )
    failed_rollback = runner.run(
        "atomic-rollback-failure",
        rollback_arguments,
        expect_exit=6,
        json_output=True,
    )
    _expect_status(failed_rollback, "ROLLBACK_REJECTED")
    state = inspect_rehearsal_state(rollback_copy)
    if (
        len(state["generations"]) != 2
        or state["rollback_execution_count"] != 0
        or len(state["registry_events"]) != 3
    ):
        raise ExecutionRehearsalError("Rollback failure left partial state.")
    _drop_trigger(rollback_copy, "rehearsal_fail_rollback_execution")
    retried_rollback = runner.run(
        "atomic-rollback-retry",
        rollback_arguments,
        expect_exit=0,
        json_output=True,
    )
    _expect_status(retried_rollback, "ROLLBACK_EXECUTED")
    return (
        "ACTIVATION_FAILURE_ATOMIC",
        "ACTIVATION_EXACT_RETRY_SUCCEEDED",
        "ROLLBACK_FAILURE_ATOMIC",
        "ROLLBACK_EXACT_RETRY_SUCCEEDED",
    )


def inspect_rehearsal_state(path: Path) -> dict:
    """Return a deterministic, read-only invariant snapshot."""
    database = Database(str(path))
    try:
        connection = database.connection
        generations = connection.execute(
            """SELECT champion_generation_id,generation_number,
                      model_artifact_id,calibration_artifact_set_id,
                      previous_champion_generation_id,activation_plan_id,
                      rollback_plan_id,generation_fingerprint
               FROM model_champion_generations
               WHERE model_scope=?
               ORDER BY generation_number""",
            (SCOPE,),
        ).fetchall()
        activation_plans = connection.execute(
            """SELECT p.activation_plan_id,p.activation_plan_fingerprint,
                      p.plan_snapshot
               FROM model_activation_plans p
               LEFT JOIN model_activation_executions e
                 ON e.activation_plan_id=p.activation_plan_id
               WHERE e.activation_plan_id IS NULL
               ORDER BY p.activation_plan_id"""
        ).fetchall()
        rollback_plans = connection.execute(
            """SELECT p.rollback_plan_id,p.rollback_plan_fingerprint
               FROM model_rollback_plans p
               LEFT JOIN model_rollback_executions e
                 ON e.rollback_plan_id=p.rollback_plan_id
               WHERE e.rollback_plan_id IS NULL
               ORDER BY p.rollback_plan_id"""
        ).fetchall()
        trigger_rows = connection.execute(
            """SELECT name FROM sqlite_master
               WHERE type='trigger'
               ORDER BY name"""
        ).fetchall()
        protected = _protected_table_fingerprints(connection)
        return {
            "schema_version": connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            "foreign_keys_enabled": connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "append_only_triggers": tuple(
                row[0]
                for row in trigger_rows
                if row[0].endswith("_no_update")
                or row[0].endswith("_no_delete")
            ),
            "generations": tuple(dict(row) for row in generations),
            "pending_activation_plans": tuple(
                {
                    "activation_plan_id": row[0],
                    "activation_plan_fingerprint": row[1],
                    "plan_snapshot": json.loads(row[2]),
                }
                for row in activation_plans
            ),
            "pending_rollback_plans": tuple(dict(row) for row in rollback_plans),
            "activation_request_count": _count(
                connection,
                "model_activation_requests",
            ),
            "activation_plan_count": _count(
                connection,
                "model_activation_plans",
            ),
            "activation_execution_count": _count(
                connection,
                "model_activation_executions",
            ),
            "rollback_request_count": _count(
                connection,
                "model_rollback_requests",
            ),
            "rollback_plan_count": _count(
                connection,
                "model_rollback_plans",
            ),
            "rollback_execution_count": _count(
                connection,
                "model_rollback_executions",
            ),
            "evidence_link_count": _count(
                connection,
                "model_activation_evidence_links",
            ),
            "validation_statuses": tuple(
                row[0]
                for row in connection.execute(
                    """SELECT validation_status
                       FROM model_activation_validations
                       WHERE rollback_plan_id IS NULL
                       ORDER BY deterministic_order""",
                )
            ),
            "registry_events": tuple(
                dict(row)
                for row in connection.execute(
                    """SELECT champion_generation_id,generation_number,
                              event_type,event_fingerprint
                       FROM model_champion_registry_events
                       WHERE model_scope=?
                       ORDER BY rowid""",
                    (SCOPE,),
                )
            ),
            "protected_table_fingerprints": protected,
        }
    finally:
        database.close()


def _seed_and_prepare_foundation(
    foundation: Path,
    manifest_path: Path,
    runner: SubprocessModelOperationsRunner,
    profile: ExecutionRehearsalProfile,
    fixture_seed: Callable[[Database], LabFixtureManifest],
    pre_bootstrap_hook: Callable[[Path], None] | None,
) -> tuple[LabFixtureManifest, tuple[CommandCapture, ...]]:
    database = Database(str(foundation))
    try:
        manifest = fixture_seed(database)
    finally:
        database.close()
    manifest_path.write_text(manifest.as_json() + "\n", encoding="utf-8")
    if pre_bootstrap_hook is not None:
        pre_bootstrap_hook(foundation)
    common = _common(foundation, output="json", profile=profile)
    champion_arguments = (
        "bootstrap-champion",
        *common,
        *_artifact_arguments(manifest.champion),
        "--timestamp",
        profile.bootstrap_timestamp,
        "--reason",
        f"{profile.fixture_label} initial champion",
        "--operator",
        profile.operator,
    )
    bootstrap = runner.run(
        "foundation-bootstrap",
        champion_arguments,
        expect_exit=0,
        json_output=True,
    )
    _expect_status(bootstrap, "BOOTSTRAP_EXECUTED")
    bootstrap_replay = runner.run(
        "foundation-bootstrap-replay",
        champion_arguments,
        expect_exit=6,
        json_output=True,
    )
    _expect_status(bootstrap_replay, "BOOTSTRAP_REJECTED")
    bootstrap_conflict = runner.run(
        "foundation-bootstrap-conflict",
        _replace_cli_option(
            champion_arguments,
            "--reason",
            f"{profile.fixture_label} conflicting bootstrap",
        ),
        expect_exit=6,
        json_output=True,
    )
    _expect_status(bootstrap_conflict, "BOOTSTRAP_REJECTED")
    generation = bootstrap.parsed_json["details"]["champion_generation"]
    prepare_arguments = (
        "prepare-activation",
        *common,
        "--request-id",
        profile.activation_prepare_request_id,
        "--name",
        f"{profile.fixture_label} activation preparation",
        "--current-generation-id",
        generation["champion_generation_id"],
        "--current-generation-fingerprint",
        generation["generation_fingerprint"],
        *_artifact_arguments(manifest.champion, "current"),
        *_artifact_arguments(manifest.challenger, "challenger"),
        "--comparison-run-id",
        manifest.comparison_run_id,
        "--comparison-run-fingerprint",
        manifest.comparison_run_fingerprint,
        "--challenger-candidate-id",
        manifest.challenger_candidate_id,
        "--recommendation-id",
        manifest.recommendation_id,
        "--recommendation-fingerprint",
        manifest.recommendation_fingerprint,
        "--shadow-evidence-fingerprint",
        manifest.shadow_evidence_fingerprint,
        "--evidence-cutoff",
        manifest.evidence_cutoff_timestamp_utc,
        "--requested-at",
        profile.activation_requested_at,
        "--reason",
        f"{profile.fixture_label} reviewed preparation",
        "--operator",
        profile.operator,
    )
    prepare = runner.run(
        "foundation-prepare-activation",
        prepare_arguments,
        expect_exit=0,
        json_output=True,
    )
    _expect_status(prepare, "ACTIVATION_PLAN_PREPARED")
    prepare_replay = runner.run(
        "foundation-prepare-activation-replay",
        prepare_arguments,
        expect_exit=0,
        json_output=True,
    )
    _expect_status(prepare_replay, "ACTIVATION_PLAN_PREPARED")
    prepare_conflict = runner.run(
        "foundation-prepare-activation-conflict",
        _replace_cli_option(
            prepare_arguments,
            "--reason",
            f"{profile.fixture_label} conflicting preparation",
        ),
        expect_exit=6,
        json_output=True,
    )
    _expect_status(prepare_conflict, "ACTIVATION_CONFLICT")
    if (
        profile.expected_plan_id is not None
        and prepare.parsed_json["details"]["activation_plan_id"]
        != profile.expected_plan_id
    ):
        raise ExecutionRehearsalError(
            "The deterministic foundation activation plan ID differs."
        )
    return manifest, (
        bootstrap,
        bootstrap_replay,
        bootstrap_conflict,
        prepare,
        prepare_replay,
        prepare_conflict,
    )


def _run_disposable_rehearsal(
    disposable: Path,
    source: Path,
    source_fingerprint: str,
    foundation: Path,
    foundation_fingerprint: str,
    disposable_before: str,
    manifest: LabFixtureManifest,
    runner: SubprocessModelOperationsRunner,
    profile: ExecutionRehearsalProfile,
    foundation_commands: tuple[CommandCapture, ...],
) -> ExecutionRehearsalReport:
    commands: list[CommandCapture] = list(foundation_commands)
    pre = inspect_rehearsal_state(disposable)
    _validate_prepared_foundation(
        pre,
        manifest,
        expected_plan_id=profile.expected_plan_id,
    )
    initial = pre["generations"][0]
    plan = pre["pending_activation_plans"][0]

    for command in (
        "diagnose-state",
        "show-champion",
        "list-generations",
    ):
        for output in ("human", "json"):
            commands.append(
                runner.run(
                    f"pre-{command}-{output}",
                    (
                        command,
                        *_common(disposable, output=output, profile=profile),
                        *(
                            ("--limit", "20")
                            if command == "list-generations"
                            else ()
                        ),
                    ),
                    expect_exit=(0, 5),
                    json_output=output == "json",
                )
            )
    for output in ("human", "json"):
        commands.append(
            runner.run(
                f"pre-show-activation-{output}",
                (
                    "show-activation",
                    *_common(disposable, output=output, profile=profile),
                    "--plan-id",
                    plan["activation_plan_id"],
                ),
                expect_exit=0,
                json_output=output == "json",
            )
        )

    activation_arguments = (
        "execute-activation",
        *_common(disposable, output="json", profile=profile),
        "--execution-request-id",
        profile.activation_execution_request_id,
        "--plan-id",
        plan["activation_plan_id"],
        "--plan-fingerprint",
        plan["activation_plan_fingerprint"],
        "--executed-at",
        profile.activation_executed_at,
        "--operator",
        profile.execution_label,
        "--confirm",
        "ACTIVATE_CHAMPION",
    )
    activation = runner.run(
        "execute-activation",
        activation_arguments,
        expect_exit=0,
        json_output=True,
    )
    commands.append(activation)
    _expect_status(activation, "ACTIVATION_EXECUTED")
    activated = activation.parsed_json["details"]["new_champion_generation"]

    activation_replay = runner.run(
        "execute-activation-replay",
        activation_arguments,
        expect_exit=6,
        json_output=True,
    )
    commands.append(activation_replay)
    _expect_status(activation_replay, "ACTIVATION_ALREADY_EXECUTED")
    activation_conflict_args = list(activation_arguments)
    activation_conflict_args[
        activation_conflict_args.index("--plan-fingerprint") + 1
    ] = "0" * 64
    activation_conflict = runner.run(
        "execute-activation-conflict",
        activation_conflict_args,
        expect_exit=6,
        json_output=True,
    )
    commands.append(activation_conflict)
    _expect_status(activation_conflict, "ACTIVATION_CONFLICT")
    activation_wrong = list(activation_arguments)
    activation_wrong[activation_wrong.index("--confirm") + 1] = "WRONG"
    activation_confirmation = runner.run(
        "execute-activation-wrong-confirmation",
        activation_wrong,
        expect_exit=2,
        json_output=True,
    )
    commands.append(activation_confirmation)
    _expect_status(activation_confirmation, "CONFIRMATION_REJECTED")

    post_activation = inspect_rehearsal_state(disposable)
    if len(post_activation["generations"]) != 2:
        raise ExecutionRehearsalError(
            "Activation did not create exactly one new generation."
        )
    if (
        post_activation["generations"][-1]["champion_generation_id"]
        != activated["champion_generation_id"]
    ):
        raise ExecutionRehearsalError(
            "Resolver state does not point at the activated challenger."
        )
    _assert_counts(
        post_activation,
        activation_execution_count=1,
        rollback_request_count=0,
        rollback_plan_count=0,
        rollback_execution_count=0,
    )

    for command in (
        "show-champion",
        "list-generations",
        "diagnose-state",
    ):
        for output in ("human", "json"):
            commands.append(
                runner.run(
                    f"post-activation-{command}-{output}",
                    (
                        command,
                        *_common(disposable, output=output, profile=profile),
                        *(
                            ("--limit", "20")
                            if command == "list-generations"
                            else ()
                        ),
                    ),
                    expect_exit=0,
                    json_output=output == "json",
                )
            )
    commands.append(
        runner.run(
            "post-activation-show-plan-json",
            (
                "show-activation",
                *_common(disposable, output="json", profile=profile),
                "--plan-id",
                plan["activation_plan_id"],
            ),
            expect_exit=0,
            json_output=True,
        )
    )

    rollback_arguments = (
        "prepare-rollback",
        *_common(disposable, output="json", profile=profile),
        "--request-id",
        profile.rollback_request_id,
        "--name",
        f"{profile.execution_label} rollback preparation",
        "--current-generation-id",
        activated["champion_generation_id"],
        "--current-generation-fingerprint",
        activated["generation_fingerprint"],
        "--target-generation-id",
        initial["champion_generation_id"],
        "--reason",
        f"{profile.execution_label} controlled rollback",
        "--incident-reference",
        profile.incident_reference,
        "--operator",
        profile.execution_label,
        "--requested-at",
        profile.rollback_prepared_at,
    )
    rollback_prepare = runner.run(
        "prepare-rollback",
        rollback_arguments,
        expect_exit=0,
        json_output=True,
    )
    commands.append(rollback_prepare)
    _expect_status(rollback_prepare, "ROLLBACK_PLAN_PREPARED")
    rollback_plan_id = rollback_prepare.parsed_json["details"][
        "rollback_plan_id"
    ]
    rollback_plan_fingerprint = rollback_prepare.parsed_json["details"][
        "rollback_plan_fingerprint"
    ]
    rollback_prepare_replay = runner.run(
        "prepare-rollback-replay",
        rollback_arguments,
        expect_exit=0,
        json_output=True,
    )
    commands.append(rollback_prepare_replay)
    _expect_status(rollback_prepare_replay, "ROLLBACK_PLAN_PREPARED")
    if (
        rollback_prepare_replay.parsed_json["details"]["rollback_plan_id"]
        != rollback_plan_id
    ):
        raise ExecutionRehearsalError("Rollback preparation replay drifted.")
    rollback_conflict_args = list(rollback_arguments)
    rollback_conflict_args[
        rollback_conflict_args.index("--reason") + 1
    ] = f"{profile.execution_label} conflicting rollback"
    rollback_prepare_conflict = runner.run(
        "prepare-rollback-conflict",
        rollback_conflict_args,
        expect_exit=6,
        json_output=True,
    )
    commands.append(rollback_prepare_conflict)
    _expect_status(rollback_prepare_conflict, "ROLLBACK_CONFLICT")

    before_rollback = inspect_rehearsal_state(disposable)
    if (
        before_rollback["generations"][-1]["champion_generation_id"]
        != activated["champion_generation_id"]
    ):
        raise ExecutionRehearsalError(
            "Rollback preparation changed the active champion."
        )

    rollback_execution_arguments = (
        "execute-rollback",
        *_common(disposable, output="json", profile=profile),
        "--execution-request-id",
        profile.rollback_execution_request_id,
        "--plan-id",
        rollback_plan_id,
        "--plan-fingerprint",
        rollback_plan_fingerprint,
        "--executed-at",
        profile.rollback_executed_at,
        "--operator",
        profile.execution_label,
        "--confirm",
        "ROLLBACK_CHAMPION",
    )
    rollback_execution = runner.run(
        "execute-rollback",
        rollback_execution_arguments,
        expect_exit=0,
        json_output=True,
    )
    commands.append(rollback_execution)
    _expect_status(rollback_execution, "ROLLBACK_EXECUTED")
    rolled_back = rollback_execution.parsed_json["details"][
        "new_champion_generation"
    ]
    rollback_replay = runner.run(
        "execute-rollback-replay",
        rollback_execution_arguments,
        expect_exit=6,
        json_output=True,
    )
    commands.append(rollback_replay)
    _expect_status(rollback_replay, "ROLLBACK_ALREADY_EXECUTED")
    rollback_conflict_args = list(rollback_execution_arguments)
    rollback_conflict_args[
        rollback_conflict_args.index("--plan-fingerprint") + 1
    ] = "0" * 64
    rollback_conflict = runner.run(
        "execute-rollback-conflict",
        rollback_conflict_args,
        expect_exit=6,
        json_output=True,
    )
    commands.append(rollback_conflict)
    _expect_status(rollback_conflict, "ROLLBACK_CONFLICT")
    rollback_wrong = list(rollback_execution_arguments)
    rollback_wrong[rollback_wrong.index("--confirm") + 1] = "WRONG"
    rollback_confirmation = runner.run(
        "execute-rollback-wrong-confirmation",
        rollback_wrong,
        expect_exit=2,
        json_output=True,
    )
    commands.append(rollback_confirmation)
    _expect_status(rollback_confirmation, "CONFIRMATION_REJECTED")

    for command in (
        "show-champion",
        "list-generations",
        "diagnose-state",
    ):
        for output in ("human", "json"):
            commands.append(
                runner.run(
                    f"final-{command}-{output}",
                    (
                        command,
                        *_common(disposable, output=output, profile=profile),
                        *(
                            ("--limit", "20")
                            if command == "list-generations"
                            else ()
                        ),
                    ),
                    expect_exit=0,
                    json_output=output == "json",
                )
            )
    commands.append(
        runner.run(
            "final-show-rollback-json",
            (
                "show-activation",
                *_common(disposable, output="json", profile=profile),
                "--plan-id",
                rollback_plan_id,
            ),
            expect_exit=0,
            json_output=True,
        )
    )

    final = inspect_rehearsal_state(disposable)
    _validate_final_state(
        final,
        manifest,
        initial_generation_id=initial["champion_generation_id"],
        activated_generation_id=activated["champion_generation_id"],
        rollback_generation_id=rolled_back["champion_generation_id"],
    )
    if (
        pre["protected_table_fingerprints"]
        != final["protected_table_fingerprints"]
    ):
        raise ExecutionRehearsalError(
            "A non-model-operations table changed during execution."
        )
    if sha256_file(source) != source_fingerprint:
        raise ExecutionRehearsalError("The original source database changed.")
    if sha256_file(foundation) != foundation_fingerprint:
        raise ExecutionRehearsalError(
            "The prepared foundation database changed."
        )
    activation_row = _single_row(
        disposable,
        """SELECT execution_fingerprint
           FROM model_activation_executions""",
    )
    rollback_row = _single_row(
        disposable,
        """SELECT execution_fingerprint
           FROM model_rollback_executions""",
    )
    chain = tuple(
        item["champion_generation_id"] for item in final["generations"]
    )
    events = tuple(item["event_type"] for item in final["registry_events"])
    return ExecutionRehearsalReport(
        label=profile.execution_label,
        source_database_name=source.name,
        foundation_database_name=foundation.name,
        disposable_database_name=disposable.name,
        source_fingerprint=source_fingerprint,
        foundation_fingerprint=foundation_fingerprint,
        disposable_before_fingerprint=disposable_before,
        disposable_after_fingerprint=sha256_file(disposable),
        initial_generation_id=initial["champion_generation_id"],
        activation_plan_id=plan["activation_plan_id"],
        activation_plan_fingerprint=plan["activation_plan_fingerprint"],
        activation_execution_fingerprint=activation_row[
            "execution_fingerprint"
        ],
        activated_generation_id=activated["champion_generation_id"],
        rollback_plan_id=rollback_plan_id,
        rollback_plan_fingerprint=rollback_plan_fingerprint,
        rollback_execution_fingerprint=rollback_row[
            "execution_fingerprint"
        ],
        rollback_generation_id=rolled_back["champion_generation_id"],
        resolver_sequence=(
            initial["champion_generation_id"],
            activated["champion_generation_id"],
            rolled_back["champion_generation_id"],
        ),
        generation_chain=chain,
        registry_event_types=events,
        final_counts={
            "generations": len(final["generations"]),
            "activation_requests": final["activation_request_count"],
            "activation_plans": final["activation_plan_count"],
            "activation_executions": final["activation_execution_count"],
            "rollback_requests": final["rollback_request_count"],
            "rollback_plans": final["rollback_plan_count"],
            "rollback_executions": final["rollback_execution_count"],
            "registry_events": len(final["registry_events"]),
            "evidence_links": final["evidence_link_count"],
        },
        commands=tuple(_redact_capture(item, disposable) for item in commands),
        protected_state_unchanged=True,
        append_only_trigger_count=len(final["append_only_triggers"]),
        foreign_key_violations=final["foreign_key_violations"],
    )


def _validate_prepared_foundation(
    state: dict,
    manifest: LabFixtureManifest,
    *,
    expected_plan_id: str | None = FOUNDATION_PLAN_ID,
) -> None:
    failures = []
    if state["schema_version"] != 33:
        failures.append("SCHEMA_NOT_V33")
    if state["foreign_keys_enabled"] != 1:
        failures.append("FOREIGN_KEYS_DISABLED")
    if state["foreign_key_violations"]:
        failures.append("FOREIGN_KEY_VIOLATIONS")
    required_triggers = {
        f"{table}_{suffix}"
        for table in _ACTIVATION_TABLES
        for suffix in ("no_update", "no_delete")
    }
    if not required_triggers.issubset(state["append_only_triggers"]):
        failures.append("APPEND_ONLY_TRIGGER_MISSING")
    if len(state["generations"]) != 1:
        failures.append("GENERATION_COUNT_NOT_ONE")
    if len(state["pending_activation_plans"]) != 1:
        failures.append("PENDING_ACTIVATION_COUNT_NOT_ONE")
    elif (
        expected_plan_id is not None
        and
        state["pending_activation_plans"][0]["activation_plan_id"]
        != expected_plan_id
    ):
        failures.append("FOUNDATION_PLAN_ID_MISMATCH")
    if state["activation_request_count"] != 1:
        failures.append("ACTIVATION_REQUEST_COUNT_NOT_ONE")
    if state["activation_plan_count"] != 1:
        failures.append("ACTIVATION_PLAN_COUNT_NOT_ONE")
    if state["activation_execution_count"] != 0:
        failures.append("ACTIVATION_ALREADY_EXECUTED")
    if any(
        state[name] != 0
        for name in (
            "rollback_request_count",
            "rollback_plan_count",
            "rollback_execution_count",
        )
    ):
        failures.append("ROLLBACK_STATE_PRESENT")
    if state["evidence_link_count"] != 30:
        failures.append("EVIDENCE_LINK_COUNT_MISMATCH")
    if state["validation_statuses"] != ("PASS",) * 9:
        failures.append("ACTIVATION_VALIDATIONS_NOT_PASS")
    if state["generations"]:
        generation = state["generations"][0]
        if generation["model_artifact_id"] != manifest.champion.model_artifact_id:
            failures.append("INITIAL_CHAMPION_MISMATCH")
    if failures:
        raise ExecutionRehearsalError(
            "Prepared foundation rejected: " + ",".join(failures)
        )


def _validate_final_state(
    state: dict,
    manifest: LabFixtureManifest,
    *,
    initial_generation_id: str,
    activated_generation_id: str,
    rollback_generation_id: str,
) -> None:
    if len(state["generations"]) != 3:
        raise ExecutionRehearsalError("Final generation count is not three.")
    initial, activated, rolled_back = state["generations"]
    if (
        initial["champion_generation_id"] != initial_generation_id
        or activated["champion_generation_id"] != activated_generation_id
        or rolled_back["champion_generation_id"] != rollback_generation_id
    ):
        raise ExecutionRehearsalError("Final generation order differs.")
    if activated["previous_champion_generation_id"] != initial_generation_id:
        raise ExecutionRehearsalError("Activation predecessor link differs.")
    if rolled_back["previous_champion_generation_id"] != activated_generation_id:
        raise ExecutionRehearsalError("Rollback predecessor link differs.")
    if (
        activated["model_artifact_id"]
        != manifest.challenger.model_artifact_id
    ):
        raise ExecutionRehearsalError("Activated artifact differs.")
    if rolled_back["model_artifact_id"] != manifest.champion.model_artifact_id:
        raise ExecutionRehearsalError("Rollback artifact differs.")
    _assert_counts(
        state,
        activation_execution_count=1,
        rollback_request_count=1,
        rollback_plan_count=1,
        rollback_execution_count=1,
    )
    expected_events = (
        "INITIAL_REGISTERED",
        "RETIRED_BY_ACTIVATION",
        "CHAMPION_ACTIVATED",
        "RETIRED_BY_ROLLBACK",
        "CHAMPION_ROLLED_BACK",
    )
    if tuple(item["event_type"] for item in state["registry_events"]) != expected_events:
        raise ExecutionRehearsalError("Registry event order differs.")
    if state["pending_activation_plans"] or state["pending_rollback_plans"]:
        raise ExecutionRehearsalError("A pending plan remains after rehearsal.")
    if state["foreign_key_violations"]:
        raise ExecutionRehearsalError("Final foreign-key violations exist.")


def _common(
    path: Path,
    *,
    output: str,
    profile: ExecutionRehearsalProfile = DEFAULT_EXECUTION_REHEARSAL_PROFILE,
) -> tuple[str, ...]:
    return (
        "--database",
        str(path.resolve()),
        "--environment",
        profile.environment,
        "--scope",
        profile.scope,
        "--output",
        output,
    )


def _activation_arguments_for(path: Path, profile):
    plan = inspect_rehearsal_state(path)["pending_activation_plans"][0]
    return (
        "execute-activation",
        *_common(path, output="json", profile=profile),
        "--execution-request-id",
        profile.activation_execution_request_id,
        "--plan-id",
        plan["activation_plan_id"],
        "--plan-fingerprint",
        plan["activation_plan_fingerprint"],
        "--executed-at",
        profile.activation_executed_at,
        "--operator",
        profile.execution_label,
        "--confirm",
        "ACTIVATE_CHAMPION",
    )


def _create_failure_trigger(path: Path, name: str, table: str) -> None:
    database = Database(str(path))
    try:
        database.connection.execute(
            f"""CREATE TRIGGER {name}
                BEFORE INSERT ON {table}
                BEGIN SELECT RAISE(ABORT,'injected rehearsal failure'); END"""
        )
        database.connection.commit()
    finally:
        database.close()


def _drop_trigger(path: Path, name: str) -> None:
    database = Database(str(path))
    try:
        database.connection.execute(f"DROP TRIGGER {name}")
        database.connection.commit()
    finally:
        database.close()


def _artifact_arguments(reference, prefix: str | None = None) -> tuple[str, ...]:
    option = f"{prefix}-" if prefix else ""
    fields = (
        ("model-artifact-id", reference.model_artifact_id),
        ("model-artifact-fingerprint", reference.model_artifact_fingerprint),
        ("preprocessing-fingerprint", reference.preprocessing_fingerprint),
        (
            "calibration-artifact-set-id",
            reference.calibration_artifact_set_id,
        ),
        (
            "calibration-artifact-set-fingerprint",
            reference.calibration_artifact_set_fingerprint,
        ),
        ("feature-schema-version", reference.feature_schema_version),
        ("feature-schema-fingerprint", reference.feature_schema_fingerprint),
        ("target-contract-version", reference.target_contract_version),
        (
            "probability-contract-version",
            reference.probability_contract_version,
        ),
        (
            "runtime-compatibility-version",
            reference.runtime_compatibility_version,
        ),
    )
    return tuple(
        value
        for name, field_value in fields
        for value in (f"--{option}{name}", field_value)
    )


def _replace_cli_option(
    arguments: tuple[str, ...],
    option: str,
    replacement: str,
) -> tuple[str, ...]:
    """Return arguments with one required option value replaced."""
    try:
        index = arguments.index(option)
    except ValueError as exc:
        raise ExecutionRehearsalError(
            f"Required CLI option is absent: {option}."
        ) from exc
    if index + 1 >= len(arguments):
        raise ExecutionRehearsalError(
            f"Required CLI option has no value: {option}."
        )
    updated = list(arguments)
    updated[index + 1] = replacement
    return tuple(updated)


def _expect_status(capture: CommandCapture, status: str) -> None:
    if capture.parsed_json is None or capture.parsed_json["status"] != status:
        raise ExecutionRehearsalError(
            f"{capture.name} returned an unexpected typed status."
        )


def _assert_counts(state: dict, **expected: int) -> None:
    failures = tuple(
        f"{name}={state[name]} expected {value}"
        for name, value in expected.items()
        if state[name] != value
    )
    if failures:
        raise ExecutionRehearsalError("; ".join(failures))


def _count(connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _protected_table_fingerprints(connection) -> dict[str, str]:
    protected = {}
    tables = tuple(
        row[0]
        for row in connection.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%'
               ORDER BY name"""
        )
        if row[0] not in _ACTIVATION_TABLES
    )
    for table in tables:
        rows = tuple(
            tuple(row)
            for row in connection.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid'
            )
        )
        material = json.dumps(rows, default=str, ensure_ascii=False)
        protected[table] = sha256(material.encode("utf-8")).hexdigest()
    return protected


def _single_row(path: Path, query: str) -> dict:
    database = Database(str(path))
    try:
        rows = database.connection.execute(query).fetchall()
        if len(rows) != 1:
            raise ExecutionRehearsalError(
                "Expected exactly one execution row."
            )
        return dict(rows[0])
    finally:
        database.close()


def _redact_capture(
    capture: CommandCapture,
    database_path: Path,
) -> CommandCapture:
    redacted = tuple(
        "<DISPOSABLE_DB>"
        if value == str(database_path.resolve())
        else value
        for value in capture.arguments
    )
    return CommandCapture(
        name=capture.name,
        arguments=redacted,
        exit_code=capture.exit_code,
        stdout=capture.stdout,
        parsed_json=capture.parsed_json,
    )
