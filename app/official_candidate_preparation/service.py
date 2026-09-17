"""Deterministic selection-to-risk-to-registry orchestration."""

from __future__ import annotations

from app.official_prediction_candidate_registry import (
    CandidateRegistrationStatus,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionCandidateRegistrationOutcome,
)
from app.risk_management import (
    RiskAssessmentDecision,
    RiskAuditRecord,
    StakeRecommendation,
)

from .exceptions import (
    CandidatePreparationConflictError,
    CandidatePreparationMappingError,
    CandidatePreparationPersistenceError,
    CandidatePreparationProvenanceError,
    CandidatePreparationScopeError,
    CandidatePreparationValidationError,
)
from .fingerprint import (
    integration_execution_id,
    integration_fingerprint,
    preparation_request_fingerprint,
    risk_result_fingerprint,
    risk_snapshot_id,
)
from .mapping import (
    map_risk_to_candidate,
    map_selection_to_risk,
    map_to_quality_gate_handoff,
    validate_risk_result,
)
from .models import (
    CandidatePreparationReason,
    CandidatePreparationStatus,
    OfficialCandidatePreparationCommand,
    OfficialCandidatePreparationExecution,
    OfficialCandidatePreparationOutcome,
    OfficialCandidatePreparationRiskSnapshot,
    OfficialCandidateQualityGateHandoff,
    PreparedOfficialCandidateRegistration,
    PreparedOfficialRiskHandoff,
)
from .policy import OfficialCandidatePreparationPolicy
from .ports import (
    CandidateLifecycleReader,
    OfficialCandidatePreparationRepository,
    OfficialCandidateRegistryPort,
    OfficialRiskAssessmentPort,
    SelectionHistoryReader,
    ValueAssessmentHistoryReader,
)
from .validation import ValidatedCandidatePreparation, validate_candidate_preparation


class OfficialCandidatePreparationService:
    """Validate provenance, call risk once, and register at most one candidate."""

    def __init__(
        self,
        *,
        repository: OfficialCandidatePreparationRepository,
        selections: SelectionHistoryReader,
        assessments: ValueAssessmentHistoryReader,
        risk_service: OfficialRiskAssessmentPort,
        candidate_registry: OfficialCandidateRegistryPort,
        candidate_lifecycle: CandidateLifecycleReader,
        policy: OfficialCandidatePreparationPolicy,
    ) -> None:
        self._repository = repository
        self._selections = selections
        self._assessments = assessments
        self._risk_service = risk_service
        self._candidate_registry = candidate_registry
        self._candidate_lifecycle = candidate_lifecycle
        self._policy = policy

    def prepare_official_candidate(
        self,
        command: OfficialCandidatePreparationCommand,
    ) -> OfficialCandidatePreparationOutcome:
        """Run one fail-closed preparation with no implicit current-time access."""

        identity = getattr(command, "integration_request_identity", "invalid-request")
        try:
            validated = validate_candidate_preparation(
                command,
                self._policy,
                self._selections,
                self._assessments,
            )
            command = validated.command
            request_fp = preparation_request_fingerprint(command)
            existing = self._repository.find_by_request_identity(
                command.integration_request_identity
            )
        except CandidatePreparationScopeError as exc:
            return self._rejection(
                identity,
                CandidatePreparationStatus.REJECTED_SCOPE,
                exc.reason,
                exc.explanation,
            )
        except CandidatePreparationProvenanceError as exc:
            return self._rejection(
                identity,
                CandidatePreparationStatus.REJECTED_PROVENANCE,
                exc.reason,
                exc.explanation,
            )
        except CandidatePreparationValidationError as exc:
            return self._rejection(
                identity,
                CandidatePreparationStatus.REJECTED_INVALID_REQUEST,
                exc.reason,
                exc.explanation,
            )
        except CandidatePreparationPersistenceError:
            return self._rejection(
                identity,
                CandidatePreparationStatus.PERSISTENCE_FAILURE,
                CandidatePreparationReason.PERSISTENCE_FAILURE,
                "Candidate-preparation history lookup failed safely.",
            )
        except Exception:
            return self._rejection(
                identity,
                CandidatePreparationStatus.REJECTED_INVALID_REQUEST,
                CandidatePreparationReason.INVALID_REQUEST,
                "Candidate-preparation request is malformed.",
            )

        if existing is not None:
            if existing.preparation_request_fingerprint != request_fp:
                return self._rejection(
                    command.integration_request_identity,
                    CandidatePreparationStatus.CONFLICT,
                    CandidatePreparationReason.REQUEST_IDENTITY_CONFLICT,
                    "Integration request identity conflicts with immutable history.",
                    command=command,
                )
            return self._existing(existing)

        handoff = map_selection_to_risk(validated, self._policy)
        try:
            audit = self._risk_service.assess(handoff.request, handoff.context)
        except Exception:
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                None,
                None,
                None,
                CandidatePreparationStatus.RISK_EXECUTION_FAILED,
                (CandidatePreparationReason.RISK_EXECUTION_FAILED,),
                ("Official risk assessment failed safely; no candidate was registered.",),
            )

        raw_risk_fp = (
            risk_result_fingerprint(audit)
            if isinstance(audit, RiskAuditRecord)
            else None
        )
        try:
            risk_fp = validate_risk_result(audit, handoff, self._policy)
        except (CandidatePreparationMappingError, AttributeError, TypeError, ValueError):
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                audit if isinstance(audit, RiskAuditRecord) else None,
                raw_risk_fp,
                None,
                CandidatePreparationStatus.REJECTED_INVALID_RISK_RESULT,
                (CandidatePreparationReason.RISK_RESULT_MALFORMED,),
                ("Risk service output failed identity or stake validation.",),
            )

        if audit.final_decision is RiskAssessmentDecision.REVIEW_REQUIRED:
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                audit,
                risk_fp,
                None,
                CandidatePreparationStatus.NO_REGISTRATION_REVIEW_REQUIRED,
                (CandidatePreparationReason.RISK_REVIEW_REQUIRED,),
                tuple(item.value for item in audit.ordered_reasons)
                or ("Risk review is required.",),
            )
        if audit.final_decision is RiskAssessmentDecision.INELIGIBLE:
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                audit,
                risk_fp,
                None,
                CandidatePreparationStatus.NO_REGISTRATION_INELIGIBLE,
                (CandidatePreparationReason.RISK_INELIGIBLE,),
                tuple(item.value for item in audit.ordered_reasons)
                or ("Risk assessment is ineligible.",),
            )

        try:
            candidate_mapping = map_risk_to_candidate(
                validated, handoff, audit, risk_fp
            )
        except CandidatePreparationMappingError:
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                audit,
                risk_fp,
                None,
                CandidatePreparationStatus.REJECTED_INVALID_RISK_RESULT,
                (CandidatePreparationReason.RISK_RESULT_MALFORMED,),
                ("Eligible risk result could not map to a valid candidate.",),
            )
        try:
            registry = self._candidate_registry.register_candidate(
                candidate_mapping.command
            )
        except Exception:
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                audit,
                risk_fp,
                candidate_mapping,
                CandidatePreparationStatus.PERSISTENCE_FAILURE,
                (CandidatePreparationReason.PERSISTENCE_FAILURE,),
                ("Candidate Registry execution failed safely.",),
            )
        if not _valid_registry_outcome(registry, candidate_mapping.command):
            return self._persist_terminal(
                validated,
                request_fp,
                handoff,
                audit,
                risk_fp,
                candidate_mapping,
                CandidatePreparationStatus.CANDIDATE_REGISTRATION_REJECTED,
                (CandidatePreparationReason.CANDIDATE_REJECTED,),
                ("Candidate Registry returned an identity-incompatible result.",),
            )
        status, reason = _registry_status(registry.final_status)
        return self._persist_terminal(
            validated,
            request_fp,
            handoff,
            audit,
            risk_fp,
            candidate_mapping,
            status,
            (reason,),
            registry.explanations,
            registry=registry,
        )

    def quality_gate_handoff(
        self,
        integration_execution_id_value: str,
    ) -> OfficialCandidateQualityGateHandoff:
        """Load a registered READY candidate as typed downstream facts only."""

        stored = self._repository.load_execution_with_risk_snapshot(
            integration_execution_id_value
        )
        if (
            stored is None
            or stored.risk_snapshot is None
            or stored.execution.registry_candidate_id is None
        ):
            raise CandidatePreparationMappingError(
                "A registered execution with a risk snapshot is required."
            )
        candidate = self._candidate_lifecycle.find_candidate_by_id(
            stored.execution.registry_candidate_id
        )
        state = self._candidate_lifecycle.current_state(
            stored.execution.registry_candidate_id
        )
        if candidate is None or state is None:
            raise CandidatePreparationMappingError(
                "Registered candidate lifecycle history is unavailable."
            )
        return map_to_quality_gate_handoff(
            candidate, state, stored.execution, stored.risk_snapshot
        )

    def _persist_terminal(
        self,
        validated: ValidatedCandidatePreparation,
        request_fp: str,
        handoff: PreparedOfficialRiskHandoff,
        audit: RiskAuditRecord | None,
        risk_fp: str | None,
        candidate_mapping: PreparedOfficialCandidateRegistration | None,
        status: CandidatePreparationStatus,
        reasons: tuple[CandidatePreparationReason, ...],
        explanations: tuple[str, ...],
        *,
        registry: OfficialPredictionCandidateRegistrationOutcome | None = None,
    ) -> OfficialCandidatePreparationOutcome:
        command = validated.command
        selection = validated.selection
        integration_fp = integration_fingerprint(
            request_fingerprint=request_fp,
            risk_handoff_fingerprint_value=handoff.handoff_fingerprint,
            risk_fingerprint=risk_fp,
            candidate_mapping_fingerprint_value=(
                candidate_mapping.candidate_mapping_fingerprint
                if candidate_mapping is not None
                else None
            ),
            registry_result=registry,
            final_status=status,
            ordered_reasons=reasons,
            policy_version=self._policy.version,
        )
        execution_id = integration_execution_id(integration_fp)
        summary = tuple(sorted({
            "candidate_registry_outcome": registry.final_status.value if registry else "none",
            "final_status": status.value,
            "match_id": selection.match_id,
            "risk_outcome": audit.final_decision.value if audit else "none",
            "selection_decision_id": selection.selection_decision_id,
        }.items()))
        execution = OfficialCandidatePreparationExecution(
            integration_execution_id=execution_id,
            integration_request_identity=command.integration_request_identity,
            preparation_request_fingerprint=request_fp,
            integration_fingerprint=integration_fp,
            selection_decision_id=selection.selection_decision_id,
            selected_value_assessment_id=selection.selected_value_assessment_id,
            match_id=selection.match_id,
            kickoff_timestamp=selection.kickoff_timestamp,
            risk_assessment_timestamp=command.risk_assessment_timestamp,
            candidate_preparation_timestamp=command.candidate_preparation_timestamp,
            bankroll_snapshot_identity=command.bankroll.snapshot_identity,
            bankroll_fingerprint=command.bankroll.fingerprint,
            exposure_snapshot_identity=command.exposure.snapshot_identity,
            exposure_fingerprint=command.exposure.fingerprint,
            risk_handoff_fingerprint=handoff.handoff_fingerprint,
            risk_outcome=audit.final_decision if audit else None,
            risk_assessment_id=audit.assessment_id if audit else None,
            risk_fingerprint=risk_fp,
            candidate_mapping_fingerprint=(
                candidate_mapping.candidate_mapping_fingerprint
                if candidate_mapping
                else None
            ),
            candidate_registry_outcome=registry.final_status if registry else None,
            registry_candidate_id=registry.registry_candidate_id if registry else None,
            candidate_version=registry.candidate_version if registry else None,
            candidate_fingerprint=(
                registry.candidate_content_fingerprint if registry else None
            ),
            previous_candidate_id=registry.previous_candidate_id if registry else None,
            final_status=status,
            integration_policy_version=self._policy.version,
            ordered_reason_codes=reasons,
            explanations=tuple(explanations),
            deterministic_execution_summary=summary,
            created_timestamp=command.candidate_preparation_timestamp,
        )
        snapshot = None
        if audit is not None and risk_fp is not None:
            snapshot = OfficialCandidatePreparationRiskSnapshot(
                risk_snapshot_id=risk_snapshot_id(execution_id, risk_fp),
                integration_execution_id=execution_id,
                risk_handoff_fingerprint=handoff.handoff_fingerprint,
                risk_fingerprint=risk_fp,
                audit=audit,
                created_timestamp=command.candidate_preparation_timestamp,
            )
        try:
            stored, existed = self._repository.append_preparation_execution(
                execution, snapshot
            )
        except CandidatePreparationConflictError:
            return self._rejection(
                command.integration_request_identity,
                CandidatePreparationStatus.CONFLICT,
                CandidatePreparationReason.REQUEST_IDENTITY_CONFLICT,
                "Immutable preparation history conflicts with this execution.",
                command=command,
            )
        except Exception:
            return self._rejection(
                command.integration_request_identity,
                CandidatePreparationStatus.PERSISTENCE_FAILURE,
                CandidatePreparationReason.PERSISTENCE_FAILURE,
                "Preparation execution persistence failed safely.",
                command=command,
                integration_fingerprint_value=integration_fp,
            )
        if existed:
            return self._existing(stored.execution)
        return _outcome(execution, audit.recommendation if audit else None)

    def _existing(
        self, execution: OfficialCandidatePreparationExecution
    ) -> OfficialCandidatePreparationOutcome:
        stored = self._repository.load_execution_with_risk_snapshot(
            execution.integration_execution_id
        )
        audit = stored.risk_snapshot.audit if stored and stored.risk_snapshot else None
        outcome = _outcome(execution, audit.recommendation if audit else None)
        return OfficialCandidatePreparationOutcome(
            **{
                **{name: getattr(outcome, name) for name in outcome.__dataclass_fields__},
                "final_status": CandidatePreparationStatus.IDEMPOTENT_EXISTING,
                "ordered_reason_codes": (CandidatePreparationReason.CANDIDATE_IDEMPOTENT,),
                "explanations": ("Identical terminal preparation execution already exists.",),
            }
        )

    def _rejection(
        self,
        identity: object,
        status: CandidatePreparationStatus,
        reason: CandidatePreparationReason,
        explanation: str,
        *,
        command: OfficialCandidatePreparationCommand | None = None,
        integration_fingerprint_value: str | None = None,
    ) -> OfficialCandidatePreparationOutcome:
        selection = getattr(command, "selection", None)
        return OfficialCandidatePreparationOutcome(
            integration_execution_id=None,
            integration_request_identity=(
                identity if isinstance(identity, str) else "invalid-request"
            ),
            selection_decision_id=getattr(selection, "selection_decision_id", None),
            selected_value_assessment_id=getattr(
                selection, "selected_value_assessment_id", None
            ),
            match_id=getattr(selection, "match_id", None),
            kickoff_timestamp=getattr(selection, "kickoff_timestamp", None),
            risk_assessment_id=None,
            risk_outcome=None,
            stake_recommendation=None,
            registry_candidate_id=None,
            candidate_version=None,
            candidate_registry_outcome=None,
            final_status=status,
            ordered_reason_codes=(reason,),
            explanations=(explanation,),
            integration_fingerprint=integration_fingerprint_value,
            candidate_fingerprint=None,
            risk_assessment_timestamp=getattr(
                command, "risk_assessment_timestamp", None
            ),
            candidate_preparation_timestamp=getattr(
                command, "candidate_preparation_timestamp", None
            ),
            integration_policy_version=self._policy.version,
        )


def _registry_status(
    value: CandidateRegistrationStatus,
) -> tuple[CandidatePreparationStatus, CandidatePreparationReason]:
    return {
        CandidateRegistrationStatus.REGISTERED: (
            CandidatePreparationStatus.CANDIDATE_REGISTERED,
            CandidatePreparationReason.CANDIDATE_REGISTERED,
        ),
        CandidateRegistrationStatus.SUPERSEDED_PREVIOUS: (
            CandidatePreparationStatus.CANDIDATE_REGISTERED,
            CandidatePreparationReason.CANDIDATE_SUPERSEDED_PREVIOUS,
        ),
        CandidateRegistrationStatus.IDEMPOTENT_EXISTING: (
            CandidatePreparationStatus.IDEMPOTENT_EXISTING,
            CandidatePreparationReason.CANDIDATE_IDEMPOTENT,
        ),
        CandidateRegistrationStatus.REJECTED_INVALID: (
            CandidatePreparationStatus.CANDIDATE_REGISTRATION_REJECTED,
            CandidatePreparationReason.CANDIDATE_REJECTED,
        ),
        CandidateRegistrationStatus.REJECTED_SCOPE: (
            CandidatePreparationStatus.REJECTED_SCOPE,
            CandidatePreparationReason.CANDIDATE_SCOPE_REJECTED,
        ),
        CandidateRegistrationStatus.ALREADY_PUBLISHED: (
            CandidatePreparationStatus.ALREADY_PUBLISHED,
            CandidatePreparationReason.ALREADY_PUBLISHED,
        ),
        CandidateRegistrationStatus.CORRECTION_REQUIRED: (
            CandidatePreparationStatus.CORRECTION_REQUIRED,
            CandidatePreparationReason.CORRECTION_REQUIRED,
        ),
        CandidateRegistrationStatus.CONFLICT: (
            CandidatePreparationStatus.CONFLICT,
            CandidatePreparationReason.REGISTRY_CONFLICT,
        ),
        CandidateRegistrationStatus.PERSISTENCE_FAILURE: (
            CandidatePreparationStatus.PERSISTENCE_FAILURE,
            CandidatePreparationReason.PERSISTENCE_FAILURE,
        ),
    }[value]


def _valid_registry_outcome(
    value: object,
    command: OfficialPredictionCandidateRegistrationCommand,
) -> bool:
    if not isinstance(value, OfficialPredictionCandidateRegistrationOutcome):
        return False
    if (
        value.prediction_id != command.prediction_id
        or value.match_id != command.match_id
        or value.registration_timestamp != command.registration_timestamp
        or not isinstance(value.final_status, CandidateRegistrationStatus)
    ):
        return False
    success = value.final_status in {
        CandidateRegistrationStatus.REGISTERED,
        CandidateRegistrationStatus.IDEMPOTENT_EXISTING,
        CandidateRegistrationStatus.SUPERSEDED_PREVIOUS,
    }
    references = (
        value.registry_candidate_id,
        value.candidate_content_fingerprint,
        value.candidate_version,
    )
    return all(item is not None for item in references) if success else True


def _outcome(
    execution: OfficialCandidatePreparationExecution,
    recommendation: StakeRecommendation | None,
) -> OfficialCandidatePreparationOutcome:
    return OfficialCandidatePreparationOutcome(
        integration_execution_id=execution.integration_execution_id,
        integration_request_identity=execution.integration_request_identity,
        selection_decision_id=execution.selection_decision_id,
        selected_value_assessment_id=execution.selected_value_assessment_id,
        match_id=execution.match_id,
        kickoff_timestamp=execution.kickoff_timestamp,
        risk_assessment_id=execution.risk_assessment_id,
        risk_outcome=execution.risk_outcome,
        stake_recommendation=recommendation,
        registry_candidate_id=execution.registry_candidate_id,
        candidate_version=execution.candidate_version,
        candidate_registry_outcome=execution.candidate_registry_outcome,
        final_status=execution.final_status,
        ordered_reason_codes=execution.ordered_reason_codes,
        explanations=execution.explanations,
        integration_fingerprint=execution.integration_fingerprint,
        candidate_fingerprint=execution.candidate_fingerprint,
        risk_assessment_timestamp=execution.risk_assessment_timestamp,
        candidate_preparation_timestamp=execution.candidate_preparation_timestamp,
        integration_policy_version=execution.integration_policy_version,
        execution=execution,
    )
