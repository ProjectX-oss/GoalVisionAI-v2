"""Read-only handoff from a selected decision to future risk processing."""

from .exceptions import SelectionMappingError
from .models import OfficialSelectionRiskInput, SelectedOfficialPrediction


def to_official_risk_handoff(
    decision: SelectedOfficialPrediction,
) -> OfficialSelectionRiskInput:
    if not isinstance(decision, SelectedOfficialPrediction):
        raise SelectionMappingError(
            "Only a successful selected decision can map to risk processing."
        )
    return OfficialSelectionRiskInput(
        selection_decision_id=decision.selection_decision_id,
        selected_value_assessment_id=decision.selected_value_assessment_id,
        match_id=decision.match_id,
        kickoff_timestamp=decision.kickoff_timestamp,
        logical_market_identity=decision.logical_market_identity,
        market_type=decision.market_type,
        selection=decision.selection,
        market_line=decision.market_line,
        source_provider=decision.source_provider,
        bookmaker_id=decision.bookmaker_id,
        fair_probability=decision.fair_probability,
        bookmaker_decimal_odds=decision.bookmaker_decimal_odds,
        implied_probability=decision.implied_probability,
        fair_decimal_odds=decision.fair_decimal_odds,
        expected_value=decision.expected_value,
        absolute_probability_edge=decision.absolute_probability_edge,
        relative_probability_edge=decision.relative_probability_edge,
        value_classification=decision.value_classification,
        freshness=decision.freshness,
        source_model_artifact_id=decision.source_model_artifact_id,
        source_model_version=decision.source_model_version,
        inference_id=decision.inference_id,
        calibrated_assembly_id=decision.calibrated_assembly_id,
        calibration_set_id=decision.calibration_set_id,
        calibration_set_fingerprint=decision.calibration_set_fingerprint,
        odds_fingerprint=decision.odds_fingerprint,
        calibrated_assembly_fingerprint=(
            decision.calibrated_assembly_fingerprint
        ),
        assessment_fingerprint=decision.selected_assessment_fingerprint,
        selection_fingerprint=decision.selection_fingerprint,
        selection_policy_version=decision.selection_policy_version,
        ranking_policy_version=decision.ranking_policy_version,
    )
