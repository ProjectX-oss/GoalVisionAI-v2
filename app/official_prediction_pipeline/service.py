"""Deterministic, manually invoked Registered Candidate publication pipeline."""

from __future__ import annotations

from dataclasses import replace

from app.official_prediction_orchestration import (
    OfficialPredictionCandidateAssembler,
    OrchestrationStatus,
    PublicationDeliveryState,
    PublicationStateRecord,
)
from app.quality_gate import QualityGateStatus

from .exceptions import PipelineConflictError, PipelineValidationError
from .fingerprint import (
    digest,
    execution_fingerprint,
    execution_id,
    gate_handoff_fingerprint,
    request_fingerprint,
    stage_event_id,
)
from .models import (
    CandidateState,
    OfficialPredictionPipelineCommand,
    OfficialPredictionPipelineOutcome,
    PipelinePublicationState,
    PipelineStage,
    PipelineStageEvent,
    PipelineStatus,
)
from .policy import OfficialPredictionPipelinePolicy
from .ports import (
    CandidateRegistryStatePort,
    OfficialPredictionPipelineRepository,
    PersistedQualityGatePort,
    PipelineMessagePreviewPort,
    PipelinePublicationStatePort,
    PreapprovedOfficialOrchestrationPort,
)
from .validation import validate_command


class OfficialPredictionPipelineService:
    def __init__(
        self,
        policy: OfficialPredictionPipelinePolicy,
        candidate_states: CandidateRegistryStatePort,
        publication_states: PipelinePublicationStatePort,
        quality_gate: PersistedQualityGatePort,
        orchestration: PreapprovedOfficialOrchestrationPort,
        message_preview: PipelineMessagePreviewPort,
        repository: OfficialPredictionPipelineRepository,
        assembler: OfficialPredictionCandidateAssembler | None = None,
    ) -> None:
        self.policy = policy
        self._candidate_states = candidate_states
        self._publication_states = publication_states
        self._quality_gate = quality_gate
        self._orchestration = orchestration
        self._message_preview = message_preview
        self._repository = repository
        self._assembler = assembler or OfficialPredictionCandidateAssembler()

    async def execute(
        self,
        command: OfficialPredictionPipelineCommand,
    ) -> OfficialPredictionPipelineOutcome:
        try:
            validated = validate_command(command, self.policy)
            request_fp = request_fingerprint(validated)
        except PipelineValidationError as exc:
            return self._unpersisted(command, PipelineStatus(exc.status), exc.reasons, exc.explanations)

        try:
            same_request = self._repository.find_by_request_identity(command.pipeline_request_identity)
            if same_request is not None:
                if same_request.request_fingerprint == request_fp:
                    return same_request
                return self._unpersisted(command, PipelineStatus.CONFLICT, ("REQUEST_IDENTITY_CONFLICT",), ("Request identity already belongs to different immutable content.",), request_fp)
        except Exception:
            return self._unpersisted(command, PipelineStatus.PERSISTENCE_FAILURE, ("IDEMPOTENCY_LOOKUP_FAILED",), ("Pipeline history lookup failed safely.",), request_fp)

        candidate_state = self._candidate_states.verify(command)
        if candidate_state.state is not CandidateState.READY or not candidate_state.is_current:
            return self._persist(command, request_fp, PipelineStatus.REJECTED_CANDIDATE_STATE, (candidate_state.state.value,), ("Candidate Registry did not confirm the exact current READY version.",), candidate_state=candidate_state.state.value)
        if candidate_state.candidate != command.candidate or candidate_state.fingerprint != command.candidate_fingerprint:
            return self._persist(command, request_fp, PipelineStatus.REJECTED_CANDIDATE_STATE, ("CANDIDATE_STATE_MISMATCH",), ("Verified Registry candidate differs from the supplied immutable candidate.",), candidate_state=candidate_state.state.value)

        publication_state = self._publication_states.verify(command)
        state = publication_state.state
        if state is PipelinePublicationState.PUBLISHED:
            return self._persist(command, request_fp, PipelineStatus.IDEMPOTENT_EXISTING, ("ALREADY_PUBLISHED",), ("The identical candidate already has a terminal Official publication.",), candidate_state=candidate_state.state.value, publication_state=state.value, publication=publication_state)
        if state is PipelinePublicationState.ACTIVE_CLAIM:
            return self._persist(command, request_fp, PipelineStatus.PUBLICATION_IN_PROGRESS, ("ACTIVE_PUBLICATION_CLAIM",), ("An atomic publication claim is active; no send was attempted.",), candidate_state=candidate_state.state.value, publication_state=state.value, publication=publication_state)
        if state is PipelinePublicationState.FAILED_RETRYABLE and not command.retry:
            return self._persist(command, request_fp, PipelineStatus.RETRY_REQUIRED, ("EXPLICIT_RETRY_REQUIRED",), ("A confirmed retryable failure may proceed only with retry=true.",), candidate_state=candidate_state.state.value, publication_state=state.value, publication=publication_state)
        if state is PipelinePublicationState.FAILED_TERMINAL:
            return self._persist(command, request_fp, PipelineStatus.ALREADY_PUBLISHED_CONFLICT, ("TERMINAL_PUBLICATION_FAILURE",), ("Terminal publication state blocks retry.",), candidate_state=candidate_state.state.value, publication_state=state.value, publication=publication_state)
        if state in {PipelinePublicationState.UNKNOWN, PipelinePublicationState.INDETERMINATE}:
            return self._persist(command, request_fp, PipelineStatus.RETRY_REQUIRED, (state.value,), ("Publication state is not safe for a send; the pipeline failed closed.",), candidate_state=candidate_state.state.value, publication_state=state.value, publication=publication_state)

        try:
            assembly = self._assembler.assemble(command.assembly_request, PublicationStateRecord(
                prediction_id=command.assembly_request.prediction.prediction_id,
                match_id=command.match_id,
                state=(PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE if state is PipelinePublicationState.FAILED_RETRYABLE else PublicationDeliveryState.NEVER_ATTEMPTED),
                observed_at=publication_state.observed_at,
                attempt_reference=publication_state.claim_identity,
            ))
            gate_candidate = assembly.gate_candidate
            if gate_candidate.calibrated_probability != command.calibrated_probability:
                raise ValueError("Calibrated probability conflicts with persisted assembly facts.")
        except Exception as exc:
            return self._persist(command, request_fp, PipelineStatus.REJECTED_PROVENANCE, ("QUALITY_GATE_HANDOFF_INVALID",), (f"Quality Gate handoff could not be verified ({type(exc).__name__}).",), candidate_state=candidate_state.state.value, publication_state=state.value)

        handoff_fp = gate_handoff_fingerprint(
            command,
            getattr(self._quality_gate, "policy_version", None),
        )
        try:
            gate = None
            if command.retry:
                previous = self._repository.find_latest_for_candidate(command.candidate_id)
                if (
                    previous is not None
                    and previous.quality_gate_status == QualityGateStatus.APPROVED.value
                    and previous.quality_gate_evaluation_id is not None
                ):
                    gate = self._quality_gate.load(previous.quality_gate_evaluation_id)
            if gate is None:
                gate = self._quality_gate.evaluate_once(gate_candidate)
        except Exception as exc:
            return self._persist(command, request_fp, PipelineStatus.QUALITY_GATE_EXECUTION_FAILED, ("QUALITY_GATE_EXECUTION_FAILED",), (f"Quality Gate execution or persistence failed ({type(exc).__name__}).",), candidate_state=candidate_state.state.value, publication_state=state.value)
        if not self._valid_gate(gate, gate_candidate):
            return self._persist(command, request_fp, PipelineStatus.REJECTED_INVALID_GATE_RESULT, ("INVALID_GATE_RESULT",), ("Quality Gate result does not belong to the exact candidate handoff.",), candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp)
        if gate.final_decision is QualityGateStatus.REJECTED:
            return self._persist(command, request_fp, PipelineStatus.NO_PUBLICATION_QUALITY_GATE_REJECTED, tuple(item.value for item in gate.ordered_reason_codes), gate.internal_explanations, candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp)
        if gate.final_decision is QualityGateStatus.REVIEW_REQUIRED:
            return self._persist(command, request_fp, PipelineStatus.NO_PUBLICATION_REVIEW_REQUIRED, tuple(item.value for item in gate.ordered_reason_codes), gate.internal_explanations, candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp)
        if gate.final_decision is not QualityGateStatus.APPROVED:
            return self._persist(command, request_fp, PipelineStatus.REJECTED_INVALID_GATE_RESULT, ("UNKNOWN_GATE_STATUS",), ("Quality Gate returned an unsupported status.",), candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp)

        request = replace(command.assembly_request, dry_run=command.dry_run)
        try:
            orchestration = await self._orchestration.prepare_and_publish_preapproved(request, gate)
        except Exception as exc:
            return self._persist(command, request_fp, PipelineStatus.ORCHESTRATION_FAILED, ("ORCHESTRATION_EXCEPTION",), (f"Orchestration failed safely ({type(exc).__name__}).",), candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp)
        orchestration_fp = digest(orchestration)
        if orchestration.prediction_id != request.prediction.prediction_id or orchestration.quality_gate_evaluation_id != gate.evaluation_id:
            return self._persist(command, request_fp, PipelineStatus.ORCHESTRATION_REJECTED, ("ORCHESTRATION_IDENTITY_MISMATCH",), ("Orchestration does not belong to this candidate and gate evaluation.",), candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp, orchestration=orchestration, orchestration_fingerprint=orchestration_fp)

        if command.dry_run:
            if orchestration.final_status is not OrchestrationStatus.APPROVED_NOT_PUBLISHED:
                return self._persist(command, request_fp, PipelineStatus.ORCHESTRATION_REJECTED, orchestration.ordered_reason_codes, orchestration.internal_explanations, candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp, orchestration=orchestration, orchestration_fingerprint=orchestration_fp)
            try:
                payload = self._message_preview.build_preview(request, gate, orchestration)
            except Exception as exc:
                return self._persist(command, request_fp, PipelineStatus.ORCHESTRATION_FAILED, ("MESSAGE_ASSEMBLY_FAILED",), (f"Dry-run message preview failed ({type(exc).__name__}).",), candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp, orchestration=orchestration, orchestration_fingerprint=orchestration_fp)
            return self._persist(command, request_fp, PipelineStatus.DRY_RUN_COMPLETED, ("DRY_RUN",), ("Quality Gate approved and the deterministic message preview was built; no claim or send occurred.",), candidate_state=candidate_state.state.value, publication_state=state.value, gate=gate, gate_fingerprint=handoff_fp, orchestration=orchestration, orchestration_fingerprint=orchestration_fp, message_fingerprint=payload.message_fingerprint)

        mapped = self._map_orchestration(orchestration)
        final_publication = self._publication_states.verify(command)
        return self._persist(command, request_fp, mapped, orchestration.ordered_reason_codes, orchestration.internal_explanations, candidate_state=candidate_state.state.value, publication_state=final_publication.state.value, gate=gate, gate_fingerprint=handoff_fp, orchestration=orchestration, orchestration_fingerprint=orchestration_fp, publication=final_publication, message_fingerprint=final_publication.message_fingerprint)

    @staticmethod
    def _valid_gate(gate, candidate) -> bool:
        return bool(
            gate is not None
            and isinstance(gate.final_decision, QualityGateStatus)
            and gate.prediction_id == candidate.prediction_id
            and gate.model_version == candidate.model_version
            and gate.raw_probability == candidate.raw_probability
            and gate.calibrated_probability == candidate.calibrated_probability
            and gate.decimal_odds == candidate.decimal_odds
            and gate.supplied_expected_value == candidate.expected_value
            and gate.prediction_timestamp == candidate.prediction_timestamp
            and gate.kickoff_timestamp == candidate.kickoff_timestamp
            and gate.evaluated_at == candidate.evaluation_timestamp
        )

    @staticmethod
    def _map_orchestration(value) -> PipelineStatus:
        if value.final_status is OrchestrationStatus.PUBLISHED:
            return PipelineStatus.PUBLISHED
        if value.final_status is OrchestrationStatus.DUPLICATE_BLOCKED:
            return PipelineStatus.PUBLICATION_IN_PROGRESS
        if value.final_status is OrchestrationStatus.RETRYABLE_PUBLICATION_FAILURE:
            reasons = set(value.ordered_reason_codes)
            if "PUBLICATION_CLAIM_FAILED" in reasons:
                return PipelineStatus.PUBLICATION_CLAIM_FAILED
            if "TELEGRAM_CONFIRMED_FAILED" in reasons:
                return PipelineStatus.PUBLICATION_SEND_FAILED
            return PipelineStatus.RETRY_REQUIRED
        if value.final_status is OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE:
            return PipelineStatus.PUBLICATION_FINALIZATION_FAILED
        if value.final_status is OrchestrationStatus.REJECTED:
            return PipelineStatus.ORCHESTRATION_REJECTED
        return PipelineStatus.ORCHESTRATION_FAILED

    def _persist(self, command, request_fp, status, reasons, explanations, *, candidate_state=None, publication_state=None, gate=None, gate_fingerprint=None, orchestration=None, orchestration_fingerprint=None, publication=None, message_fingerprint=None):
        base = self._outcome(command, status, reasons, explanations, request_fp, candidate_state, publication_state, gate, gate_fingerprint, orchestration, orchestration_fingerprint, publication, message_fingerprint)
        pipeline_fp = execution_fingerprint(base)
        completed = replace(base, pipeline_execution_id=execution_id(request_fp, status.value), pipeline_fingerprint=pipeline_fp)
        stages = self._stages(completed)
        try:
            return self._repository.append_pipeline_execution(completed, stages)
        except PipelineConflictError:
            return self._unpersisted(command, PipelineStatus.CONFLICT, ("PERSISTENCE_CONFLICT",), ("Immutable pipeline history conflicts with this execution.",), request_fp)
        except Exception:
            return self._unpersisted(command, PipelineStatus.PERSISTENCE_FAILURE, ("PERSISTENCE_FAILURE",), ("Pipeline outcome could not be persisted atomically.",), request_fp)

    def _outcome(self, command, status, reasons, explanations, request_fp, candidate_state=None, publication_state=None, gate=None, gate_fingerprint=None, orchestration=None, orchestration_fingerprint=None, publication=None, message_fingerprint=None):
        snapshot = tuple(sorted({"candidate_state": candidate_state or "none", "final_status": status.value, "publication_state": publication_state or "none", "request_fingerprint": request_fp}.items()))
        return OfficialPredictionPipelineOutcome(
            pipeline_execution_id=None,
            pipeline_request_identity=command.pipeline_request_identity,
            manual_run_identity=command.manual_run_identity,
            candidate_id=command.candidate_id,
            candidate_version=command.candidate_version,
            candidate_fingerprint=command.candidate_fingerprint,
            match_id=command.match_id,
            kickoff_timestamp=command.kickoff_timestamp,
            quality_gate_evaluation_id=getattr(gate, "evaluation_id", None),
            quality_gate_status=getattr(getattr(gate, "final_decision", None), "value", None),
            quality_gate_fingerprint=gate_fingerprint,
            orchestration_id=getattr(orchestration, "orchestration_id", None),
            orchestration_status=getattr(getattr(orchestration, "final_status", None), "value", None),
            orchestration_fingerprint=orchestration_fingerprint,
            publication_event_id=getattr(publication, "publication_event_id", None),
            publication_status=getattr(getattr(publication, "state", None), "value", None),
            publication_fingerprint=getattr(publication, "publication_fingerprint", None),
            publication_claim_identity=getattr(publication, "claim_identity", None),
            message_fingerprint=message_fingerprint or getattr(publication, "message_fingerprint", None),
            telegram_message_reference=getattr(publication, "telegram_message_reference", None),
            final_status=status,
            dry_run=command.dry_run,
            retry=command.retry,
            ordered_reason_codes=tuple(reasons),
            explanations=tuple(explanations),
            request_fingerprint=request_fp,
            pipeline_fingerprint=None,
            quality_gate_evaluation_timestamp=command.quality_gate_evaluation_timestamp,
            pipeline_execution_timestamp=command.pipeline_execution_timestamp,
            publication_effective_timestamp=command.publication_effective_timestamp,
            pipeline_policy_version=self.policy.version,
            candidate_state_result=candidate_state,
            publication_state_result=publication_state,
            deterministic_execution_snapshot=snapshot,
        )

    def _unpersisted(self, command, status, reasons, explanations, request_fp=None):
        identity = getattr(command, "pipeline_request_identity", "invalid-request")
        return OfficialPredictionPipelineOutcome(
            pipeline_execution_id=None,
            pipeline_request_identity=identity if isinstance(identity, str) else "invalid-request",
            manual_run_identity=getattr(command, "manual_run_identity", None),
            candidate_id=getattr(command, "candidate_id", None),
            candidate_version=getattr(command, "candidate_version", None),
            candidate_fingerprint=getattr(command, "candidate_fingerprint", None),
            match_id=getattr(command, "match_id", None),
            kickoff_timestamp=getattr(command, "kickoff_timestamp", None),
            quality_gate_evaluation_id=None,
            quality_gate_status=None,
            quality_gate_fingerprint=None,
            orchestration_id=None,
            orchestration_status=None,
            orchestration_fingerprint=None,
            publication_event_id=None,
            publication_status=None,
            publication_fingerprint=None,
            publication_claim_identity=None,
            message_fingerprint=None,
            telegram_message_reference=None,
            final_status=status,
            dry_run=bool(getattr(command, "dry_run", False)),
            retry=bool(getattr(command, "retry", False)),
            ordered_reason_codes=tuple(reasons),
            explanations=tuple(explanations),
            request_fingerprint=request_fp,
            pipeline_fingerprint=None,
            quality_gate_evaluation_timestamp=getattr(command, "quality_gate_evaluation_timestamp", None),
            pipeline_execution_timestamp=getattr(command, "pipeline_execution_timestamp", None),
            publication_effective_timestamp=getattr(command, "publication_effective_timestamp", None),
            pipeline_policy_version=self.policy.version,
        )

    @staticmethod
    def _stages(outcome):
        names = [PipelineStage.REQUEST_VALIDATION, PipelineStage.CANDIDATE_STATE_VERIFICATION, PipelineStage.PUBLICATION_STATE_VERIFICATION]
        if outcome.quality_gate_evaluation_id:
            names.append(PipelineStage.QUALITY_GATE)
        if outcome.orchestration_id:
            names.append(PipelineStage.ORCHESTRATION)
        if outcome.message_fingerprint:
            names.append(PipelineStage.MESSAGE_ASSEMBLY)
        if not outcome.dry_run and outcome.publication_claim_identity:
            names.extend((PipelineStage.PUBLICATION_CLAIM, PipelineStage.TELEGRAM_SEND, PipelineStage.PUBLICATION_FINALIZATION))
        return tuple(PipelineStageEvent(
            stage_event_id(outcome.pipeline_execution_id, order, stage.value), outcome.pipeline_execution_id, order, stage, "COMPLETED",
            outcome.quality_gate_evaluation_id if stage is PipelineStage.QUALITY_GATE else outcome.orchestration_id if stage is PipelineStage.ORCHESTRATION else outcome.publication_event_id if order >= 7 else None,
            outcome.quality_gate_fingerprint if stage is PipelineStage.QUALITY_GATE else outcome.orchestration_fingerprint if stage is PipelineStage.ORCHESTRATION else outcome.message_fingerprint if stage is PipelineStage.MESSAGE_ASSEMBLY else None,
            outcome.ordered_reason_codes if stage is names[-1] else (), tuple(sorted({"final_status": outcome.final_status.value, "stage": stage.value}.items())), outcome.pipeline_execution_timestamp,
        ) for order, stage in enumerate(names, 1))


async def execute_official_prediction_pipeline(service: OfficialPredictionPipelineService, command: OfficialPredictionPipelineCommand) -> OfficialPredictionPipelineOutcome:
    """Explicit one-candidate callable; it is never invoked at import or startup."""
    return await service.execute(command)
