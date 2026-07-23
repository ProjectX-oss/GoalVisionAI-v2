"""Central request, policy, and evidence validation."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from .exceptions import ActivationNotEligibleError, ActivationValidationError
from .fingerprint import canonical_json, sha256_fingerprint
from .models import ActivationValidation, ValidationStatus

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def utc(value, name):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ActivationValidationError(f"{name} must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise ActivationValidationError(f"{name} must be timezone-aware.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_activation_request(request, policy):
    for name in (
        "activation_request_id", "model_scope", "current_champion_generation_id",
        "comparison_run_id", "challenger_candidate_id", "recommendation_id",
        "operator_identity",
    ):
        if not _ID.fullmatch(getattr(request, name)):
            raise ActivationValidationError(f"{name} is invalid.")
    if request.policy_version != policy.version:
        raise ActivationValidationError("Activation policy version is unsupported.")
    if request.current_champion.model_artifact_id == request.challenger.model_artifact_id:
        raise ActivationValidationError("Challenger is already the requested champion.")
    requested = utc(request.requested_timestamp_utc, "requested_timestamp_utc")
    cutoff = utc(request.evidence_cutoff_timestamp_utc, "evidence_cutoff_timestamp_utc")
    if cutoff > requested:
        raise ActivationValidationError("Evidence cutoff cannot be after the request.")
    if not request.activation_reason.strip():
        raise ActivationValidationError("A manual activation reason is required.")


def evaluate_evidence(evidence, policy):
    checks = (
        ("EVIDENCE", "MINIMUM_SETTLED_SHADOW", evidence.settled_count >= policy.minimum_settled_shadow_evaluations, evidence.settled_count, policy.minimum_settled_shadow_evaluations),
        ("DURATION", "MINIMUM_OBSERVATION_DAYS", evidence.observation_days >= policy.minimum_shadow_observation_days, evidence.observation_days, policy.minimum_shadow_observation_days),
        ("AGREEMENT", "MINIMUM_AGREEMENT_RATIO", evidence.agreement_ratio >= policy.minimum_agreement_ratio, evidence.agreement_ratio, policy.minimum_agreement_ratio),
        ("DISAGREEMENT", "MAXIMUM_CRITICAL_RATIO", evidence.critical_disagreement_ratio <= policy.maximum_critical_disagreement_ratio, evidence.critical_disagreement_ratio, policy.maximum_critical_disagreement_ratio),
        ("PREDICTIVE", "MAXIMUM_PREDICTIVE_DEGRADATION", evidence.predictive_degradation <= policy.maximum_predictive_degradation, evidence.predictive_degradation, policy.maximum_predictive_degradation),
        ("CALIBRATION", "MAXIMUM_CALIBRATION_DEGRADATION", evidence.calibration_degradation <= policy.maximum_calibration_degradation, evidence.calibration_degradation, policy.maximum_calibration_degradation),
        ("BETTING", "MAXIMUM_BETTING_DEGRADATION", evidence.betting_performance_degradation <= policy.maximum_betting_performance_degradation, evidence.betting_performance_degradation, policy.maximum_betting_performance_degradation),
        ("RISK", "MAXIMUM_DRAWDOWN_DETERIORATION", evidence.drawdown_deterioration <= policy.maximum_drawdown_deterioration, evidence.drawdown_deterioration, policy.maximum_drawdown_deterioration),
        ("COMPLETENESS", "MINIMUM_EVIDENCE_COMPLETENESS", evidence.evidence_completeness >= policy.minimum_evidence_completeness, evidence.evidence_completeness, policy.minimum_evidence_completeness),
    )
    validations = []
    for order, (category, name, passed, actual, threshold) in enumerate(checks):
        detail = canonical_json({"actual": actual, "threshold": threshold})
        fingerprint = sha256_fingerprint((category, name, passed, detail, policy.version))
        validations.append(ActivationValidation(
            validation_id=f"activation-validation-{fingerprint}", category=category, name=name,
            status=ValidationStatus.PASS if passed else ValidationStatus.FAIL,
            detail_snapshot=detail, validation_fingerprint=fingerprint, deterministic_order=order,
        ))
    failures = tuple(item.name for item in validations if item.status is ValidationStatus.FAIL)
    if failures:
        raise ActivationNotEligibleError("Activation evidence failed: " + ",".join(failures))
    return tuple(validations)


def validate_rollback_request(request, policy):
    if request.policy_version != policy.version or not policy.rollback_enabled:
        raise ActivationValidationError("Rollback policy is unsupported.")
    for name in (
        "rollback_request_id", "model_scope", "current_champion_generation_id",
        "target_champion_generation_id", "operator_identity", "incident_reference",
    ):
        if not _ID.fullmatch(getattr(request, name)):
            raise ActivationValidationError(f"{name} is invalid.")
    if request.current_champion_generation_id == request.target_champion_generation_id:
        raise ActivationValidationError("Rollback target must be a prior champion generation.")
    if not request.rollback_reason.strip():
        raise ActivationValidationError("A rollback reason is required.")
    utc(request.requested_timestamp_utc, "requested_timestamp_utc")
