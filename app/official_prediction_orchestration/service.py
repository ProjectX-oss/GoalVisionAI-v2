import hashlib
from dataclasses import replace

from app.publication_quality_gate import (
    GateReason,
    OfficialPublicationQualityGate,
    OfficialQualityGateEvaluation,
    QualityGateEvaluationRepository,
)
from app.quality_gate import QualityGateStatus

from .assembler import OfficialPredictionCandidateAssembler
from .exceptions import (
    CandidateAssemblyError,
    ConfirmedOfficialPublisherError,
    IndeterminateOfficialPublisherError,
)
from .fingerprint import OfficialCandidateFingerprint, canonical_items, fingerprint_items
from .models import (
    ApprovedOfficialPredictionPublication,
    AssemblyReason,
    OfficialCandidateAssembly,
    OfficialCandidateAssemblyRequest,
    OfficialPredictionOrchestrationOutcome,
    OfficialPredictionOrchestrationRecord,
    OfficialPredictionPublicationResult,
    OrchestrationStatus,
    PublicationDeliveryState,
    PublisherResultStatus,
)
from .ports import (
    AtomicOfficialPredictionPublisher,
    OfficialPublicationStateReader,
    OrchestrationHistoryRepository,
)


_SAFE_TERMINAL_STATUSES = {
    OrchestrationStatus.PUBLISHED,
    OrchestrationStatus.APPROVED_NOT_PUBLISHED,
    OrchestrationStatus.REJECTED,
    OrchestrationStatus.REVIEW_REQUIRED,
    OrchestrationStatus.DUPLICATE_BLOCKED,
    OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
}


class OfficialPredictionOrchestrationService:
    """The callable final Official pre-publication application boundary."""

    def __init__(
        self,
        assembler: OfficialPredictionCandidateAssembler,
        fingerprint: OfficialCandidateFingerprint,
        gate: OfficialPublicationQualityGate,
        gate_evaluations: QualityGateEvaluationRepository,
        history: OrchestrationHistoryRepository,
        publication_states: OfficialPublicationStateReader,
        publisher: AtomicOfficialPredictionPublisher,
    ) -> None:
        self._assembler = assembler
        self._fingerprint = fingerprint
        self._gate = gate
        self._gate_evaluations = gate_evaluations
        self._history = history
        self._publication_states = publication_states
        self._publisher = publisher

    async def prepare_and_publish_official_prediction(
        self,
        request: OfficialCandidateAssemblyRequest,
    ) -> OfficialPredictionOrchestrationOutcome:
        """Assemble, audit, gate, and only then invoke the atomic publisher."""
        prediction = request.prediction
        request_snapshot = self._request_snapshot(request)
        try:
            publication = self._publication_states.get(
                prediction.prediction_id,
                prediction.match_id,
                request.evaluation_timestamp,
            )
            assembly = self._assembler.assemble(request, publication)
        except CandidateAssemblyError as exc:
            return self._assembly_failure(request, request_snapshot, exc)
        except (ValueError, TypeError) as exc:
            failure = CandidateAssemblyError(
                (AssemblyReason.PUBLICATION_STATE_MISSING,),
                (f"Publication-state assembly failed: {type(exc).__name__}.",),
            )
            return self._assembly_failure(request, request_snapshot, failure)

        candidate_fingerprint = self._fingerprint.generate(assembly)
        try:
            existing = self._history.latest_for_fingerprint(
                prediction.prediction_id,
                candidate_fingerprint,
                request.dry_run,
            )
        except Exception as exc:
            return self._unpersisted_failure(
                request,
                candidate_fingerprint,
                AssemblyReason.ORCHESTRATION_PERSISTENCE_FAILED,
                f"Orchestration history lookup failed: {type(exc).__name__}.",
                assembly.normalized_input,
            )
        if existing is not None and existing.outcome.final_status in _SAFE_TERMINAL_STATUSES:
            return existing.outcome

        try:
            evaluation = self._gate.evaluate(assembly.gate_candidate)
        except Exception as exc:
            return self._record_failure(
                request,
                assembly,
                candidate_fingerprint,
                AssemblyReason.QUALITY_GATE_EVALUATION_FAILED,
                f"Quality Gate evaluation failed: {type(exc).__name__}.",
            )
        try:
            evaluation = self._gate_evaluations.append(evaluation)
        except Exception as exc:
            return self._record_failure(
                request,
                assembly,
                candidate_fingerprint,
                AssemblyReason.QUALITY_GATE_PERSISTENCE_FAILED,
                f"Quality Gate persistence failed: {type(exc).__name__}.",
            )

        reasons = tuple(item.value for item in evaluation.ordered_reason_codes)
        explanations = evaluation.internal_explanations
        if evaluation.final_decision is QualityGateStatus.REJECTED:
            status = self._rejected_status(assembly, evaluation.ordered_reason_codes)
            return self._record_outcome(
                request,
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
                status,
                reasons,
                explanations,
                assembly.publication_attempt_reference,
            )
        if evaluation.final_decision is QualityGateStatus.REVIEW_REQUIRED:
            return self._record_outcome(
                request,
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
                OrchestrationStatus.REVIEW_REQUIRED,
                reasons,
                explanations,
                None,
            )
        if request.dry_run:
            return self._record_outcome(
                request,
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
                OrchestrationStatus.APPROVED_NOT_PUBLISHED,
                (AssemblyReason.DRY_RUN.value,),
                ("Dry-run completed after persisted Quality Gate approval.",),
                None,
            )
        if not self._publisher.enabled:
            return self._record_outcome(
                request,
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
                OrchestrationStatus.APPROVED_NOT_PUBLISHED,
                (AssemblyReason.PUBLISHER_DISABLED.value,),
                ("The explicitly injected Official publisher is disabled.",),
                None,
            )

        approved = ApprovedOfficialPredictionPublication(
            orchestration_id=self._approval_id(
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
            ),
            assembly=assembly,
            candidate_fingerprint=candidate_fingerprint,
            quality_gate_evaluation=evaluation,
            approval_status=QualityGateStatus.APPROVED,
            evaluated_at=request.evaluation_timestamp,
            dry_run=False,
        )
        result = await self._publish(approved)
        status, mapped_reasons, mapped_explanations = self._publisher_outcome(result)
        outcome = self._record_outcome(
            request,
            assembly,
            candidate_fingerprint,
            evaluation.evaluation_id,
            status,
            mapped_reasons,
            mapped_explanations,
            result.attempt_reference,
        )
        return outcome

    async def prepare_and_publish_preapproved(
        self,
        request: OfficialCandidateAssemblyRequest,
        evaluation: object,
    ) -> OfficialPredictionOrchestrationOutcome:
        """Continue from an exact persisted gate evaluation without evaluating again.

        This recovery/integration boundary is intentionally explicit.  It exists for
        callers that own the single Quality Gate invocation and must never be used
        with unverified or non-approved evidence.
        """
        prediction = request.prediction
        snapshot = self._request_snapshot(request)
        try:
            publication = self._publication_states.get(
                prediction.prediction_id,
                prediction.match_id,
                request.evaluation_timestamp,
            )
            assembly = self._assembler.assemble(request, publication)
        except CandidateAssemblyError as exc:
            return self._assembly_failure(request, snapshot, exc)
        except (ValueError, TypeError) as exc:
            return self._assembly_failure(
                request,
                snapshot,
                CandidateAssemblyError(
                    (AssemblyReason.PUBLICATION_STATE_MISSING,),
                    (f"Publication-state assembly failed: {type(exc).__name__}.",),
                ),
            )
        candidate_fingerprint = self._fingerprint.generate(assembly)
        if not self._verified_preapproval(assembly, evaluation):
            return self._record_failure(
                request,
                assembly,
                candidate_fingerprint,
                AssemblyReason.QUALITY_GATE_EVALUATION_FAILED,
                "Supplied Quality Gate evaluation does not belong to this candidate.",
            )
        assert hasattr(evaluation, "evaluation_id")
        try:
            existing = self._history.latest_for_fingerprint(
                prediction.prediction_id,
                candidate_fingerprint,
                request.dry_run,
            )
        except Exception as exc:
            return self._unpersisted_failure(
                request,
                candidate_fingerprint,
                AssemblyReason.ORCHESTRATION_PERSISTENCE_FAILED,
                f"Orchestration history lookup failed: {type(exc).__name__}.",
                assembly.normalized_input,
            )
        if existing is not None and existing.outcome.final_status in _SAFE_TERMINAL_STATUSES:
            return existing.outcome
        if request.dry_run:
            return self._record_outcome(
                request,
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
                OrchestrationStatus.APPROVED_NOT_PUBLISHED,
                (AssemblyReason.DRY_RUN.value,),
                ("Dry-run completed from the verified persisted Quality Gate approval.",),
                None,
            )
        if not self._publisher.enabled:
            return self._record_outcome(
                request,
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
                OrchestrationStatus.APPROVED_NOT_PUBLISHED,
                (AssemblyReason.PUBLISHER_DISABLED.value,),
                ("The explicitly injected Official publisher is disabled.",),
                None,
            )
        approved = ApprovedOfficialPredictionPublication(
            orchestration_id=self._approval_id(
                assembly,
                candidate_fingerprint,
                evaluation.evaluation_id,
            ),
            assembly=assembly,
            candidate_fingerprint=candidate_fingerprint,
            quality_gate_evaluation=evaluation,
            approval_status=QualityGateStatus.APPROVED,
            evaluated_at=request.evaluation_timestamp,
            dry_run=False,
        )
        result = await self._publish(approved)
        status, reasons, explanations = self._publisher_outcome(result)
        return self._record_outcome(
            request,
            assembly,
            candidate_fingerprint,
            evaluation.evaluation_id,
            status,
            reasons,
            explanations,
            result.attempt_reference,
        )

    def _verified_preapproval(
        self,
        assembly: OfficialCandidateAssembly,
        evaluation: object,
    ) -> bool:
        candidate = assembly.gate_candidate
        return bool(
            isinstance(evaluation, OfficialQualityGateEvaluation)
            and evaluation.final_decision is QualityGateStatus.APPROVED
            and evaluation.prediction_id == candidate.prediction_id
            and evaluation.model_version == candidate.model_version
            and evaluation.policy_version == self._gate.policy.version
            and evaluation.raw_probability == candidate.raw_probability
            and evaluation.calibrated_probability == candidate.calibrated_probability
            and evaluation.decimal_odds == candidate.decimal_odds
            and evaluation.supplied_expected_value == candidate.expected_value
            and evaluation.confidence == candidate.confidence
            and evaluation.prediction_timestamp == candidate.prediction_timestamp
            and evaluation.kickoff_timestamp == candidate.kickoff_timestamp
            and evaluation.evaluated_at == candidate.evaluation_timestamp
            and evaluation.risk_result == candidate.risk_result
            and evaluation.exposure_result == candidate.exposure_result
        )

    async def _publish(
        self,
        approved: ApprovedOfficialPredictionPublication,
    ) -> OfficialPredictionPublicationResult:
        try:
            return await self._publisher.publish(approved)
        except ConfirmedOfficialPublisherError as exc:
            return OfficialPredictionPublicationResult(
                PublisherResultStatus.RETRYABLE_FAILURE,
                exc.attempt_reference,
                (AssemblyReason.PUBLISHER_CONFIRMED_FAILURE.value,),
                (str(exc),),
            )

        except IndeterminateOfficialPublisherError as exc:
            return OfficialPredictionPublicationResult(
                PublisherResultStatus.INDETERMINATE_FAILURE,
                exc.attempt_reference,
                (AssemblyReason.PUBLISHER_INDETERMINATE_FAILURE.value,),
                (str(exc),),
            )
        except Exception as exc:
            return OfficialPredictionPublicationResult(
                PublisherResultStatus.INDETERMINATE_FAILURE,
                None,
                (AssemblyReason.PUBLISHER_INDETERMINATE_FAILURE.value,),
                (
                    "Publisher raised an unknown post-claim error; automatic retry "
                    f"is blocked ({type(exc).__name__}).",
                ),
            )

    @staticmethod
    def _approval_id(
        assembly: OfficialCandidateAssembly,
        candidate_fingerprint: str,
        gate_evaluation_id: str,
    ) -> str:
        seed = "|".join((
            "official-publication-approval-v1",
            assembly.prediction_id,
            assembly.match_id,
            candidate_fingerprint,
            gate_evaluation_id,
        ))
        return "official-publication-approval-" + hashlib.sha256(
            seed.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _publisher_outcome(
        result: OfficialPredictionPublicationResult,
    ) -> tuple[OrchestrationStatus, tuple[str, ...], tuple[str, ...]]:
        mapping = {
            PublisherResultStatus.PUBLISHED: OrchestrationStatus.PUBLISHED,
            PublisherResultStatus.DUPLICATE_BLOCKED: OrchestrationStatus.DUPLICATE_BLOCKED,
            PublisherResultStatus.RETRYABLE_FAILURE: OrchestrationStatus.RETRYABLE_PUBLICATION_FAILURE,
            PublisherResultStatus.INDETERMINATE_FAILURE: OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
        }
        default_reasons = {
            PublisherResultStatus.PUBLISHED: (),
            PublisherResultStatus.DUPLICATE_BLOCKED: (
                AssemblyReason.PUBLISHER_DUPLICATE_BLOCKED.value,
            ),
            PublisherResultStatus.RETRYABLE_FAILURE: (
                AssemblyReason.PUBLISHER_CONFIRMED_FAILURE.value,
            ),
            PublisherResultStatus.INDETERMINATE_FAILURE: (
                AssemblyReason.PUBLISHER_INDETERMINATE_FAILURE.value,
            ),
        }
        return (
            mapping[result.status],
            result.ordered_reason_codes or default_reasons[result.status],
            result.internal_explanations,
        )

    @staticmethod
    def _rejected_status(
        assembly: OfficialCandidateAssembly,
        gate_reasons: tuple[GateReason, ...],
    ) -> OrchestrationStatus:
        if assembly.publication_state is PublicationDeliveryState.INDETERMINATE_FAILURE:
            return OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE
        if (
            assembly.publication_state
            in {
                PublicationDeliveryState.PUBLISHED,
                PublicationDeliveryState.CLAIMED,
                PublicationDeliveryState.ATTEMPTING,
            }
            or GateReason.ALREADY_PUBLISHED in gate_reasons
            or GateReason.ACTIVE_PUBLICATION_ATTEMPT in gate_reasons
        ):
            return OrchestrationStatus.DUPLICATE_BLOCKED
        return OrchestrationStatus.REJECTED

    def _assembly_failure(
        self,
        request: OfficialCandidateAssemblyRequest,
        snapshot: tuple[tuple[str, str], ...],
        error: CandidateAssemblyError,
    ) -> OfficialPredictionOrchestrationOutcome:
        input_fingerprint = fingerprint_items(snapshot)
        outcome = self._make_outcome(
            request,
            candidate_fingerprint=None,
            gate_evaluation_id=None,
            status=OrchestrationStatus.ASSEMBLY_FAILED,
            reasons=tuple(item.value for item in error.reasons),
            explanations=error.explanations,
            attempt_reference=None,
            identity_seed=f"assembly:{input_fingerprint}",
        )
        record = OfficialPredictionOrchestrationRecord(
            outcome=outcome,
            normalized_input=snapshot,
            created_timestamp=request.evaluation_timestamp,
        )
        try:
            return self._history.append(record).outcome
        except Exception:
            return outcome

    def _record_failure(
        self,
        request: OfficialCandidateAssemblyRequest,
        assembly: OfficialCandidateAssembly,
        fingerprint: str,
        reason: AssemblyReason,
        explanation: str,
    ) -> OfficialPredictionOrchestrationOutcome:
        return self._record_outcome(
            request,
            assembly,
            fingerprint,
            None,
            OrchestrationStatus.ASSEMBLY_FAILED,
            (reason.value,),
            (explanation,),
            None,
        )

    def _record_outcome(
        self,
        request: OfficialCandidateAssemblyRequest,
        assembly: OfficialCandidateAssembly,
        candidate_fingerprint: str,
        gate_evaluation_id: str | None,
        status: OrchestrationStatus,
        reasons: tuple[str, ...],
        explanations: tuple[str, ...],
        attempt_reference: str | None,
    ) -> OfficialPredictionOrchestrationOutcome:
        try:
            ordinal = len(self._history.history_for_prediction(request.prediction.prediction_id))
        except Exception:
            ordinal = 0
        outcome = self._make_outcome(
            request,
            candidate_fingerprint,
            gate_evaluation_id,
            status,
            reasons,
            explanations,
            attempt_reference,
            identity_seed=(
                f"candidate:{candidate_fingerprint}:{status.value}:"
                f"{attempt_reference or 'none'}:{ordinal}"
            ),
        )
        record = OfficialPredictionOrchestrationRecord(
            outcome=outcome,
            normalized_input=assembly.normalized_input,
            created_timestamp=request.evaluation_timestamp,
        )
        try:
            return self._history.append(record).outcome
        except Exception as exc:
            if status in {
                OrchestrationStatus.PUBLISHED,
                OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
            }:
                return replace(
                    outcome,
                    final_status=OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE,
                    ordered_reason_codes=(
                        AssemblyReason.ORCHESTRATION_PERSISTENCE_FAILED.value,
                    ),
                    internal_explanations=(
                        "Publication may have succeeded, but orchestration audit "
                        f"persistence failed ({type(exc).__name__}).",
                    ),
                )
            return replace(
                outcome,
                final_status=OrchestrationStatus.ASSEMBLY_FAILED,
                ordered_reason_codes=(
                    AssemblyReason.ORCHESTRATION_PERSISTENCE_FAILED.value,
                ),
                internal_explanations=(
                    f"Orchestration audit persistence failed: {type(exc).__name__}.",
                ),
            )

    def _unpersisted_failure(
        self,
        request: OfficialCandidateAssemblyRequest,
        candidate_fingerprint: str,
        reason: AssemblyReason,
        explanation: str,
        snapshot: tuple[tuple[str, str], ...],
    ) -> OfficialPredictionOrchestrationOutcome:
        del snapshot
        return self._make_outcome(
            request,
            candidate_fingerprint,
            None,
            OrchestrationStatus.ASSEMBLY_FAILED,
            (reason.value,),
            (explanation,),
            None,
            f"unpersisted:{candidate_fingerprint}:{reason.value}",
        )

    def _make_outcome(
        self,
        request: OfficialCandidateAssemblyRequest,
        candidate_fingerprint: str | None,
        gate_evaluation_id: str | None,
        status: OrchestrationStatus,
        reasons: tuple[str, ...],
        explanations: tuple[str, ...],
        attempt_reference: str | None,
        identity_seed: str,
    ) -> OfficialPredictionOrchestrationOutcome:
        digest = hashlib.sha256(
            (
                f"official-orchestration-v1|{request.prediction.prediction_id}|"
                f"{int(request.dry_run)}|{identity_seed}"
            ).encode("utf-8")
        ).hexdigest()
        return OfficialPredictionOrchestrationOutcome(
            orchestration_id=f"official-orchestration-{digest}",
            prediction_id=request.prediction.prediction_id,
            candidate_fingerprint=candidate_fingerprint,
            quality_gate_evaluation_id=gate_evaluation_id,
            final_status=status,
            ordered_reason_codes=reasons,
            internal_explanations=explanations,
            publication_attempt_reference=attempt_reference,
            evaluated_timestamp=request.evaluation_timestamp,
            dry_run=request.dry_run,
            policy_version=self._gate.policy.version,
            model_version=request.prediction.model_version,
        )

    @staticmethod
    def _request_snapshot(
        request: OfficialCandidateAssemblyRequest,
    ) -> tuple[tuple[str, str], ...]:
        prediction = request.prediction
        calibration_ids = tuple(sorted(item.calibration_run_id for item in request.calibration_records))
        health_ids = tuple(sorted(item.record_id for item in request.model_health_records))
        risk_ids = tuple(sorted(item.evaluation_id for item in request.risk_evaluations))
        exposure_ids = tuple(sorted(item.evaluation_id for item in request.exposure_evaluations))
        return canonical_items({
            "bankroll_reference": request.bankroll.reference_id if request.bankroll else None,
            "calibration_record_ids": calibration_ids,
            "dry_run": request.dry_run,
            "evaluation_timestamp": request.evaluation_timestamp,
            "exposure_evaluation_ids": exposure_ids,
            "health_record_ids": health_ids,
            "match_id": prediction.match_id,
            "model_version": prediction.model_version,
            "prediction_id": prediction.prediction_id,
            "risk_evaluation_ids": risk_ids,
        })
