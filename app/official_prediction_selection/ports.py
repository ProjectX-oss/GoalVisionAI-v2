"""Read-only and append-only service boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.market_value_assessment import MarketValueAssessment

from .models import (
    AssessmentEligibilityEvaluation,
    OfficialSelectionDecision,
    PublicationProtectionState,
    SelectionDecisionWithEvaluations,
)


class PersistedMarketValueAssessmentReader(Protocol):
    def load_market_value_assessment(
        self, value_assessment_id: str
    ) -> MarketValueAssessment | None: ...


class PublicationStateProtection(Protocol):
    def classify(
        self,
        logical_prediction_identity: str,
        match_id: str,
        evaluated_at: datetime,
    ) -> PublicationProtectionState: ...


class OfficialPredictionSelectionRepository(Protocol):
    def append_selection_decision(
        self,
        decision: OfficialSelectionDecision,
        evaluations: tuple[AssessmentEligibilityEvaluation, ...],
    ) -> tuple[SelectionDecisionWithEvaluations, bool]: ...

    def find_by_decision_fingerprint(
        self, decision_fingerprint: str
    ) -> OfficialSelectionDecision | None: ...

    def find_by_request_identity(
        self, request_identity: str
    ) -> OfficialSelectionDecision | None: ...

    def load_selection_decision(
        self, selection_decision_id: str
    ) -> OfficialSelectionDecision | None: ...

    def load_selection_with_evaluations(
        self, selection_decision_id: str
    ) -> SelectionDecisionWithEvaluations | None: ...

    def list_selection_decisions_for_match(
        self, match_id: str
    ) -> tuple[OfficialSelectionDecision, ...]: ...

    def list_selected_decisions(self) -> tuple[OfficialSelectionDecision, ...]: ...

    def list_no_selection_decisions(
        self,
    ) -> tuple[OfficialSelectionDecision, ...]: ...

    def find_latest_selection_for_match(
        self, match_id: str
    ) -> OfficialSelectionDecision | None: ...
