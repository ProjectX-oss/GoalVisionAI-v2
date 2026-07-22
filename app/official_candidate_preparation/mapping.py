"""Explicit adapters into risk, registry, and downstream Quality Gate facts."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.market_value_assessment import MarketSelection
from app.official_prediction_candidate_registry import (
    CandidateLifecycleState,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionCandidateVersion,
)
from app.official_prediction_orchestration import (
    BankrollScopeRecord,
    ExposureEvaluationRecord,
    RiskEvaluationRecord,
)
from app.official_prediction_selection import to_official_risk_handoff
from app.publication_quality_gate import ExposureDecision
from app.risk_management import (
    DEFAULT_OFFICIAL_RISK_POLICY,
    RiskAssessmentContext,
    RiskAssessmentDecision,
    RiskAssessmentPhase,
    RiskAssessmentRequest,
    RiskAuditRecord,
    RiskProductScope,
)

from .exceptions import CandidatePreparationMappingError
from .fingerprint import (
    candidate_facts_fingerprint,
    candidate_mapping_fingerprint,
    preparation_request_fingerprint,
    risk_handoff_fingerprint,
    risk_result_fingerprint,
)
from .models import (
    CandidatePreparationStatus,
    OfficialCandidatePreparationExecution,
    OfficialCandidatePreparationRiskSnapshot,
    OfficialCandidateQualityGateHandoff,
    PreparedOfficialCandidateRegistration,
    PreparedOfficialRiskHandoff,
)
from .policy import OfficialCandidatePreparationPolicy
from .validation import ValidatedCandidatePreparation


_SELECTION_NAMES = {
    MarketSelection.HOME: "HOME",
    MarketSelection.DRAW: "DRAW",
    MarketSelection.AWAY: "AWAY",
    MarketSelection.HOME_DRAW: "HOME OR DRAW",
    MarketSelection.HOME_AWAY: "HOME OR AWAY",
    MarketSelection.DRAW_AWAY: "AWAY OR DRAW",
    MarketSelection.OVER: "OVER",
    MarketSelection.UNDER: "UNDER",
    MarketSelection.YES: "YES",
    MarketSelection.NO: "NO",
}


def map_selection_to_risk(
    value: ValidatedCandidatePreparation,
    policy: OfficialCandidatePreparationPolicy,
) -> PreparedOfficialRiskHandoff:
    """Map verified selected facts into the existing pure risk boundary."""

    command = value.command
    selection = value.selection
    facts = command.candidate_facts
    risk_input = to_official_risk_handoff(selection)
    request = RiskAssessmentRequest(
        prediction_id=selection.selection_decision_id,
        fixture_id=facts.fixture_id,
        competition=facts.competition_name,
        market=selection.market_type.value,
        selection=_SELECTION_NAMES[selection.selection],
        product_scope=RiskProductScope.OFFICIAL,
        prediction_timestamp=selection.selection_timestamp,
        kickoff=selection.kickoff_timestamp,
        accepted_probability=selection.fair_probability,
        offered_odds=selection.bookmaker_decimal_odds,
        expected_value=selection.expected_value,
        quality_gate_status=None,
        model_confidence=facts.model_confidence,
        uncertainty=facts.uncertainty,
        calibration_sample_size=facts.calibration_sample_size,
        model_sample_size=facts.model_sample_size,
        correlation_group_ids=tuple(
            item.group_id for item in facts.correlation_groups
        ),
        requested_stake=None,
        candidate_policy_version=policy.version,
        calibrated_probability_available=True,
        team_ids=facts.team_ids,
        market_family=facts.market_family,
        assessment_phase=RiskAssessmentPhase.PRE_PUBLICATION_GATE,
    )
    context = RiskAssessmentContext(
        bankroll=command.bankroll.state,
        exposure=command.exposure.snapshot,
        correlation_groups=facts.correlation_groups,
        assessed_at=command.risk_assessment_timestamp,
    )
    prepared = PreparedOfficialRiskHandoff(
        selection=risk_input,
        request=request,
        context=context,
        bankroll_snapshot_identity=command.bankroll.snapshot_identity,
        bankroll_fingerprint=command.bankroll.fingerprint,
        available_bankroll=command.bankroll.available_bankroll,
        reserved_exposure=command.bankroll.reserved_exposure,
        exposure_snapshot_identity=command.exposure.snapshot_identity,
        exposure_fingerprint=command.exposure.fingerprint,
        handoff_fingerprint="",
    )
    return replace(
        prepared,
        handoff_fingerprint=risk_handoff_fingerprint(prepared),
    )


def validate_risk_result(
    audit: RiskAuditRecord,
    handoff: PreparedOfficialRiskHandoff,
    policy: OfficialCandidatePreparationPolicy,
) -> str:
    """Reject malformed or identity-incompatible responses from the risk port."""

    if not isinstance(audit, RiskAuditRecord):
        raise CandidatePreparationMappingError("Risk service returned an unsupported result.")
    recommendation = audit.recommendation
    expected = (
        audit.prediction_id == handoff.request.prediction_id
        and audit.product_scope is RiskProductScope.OFFICIAL
        and audit.policy_version == policy.risk_policy_version
        and audit.bankroll_snapshot == handoff.context.bankroll
        and audit.exposure_snapshot == handoff.context.exposure
        and audit.quality_gate_status is None
        and audit.assessed_at == handoff.context.assessed_at
        and audit.assessment_phase is RiskAssessmentPhase.PRE_PUBLICATION_GATE
        and isinstance(audit.final_decision, RiskAssessmentDecision)
    )
    if not expected:
        raise CandidatePreparationMappingError("Risk result provenance is incompatible.")
    if audit.final_decision in {
        RiskAssessmentDecision.ELIGIBLE,
        RiskAssessmentDecision.REDUCED_STAKE,
    }:
        if recommendation is None:
            raise CandidatePreparationMappingError(
                "Eligible risk result lacks a stake recommendation."
            )
        percentage = recommendation.internal_stake_percentage
        if (
            recommendation.currency != policy.currency
            or not all(
                isinstance(item, Decimal) and item.is_finite()
                for item in (
                    recommendation.unquantized_stake,
                    recommendation.final_stake,
                    percentage,
                )
            )
            or not (
                DEFAULT_OFFICIAL_RISK_POLICY.minimum_stake_percentage
                <= percentage
                <= DEFAULT_OFFICIAL_RISK_POLICY.maximum_stake_percentage
            )
            or recommendation.final_stake <= 0
            or recommendation.final_stake > handoff.context.bankroll.current_bankroll
            or recommendation.final_stake > handoff.available_bankroll
        ):
            raise CandidatePreparationMappingError("Risk stake recommendation is malformed.")
    elif audit.final_decision is RiskAssessmentDecision.INELIGIBLE:
        if recommendation is not None:
            raise CandidatePreparationMappingError(
                "Ineligible risk result must not recommend a stake."
            )
    return risk_result_fingerprint(audit)


def map_risk_to_candidate(
    value: ValidatedCandidatePreparation,
    handoff: PreparedOfficialRiskHandoff,
    audit: RiskAuditRecord,
    risk_fingerprint: str,
) -> PreparedOfficialCandidateRegistration:
    """Preserve selected, risk, stake, bankroll, and exposure provenance."""

    selection = value.selection
    command = value.command
    facts = command.candidate_facts
    recommendation = audit.recommendation
    if recommendation is None or audit.final_decision not in {
        RiskAssessmentDecision.ELIGIBLE,
        RiskAssessmentDecision.REDUCED_STAKE,
    }:
        raise CandidatePreparationMappingError(
            "Only an eligible risk result can map to candidate registration."
        )
    provenance = (
        ("assessment_fingerprint", selection.selected_assessment_fingerprint),
        ("bankroll_fingerprint", command.bankroll.fingerprint),
        ("bankroll_snapshot_identity", command.bankroll.snapshot_identity),
        ("bankroll_available_amount", str(command.bankroll.available_bankroll)),
        ("bankroll_currency", command.bankroll.state.currency),
        ("bankroll_current_amount", str(command.bankroll.state.current_bankroll)),
        ("bankroll_reserved_exposure", str(command.bankroll.reserved_exposure)),
        ("calibrated_assembly_fingerprint", selection.calibrated_assembly_fingerprint),
        ("calibrated_assembly_id", selection.calibrated_assembly_id),
        ("calibration_set_fingerprint", selection.calibration_set_fingerprint),
        ("calibration_set_id", selection.calibration_set_id or "none"),
        ("candidate_preparation_policy", command.integration_policy_version),
        ("candidate_facts_fingerprint", candidate_facts_fingerprint(facts)),
        ("exposure_fingerprint", command.exposure.fingerprint),
        (
            "exposure_decision",
            "WARNING" if audit.limiting_exposure is not None else "CLEAR",
        ),
        ("exposure_snapshot_identity", command.exposure.snapshot_identity),
        ("fair_decimal_odds", str(selection.fair_decimal_odds)),
        ("fair_probability", str(selection.fair_probability)),
        ("feature_set_id", selection.feature_set_id),
        ("freshness_calibrated", selection.freshness.calibrated_freshness.value),
        ("freshness_odds", selection.freshness.odds_freshness.value),
        ("freshness_overall", selection.freshness.overall_freshness.value),
        ("implied_probability", str(selection.implied_probability)),
        ("inference_id", selection.inference_id),
        ("integration_request_identity", command.integration_request_identity),
        ("metadata_version", command.metadata_version),
        ("model_input_id", selection.model_input_id),
        ("bookmaker_id", selection.bookmaker_id),
        ("odds_fingerprint", selection.odds_fingerprint),
        ("odds_record_id", value.assessment.odds_record_id),
        ("probability_edge_absolute", str(selection.absolute_probability_edge)),
        ("probability_edge_relative", str(selection.relative_probability_edge)),
        (
            "preparation_request_fingerprint",
            preparation_request_fingerprint(command),
        ),
        ("ranking_policy_version", selection.ranking_policy_version),
        ("risk_assessment_id", audit.assessment_id),
        ("risk_decision", audit.final_decision.value),
        ("risk_fingerprint", risk_fingerprint),
        ("risk_handoff_fingerprint", handoff.handoff_fingerprint),
        ("risk_policy_version", audit.policy_version),
        (
            "risk_reason_codes",
            ",".join(item.value for item in audit.ordered_reasons) or "none",
        ),
        (
            "risk_warning_codes",
            ",".join(item.value for item in audit.ordered_warnings) or "none",
        ),
        ("selection_decision_id", selection.selection_decision_id),
        ("selection_fingerprint", selection.selection_fingerprint),
        ("selection_policy_version", selection.selection_policy_version),
        ("selection_request_identity", selection.selection_request_identity),
        ("selected_rank", str(selection.selected_rank)),
        ("selected_value_assessment_id", selection.selected_value_assessment_id),
        ("source_model_artifact_id", selection.source_model_artifact_id),
        ("source_provider", selection.source_provider),
        *(
            (("source_run_identity", command.source_run_identity),)
            if command.source_run_identity is not None
            else ()
        ),
        ("source_snapshot_id", selection.source_snapshot_id),
        ("stake_amount", str(recommendation.final_stake)),
        ("stake_band", recommendation.band.value),
        ("stake_currency", recommendation.currency),
        ("stake_internal_percentage", str(recommendation.internal_stake_percentage)),
        ("value_classification", selection.value_classification.value),
        ("value_expected_return", str(selection.expected_return)),
        *(
            (("model_name", facts.model_name),)
            if facts.model_name is not None
            else ()
        ),
        *(
            (
                (
                    "calibration_artifact_references",
                    ",".join(facts.calibration_artifact_references),
                ),
            )
            if facts.calibration_artifact_references
            else ()
        ),
        *command.metadata,
    )
    registry_command = OfficialPredictionCandidateRegistrationCommand(
        source_event_id=facts.source_event_id,
        prediction_id=selection.selection_decision_id,
        match_id=selection.match_id,
        competition_id=facts.competition_id,
        competition_name=facts.competition_name,
        home_team_id=facts.home_team_id,
        home_team_name=facts.home_team_name,
        away_team_id=facts.away_team_id,
        away_team_name=facts.away_team_name,
        kickoff_timestamp=selection.kickoff_timestamp,
        prediction_creation_timestamp=selection.selection_timestamp,
        model_version=selection.source_model_version,
        market_type=selection.market_type.value,
        selection=_SELECTION_NAMES[selection.selection],
        market_line=selection.market_line,
        raw_model_probability=facts.raw_model_probability,
        supplied_expected_value=selection.expected_value,
        decimal_odds=selection.bookmaker_decimal_odds,
        odds_timestamp=value.evaluation.freshness.odds_effective_timestamp,
        odds_source_id=facts.odds_source_id,
        core_match_data_timestamp=facts.core_match_data_timestamp,
        lineup_status=facts.lineup_status,
        lineup_data_timestamp=facts.lineup_data_timestamp,
        injury_suspension_status=facts.injury_suspension_status,
        injury_suspension_data_timestamp=facts.injury_suspension_data_timestamp,
        confidence_level=facts.confidence_level,
        public_reasoning_facts=facts.public_reasoning_facts,
        source_data_version=facts.source_data_version,
        supporting_data_status=facts.supporting_data_status,
        market_availability=facts.market_availability,
        bankroll_scope=RiskProductScope.OFFICIAL,
        destination_scope=RiskProductScope.OFFICIAL,
        registration_timestamp=command.candidate_preparation_timestamp,
        provenance=tuple(sorted(provenance)),
    )
    prepared = PreparedOfficialCandidateRegistration(registry_command, "")
    return replace(
        prepared,
        candidate_mapping_fingerprint=candidate_mapping_fingerprint(prepared),
    )


def map_to_quality_gate_handoff(
    candidate: OfficialPredictionCandidateVersion,
    lifecycle_state: CandidateLifecycleState,
    execution: OfficialCandidatePreparationExecution,
    risk_snapshot: OfficialCandidatePreparationRiskSnapshot,
) -> OfficialCandidateQualityGateHandoff:
    """Create typed downstream facts without running the Quality Gate."""

    required = {
        "assessment_fingerprint",
        "risk_assessment_id",
        "risk_fingerprint",
        "selection_decision_id",
        "selection_fingerprint",
        "stake_amount",
        "stake_internal_percentage",
    }
    provenance = dict(candidate.prepared.provenance)
    if (
        lifecycle_state is not CandidateLifecycleState.READY
        or execution.registry_candidate_id != candidate.registry_candidate_id
        or execution.candidate_fingerprint != candidate.content_fingerprint
        or execution.final_status not in {
            CandidatePreparationStatus.CANDIDATE_REGISTERED,
            CandidatePreparationStatus.IDEMPOTENT_EXISTING,
        }
        or not required.issubset(provenance)
        or provenance["risk_assessment_id"] != risk_snapshot.audit.assessment_id
    ):
        raise CandidatePreparationMappingError(
            "Registered candidate is not a valid READY Quality Gate handoff."
        )
    prepared = candidate.prepared
    decision = risk_snapshot.audit.final_decision
    return OfficialCandidateQualityGateHandoff(
        candidate=candidate,
        lifecycle_state=lifecycle_state,
        execution=execution,
        risk_snapshot=risk_snapshot,
        risk_evaluation=RiskEvaluationRecord(
            evaluation_id=risk_snapshot.audit.assessment_id,
            prediction_id=prepared.prediction_id,
            match_id=prepared.match_id,
            model_version=prepared.model_version,
            market=prepared.market_identity.market.value,
            selection=prepared.market_identity.selection,
            market_line=prepared.market_identity.market_line,
            bankroll_scope=RiskProductScope.OFFICIAL,
            decision=decision,
            evaluated_at=risk_snapshot.audit.assessed_at,
        ),
        exposure_evaluation=ExposureEvaluationRecord(
            evaluation_id=risk_snapshot.risk_snapshot_id + "-exposure",
            prediction_id=prepared.prediction_id,
            match_id=prepared.match_id,
            model_version=prepared.model_version,
            market=prepared.market_identity.market.value,
            selection=prepared.market_identity.selection,
            market_line=prepared.market_identity.market_line,
            bankroll_scope=RiskProductScope.OFFICIAL,
            decision=(
                ExposureDecision.WARNING
                if risk_snapshot.audit.limiting_exposure is not None
                else ExposureDecision.CLEAR
            ),
            evaluated_at=risk_snapshot.audit.assessed_at,
        ),
        bankroll=BankrollScopeRecord(
            reference_id=execution.bankroll_snapshot_identity,
            product_scope=RiskProductScope.OFFICIAL,
            snapshot_timestamp=risk_snapshot.audit.bankroll_snapshot.snapshot_timestamp,
        ),
    )
