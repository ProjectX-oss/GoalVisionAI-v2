"""Strictly bounded manual runner; never discovers or schedules candidates."""

from __future__ import annotations

from .models import ManualPipelineRunSummary, OfficialPredictionPipelineCommand, PipelineStatus
from .policy import OfficialPredictionPipelinePolicy
from .service import OfficialPredictionPipelineService


async def run_official_prediction_pipeline_once(
    service: OfficialPredictionPipelineService,
    command: OfficialPredictionPipelineCommand,
):
    return await service.execute(command)


async def run_official_prediction_pipeline_batch(
    service: OfficialPredictionPipelineService,
    commands: tuple[OfficialPredictionPipelineCommand, ...],
    policy: OfficialPredictionPipelinePolicy,
) -> ManualPipelineRunSummary:
    if not commands or len(commands) > policy.maximum_batch_size:
        raise ValueError("Manual pipeline batch must be explicitly bounded.")
    identities = [(item.candidate_id, item.candidate_version, item.pipeline_request_identity) for item in commands]
    if len(set(identities)) != len(identities):
        raise ValueError("Manual pipeline batch contains duplicate candidates.")
    ordered = tuple(sorted(commands, key=lambda item: (item.kickoff_timestamp, item.candidate_id, item.candidate_version, item.pipeline_request_identity)))
    outcomes = tuple([await service.execute(item) for item in ordered])
    published = {PipelineStatus.PUBLISHED, PipelineStatus.IDEMPOTENT_EXISTING}
    rejected = {
        PipelineStatus.NO_PUBLICATION_QUALITY_GATE_REJECTED,
        PipelineStatus.NO_PUBLICATION_REVIEW_REQUIRED,
        PipelineStatus.REJECTED_INVALID_REQUEST,
        PipelineStatus.REJECTED_CANDIDATE_STATE,
        PipelineStatus.REJECTED_PROVENANCE,
        PipelineStatus.REJECTED_SCOPE,
        PipelineStatus.REJECTED_INVALID_GATE_RESULT,
        PipelineStatus.ORCHESTRATION_REJECTED,
    }
    retry = {PipelineStatus.RETRY_REQUIRED, PipelineStatus.PUBLICATION_IN_PROGRESS}
    return ManualPipelineRunSummary(
        manual_run_identity=ordered[0].manual_run_identity if all(item.manual_run_identity == ordered[0].manual_run_identity for item in ordered) else None,
        selected_count=len(ordered),
        published_count=sum(item.final_status in published for item in outcomes),
        rejected_count=sum(item.final_status in rejected for item in outcomes),
        retry_required_count=sum(item.final_status in retry for item in outcomes),
        failed_count=sum(item.final_status not in published | rejected | retry | {PipelineStatus.DRY_RUN_COMPLETED} for item in outcomes),
        outcomes=outcomes,
    )
