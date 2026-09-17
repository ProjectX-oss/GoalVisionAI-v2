"""Deterministic Official single-market selection boundary."""

from .exceptions import (
    InvalidSelectionRequestError,
    OfficialPredictionSelectionError,
    SelectionConflictError,
    SelectionMappingError,
    SelectionPersistenceError,
    SelectionProvenanceError,
    SelectionScopeError,
)
from .factory import build_official_prediction_selection_service
from .mapping import to_official_risk_handoff
from .models import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    AssessmentFreshnessSummary,
    OfficialNoSelectionDecision,
    OfficialPredictionSelectionCommand,
    OfficialPredictionSelectionOutcome,
    OfficialSelectionDecision,
    OfficialSelectionOutcomeStatus,
    OfficialSelectionRiskInput,
    PublicationProtectionState,
    SelectedOfficialPrediction,
    SelectionDecisionWithEvaluations,
    SelectionReason,
)
from .policy import (
    DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY,
    DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
    OfficialPredictionRankingPolicy,
    OfficialPredictionSelectionPolicy,
)
from .publication_state import CandidatePublicationStateProtectionAdapter
from .ports import OfficialPredictionSelectionRepository
from .repository import SQLiteOfficialPredictionSelectionRepository
from .service import (
    OfficialPredictionSelectionService,
    select_official_prediction,
)


__all__ = (
    "AssessmentEligibilityEvaluation",
    "AssessmentEligibilityStatus",
    "AssessmentFreshnessSummary",
    "CandidatePublicationStateProtectionAdapter",
    "DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY",
    "DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY",
    "InvalidSelectionRequestError",
    "OfficialNoSelectionDecision",
    "OfficialPredictionRankingPolicy",
    "OfficialPredictionSelectionCommand",
    "OfficialPredictionSelectionError",
    "OfficialPredictionSelectionOutcome",
    "OfficialPredictionSelectionPolicy",
    "OfficialPredictionSelectionRepository",
    "OfficialPredictionSelectionService",
    "OfficialSelectionDecision",
    "OfficialSelectionOutcomeStatus",
    "OfficialSelectionRiskInput",
    "PublicationProtectionState",
    "SQLiteOfficialPredictionSelectionRepository",
    "SelectedOfficialPrediction",
    "SelectionConflictError",
    "SelectionDecisionWithEvaluations",
    "SelectionMappingError",
    "SelectionPersistenceError",
    "SelectionProvenanceError",
    "SelectionReason",
    "SelectionScopeError",
    "build_official_prediction_selection_service",
    "select_official_prediction",
    "to_official_risk_handoff",
)
