from decimal import Decimal

from app.quality_gate import PublicationQualityGate
from app.results import ResolvedPredictionResult

from .models import (
    ShadowEvaluationError,
    ShadowEvaluationOutcome,
    ShadowEvaluationRecord,
    ShadowEvaluationRequest,
    ShadowEvaluationResult,
    ShadowSettlementFacts,
)
from .repository import ShadowEvaluationRepository


class QualityGateShadowEvaluationService:
    """Evaluates and audits without exposing a control signal to live flow."""

    def __init__(
        self,
        gate: PublicationQualityGate,
        repository: ShadowEvaluationRepository,
    ) -> None:
        self._gate = gate
        self._repository = repository

    def evaluate(
        self,
        request: ShadowEvaluationRequest,
    ) -> ShadowEvaluationResult:
        try:
            existing = self._repository.get_by_identity(
                request.candidate.prediction_id,
                request.policy_version,
                request.stage,
            )
            if existing is not None:
                return ShadowEvaluationResult(
                    outcome=ShadowEvaluationOutcome.EXISTING,
                    record=existing,
                )
            decision = self._gate.evaluate(request.candidate, request.context)
            if decision.policy_version != request.policy_version:
                raise ValueError("Gate decision policy version mismatch.")
            record = ShadowEvaluationRecord(
                shadow_evaluation_id=request.shadow_evaluation_id,
                prediction_id=request.candidate.prediction_id,
                fixture_id=request.candidate.fixture_id,
                product_scope=request.candidate.product_scope,
                stage=request.stage,
                candidate_snapshot=request.candidate,
                context_snapshot=request.context,
                policy_version=decision.policy_version,
                evaluation_timestamp=decision.evaluation_timestamp,
                gate_status=decision.status,
                ordered_check_results=decision.checks,
                rejection_reasons=decision.rejection_reasons,
                review_reasons=decision.review_reasons,
                evaluated_probability=decision.evaluated_probability,
                probability_source=decision.probability_source,
                calculated_expected_value=decision.expected_value,
                market_disagreement=decision.market_disagreement,
                actually_published=request.actually_published,
                actual_publication_timestamp=(
                    request.actual_publication_timestamp
                ),
                actual_offered_odds=request.actual_offered_odds,
                settlement_outcome=None,
                eventual_profit_loss_units=None,
                settled_at=None,
                created_at=request.created_at,
            )
            stored, inserted = self._repository.insert_once(record)
            return ShadowEvaluationResult(
                outcome=(
                    ShadowEvaluationOutcome.RECORDED
                    if inserted
                    else ShadowEvaluationOutcome.EXISTING
                ),
                record=stored,
            )
        except Exception as exc:
            error = self._safe_error(request, exc)
            try:
                stored, _ = self._repository.insert_error_once(error)
                error = stored
            except Exception:
                pass
            return ShadowEvaluationResult(
                outcome=ShadowEvaluationOutcome.ERROR,
                error=error,
            )

    def record_error(
        self,
        error: ShadowEvaluationError,
    ) -> ShadowEvaluationResult:
        try:
            stored, _ = self._repository.insert_error_once(error)
            error = stored
        except Exception:
            pass
        return ShadowEvaluationResult(
            outcome=ShadowEvaluationOutcome.ERROR,
            error=error,
        )

    @staticmethod
    def _safe_error(
        request: ShadowEvaluationRequest,
        exception: Exception,
    ) -> ShadowEvaluationError:
        error_type = type(exception).__name__
        if not error_type.isidentifier():
            error_type = "ShadowEvaluationFailure"
        return ShadowEvaluationError(
            shadow_evaluation_id=request.shadow_evaluation_id,
            prediction_id=request.candidate.prediction_id,
            stage=request.stage,
            policy_version=request.policy_version,
            error_type=error_type,
            safe_message="Quality gate shadow evaluation failed safely.",
            occurred_at=request.created_at,
        )


class ShadowSettlementEnrichmentService:
    def __init__(self, repository: ShadowEvaluationRepository) -> None:
        self._repository = repository

    def attach(
        self,
        shadow_evaluation_id: str,
        facts: ShadowSettlementFacts,
    ) -> ShadowEvaluationRecord:
        existing = self._repository.get(shadow_evaluation_id)
        if existing is None:
            raise KeyError("Shadow evaluation does not exist.")
        original_decision = (
            existing.gate_status,
            existing.ordered_check_results,
            existing.rejection_reasons,
            existing.review_reasons,
            existing.evaluated_probability,
            existing.calculated_expected_value,
        )
        enriched = self._repository.attach_settlement(
            shadow_evaluation_id,
            facts,
        )
        enriched_decision = (
            enriched.gate_status,
            enriched.ordered_check_results,
            enriched.rejection_reasons,
            enriched.review_reasons,
            enriched.evaluated_probability,
            enriched.calculated_expected_value,
        )
        if enriched_decision != original_decision:
            raise RuntimeError("Settlement enrichment changed the gate decision.")
        return enriched

    def attach_authoritative(
        self,
        shadow_evaluation_id: str,
        result: ResolvedPredictionResult,
        profit_loss_units: Decimal,
    ) -> ShadowEvaluationRecord:
        existing = self._repository.get(shadow_evaluation_id)
        if existing is None:
            raise KeyError("Shadow evaluation does not exist.")
        if (
            existing.prediction_id != result.prediction_id
            or existing.fixture_id != result.fixture_id
        ):
            raise ValueError(
                "Authoritative settlement does not match the shadow record."
            )
        return self.attach(
            shadow_evaluation_id,
            ShadowSettlementFacts.from_authoritative_result(
                result,
                profit_loss_units,
            ),
        )
