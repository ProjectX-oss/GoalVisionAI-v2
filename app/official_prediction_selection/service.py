"""Official single-market selection application service."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.market_value_assessment import MarketValueAssessment
from app.market_value_assessment.market_mapping import MarketMappingRegistry

from .eligibility import evaluate_assessment, ordered_reasons
from .exceptions import (
    InvalidSelectionRequestError,
    SelectionConflictError,
    SelectionPersistenceError,
    SelectionProvenanceError,
    SelectionScopeError,
)
from .fingerprint import (
    no_selection_fingerprint,
    request_fingerprint,
    selected_fingerprint,
    selection_decision_id,
)
from .models import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    OfficialNoSelectionDecision,
    OfficialPredictionSelectionCommand,
    OfficialPredictionSelectionOutcome,
    OfficialSelectionDecision,
    OfficialSelectionOutcomeStatus,
    SelectedOfficialPrediction,
    SelectionReason,
)
from .policy import (
    OfficialPredictionRankingPolicy,
    OfficialPredictionSelectionPolicy,
)
from .ports import (
    OfficialPredictionSelectionRepository,
    PersistedMarketValueAssessmentReader,
    PublicationStateProtection,
)
from .ranking import deduplicate_and_rank, ranking_values
from .validation import validate_selection_request


class OfficialPredictionSelectionService:
    """Select at most one Official single without downstream side effects."""

    def __init__(
        self,
        repository: OfficialPredictionSelectionRepository,
        assessments: PersistedMarketValueAssessmentReader,
        publication_states: PublicationStateProtection,
        mappings: MarketMappingRegistry,
        selection_policy: OfficialPredictionSelectionPolicy,
        ranking_policy: OfficialPredictionRankingPolicy,
    ) -> None:
        self.repository = repository
        self.assessments = assessments
        self.publication_states = publication_states
        self.mappings = mappings
        self.selection_policy = selection_policy
        self.ranking_policy = ranking_policy

    def select(
        self,
        command: OfficialPredictionSelectionCommand,
    ) -> OfficialPredictionSelectionOutcome:
        request_identity = getattr(command, "selection_request_identity", "")
        match_id = getattr(command, "match_id", "")
        selection_timestamp = getattr(command, "selection_timestamp", None)
        try:
            request = validate_selection_request(
                command,
                self.selection_policy,
                self.assessments,
            )
        except SelectionScopeError as exc:
            return self._failure(
                OfficialSelectionOutcomeStatus.REJECTED_SCOPE,
                request_identity,
                match_id,
                selection_timestamp,
                exc.reason,
                exc.explanation,
            )
        except InvalidSelectionRequestError as exc:
            return self._failure(
                OfficialSelectionOutcomeStatus.REJECTED_INVALID_REQUEST,
                request_identity,
                match_id,
                selection_timestamp,
                exc.reason,
                exc.explanation,
            )
        except SelectionProvenanceError as exc:
            return self._failure(
                OfficialSelectionOutcomeStatus.REJECTED_PROVENANCE,
                request_identity,
                match_id,
                selection_timestamp,
                exc.reason,
                exc.explanation,
            )
        except SelectionPersistenceError:
            return self._failure(
                OfficialSelectionOutcomeStatus.PERSISTENCE_FAILURE,
                request_identity,
                match_id,
                selection_timestamp,
                SelectionReason.PERSISTENCE_FAILURE,
                "Selection dependency persistence failed safely.",
            )

        assert request.selection_timestamp is not None
        assert request.kickoff_timestamp is not None
        fingerprint = request_fingerprint(request, self.ranking_policy.version)
        try:
            existing = self.repository.find_by_request_identity(
                request.selection_request_identity
            )
        except SelectionPersistenceError:
            return self._failure(
                OfficialSelectionOutcomeStatus.PERSISTENCE_FAILURE,
                request.selection_request_identity,
                request.match_id,
                request.selection_timestamp,
                SelectionReason.PERSISTENCE_FAILURE,
                "Selection history lookup failed safely.",
            )
        if existing is not None:
            if _request_fingerprint(existing) != fingerprint:
                return self._failure(
                    OfficialSelectionOutcomeStatus.CONFLICT,
                    request.selection_request_identity,
                    request.match_id,
                    request.selection_timestamp,
                    SelectionReason.REQUEST_IDENTITY_CONFLICT,
                    "Selection request identity was reused with different content.",
                )
            return self._outcome(
                existing,
                OfficialSelectionOutcomeStatus.IDEMPOTENT_EXISTING,
            )

        evaluations = tuple(
            evaluate_assessment(
                assessment,
                deterministic_input_order=index,
                request=request,
                request_identity_fingerprint=fingerprint,
                policy=self.selection_policy,
                mappings=self.mappings,
                publication_states=self.publication_states,
            )
            for index, assessment in enumerate(request.assessments)
        )
        evaluations, ranked = deduplicate_and_rank(
            evaluations,
            request.assessments,
            self.selection_policy,
            self.ranking_policy,
        )
        eligible_count = len(ranked)
        rejected_count = len(evaluations) - eligible_count
        if ranked:
            selected_evaluation, selected_assessment = ranked[0]
            decision = self._selected_decision(
                request,
                fingerprint,
                selected_evaluation,
                selected_assessment,
                eligible_count,
                rejected_count,
            )
        else:
            decision = self._no_selection_decision(
                request,
                fingerprint,
                evaluations,
                eligible_count,
                rejected_count,
            )

        try:
            stored, identical = self.repository.append_selection_decision(
                decision,
                evaluations,
            )
        except SelectionConflictError as exc:
            return self._failure(
                OfficialSelectionOutcomeStatus.CONFLICT,
                request.selection_request_identity,
                request.match_id,
                request.selection_timestamp,
                SelectionReason.REQUEST_IDENTITY_CONFLICT,
                str(exc),
            )
        except SelectionPersistenceError:
            return self._failure(
                OfficialSelectionOutcomeStatus.PERSISTENCE_FAILURE,
                request.selection_request_identity,
                request.match_id,
                request.selection_timestamp,
                SelectionReason.PERSISTENCE_FAILURE,
                "Selection decision persistence failed safely.",
            )
        status = (
            OfficialSelectionOutcomeStatus.IDEMPOTENT_EXISTING
            if identical
            else (
                OfficialSelectionOutcomeStatus.SELECTED
                if isinstance(stored.decision, SelectedOfficialPrediction)
                else OfficialSelectionOutcomeStatus.NO_SELECTION
            )
        )
        return self._outcome(stored.decision, status)

    def _selected_decision(
        self,
        request: OfficialPredictionSelectionCommand,
        request_identity_fingerprint: str,
        evaluation: AssessmentEligibilityEvaluation,
        assessment: MarketValueAssessment,
        eligible_count: int,
        rejected_count: int,
    ) -> SelectedOfficialPrediction:
        rank = 1
        fingerprint = selected_fingerprint(
            request_identity_fingerprint=request_identity_fingerprint,
            evaluation=evaluation,
            ranking_values=ranking_values(evaluation, assessment),
            selected_rank=rank,
            eligible_count=eligible_count,
            rejected_count=rejected_count,
            selection_policy_version=self.selection_policy.version,
            ranking_policy_version=self.ranking_policy.version,
        )
        return SelectedOfficialPrediction(
            selection_decision_id=selection_decision_id(fingerprint),
            selection_request_identity=request.selection_request_identity,
            selection_request_fingerprint=request_identity_fingerprint,
            match_id=request.match_id,
            kickoff_timestamp=request.kickoff_timestamp,
            selection_timestamp=request.selection_timestamp,
            selected_value_assessment_id=assessment.value_assessment_id,
            selected_assessment_fingerprint=assessment.assessment_fingerprint,
            source_provider=assessment.source_provider,
            bookmaker_id=assessment.bookmaker_id,
            logical_market_identity=evaluation.logical_market_identity,
            market_type=assessment.market_type,
            selection=assessment.selection,
            market_line=assessment.market_line,
            fair_probability=assessment.fair_probability,
            bookmaker_decimal_odds=assessment.bookmaker_decimal_odds,
            implied_probability=assessment.implied_probability,
            fair_decimal_odds=assessment.fair_decimal_odds,
            absolute_probability_edge=assessment.absolute_probability_edge,
            relative_probability_edge=assessment.relative_probability_edge,
            expected_value=assessment.expected_value,
            expected_return=assessment.expected_return,
            value_classification=assessment.value_classification,
            freshness=evaluation.freshness,
            source_model_artifact_id=assessment.source_model_artifact_id,
            source_model_version=assessment.source_model_version,
            inference_id=assessment.inference_id,
            model_input_id=assessment.model_input_id,
            source_snapshot_id=assessment.source_snapshot_id,
            feature_set_id=assessment.feature_set_id,
            calibrated_assembly_id=assessment.calibrated_assembly_id,
            calibration_set_id=assessment.calibration_set_id,
            calibration_set_fingerprint=assessment.calibration_set_fingerprint,
            source_calibrated_targets=assessment.source_calibrated_targets,
            odds_fingerprint=assessment.odds_fingerprint,
            calibrated_assembly_fingerprint=(
                assessment.calibrated_assembly_fingerprint
            ),
            value_policy_version=assessment.value_policy_version,
            selection_policy_version=self.selection_policy.version,
            ranking_policy_version=self.ranking_policy.version,
            selected_rank=rank,
            eligible_assessment_count=eligible_count,
            rejected_assessment_count=rejected_count,
            selection_fingerprint=fingerprint,
            ordered_reason_codes=(SelectionReason.SELECTED_HIGHEST_RANKED,),
            deterministic_decision_summary=(
                ("outcome", OfficialSelectionOutcomeStatus.SELECTED.value),
                ("selected_value_assessment_id", assessment.value_assessment_id),
                ("logical_market_identity", evaluation.logical_market_identity),
                ("eligible_count", str(eligible_count)),
                ("rejected_count", str(rejected_count)),
            ),
            created_timestamp=request.selection_timestamp,
        )

    def _no_selection_decision(
        self,
        request: OfficialPredictionSelectionCommand,
        request_identity_fingerprint: str,
        evaluations: tuple[AssessmentEligibilityEvaluation, ...],
        eligible_count: int,
        rejected_count: int,
    ) -> OfficialNoSelectionDecision:
        final_reason = SelectionReason.NO_ELIGIBLE_ASSESSMENTS
        counts = Counter(
            reason
            for evaluation in evaluations
            for reason in evaluation.ordered_rejection_reasons
        )
        counted_reasons = ordered_reasons(tuple(counts))
        rejection_counts = tuple((reason, counts[reason]) for reason in counted_reasons)
        reason_codes = (final_reason,) + tuple(
            reason for reason in counted_reasons if reason is not final_reason
        )
        fingerprint = no_selection_fingerprint(
            request_identity_fingerprint=request_identity_fingerprint,
            evaluations=evaluations,
            final_reason=final_reason,
            eligible_count=eligible_count,
            rejected_count=rejected_count,
            selection_policy_version=self.selection_policy.version,
            ranking_policy_version=self.ranking_policy.version,
        )
        return OfficialNoSelectionDecision(
            selection_decision_id=selection_decision_id(fingerprint),
            selection_request_identity=request.selection_request_identity,
            selection_request_fingerprint=request_identity_fingerprint,
            match_id=request.match_id,
            kickoff_timestamp=request.kickoff_timestamp,
            selection_timestamp=request.selection_timestamp,
            final_reason_code=final_reason,
            evaluation_summaries=evaluations,
            assessment_count=len(evaluations),
            eligible_assessment_count=eligible_count,
            rejected_assessment_count=rejected_count,
            rejection_reason_counts=rejection_counts,
            selection_policy_version=self.selection_policy.version,
            ranking_policy_version=self.ranking_policy.version,
            no_selection_fingerprint=fingerprint,
            ordered_reason_codes=reason_codes,
            deterministic_decision_summary=(
                ("outcome", OfficialSelectionOutcomeStatus.NO_SELECTION.value),
                ("assessment_count", str(len(evaluations))),
                ("eligible_count", str(eligible_count)),
                ("rejected_count", str(rejected_count)),
            ),
            created_timestamp=request.selection_timestamp,
        )

    def _outcome(
        self,
        decision: OfficialSelectionDecision,
        status: OfficialSelectionOutcomeStatus,
    ) -> OfficialPredictionSelectionOutcome:
        if isinstance(decision, SelectedOfficialPrediction):
            return OfficialPredictionSelectionOutcome(
                decision.selection_decision_id,
                decision.selection_request_identity,
                decision.match_id,
                decision.selected_value_assessment_id,
                decision.logical_market_identity,
                decision.bookmaker_decimal_odds,
                decision.fair_probability,
                decision.expected_value,
                status,
                decision.ordered_reason_codes,
                ("Official single-market selection decision persisted.",),
                decision.eligible_assessment_count,
                decision.rejected_assessment_count,
                decision.selection_fingerprint,
                decision.selection_timestamp,
                decision.selection_policy_version,
                decision,
            )
        return OfficialPredictionSelectionOutcome(
            decision.selection_decision_id,
            decision.selection_request_identity,
            decision.match_id,
            None,
            None,
            None,
            None,
            None,
            status,
            decision.ordered_reason_codes,
            ("No qualifying Official single-market assessment was selected.",),
            decision.eligible_assessment_count,
            decision.rejected_assessment_count,
            decision.no_selection_fingerprint,
            decision.selection_timestamp,
            decision.selection_policy_version,
            decision,
        )

    def _failure(
        self,
        status: OfficialSelectionOutcomeStatus,
        request_identity: str,
        match_id: str,
        selection_timestamp: datetime | None,
        reason: SelectionReason,
        explanation: str,
    ) -> OfficialPredictionSelectionOutcome:
        return OfficialPredictionSelectionOutcome(
            None,
            request_identity,
            match_id,
            None,
            None,
            None,
            None,
            None,
            status,
            (reason,),
            (explanation,),
            0,
            0,
            None,
            selection_timestamp,
            self.selection_policy.version,
            None,
        )


def select_official_prediction(
    service: OfficialPredictionSelectionService,
    command: OfficialPredictionSelectionCommand,
) -> OfficialPredictionSelectionOutcome:
    """Public deterministic selection boundary."""

    return service.select(command)


def _request_fingerprint(decision: OfficialSelectionDecision) -> str:
    return decision.selection_request_fingerprint
