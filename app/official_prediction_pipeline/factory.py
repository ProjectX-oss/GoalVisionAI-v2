"""Explicit dependency-injected composition; construction performs no execution."""

from app.official_prediction_orchestration import OfficialPredictionCandidateAssembler

from .policy import DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY, OfficialPredictionPipelinePolicy
from .service import OfficialPredictionPipelineService


def build_official_prediction_pipeline_service(
    *,
    repository,
    candidate_states,
    publication_states,
    quality_gate,
    orchestration,
    message_preview,
    policy: OfficialPredictionPipelinePolicy = DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY,
) -> OfficialPredictionPipelineService:
    """Build the manual service without discovery, scheduling, startup, or sends."""
    return OfficialPredictionPipelineService(
        policy=policy,
        candidate_states=candidate_states,
        publication_states=publication_states,
        quality_gate=quality_gate,
        orchestration=orchestration,
        message_preview=message_preview,
        repository=repository,
        assembler=OfficialPredictionCandidateAssembler(),
    )
