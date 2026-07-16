from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.quality_gate import (
    PublicationCandidate,
    PublicationType,
    QualityGateDecision,
    QualityGateStatus,
)
from app.quality_gate_shadow import ShadowEvaluationRecord

from .engine import RiskAssessmentService
from .models import (
    BankrollStateSnapshot,
    ComboExceptionAssessment,
    ExposureSnapshot,
    PublicStakeRecommendation,
    RiskAssessmentContext,
    RiskAssessmentDecision,
    RiskAssessmentRequest,
    RiskAuditRecord,
    RiskProductScope,
    RiskReason,
    ShadowRiskRecommendation,
    StakeBand,
    UnsupportedRiskProductPolicy,
)


class QualityGateRiskAdapter:
    """Consumes an existing gate decision without evaluating gate rules."""

    @staticmethod
    def apply(
        request: RiskAssessmentRequest,
        decision: QualityGateDecision | None,
    ) -> RiskAssessmentRequest:
        if decision is None:
            return replace(request, quality_gate_status=None)
        if decision.candidate_id != request.prediction_id:
            raise ValueError("Quality Gate decision does not match the risk request.")
        return replace(
            request,
            quality_gate_status=decision.status,
            accepted_probability=(
                decision.evaluated_probability
                if decision.evaluated_probability is not None
                else request.accepted_probability
            ),
            expected_value=(
                decision.expected_value
                if decision.expected_value is not None
                else request.expected_value
            ),
            candidate_policy_version=decision.policy_version,
        )

    @staticmethod
    def from_candidate(
        candidate: PublicationCandidate,
        decision: QualityGateDecision | None,
        *,
        model_sample_size: int,
        correlation_group_ids: tuple[str, ...] = (),
        requested_stake: Decimal | None = None,
        team_ids: tuple[str, ...] = (),
        market_family: str | None = None,
    ) -> RiskAssessmentRequest:
        request = RiskAssessmentRequest(
            prediction_id=candidate.prediction_id,
            fixture_id=candidate.fixture_id,
            competition=candidate.competition,
            market=candidate.market,
            selection=candidate.selection,
            product_scope=RiskProductScope(candidate.product_scope),
            prediction_timestamp=candidate.prediction_timestamp,
            kickoff=candidate.kickoff_time,
            accepted_probability=(
                candidate.calibrated_probability
                if candidate.calibrated_probability is not None
                else candidate.raw_probability
            ),
            offered_odds=candidate.offered_odds,
            expected_value=candidate.expected_value or Decimal("0"),
            quality_gate_status=None,
            model_confidence=candidate.confidence_score,
            uncertainty=candidate.uncertainty_score,
            calibration_sample_size=candidate.calibration_sample_size or 0,
            model_sample_size=model_sample_size,
            correlation_group_ids=correlation_group_ids,
            requested_stake=requested_stake,
            candidate_policy_version=(
                decision.policy_version if decision else "quality-gate-unavailable"
            ),
            calibrated_probability_available=(
                candidate.calibrated_probability is not None
            ),
            team_ids=team_ids,
            market_family=market_family,
        )
        return QualityGateRiskAdapter.apply(request, decision)


class PublicStakeAdapter:
    """Telegram-facing shape intentionally excludes internal stake percentage."""

    @staticmethod
    def adapt(audit: RiskAuditRecord) -> PublicStakeRecommendation | None:
        recommendation = audit.recommendation
        if recommendation is None or recommendation.public_stars is None:
            return None
        return PublicStakeRecommendation(
            prediction_id=audit.prediction_id,
            decision=audit.final_decision,
            stake_band=recommendation.band,
            stake_amount=recommendation.final_stake,
            currency=recommendation.currency,
            public_stars=recommendation.public_stars,
            reason_codes=tuple(item.value for item in audit.ordered_reasons),
        )


class ComboExceptionRiskService:
    """Represents eligibility only; it never creates a combo."""

    def evaluate(
        self,
        candidate: PublicationCandidate,
        *,
        exception_already_used: bool,
        confidence_threshold: Decimal = Decimal("0.75"),
    ) -> ComboExceptionAssessment:
        selections = candidate.combo_selections
        combined_odds = Decimal("1")
        for item in selections:
            combined_odds *= item.offered_odds
        eligible = (
            candidate.publication_type is PublicationType.COMBO
            and len(selections) == 2
            and all(item.offered_odds < Decimal("1.60") for item in selections)
            and combined_odds >= Decimal("2.00")
            and all(
                item.confidence_score >= confidence_threshold for item in selections
            )
            and not exception_already_used
        )
        return ComboExceptionAssessment(
            eligible=eligible,
            selection_count=len(selections),
            combined_odds=combined_odds,
            separate_exposure_required=True,
            reason=None if eligible else RiskReason.COMBO_EXCEPTION_NOT_ELIGIBLE,
        )


@runtime_checkable
class HistoricalBankrollSnapshotProvider(Protocol):
    def at(
        self,
        product_scope: RiskProductScope,
        timestamp,
    ) -> BankrollStateSnapshot | None: ...


@runtime_checkable
class HistoricalExposureSnapshotProvider(Protocol):
    def at(
        self,
        product_scope: RiskProductScope,
        timestamp,
    ) -> ExposureSnapshot | None: ...


@runtime_checkable
class CorrelationEstimator(Protocol):
    def group_ids_for(self, request: RiskAssessmentRequest) -> tuple[str, ...]: ...


class SuppliedCorrelationEstimator:
    def group_ids_for(self, request: RiskAssessmentRequest) -> tuple[str, ...]:
        return request.correlation_group_ids


class ShadowRiskRecommendationAdapter:
    def __init__(
        self,
        service: RiskAssessmentService,
        bankrolls: HistoricalBankrollSnapshotProvider,
        exposures: HistoricalExposureSnapshotProvider,
    ) -> None:
        self._service = service
        self._bankrolls = bankrolls
        self._exposures = exposures

    def assess(
        self,
        record: ShadowEvaluationRecord,
        *,
        model_sample_size: int,
        correlation_group_ids: tuple[str, ...] = (),
    ) -> ShadowRiskRecommendation:
        scope = RiskProductScope(record.product_scope)
        bankroll = self._bankrolls.at(scope, record.evaluation_timestamp)
        exposure = self._exposures.at(scope, record.evaluation_timestamp)
        if (
            bankroll is None
            or exposure is None
            or bankroll.snapshot_timestamp > record.evaluation_timestamp
            or exposure.snapshot_timestamp > record.evaluation_timestamp
        ):
            return ShadowRiskRecommendation(
                False,
                record.shadow_evaluation_id,
                record.policy_version,
                None,
                RiskReason.NO_HISTORICAL_BANKROLL_SNAPSHOT,
            )
        request = QualityGateRiskAdapter.from_candidate(
            record.candidate_snapshot,
            _shadow_decision(record),
            model_sample_size=model_sample_size,
            correlation_group_ids=correlation_group_ids,
        )
        audit = self._service.assess(
            request,
            RiskAssessmentContext(
                bankroll,
                exposure,
                (),
                record.evaluation_timestamp,
            ),
        )
        return ShadowRiskRecommendation(
            True,
            record.shadow_evaluation_id,
            audit.policy_version,
            audit,
            None,
        )


class RiskPolicyRegistry:
    def __init__(self, services: tuple[tuple[RiskProductScope, RiskAssessmentService], ...]):
        self._services = dict(services)

    def for_scope(self, scope: RiskProductScope) -> RiskAssessmentService:
        try:
            return self._services[scope]
        except KeyError as exc:
            raise UnsupportedRiskProductPolicy(
                f"No explicit risk policy is configured for {scope.value}."
            ) from exc


def _shadow_decision(record: ShadowEvaluationRecord) -> QualityGateDecision:
    return QualityGateDecision(
        candidate_id=record.prediction_id,
        status=record.gate_status,
        checks=record.ordered_check_results,
        rejection_reasons=record.rejection_reasons,
        review_reasons=record.review_reasons,
        evaluated_probability=record.evaluated_probability,
        probability_source=record.probability_source,
        expected_value=record.calculated_expected_value,
        market_disagreement=record.market_disagreement,
        policy_version=record.policy_version,
        evaluation_timestamp=record.evaluation_timestamp,
    )
