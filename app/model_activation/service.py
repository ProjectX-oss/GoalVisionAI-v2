"""Two-stage manual activation and rollback application services."""

from __future__ import annotations

from .evidence import build_activation_evidence
from .exceptions import (
    ActivationConflictError, ActivationNotEligibleError, ActivationStalePlanError,
    ActivationValidationError, ChampionStateInvalidError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    ActivationOutcome, ActivationPlan, ActivationStatus, ActivationValidation,
    RollbackPlan, ValidationStatus,
)
from .source_verification import verify_promotion, verify_runtime_artifact
from .validation import (
    evaluate_evidence, utc, validate_activation_request, validate_rollback_request,
)


class ModelActivationService:
    def __init__(
        self, repository, comparison_repository, shadow_repository,
        model_repository, calibration_repository, policy,
    ):
        self._repository = repository
        self._comparison_repository = comparison_repository
        self._shadow_repository = shadow_repository
        self._model_repository = model_repository
        self._calibration_repository = calibration_repository
        self._policy = policy

    def prepare_activation(self, request):
        try:
            validate_activation_request(request, self._policy)
            current = self._repository.resolve_current_champion(request.model_scope)
            _match_current(request, current)
            verify_promotion(request, self._comparison_repository)
            verify_runtime_artifact(request.current_champion, self._model_repository, self._calibration_repository, self._policy)
            verify_runtime_artifact(request.challenger, self._model_repository, self._calibration_repository, self._policy)
            evidence = build_activation_evidence(request, self._shadow_repository)
            validations = evaluate_evidence(evidence, self._policy)
            if any(item.status is ValidationStatus.WARNING for item in validations) and self._policy.warnings_require_manual_override and not request.warning_override_reason:
                raise ActivationNotEligibleError("Warnings require an explicit manual override reason.")
            request_fp = sha256_fingerprint(request)
            prepared = utc(request.requested_timestamp_utc, "requested_timestamp_utc")
            policy_snapshot = canonical_json(self._policy)
            core = {
                "request_fingerprint": request_fp,
                "expected_generation_number": current.generation_number,
                "expected_registry_fingerprint": current.generation_fingerprint,
                "validations": tuple(item.validation_fingerprint for item in validations),
                "evidence": evidence.evidence_fingerprint,
                "policy": policy_snapshot,
                "prepared": prepared,
            }
            fingerprint = sha256_fingerprint(core)
            plan = ActivationPlan(
                activation_plan_id=f"activation-plan-{fingerprint}", request=request,
                request_fingerprint=request_fp,
                expected_registry_generation_number=current.generation_number,
                expected_registry_fingerprint=current.generation_fingerprint,
                validations=validations, evidence=evidence, policy_snapshot=policy_snapshot,
                prepared_timestamp_utc=prepared, activation_plan_fingerprint=fingerprint,
            )
            stored = self._repository.append_activation_plan(plan)
            return ActivationOutcome(
                ActivationStatus.ACTIVATION_PLAN_PREPARED, request.model_scope,
                stored.activation_plan_id, stored.activation_plan_fingerprint,
                current, (),
            )
        except ActivationConflictError as exc:
            return _failure(ActivationStatus.ACTIVATION_CONFLICT, request.model_scope, exc)
        except (ActivationValidationError, ActivationNotEligibleError, ChampionStateInvalidError) as exc:
            return _failure(ActivationStatus.ACTIVATION_NOT_ELIGIBLE, request.model_scope, exc)

    def execute_activation(self, command):
        plan = self._repository.load_activation_plan(command.activation_plan_id)
        if plan is None or plan.activation_plan_fingerprint != command.activation_plan_fingerprint:
            return _failure(ActivationStatus.ACTIVATION_STALE_PLAN, "", "Activation plan is missing or differs.")
        try:
            execution_timestamp = utc(command.execution_timestamp_utc, "execution_timestamp_utc")
            if execution_timestamp < plan.prepared_timestamp_utc or not command.operator_identity.strip():
                raise ActivationValidationError("Activation execution chronology or operator is invalid.")
            current = self._repository.resolve_current_champion(plan.request.model_scope)
            _match_current(plan.request, current)
            verify_promotion(plan.request, self._comparison_repository)
            verify_runtime_artifact(plan.request.current_champion, self._model_repository, self._calibration_repository, self._policy)
            verify_runtime_artifact(plan.request.challenger, self._model_repository, self._calibration_repository, self._policy)
            evidence = build_activation_evidence(plan.request, self._shadow_repository)
            if evidence.evidence_fingerprint != plan.evidence.evidence_fingerprint:
                raise ActivationStalePlanError("Shadow evidence changed after plan preparation.")
            generation, replay = self._repository.execute_activation(
                plan, command.activation_execution_request_id,
                command.execution_timestamp_utc, command.operator_identity,
            )
            return ActivationOutcome(
                ActivationStatus.ACTIVATION_ALREADY_EXECUTED if replay else ActivationStatus.ACTIVATION_EXECUTED,
                plan.request.model_scope, plan.activation_plan_id,
                plan.activation_plan_fingerprint, generation, (),
            )
        except ActivationStalePlanError as exc:
            return _failure(ActivationStatus.ACTIVATION_STALE_PLAN, plan.request.model_scope, exc, plan)
        except ChampionStateInvalidError as exc:
            return _failure(ActivationStatus.ACTIVATION_STATE_CHANGED, plan.request.model_scope, exc, plan)
        except ActivationConflictError as exc:
            return _failure(ActivationStatus.ACTIVATION_CONFLICT, plan.request.model_scope, exc, plan)
        except (ActivationValidationError, ActivationNotEligibleError) as exc:
            return _failure(ActivationStatus.ACTIVATION_NOT_ELIGIBLE, plan.request.model_scope, exc, plan)

    def prepare_rollback(self, request):
        try:
            validate_rollback_request(request, self._policy)
            current = self._repository.resolve_current_champion(request.model_scope)
            if (
                current.champion_generation_id != request.current_champion_generation_id
                or current.generation_fingerprint != request.current_champion_generation_fingerprint
            ):
                raise ActivationStalePlanError("Requested current champion is stale.")
            target = self._repository.load_generation(request.target_champion_generation_id)
            if target is None or target.model_scope != request.model_scope or target.generation_number >= current.generation_number:
                raise ActivationNotEligibleError("Rollback target is not a prior champion generation.")
            verify_runtime_artifact(target.artifact, self._model_repository, self._calibration_repository, self._policy)
            detail = canonical_json({"target": target.generation_fingerprint, "incident": request.incident_reference})
            validation_fp = sha256_fingerprint(("ROLLBACK_TARGET_COMPATIBLE", detail, self._policy.version))
            validations = (ActivationValidation(
                f"activation-validation-{validation_fp}", "ROLLBACK", "TARGET_RUNTIME_COMPATIBLE",
                ValidationStatus.PASS, detail, validation_fp, 0,
            ),)
            request_fp = sha256_fingerprint(request)
            prepared = utc(request.requested_timestamp_utc, "requested_timestamp_utc")
            policy_snapshot = canonical_json(self._policy)
            core = {
                "request": request_fp, "current": current.generation_fingerprint,
                "target": target.generation_fingerprint,
                "validations": tuple(item.validation_fingerprint for item in validations),
                "policy": policy_snapshot, "prepared": prepared,
            }
            fingerprint = sha256_fingerprint(core)
            plan = RollbackPlan(
                rollback_plan_id=f"rollback-plan-{fingerprint}", request=request,
                request_fingerprint=request_fp,
                expected_registry_generation_number=current.generation_number,
                expected_registry_fingerprint=current.generation_fingerprint,
                target_generation=target, validations=validations,
                policy_snapshot=policy_snapshot, prepared_timestamp_utc=prepared,
                rollback_plan_fingerprint=fingerprint,
            )
            stored = self._repository.append_rollback_plan(plan)
            return ActivationOutcome(
                ActivationStatus.ROLLBACK_PLAN_PREPARED, request.model_scope,
                stored.rollback_plan_id, stored.rollback_plan_fingerprint, current, (),
            )
        except ActivationConflictError as exc:
            return _failure(ActivationStatus.ROLLBACK_CONFLICT, request.model_scope, exc)
        except ActivationStalePlanError as exc:
            return _failure(ActivationStatus.ROLLBACK_STALE_PLAN, request.model_scope, exc)
        except (ActivationValidationError, ActivationNotEligibleError, ChampionStateInvalidError) as exc:
            return _failure(ActivationStatus.ROLLBACK_NOT_ELIGIBLE, request.model_scope, exc)

    def execute_rollback(self, command):
        plan = self._repository.load_rollback_plan(command.rollback_plan_id)
        if plan is None or plan.rollback_plan_fingerprint != command.rollback_plan_fingerprint:
            return _failure(ActivationStatus.ROLLBACK_STALE_PLAN, "", "Rollback plan is missing or differs.")
        try:
            execution_timestamp = utc(command.execution_timestamp_utc, "execution_timestamp_utc")
            if execution_timestamp < plan.prepared_timestamp_utc or not command.operator_identity.strip():
                raise ActivationValidationError("Rollback execution chronology or operator is invalid.")
            current = self._repository.resolve_current_champion(plan.request.model_scope)
            if current.generation_fingerprint != plan.expected_registry_fingerprint:
                raise ActivationStalePlanError("Champion state changed after rollback preparation.")
            verify_runtime_artifact(plan.target_generation.artifact, self._model_repository, self._calibration_repository, self._policy)
            generation, replay = self._repository.execute_rollback(
                plan, command.rollback_execution_request_id,
                command.execution_timestamp_utc, command.operator_identity,
            )
            return ActivationOutcome(
                ActivationStatus.ROLLBACK_ALREADY_EXECUTED if replay else ActivationStatus.ROLLBACK_EXECUTED,
                plan.request.model_scope, plan.rollback_plan_id,
                plan.rollback_plan_fingerprint, generation, (),
            )
        except ActivationStalePlanError as exc:
            return _failure(ActivationStatus.ROLLBACK_STALE_PLAN, plan.request.model_scope, exc, plan)
        except ActivationConflictError as exc:
            return _failure(ActivationStatus.ROLLBACK_CONFLICT, plan.request.model_scope, exc, plan)
        except (ActivationValidationError, ActivationNotEligibleError, ChampionStateInvalidError) as exc:
            return _failure(ActivationStatus.ROLLBACK_NOT_ELIGIBLE, plan.request.model_scope, exc, plan)


def prepare_activation(service, request): return service.prepare_activation(request)
def execute_activation(service, command): return service.execute_activation(command)
def prepare_rollback(service, request): return service.prepare_rollback(request)
def execute_rollback(service, command): return service.execute_rollback(command)


def _match_current(request, current):
    if (
        current.champion_generation_id != request.current_champion_generation_id
        or current.generation_fingerprint != request.current_champion_generation_fingerprint
        or current.artifact != request.current_champion
    ):
        raise ChampionStateInvalidError("Requested current champion is not the active registry champion.")


def _failure(status, scope, error, plan=None):
    return ActivationOutcome(
        status, scope,
        getattr(plan, "activation_plan_id", getattr(plan, "rollback_plan_id", None)) if plan else None,
        getattr(plan, "activation_plan_fingerprint", getattr(plan, "rollback_plan_fingerprint", None)) if plan else None,
        None, (str(error),),
    )
