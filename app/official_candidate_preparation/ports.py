"""Injected read-only, execution, registration, and append-only boundaries."""

from __future__ import annotations

from typing import Protocol

from app.market_value_assessment import MarketValueAssessment
from app.official_prediction_candidate_registry import (
    CandidateLifecycleState,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionCandidateRegistrationOutcome,
    OfficialPredictionCandidateVersion,
)
from app.official_prediction_selection import SelectionDecisionWithEvaluations
from app.risk_management import (
    RiskAssessmentContext,
    RiskAssessmentRequest,
    RiskAuditRecord,
)

from .models import (
    OfficialCandidatePreparationExecution,
    OfficialCandidatePreparationRiskSnapshot,
    PreparationExecutionWithRiskSnapshot,
)


class SelectionHistoryReader(Protocol):
    def load_selection_with_evaluations(
        self, selection_decision_id: str
    ) -> SelectionDecisionWithEvaluations | None: ...


class ValueAssessmentHistoryReader(Protocol):
    def load_market_value_assessment(
        self, value_assessment_id: str
    ) -> MarketValueAssessment | None: ...


class OfficialRiskAssessmentPort(Protocol):
    def assess(
        self,
        request: RiskAssessmentRequest,
        context: RiskAssessmentContext,
    ) -> RiskAuditRecord: ...


class OfficialCandidateRegistryPort(Protocol):
    def register_candidate(
        self,
        command: OfficialPredictionCandidateRegistrationCommand,
    ) -> OfficialPredictionCandidateRegistrationOutcome: ...


class CandidateLifecycleReader(Protocol):
    def find_candidate_by_id(
        self, registry_candidate_id: str
    ) -> OfficialPredictionCandidateVersion | None: ...

    def current_state(
        self, registry_candidate_id: str
    ) -> CandidateLifecycleState | None: ...


class OfficialCandidatePreparationRepository(Protocol):
    def append_preparation_execution(
        self,
        execution: OfficialCandidatePreparationExecution,
        risk_snapshot: OfficialCandidatePreparationRiskSnapshot | None,
    ) -> tuple[PreparationExecutionWithRiskSnapshot, bool]: ...

    def find_by_integration_fingerprint(
        self, integration_fingerprint: str
    ) -> OfficialCandidatePreparationExecution | None: ...

    def find_by_request_identity(
        self, request_identity: str
    ) -> OfficialCandidatePreparationExecution | None: ...

    def load_preparation_execution(
        self, integration_execution_id: str
    ) -> OfficialCandidatePreparationExecution | None: ...

    def load_execution_with_risk_snapshot(
        self, integration_execution_id: str
    ) -> PreparationExecutionWithRiskSnapshot | None: ...

    def list_executions_for_selection(
        self, selection_decision_id: str
    ) -> tuple[OfficialCandidatePreparationExecution, ...]: ...

    def list_executions_for_match(
        self, match_id: str
    ) -> tuple[OfficialCandidatePreparationExecution, ...]: ...

    def list_registered_candidates(
        self,
    ) -> tuple[OfficialCandidatePreparationExecution, ...]: ...

    def list_no_registration_decisions(
        self,
    ) -> tuple[OfficialCandidatePreparationExecution, ...]: ...

    def find_latest_for_selection(
        self, selection_decision_id: str
    ) -> OfficialCandidatePreparationExecution | None: ...
