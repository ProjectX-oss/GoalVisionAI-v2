"""Canonical SHA-256 identities for candidate-preparation material."""

from __future__ import annotations

import hashlib
import json

from app.match_data_snapshot import canonical_data
from app.official_prediction_candidate_registry import (
    OfficialPredictionCandidateRegistrationOutcome,
)
from app.risk_management import RiskAuditRecord

from .models import (
    CandidatePreparationReason,
    CandidatePreparationStatus,
    OfficialBankrollPreparationContext,
    OfficialCandidatePreparationCommand,
    OfficialCandidateRegistrationFacts,
    OfficialExposurePreparationContext,
    PreparedOfficialCandidateRegistration,
    PreparedOfficialRiskHandoff,
)


def digest(value: object) -> str:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bankroll_context_fingerprint(
    value: OfficialBankrollPreparationContext,
) -> str:
    return digest(
        {
            "version": "official-preparation-bankroll-v1",
            "snapshot_identity": value.snapshot_identity,
            "match_id": value.match_id,
            "kickoff": value.kickoff_timestamp,
            "available_bankroll": value.available_bankroll,
            "reserved_exposure": value.reserved_exposure,
            "state": value.state,
        }
    )


def exposure_context_fingerprint(
    value: OfficialExposurePreparationContext,
) -> str:
    ordered_positions = tuple(
        sorted(
            value.snapshot.positions,
            key=lambda item: (item.exposure_type.value, item.scope_key),
        )
    )
    return digest(
        {
            "version": "official-preparation-exposure-v1",
            "snapshot_identity": value.snapshot_identity,
            "match_id": value.match_id,
            "kickoff": value.kickoff_timestamp,
            "product_scope": value.snapshot.product_scope,
            "positions": ordered_positions,
            "snapshot_timestamp": value.snapshot.snapshot_timestamp,
            "authoritative_source_reference": (
                value.snapshot.authoritative_source_reference
            ),
        }
    )


def candidate_facts_fingerprint(
    value: OfficialCandidateRegistrationFacts,
) -> str:
    return digest(
        {
            "version": "official-preparation-candidate-facts-v1",
            "facts": value,
        }
    )


def preparation_request_fingerprint(
    command: OfficialCandidatePreparationCommand,
) -> str:
    selection = command.selection
    return digest(
        {
            "version": "official-candidate-preparation-request-v1",
            "request_identity": command.integration_request_identity,
            "selection_decision_id": selection.selection_decision_id,
            "selection_fingerprint": selection.selection_fingerprint,
            "selected_assessment_fingerprint": (
                selection.selected_assessment_fingerprint
            ),
            "match_id": selection.match_id,
            "kickoff": selection.kickoff_timestamp,
            "bankroll_snapshot_identity": command.bankroll.snapshot_identity,
            "bankroll_fingerprint": command.bankroll.fingerprint,
            "exposure_snapshot_identity": command.exposure.snapshot_identity,
            "exposure_fingerprint": command.exposure.fingerprint,
            "candidate_facts_fingerprint": candidate_facts_fingerprint(
                command.candidate_facts
            ),
            "risk_assessment_timestamp": command.risk_assessment_timestamp,
            "candidate_preparation_timestamp": (
                command.candidate_preparation_timestamp
            ),
            "bankroll_scope": command.bankroll_scope.value,
            "destination_scope": command.destination_scope.value,
            "integration_policy_version": command.integration_policy_version,
            "metadata_version": command.metadata_version,
            "source_run_identity": command.source_run_identity,
            "metadata": command.metadata,
        }
    )


def risk_handoff_fingerprint(value: PreparedOfficialRiskHandoff) -> str:
    return digest(
        {
            "version": "official-candidate-preparation-risk-handoff-v1",
            "selection": value.selection,
            "request": value.request,
            "context": value.context,
            "bankroll_snapshot_identity": value.bankroll_snapshot_identity,
            "bankroll_fingerprint": value.bankroll_fingerprint,
            "available_bankroll": value.available_bankroll,
            "reserved_exposure": value.reserved_exposure,
            "exposure_snapshot_identity": value.exposure_snapshot_identity,
            "exposure_fingerprint": value.exposure_fingerprint,
        }
    )


def risk_result_fingerprint(value: RiskAuditRecord) -> str:
    return digest(
        {
            "version": "official-candidate-preparation-risk-result-v1",
            "audit": value,
        }
    )


def candidate_mapping_fingerprint(
    value: PreparedOfficialCandidateRegistration,
) -> str:
    return digest(
        {
            "version": "official-candidate-preparation-mapping-v1",
            "command": value.command,
        }
    )


def integration_fingerprint(
    *,
    request_fingerprint: str,
    risk_handoff_fingerprint_value: str | None,
    risk_fingerprint: str | None,
    candidate_mapping_fingerprint_value: str | None,
    registry_result: OfficialPredictionCandidateRegistrationOutcome | None,
    final_status: CandidatePreparationStatus,
    ordered_reasons: tuple[CandidatePreparationReason, ...],
    policy_version: str,
) -> str:
    registry_reference = None
    if registry_result is not None:
        registry_reference = {
            "status": registry_result.final_status.value,
            "candidate_id": registry_result.registry_candidate_id,
            "candidate_version": registry_result.candidate_version,
            "candidate_fingerprint": (
                registry_result.candidate_content_fingerprint
            ),
            "previous_candidate_id": registry_result.previous_candidate_id,
            "reason_codes": registry_result.ordered_reason_codes,
        }
    return digest(
        {
            "version": "official-candidate-preparation-execution-v1",
            "request_fingerprint": request_fingerprint,
            "risk_handoff_fingerprint": risk_handoff_fingerprint_value,
            "risk_result_fingerprint": risk_fingerprint,
            "candidate_mapping_fingerprint": (
                candidate_mapping_fingerprint_value
            ),
            "registry_result": registry_reference,
            "final_status": final_status.value,
            "ordered_reasons": tuple(item.value for item in ordered_reasons),
            "policy_version": policy_version,
        }
    )


def integration_execution_id(fingerprint: str) -> str:
    return "official-candidate-preparation-" + hashlib.sha256(
        f"official-candidate-preparation-id-v1|{fingerprint}".encode("utf-8")
    ).hexdigest()


def risk_snapshot_id(execution_id: str, risk_fingerprint: str) -> str:
    return "official-candidate-risk-snapshot-" + hashlib.sha256(
        f"official-candidate-risk-snapshot-v1|{execution_id}|{risk_fingerprint}".encode(
            "utf-8"
        )
    ).hexdigest()
