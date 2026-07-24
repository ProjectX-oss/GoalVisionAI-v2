"""Manual operator orchestration over the existing activation domain."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import Any

from app.model_activation import (
    ActivationExecutionCommand,
    ActivationOutcome,
    ActivationRequest,
    ActivationStatus,
    ChampionGeneration,
    RollbackExecutionCommand,
    RollbackRequest,
    RuntimeArtifactReference,
    sha256_fingerprint,
)
from app.model_activation.evidence import build_activation_evidence
from app.model_activation.exceptions import (
    ActivationConflictError,
    ActivationNotEligibleError,
    ActivationPersistenceError,
    ActivationValidationError,
    ChampionStateInvalidError,
)
from app.model_activation.fingerprint import canonical_value
from app.model_activation.inspection import verify_generation_chain
from app.model_activation.source_verification import verify_runtime_artifact

from .models import (
    DiagnosticFinding,
    DiagnosticStatus,
    OperationMode,
    OperatorResult,
    OperatorStatus,
)


ACTIVATION_CONFIRMATION = "ACTIVATE_CHAMPION"
ROLLBACK_CONFIRMATION = "ROLLBACK_CHAMPION"
_READ_ONLY_RECOVERY = (
    "Run show-champion, show-activation, list-generations, and diagnose-state; "
    "never edit append-only rows manually."
)


class ModelOperationsService:
    def __init__(
        self,
        *,
        repository,
        activation_service,
        resolver,
        model_repository,
        calibration_repository,
        shadow_repository,
        policy,
        connection: sqlite3.Connection,
    ) -> None:
        self._repository = repository
        self._activation_service = activation_service
        self._resolver = resolver
        self._model_repository = model_repository
        self._calibration_repository = calibration_repository
        self._shadow_repository = shadow_repository
        self._policy = policy
        self._connection = connection

    def bootstrap_champion(
        self,
        *,
        scope: str,
        artifact: RuntimeArtifactReference,
        timestamp: str,
        reason: str,
        operator: str,
    ) -> OperatorResult:
        try:
            if not reason.strip() or not operator.strip():
                raise ActivationValidationError(
                    "Bootstrap reason and operator are required."
                )
            if self._repository.list_generations(scope):
                raise ActivationConflictError(
                    "Champion scope is already initialized."
                )
            verify_runtime_artifact(
                artifact,
                self._model_repository,
                self._calibration_repository,
                self._policy,
            )
            generation = self._repository.bootstrap_champion(
                scope,
                artifact,
                timestamp,
                reason,
                operator,
            )
            return _result(
                "bootstrap-champion",
                OperatorStatus.BOOTSTRAP_EXECUTED,
                True,
                OperationMode.STATE_CHANGING,
                True,
                scope,
                details={"champion_generation": _generation_details(generation)},
            )
        except (
            ActivationConflictError,
            ActivationNotEligibleError,
            ActivationPersistenceError,
            ActivationValidationError,
            ChampionStateInvalidError,
        ) as exc:
            return _known_failure(
                "bootstrap-champion",
                OperatorStatus.BOOTSTRAP_REJECTED,
                scope,
                exc,
            )

    def prepare_activation(
        self,
        request: ActivationRequest,
        *,
        expected_shadow_evidence_fingerprint: str,
    ) -> OperatorResult:
        try:
            if not expected_shadow_evidence_fingerprint.strip():
                raise ActivationValidationError(
                    "An explicit shadow-evidence fingerprint is required."
                )
            evidence = build_activation_evidence(
                request,
                self._shadow_repository,
            )
            if (
                evidence.evidence_fingerprint
                != expected_shadow_evidence_fingerprint
            ):
                raise ActivationNotEligibleError(
                    "Explicit shadow-evidence fingerprint differs."
                )
            outcome = self._activation_service.prepare_activation(request)
            if outcome.status is not ActivationStatus.ACTIVATION_PLAN_PREPARED:
                return _activation_failure("prepare-activation", outcome)
            plan = self._repository.load_activation_plan(outcome.plan_id)
            if plan is None:
                raise ActivationPersistenceError(
                    "Prepared activation plan could not be reloaded."
                )
            return _result(
                "prepare-activation",
                OperatorStatus.ACTIVATION_PLAN_PREPARED,
                True,
                OperationMode.STATE_CHANGING,
                False,
                request.model_scope,
                details={
                    "activation_plan_id": plan.activation_plan_id,
                    "activation_plan_fingerprint": (
                        plan.activation_plan_fingerprint
                    ),
                    "current_champion_generation_id": (
                        request.current_champion_generation_id
                    ),
                    "challenger_model_artifact_id": (
                        request.challenger.model_artifact_id
                    ),
                    "expected_shadow_evidence_fingerprint": (
                        expected_shadow_evidence_fingerprint
                    ),
                    "validations": tuple(
                        {
                            "category": item.category,
                            "name": item.name,
                            "status": item.status.value,
                            "fingerprint": item.validation_fingerprint,
                        }
                        for item in plan.validations
                    ),
                    "review": (
                        "Plan persisted for review only; champion state "
                        "has not changed."
                    ),
                },
            )
        except (
            ActivationNotEligibleError,
            ActivationPersistenceError,
            ActivationValidationError,
            ChampionStateInvalidError,
        ) as exc:
            return _known_failure(
                "prepare-activation",
                OperatorStatus.ACTIVATION_REJECTED,
                request.model_scope,
                exc,
            )

    def execute_activation(
        self,
        command: ActivationExecutionCommand,
        *,
        confirmation: str,
    ) -> OperatorResult:
        if confirmation != ACTIVATION_CONFIRMATION:
            return _confirmation_failure(
                "execute-activation",
                command.activation_plan_id,
                ACTIVATION_CONFIRMATION,
            )
        existing = self._row(
            """SELECT activation_execution_request_id,activation_plan_id,
                      activation_plan_fingerprint,champion_generation_id,
                      execution_fingerprint
               FROM model_activation_executions
               WHERE activation_execution_request_id=? OR activation_plan_id=?
               ORDER BY activation_execution_id LIMIT 1""",
            (
                command.activation_execution_request_id,
                command.activation_plan_id,
            ),
        )
        if existing is not None:
            if (
                existing["activation_plan_id"] == command.activation_plan_id
                and existing["activation_plan_fingerprint"]
                == command.activation_plan_fingerprint
            ):
                return _result(
                    "execute-activation",
                    OperatorStatus.ACTIVATION_ALREADY_EXECUTED,
                    False,
                    OperationMode.STATE_CHANGING,
                    False,
                    details=existing,
                    reason_codes=("PLAN_ALREADY_EXECUTED",),
                    recovery=(_READ_ONLY_RECOVERY,),
                )
            return _result(
                "execute-activation",
                OperatorStatus.ACTIVATION_CONFLICT,
                False,
                OperationMode.STATE_CHANGING,
                False,
                reason_codes=("EXECUTION_REQUEST_CONFLICT",),
                recovery=(_READ_ONLY_RECOVERY,),
            )
        try:
            outcome = self._activation_service.execute_activation(command)
        except (
            ActivationConflictError,
            ActivationNotEligibleError,
            ActivationPersistenceError,
            ActivationValidationError,
            ChampionStateInvalidError,
        ) as exc:
            return _known_failure(
                "execute-activation",
                OperatorStatus.ACTIVATION_REJECTED,
                "",
                exc,
            )
        if outcome.status is ActivationStatus.ACTIVATION_EXECUTED:
            generation = outcome.champion_generation
            assert generation is not None
            execution = self._execution_row(
                "model_activation_executions",
                "activation_plan_id",
                command.activation_plan_id,
            )
            return _result(
                "execute-activation",
                OperatorStatus.ACTIVATION_EXECUTED,
                True,
                OperationMode.STATE_CHANGING,
                True,
                outcome.model_scope,
                details={
                    "replaced_champion_generation_id": (
                        generation.previous_champion_generation_id
                    ),
                    "new_champion_generation": _generation_details(generation),
                    "activation_execution_fingerprint": (
                        execution["execution_fingerprint"]
                        if execution is not None
                        else None
                    ),
                },
            )
        return _activation_failure("execute-activation", outcome)

    def prepare_rollback(self, request: RollbackRequest) -> OperatorResult:
        try:
            outcome = self._activation_service.prepare_rollback(request)
        except (
            ActivationConflictError,
            ActivationNotEligibleError,
            ActivationPersistenceError,
            ActivationValidationError,
            ChampionStateInvalidError,
        ) as exc:
            return _known_failure(
                "prepare-rollback",
                OperatorStatus.ROLLBACK_REJECTED,
                request.model_scope,
                exc,
            )
        if outcome.status is ActivationStatus.ROLLBACK_PLAN_PREPARED:
            plan = self._repository.load_rollback_plan(outcome.plan_id)
            if plan is None:
                return _known_failure(
                    "prepare-rollback",
                    OperatorStatus.ROLLBACK_REJECTED,
                    request.model_scope,
                    ActivationPersistenceError(
                        "Prepared rollback plan could not be reloaded."
                    ),
                )
            return _result(
                "prepare-rollback",
                OperatorStatus.ROLLBACK_PLAN_PREPARED,
                True,
                OperationMode.STATE_CHANGING,
                False,
                request.model_scope,
                details={
                    "rollback_plan_id": plan.rollback_plan_id,
                    "rollback_plan_fingerprint": (
                        plan.rollback_plan_fingerprint
                    ),
                    "current_champion_generation_id": (
                        request.current_champion_generation_id
                    ),
                    "target_champion_generation_id": (
                        request.target_champion_generation_id
                    ),
                    "incident_reference": request.incident_reference,
                    "validations": tuple(
                        {
                            "category": item.category,
                            "name": item.name,
                            "status": item.status.value,
                            "fingerprint": item.validation_fingerprint,
                        }
                        for item in plan.validations
                    ),
                    "review": (
                        "Plan persisted for review only; champion state "
                        "has not changed."
                    ),
                },
            )
        return _activation_failure("prepare-rollback", outcome)

    def execute_rollback(
        self,
        command: RollbackExecutionCommand,
        *,
        confirmation: str,
    ) -> OperatorResult:
        if confirmation != ROLLBACK_CONFIRMATION:
            return _confirmation_failure(
                "execute-rollback",
                command.rollback_plan_id,
                ROLLBACK_CONFIRMATION,
            )
        existing = self._row(
            """SELECT rollback_execution_request_id,rollback_plan_id,
                      rollback_plan_fingerprint,champion_generation_id,
                      execution_fingerprint
               FROM model_rollback_executions
               WHERE rollback_execution_request_id=? OR rollback_plan_id=?
               ORDER BY rollback_execution_id LIMIT 1""",
            (
                command.rollback_execution_request_id,
                command.rollback_plan_id,
            ),
        )
        if existing is not None:
            if (
                existing["rollback_plan_id"] == command.rollback_plan_id
                and existing["rollback_plan_fingerprint"]
                == command.rollback_plan_fingerprint
            ):
                return _result(
                    "execute-rollback",
                    OperatorStatus.ROLLBACK_ALREADY_EXECUTED,
                    False,
                    OperationMode.STATE_CHANGING,
                    False,
                    details=existing,
                    reason_codes=("PLAN_ALREADY_EXECUTED",),
                    recovery=(_READ_ONLY_RECOVERY,),
                )
            return _result(
                "execute-rollback",
                OperatorStatus.ROLLBACK_CONFLICT,
                False,
                OperationMode.STATE_CHANGING,
                False,
                reason_codes=("EXECUTION_REQUEST_CONFLICT",),
                recovery=(_READ_ONLY_RECOVERY,),
            )
        try:
            outcome = self._activation_service.execute_rollback(command)
        except (
            ActivationConflictError,
            ActivationNotEligibleError,
            ActivationPersistenceError,
            ActivationValidationError,
            ChampionStateInvalidError,
        ) as exc:
            return _known_failure(
                "execute-rollback",
                OperatorStatus.ROLLBACK_REJECTED,
                "",
                exc,
            )
        if outcome.status is ActivationStatus.ROLLBACK_EXECUTED:
            generation = outcome.champion_generation
            assert generation is not None
            execution = self._execution_row(
                "model_rollback_executions",
                "rollback_plan_id",
                command.rollback_plan_id,
            )
            return _result(
                "execute-rollback",
                OperatorStatus.ROLLBACK_EXECUTED,
                True,
                OperationMode.STATE_CHANGING,
                True,
                outcome.model_scope,
                details={
                    "replaced_champion_generation_id": (
                        generation.previous_champion_generation_id
                    ),
                    "new_champion_generation": _generation_details(generation),
                    "rollback_execution_fingerprint": (
                        execution["execution_fingerprint"]
                        if execution is not None
                        else None
                    ),
                },
            )
        return _activation_failure("execute-rollback", outcome)

    def show_champion(self, scope: str) -> OperatorResult:
        resolution = self._resolver.resolve(scope)
        if (
            resolution.status is not ActivationStatus.CHAMPION_RESOLVED
            or resolution.champion_generation is None
        ):
            return _result(
                "show-champion",
                OperatorStatus.NOT_FOUND,
                False,
                OperationMode.READ_ONLY,
                False,
                scope,
                reason_codes=tuple(resolution.reason_codes),
                recovery=(_READ_ONLY_RECOVERY,),
            )
        return _result(
            "show-champion",
            OperatorStatus.CHAMPION_SHOWN,
            True,
            OperationMode.READ_ONLY,
            False,
            scope,
            details={
                "champion_generation": _generation_details(
                    resolution.champion_generation
                )
            },
        )

    def show_activation(self, scope: str, plan_id: str) -> OperatorResult:
        plan = self._repository.load_activation_plan(plan_id)
        plan_type = "ACTIVATION"
        if plan is None:
            plan = self._repository.load_rollback_plan(plan_id)
            plan_type = "ROLLBACK"
        if plan is None:
            return _result(
                "show-activation",
                OperatorStatus.NOT_FOUND,
                False,
                OperationMode.READ_ONLY,
                False,
                scope,
                reason_codes=("PLAN_NOT_FOUND",),
            )
        request_scope = plan.request.model_scope
        if request_scope != scope:
            return _result(
                "show-activation",
                OperatorStatus.NOT_FOUND,
                False,
                OperationMode.READ_ONLY,
                False,
                scope,
                reason_codes=("PLAN_SCOPE_MISMATCH",),
            )
        activation_plan_id = plan_id if plan_type == "ACTIVATION" else None
        rollback_plan_id = plan_id if plan_type == "ROLLBACK" else None
        validations = self._rows(
            """SELECT category,validation_name,validation_status,
                      detail_snapshot,validation_fingerprint,deterministic_order
               FROM model_activation_validations
               WHERE activation_plan_id IS ? AND rollback_plan_id IS ?
               ORDER BY deterministic_order""",
            (activation_plan_id, rollback_plan_id),
        )
        evidence = (
            self._rows(
                """SELECT shadow_execution_id,shadow_execution_fingerprint,
                          shadow_settlement_fingerprint,
                          evidence_link_fingerprint,deterministic_order
                   FROM model_activation_evidence_links
                   WHERE activation_plan_id=?
                   ORDER BY deterministic_order""",
                (plan_id,),
            )
            if plan_type == "ACTIVATION"
            else ()
        )
        execution_table = (
            "model_activation_executions"
            if plan_type == "ACTIVATION"
            else "model_rollback_executions"
        )
        execution = self._row(
            f"SELECT * FROM {execution_table} WHERE "
            f"{'activation_plan_id' if plan_type == 'ACTIVATION' else 'rollback_plan_id'}=?",
            (plan_id,),
        )
        generation = None
        events: tuple[dict[str, Any], ...] = ()
        if execution is not None:
            generation_id = execution["champion_generation_id"]
            generation = self._repository.load_generation(generation_id)
            events = self._rows(
                """SELECT registry_event_id,event_type,operator_identity,
                          event_timestamp_utc,event_fingerprint
                   FROM model_champion_registry_events
                   WHERE champion_generation_id=?
                   ORDER BY event_timestamp_utc,event_type""",
                (generation_id,),
            )
        return _result(
            "show-activation",
            OperatorStatus.ACTIVATION_SHOWN,
            True,
            OperationMode.READ_ONLY,
            False,
            scope,
            details={
                "plan_type": plan_type,
                "request": canonical_value(plan.request),
                "plan": canonical_value(plan),
                "validations": validations,
                "evidence_links": evidence,
                "execution": execution,
                "registry_events": events,
                "resulting_champion_generation": (
                    _generation_details(generation)
                    if generation is not None
                    else None
                ),
                "typed_outcome": (
                    "EXECUTED" if execution is not None else "PREPARED"
                ),
            },
        )

    def list_generations(self, scope: str, limit: int) -> OperatorResult:
        if limit < 1 or limit > 100:
            return _result(
                "list-generations",
                OperatorStatus.INVALID_ARGUMENTS,
                False,
                OperationMode.READ_ONLY,
                False,
                scope,
                reason_codes=("LIMIT_OUT_OF_RANGE",),
            )
        generations = self._repository.list_generations(scope)
        selected = generations[-limit:]
        return _result(
            "list-generations",
            OperatorStatus.GENERATIONS_LISTED,
            True,
            OperationMode.READ_ONLY,
            False,
            scope,
            details={
                "total_generations": len(generations),
                "returned_generations": len(selected),
                "generations": tuple(
                    _generation_details(item) for item in selected
                ),
            },
        )

    def diagnose_state(self, scope: str) -> OperatorResult:
        findings: list[DiagnosticFinding] = []
        try:
            migration = self._connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        except sqlite3.DatabaseError:
            migration = None
        if migration is None or int(migration) < 31:
            findings.append(
                _finding(
                    "SCHEMA_BELOW_V31",
                    DiagnosticStatus.INVALID_STATE,
                    "Database schema is below migration v31.",
                )
            )

        try:
            generations = self._repository.list_generations(scope)
        except Exception:
            findings.append(
                _finding(
                    "CHAMPION_REGISTRY_UNREADABLE",
                    DiagnosticStatus.INVALID_STATE,
                    "Champion generation snapshots could not be read safely.",
                )
            )
            generations = ()
        if not generations:
            findings.append(
                _finding(
                    "MISSING_CHAMPION",
                    DiagnosticStatus.INVALID_STATE,
                    "No champion generation exists for the configured scope.",
                )
            )
        try:
            chain_failures = verify_generation_chain(self._repository, scope)
        except Exception:
            chain_failures = ("CHAMPION_GENERATION_CHAIN_UNREADABLE",)
        for failure in chain_failures:
            findings.append(
                _finding(
                    "INVALID_GENERATION_CHAIN",
                    DiagnosticStatus.INVALID_STATE,
                    failure,
                )
            )
        numbers = [item.generation_number for item in generations]
        if len(numbers) != len(set(numbers)):
            findings.append(
                _finding(
                    "DUPLICATE_ACTIVE_GENERATION",
                    DiagnosticStatus.INVALID_STATE,
                    "Duplicate generation numbers make current state ambiguous.",
                )
            )
        for generation in generations:
            if not _generation_fingerprint_valid(generation):
                findings.append(
                    _finding(
                        "GENERATION_FINGERPRINT_MISMATCH",
                        DiagnosticStatus.INVALID_STATE,
                        generation.champion_generation_id,
                    )
                )
            event_types = {
                row["event_type"]
                for row in self._rows(
                    """SELECT event_type FROM model_champion_registry_events
                       WHERE champion_generation_id=?""",
                    (generation.champion_generation_id,),
                )
            }
            required = {
                "INITIAL_REGISTRATION": "INITIAL_REGISTERED",
                "APPROVED_ACTIVATION": "CHAMPION_ACTIVATED",
                "MANUAL_ROLLBACK": "CHAMPION_ROLLED_BACK",
            }[generation.activation_reason.value]
            if required not in event_types:
                findings.append(
                    _finding(
                        "MISSING_REGISTRY_EVENT",
                        DiagnosticStatus.RECOVERY_REQUIRED,
                        f"{generation.champion_generation_id}:{required}",
                    )
                )
            if (
                generation.activation_reason.value == "APPROVED_ACTIVATION"
                and self._row(
                    """SELECT activation_execution_id
                       FROM model_activation_executions
                       WHERE champion_generation_id=?""",
                    (generation.champion_generation_id,),
                )
                is None
            ):
                findings.append(
                    _finding(
                        "MISSING_ACTIVATION_EXECUTION",
                        DiagnosticStatus.RECOVERY_REQUIRED,
                        generation.champion_generation_id,
                    )
                )
            if (
                generation.activation_reason.value == "MANUAL_ROLLBACK"
                and self._row(
                    """SELECT rollback_execution_id
                       FROM model_rollback_executions
                       WHERE champion_generation_id=?""",
                    (generation.champion_generation_id,),
                )
                is None
            ):
                findings.append(
                    _finding(
                        "MISSING_ROLLBACK_EXECUTION",
                        DiagnosticStatus.RECOVERY_REQUIRED,
                        generation.champion_generation_id,
                    )
                )

        resolution = self._resolver.resolve(scope)
        if resolution.status is not ActivationStatus.CHAMPION_RESOLVED:
            findings.append(
                _finding(
                    "RUNTIME_RESOLUTION_FAILED",
                    DiagnosticStatus.INVALID_STATE,
                    "; ".join(resolution.reason_codes)
                    or "Runtime champion resolution failed.",
                )
            )

        pending_activation = self._rows(
            """SELECT p.activation_plan_id,p.prepared_timestamp_utc
               FROM model_activation_plans p
               JOIN model_activation_requests r
                 ON r.activation_request_id=p.activation_request_id
               LEFT JOIN model_activation_executions e
                 ON e.activation_plan_id=p.activation_plan_id
               WHERE r.model_scope=? AND e.activation_plan_id IS NULL
               ORDER BY p.prepared_timestamp_utc,p.activation_plan_id""",
            (scope,),
        )
        pending_rollback = self._rows(
            """SELECT p.rollback_plan_id,p.prepared_timestamp_utc
               FROM model_rollback_plans p
               JOIN model_rollback_requests r
                 ON r.rollback_request_id=p.rollback_request_id
               LEFT JOIN model_rollback_executions e
                 ON e.rollback_plan_id=p.rollback_plan_id
               WHERE r.model_scope=? AND e.rollback_plan_id IS NULL
               ORDER BY p.prepared_timestamp_utc,p.rollback_plan_id""",
            (scope,),
        )
        if pending_activation or pending_rollback:
            findings.append(
                _finding(
                    "PREPARED_PLAN_REVIEW_REQUIRED",
                    DiagnosticStatus.WARNING,
                    "One or more prepared plans have not been executed.",
                )
            )
        try:
            trigger_count = self._connection.execute(
                """SELECT COUNT(*) FROM sqlite_master
                   WHERE type='trigger' AND
                   (name LIKE 'model_activation_%_no_%'
                    OR name LIKE 'model_rollback_%_no_%'
                    OR name LIKE 'model_champion_%_no_%')"""
            ).fetchone()[0]
        except sqlite3.DatabaseError:
            trigger_count = 0
        if trigger_count < 20:
            findings.append(
                _finding(
                    "APPEND_ONLY_GUARDS_MISSING",
                    DiagnosticStatus.INVALID_STATE,
                    f"Expected at least 20 guards; found {trigger_count}.",
                )
            )

        diagnostic_status = _diagnostic_status(findings)
        return _result(
            "diagnose-state",
            diagnostic_status,
            diagnostic_status is DiagnosticStatus.HEALTHY,
            OperationMode.READ_ONLY,
            False,
            scope,
            details={
                "migration_version": migration,
                "generation_count": len(generations),
                "pending_activation_plans": pending_activation,
                "pending_rollback_plans": pending_rollback,
                "append_only_guard_count": trigger_count,
                "findings": tuple(asdict(item) for item in findings),
            },
            recovery=(
                ()
                if diagnostic_status is DiagnosticStatus.HEALTHY
                else (_READ_ONLY_RECOVERY,)
            ),
        )

    def _execution_row(self, table: str, key: str, value: str):
        return self._row(
            f"SELECT * FROM {table} WHERE {key}=?",
            (value,),
        )

    def _row(self, sql: str, parameters: tuple[Any, ...]):
        row = self._connection.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None

    def _rows(self, sql: str, parameters: tuple[Any, ...]):
        return tuple(
            dict(row)
            for row in self._connection.execute(sql, parameters).fetchall()
        )


def _activation_failure(command: str, outcome: ActivationOutcome) -> OperatorResult:
    mapping = {
        ActivationStatus.ACTIVATION_ALREADY_EXECUTED: (
            OperatorStatus.ACTIVATION_ALREADY_EXECUTED
        ),
        ActivationStatus.ACTIVATION_STALE_PLAN: (
            OperatorStatus.ACTIVATION_STALE_PLAN
        ),
        ActivationStatus.ACTIVATION_STATE_CHANGED: (
            OperatorStatus.ACTIVATION_STALE_PLAN
        ),
        ActivationStatus.ACTIVATION_CONFLICT: (
            OperatorStatus.ACTIVATION_CONFLICT
        ),
        ActivationStatus.ROLLBACK_ALREADY_EXECUTED: (
            OperatorStatus.ROLLBACK_ALREADY_EXECUTED
        ),
        ActivationStatus.ROLLBACK_STALE_PLAN: (
            OperatorStatus.ROLLBACK_STALE_PLAN
        ),
        ActivationStatus.ROLLBACK_CONFLICT: OperatorStatus.ROLLBACK_CONFLICT,
    }
    fallback = (
        OperatorStatus.ROLLBACK_REJECTED
        if command.startswith("prepare-rollback")
        or command.startswith("execute-rollback")
        else OperatorStatus.ACTIVATION_REJECTED
    )
    return _result(
        command,
        mapping.get(outcome.status, fallback),
        False,
        OperationMode.STATE_CHANGING,
        False,
        outcome.model_scope or None,
        reason_codes=outcome.reason_codes or (outcome.status.value,),
        recovery=(_READ_ONLY_RECOVERY,),
        details={
            "plan_id": outcome.plan_id,
            "plan_fingerprint": outcome.plan_fingerprint,
        },
    )


def _known_failure(
    command: str,
    status: OperatorStatus,
    scope: str,
    error: Exception,
) -> OperatorResult:
    return _result(
        command,
        status,
        False,
        OperationMode.STATE_CHANGING,
        False,
        scope,
        reason_codes=(type(error).__name__.upper(), str(error)),
        recovery=(_READ_ONLY_RECOVERY,),
    )


def _confirmation_failure(
    command: str,
    plan_id: str,
    expected: str,
) -> OperatorResult:
    return _result(
        command,
        OperatorStatus.CONFIRMATION_REJECTED,
        False,
        OperationMode.STATE_CHANGING,
        False,
        reason_codes=("EXACT_CONFIRMATION_REQUIRED",),
        recovery=(
            f"Review plan {plan_id}, then supply the exact phrase {expected}.",
        ),
    )


def _result(
    command: str,
    status,
    success: bool,
    mode: OperationMode,
    changed: bool,
    scope: str | None = None,
    *,
    reason_codes: tuple[str, ...] = (),
    recovery: tuple[str, ...] = (),
    details: dict[str, Any] | None = None,
) -> OperatorResult:
    status_value = status.value if hasattr(status, "value") else str(status)
    return OperatorResult(
        command=command,
        status=status_value,
        success=success,
        mode=mode,
        production_state_changed=changed,
        model_scope=scope,
        reason_codes=tuple(reason_codes),
        recovery_guidance=tuple(recovery),
        details=details or {},
    )


def _generation_details(generation: ChampionGeneration) -> dict[str, Any]:
    return {
        "model_scope": generation.model_scope,
        "champion_generation_id": generation.champion_generation_id,
        "generation_number": generation.generation_number,
        "model_artifact_id": generation.artifact.model_artifact_id,
        "model_artifact_fingerprint": (
            generation.artifact.model_artifact_fingerprint
        ),
        "preprocessing_fingerprint": (
            generation.artifact.preprocessing_fingerprint
        ),
        "calibration_artifact_set_id": (
            generation.artifact.calibration_artifact_set_id
        ),
        "calibration_artifact_set_fingerprint": (
            generation.artifact.calibration_artifact_set_fingerprint
        ),
        "feature_schema_version": generation.artifact.feature_schema_version,
        "feature_schema_fingerprint": (
            generation.artifact.feature_schema_fingerprint
        ),
        "target_contract_version": generation.artifact.target_contract_version,
        "probability_contract_version": (
            generation.artifact.probability_contract_version
        ),
        "runtime_compatibility_version": (
            generation.artifact.runtime_compatibility_version
        ),
        "activation_timestamp_utc": generation.activation_timestamp_utc,
        "activation_reason": generation.activation_reason.value,
        "activation_reason_detail": generation.activation_reason_detail,
        "previous_champion_generation_id": (
            generation.previous_champion_generation_id
        ),
        "source_promotion_recommendation_id": (
            generation.source_recommendation_id
        ),
        "source_promotion_recommendation_fingerprint": (
            generation.source_recommendation_fingerprint
        ),
        "source_shadow_evidence_fingerprint": (
            generation.source_shadow_evidence_fingerprint
        ),
        "activation_plan_id": generation.activation_plan_id,
        "rollback_plan_id": generation.rollback_plan_id,
        "generation_fingerprint": generation.generation_fingerprint,
    }


def _generation_fingerprint_valid(generation: ChampionGeneration) -> bool:
    core = {
        "scope": generation.model_scope,
        "number": generation.generation_number,
        "artifact": generation.artifact,
        "timestamp": generation.activation_timestamp_utc,
        "reason": generation.activation_reason,
        "detail": generation.activation_reason_detail,
        "recommendation_id": generation.source_recommendation_id,
        "recommendation_fp": generation.source_recommendation_fingerprint,
        "evidence_fp": generation.source_shadow_evidence_fingerprint,
        "previous_id": generation.previous_champion_generation_id,
        "activation_plan_id": generation.activation_plan_id,
        "rollback_plan_id": generation.rollback_plan_id,
    }
    return sha256_fingerprint(core) == generation.generation_fingerprint


def _finding(
    code: str,
    severity: DiagnosticStatus,
    detail: str,
) -> DiagnosticFinding:
    return DiagnosticFinding(code, severity, detail, _READ_ONLY_RECOVERY)


def _diagnostic_status(
    findings: list[DiagnosticFinding],
) -> DiagnosticStatus:
    severities = {item.severity for item in findings}
    if DiagnosticStatus.INVALID_STATE in severities:
        return DiagnosticStatus.INVALID_STATE
    if DiagnosticStatus.RECOVERY_REQUIRED in severities:
        return DiagnosticStatus.RECOVERY_REQUIRED
    if DiagnosticStatus.WARNING in severities:
        return DiagnosticStatus.WARNING
    return DiagnosticStatus.HEALTHY
