"""Adapters that reuse registry, gate, orchestration, and message APIs."""

from __future__ import annotations

from dataclasses import replace

from app.official_prediction_candidate_registry import (
    CandidateLifecycleState,
    SQLiteOfficialPredictionCandidateRepository,
)
from app.official_prediction_orchestration import (
    ApprovedOfficialPredictionPublication,
    OfficialCandidateFingerprint,
    OfficialPredictionCandidateAssembler,
    OfficialPredictionOrchestrationOutcome,
    OfficialPredictionOrchestrationService,
    OfficialPublicationStateReader,
    PublicationDeliveryState,
)
from app.official_prediction_publication import (
    OfficialPredictionDestination,
    OfficialPredictionMessageBuilder,
    OfficialPredictionMessageInput,
    OfficialPredictionPublicFactsProvider,
    PredictionPublicationEventStatus,
    SQLiteAtomicPredictionPublicationRepository,
)
from app.publication_quality_gate import (
    OfficialPublicationQualityGate,
    OfficialQualityGateEvaluation,
    QualityGateEvaluationRepository,
)
from app.quality_gate import QualityGateStatus

from .models import (
    CandidateState,
    CandidateStateVerification,
    OfficialPredictionPipelineCommand,
    PipelinePublicationState,
    PublicationStateVerification,
)


class SQLiteCandidateRegistryStateAdapter:
    """Read-only exact-version and current-lifecycle verification."""

    def __init__(self, repository: SQLiteOfficialPredictionCandidateRepository) -> None:
        self._repository = repository

    def verify(self, command: OfficialPredictionPipelineCommand) -> CandidateStateVerification:
        try:
            candidate = self._repository.find_candidate_by_id(command.candidate_id)
            if candidate is None:
                return CandidateStateVerification(CandidateState.MISSING, None, False)
            state = self._repository.current_state(command.candidate_id)
        except Exception:
            return CandidateStateVerification(CandidateState.INDETERMINATE, None, False)
        mapped = {
            CandidateLifecycleState.READY: CandidateState.READY,
            CandidateLifecycleState.SUPERSEDED: CandidateState.SUPERSEDED,
            CandidateLifecycleState.WITHDRAWN: CandidateState.WITHDRAWN,
            CandidateLifecycleState.INVALIDATED: CandidateState.INVALIDATED,
        }.get(state, CandidateState.UNKNOWN)
        exact = (
            candidate.candidate_version == command.candidate_version
            and candidate.content_fingerprint == command.candidate_fingerprint
        )
        return CandidateStateVerification(
            mapped if exact else CandidateState.UNKNOWN,
            candidate,
            mapped is CandidateState.READY and exact,
            fingerprint=candidate.content_fingerprint,
        )


class ExistingPublicationStateAdapter:
    """Maps durable publication state without acquiring a claim."""

    def __init__(
        self,
        reader: OfficialPublicationStateReader,
        events: SQLiteAtomicPredictionPublicationRepository | None = None,
    ) -> None:
        self._reader = reader
        self._events = events

    def verify(self, command: OfficialPredictionPipelineCommand) -> PublicationStateVerification:
        try:
            record = self._reader.get(
                command.assembly_request.prediction.prediction_id,
                command.match_id,
                command.pipeline_execution_timestamp,
            )
        except Exception:
            return PublicationStateVerification(PipelinePublicationState.INDETERMINATE, command.pipeline_execution_timestamp)
        mapping = {
            PublicationDeliveryState.NEVER_ATTEMPTED: PipelinePublicationState.NOT_PUBLISHED,
            PublicationDeliveryState.PUBLISHED: PipelinePublicationState.PUBLISHED,
            PublicationDeliveryState.CLAIMED: PipelinePublicationState.ACTIVE_CLAIM,
            PublicationDeliveryState.ATTEMPTING: PipelinePublicationState.ACTIVE_CLAIM,
            PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE: PipelinePublicationState.FAILED_RETRYABLE,
            PublicationDeliveryState.INDETERMINATE_FAILURE: PipelinePublicationState.INDETERMINATE,
        }
        state = mapping.get(record.state, PipelinePublicationState.UNKNOWN)
        event = None
        if self._events is not None:
            try:
                event = self._events.latest(command.assembly_request.prediction.prediction_id, "OFFICIAL")
            except Exception:
                return PublicationStateVerification(PipelinePublicationState.INDETERMINATE, record.observed_at)
        if event is not None and event.status is PredictionPublicationEventStatus.FAILED:
            state = PipelinePublicationState.FAILED_RETRYABLE
        return PublicationStateVerification(
            state=state,
            observed_at=record.observed_at,
            publication_event_id=getattr(event, "event_id", None),
            publication_fingerprint=getattr(getattr(event, "payload", None), "message_fingerprint", None),
            message_fingerprint=getattr(getattr(event, "payload", None), "message_fingerprint", None),
            claim_identity=getattr(event, "attempt_reference", None) or record.attempt_reference,
            telegram_message_reference=(str(event.telegram_message_id) if event is not None and event.telegram_message_id else None),
        )


class PersistedQualityGateAdapter:
    def __init__(self, gate: OfficialPublicationQualityGate, repository: QualityGateEvaluationRepository) -> None:
        self._gate = gate
        self._repository = repository

    @property
    def policy_version(self) -> str:
        return self._gate.policy.version

    def evaluate_once(self, candidate: object) -> OfficialQualityGateEvaluation:
        return self._repository.append(self._gate.evaluate(candidate))

    def load(self, evaluation_id: str) -> OfficialQualityGateEvaluation | None:
        return self._repository.get(evaluation_id)


class ExistingPreapprovedOrchestrationAdapter:
    def __init__(self, service: OfficialPredictionOrchestrationService) -> None:
        self._service = service

    async def prepare_and_publish_preapproved(self, request, evaluation):
        return await self._service.prepare_and_publish_preapproved(request, evaluation)


class ExistingMessagePreviewAdapter:
    """Builds the exact existing public payload without claiming or sending."""

    def __init__(
        self,
        assembler: OfficialPredictionCandidateAssembler,
        publication_states: OfficialPublicationStateReader,
        messages: OfficialPredictionMessageBuilder,
        public_facts: OfficialPredictionPublicFactsProvider,
        destination: OfficialPredictionDestination,
    ) -> None:
        self._assembler = assembler
        self._publication_states = publication_states
        self._messages = messages
        self._public_facts = public_facts
        self._destination = destination
        self._fingerprint = OfficialCandidateFingerprint()

    def build_preview(self, request, evaluation, orchestration):
        publication = self._publication_states.get(
            request.prediction.prediction_id,
            request.prediction.match_id,
            request.evaluation_timestamp,
        )
        assembly = self._assembler.assemble(request, publication)
        approved = ApprovedOfficialPredictionPublication(
            orchestration_id=orchestration.orchestration_id,
            assembly=assembly,
            candidate_fingerprint=self._fingerprint.generate(assembly),
            quality_gate_evaluation=evaluation,
            approval_status=QualityGateStatus.APPROVED,
            evaluated_at=request.evaluation_timestamp,
            dry_run=False,
        )
        facts = self._public_facts.get(approved)
        if facts is None:
            raise ValueError("Approved public message facts are unavailable.")
        # Providers normally derive these identities from the approval.  A strict
        # immutable replacement supports providers that intentionally prebuild facts.
        if facts.orchestration_id != approved.orchestration_id:
            facts = replace(facts, orchestration_id=approved.orchestration_id)
        return self._messages.build(OfficialPredictionMessageInput(approved, facts, self._destination))
