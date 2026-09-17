"""Injected read-only and execution boundaries used by the pipeline."""

from __future__ import annotations

from typing import Protocol

from app.official_prediction_orchestration import (
    OfficialCandidateAssemblyRequest,
    OfficialPredictionOrchestrationOutcome,
)
from app.official_prediction_publication import OfficialPredictionPublicationPayload
from app.publication_quality_gate import OfficialPublicationCandidate, OfficialQualityGateEvaluation

from .models import (
    CandidateStateVerification,
    OfficialPredictionPipelineCommand,
    OfficialPredictionPipelineOutcome,
    PipelineExecutionWithStages,
    PipelineStageEvent,
    PublicationStateVerification,
)


class CandidateRegistryStatePort(Protocol):
    def verify(self, command: OfficialPredictionPipelineCommand) -> CandidateStateVerification: ...


class PipelinePublicationStatePort(Protocol):
    def verify(self, command: OfficialPredictionPipelineCommand) -> PublicationStateVerification: ...


class PersistedQualityGatePort(Protocol):
    def evaluate_once(self, candidate: OfficialPublicationCandidate) -> OfficialQualityGateEvaluation: ...
    def load(self, evaluation_id: str) -> OfficialQualityGateEvaluation | None: ...


class PreapprovedOfficialOrchestrationPort(Protocol):
    async def prepare_and_publish_preapproved(
        self,
        request: OfficialCandidateAssemblyRequest,
        evaluation: OfficialQualityGateEvaluation,
    ) -> OfficialPredictionOrchestrationOutcome: ...


class PipelineMessagePreviewPort(Protocol):
    def build_preview(
        self,
        request: OfficialCandidateAssemblyRequest,
        evaluation: OfficialQualityGateEvaluation,
        orchestration: OfficialPredictionOrchestrationOutcome,
    ) -> OfficialPredictionPublicationPayload: ...


class OfficialPredictionPipelineRepository(Protocol):
    def append_pipeline_execution(
        self,
        execution: OfficialPredictionPipelineOutcome,
        stage_events: tuple[PipelineStageEvent, ...] = (),
    ) -> OfficialPredictionPipelineOutcome: ...

    def append_stage_events(self, events: tuple[PipelineStageEvent, ...]) -> tuple[PipelineStageEvent, ...]: ...
    def find_by_pipeline_fingerprint(self, fingerprint: str) -> OfficialPredictionPipelineOutcome | None: ...
    def find_by_request_identity(self, identity: str) -> OfficialPredictionPipelineOutcome | None: ...
    def load_pipeline_execution(self, execution_id: str) -> OfficialPredictionPipelineOutcome | None: ...
    def load_execution_with_stages(self, execution_id: str) -> PipelineExecutionWithStages | None: ...
    def list_executions_for_candidate(self, candidate_id: str) -> tuple[OfficialPredictionPipelineOutcome, ...]: ...
    def list_executions_for_match(self, match_id: str) -> tuple[OfficialPredictionPipelineOutcome, ...]: ...
    def list_published_executions(self) -> tuple[OfficialPredictionPipelineOutcome, ...]: ...
    def list_gate_rejected_executions(self) -> tuple[OfficialPredictionPipelineOutcome, ...]: ...
    def list_retry_required_executions(self) -> tuple[OfficialPredictionPipelineOutcome, ...]: ...
    def find_latest_for_candidate(self, candidate_id: str) -> OfficialPredictionPipelineOutcome | None: ...
