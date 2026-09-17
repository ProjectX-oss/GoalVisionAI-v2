"""Canonical SHA-256 identities for pipeline requests, handoffs, and results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from .models import OfficialPredictionPipelineCommand, OfficialPredictionPipelineOutcome


def digest(value: object) -> str:
    payload = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def request_fingerprint(command: OfficialPredictionPipelineCommand) -> str:
    return digest({
        "version": "official-pipeline-request-v1",
        "pipeline_request_identity": command.pipeline_request_identity,
        "candidate_id": command.candidate_id,
        "candidate_version": command.candidate_version,
        "candidate_fingerprint": command.candidate_fingerprint,
        "candidate_preparation_fingerprint": command.candidate_preparation_fingerprint,
        "selection_fingerprint": command.selection_fingerprint,
        "value_assessment_fingerprint": command.value_assessment_fingerprint,
        "calibrated_assembly_fingerprint": command.calibrated_assembly_fingerprint,
        "odds_fingerprint": command.odds_fingerprint,
        "risk_fingerprint": command.risk_fingerprint,
        "quality_gate_evaluation_timestamp": command.quality_gate_evaluation_timestamp,
        "pipeline_execution_timestamp": command.pipeline_execution_timestamp,
        "publication_effective_timestamp": command.publication_effective_timestamp,
        "dry_run": command.dry_run,
        "retry": command.retry,
        "pipeline_policy_version": command.pipeline_policy_version,
        "metadata_version": command.metadata_version,
    })


def gate_handoff_fingerprint(
    command: OfficialPredictionPipelineCommand,
    gate_policy_version: str | None = None,
) -> str:
    return digest({
        "version": "official-pipeline-gate-handoff-v1",
        "candidate": command.candidate,
        "assembly_request": command.assembly_request,
        "provenance": {
            "preparation": command.candidate_preparation_fingerprint,
            "selection": command.selection_fingerprint,
            "value": command.value_assessment_fingerprint,
            "calibration": command.calibrated_assembly_fingerprint,
            "odds": command.odds_fingerprint,
            "risk": command.risk_fingerprint,
            "bankroll": command.bankroll_snapshot_identity,
            "exposure": command.exposure_snapshot_identity,
        },
        "stake": (command.internal_stake_percentage, command.stake_amount),
        "gate_policy": gate_policy_version or "unbound-gate-policy",
        "evaluated_at": command.quality_gate_evaluation_timestamp,
    })


def publication_plan_fingerprint(
    command: OfficialPredictionPipelineCommand,
    gate_fingerprint: str,
    orchestration_fingerprint: str,
    message_fingerprint: str,
) -> str:
    return digest({
        "version": "official-pipeline-publication-plan-v1",
        "candidate_fingerprint": command.candidate_fingerprint,
        "gate_fingerprint": gate_fingerprint,
        "orchestration_fingerprint": orchestration_fingerprint,
        "message_fingerprint": message_fingerprint,
        "destination": str(getattr(command.destination_scope, "value", command.destination_scope)),
        "publication_effective_timestamp": command.publication_effective_timestamp,
        "pipeline_policy_version": command.pipeline_policy_version,
    })


def execution_fingerprint(outcome: OfficialPredictionPipelineOutcome) -> str:
    return digest({
        "version": "official-pipeline-execution-v1",
        "request_fingerprint": outcome.request_fingerprint,
        "candidate_state": outcome.candidate_state_result,
        "publication_state": outcome.publication_state_result,
        "quality_gate": (outcome.quality_gate_evaluation_id, outcome.quality_gate_fingerprint),
        "orchestration": (outcome.orchestration_id, outcome.orchestration_fingerprint),
        "publication": (outcome.publication_event_id, outcome.publication_fingerprint),
        "final_status": outcome.final_status,
        "dry_run": outcome.dry_run,
        "retry": outcome.retry,
        "ordered_reason_codes": outcome.ordered_reason_codes,
        "pipeline_policy_version": outcome.pipeline_policy_version,
    })


def execution_id(request_fp: str, status: str) -> str:
    return "official-pipeline-execution-" + digest(("v1", request_fp, status))


def stage_event_id(execution_id_value: str, order: int, stage: str) -> str:
    return "official-pipeline-stage-" + digest(("v1", execution_id_value, order, stage))


def _stable(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _stable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_stable(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True)) if isinstance(value, (set, frozenset)) else items
    return f"<{type(value).__module__}.{type(value).__qualname__}>"
