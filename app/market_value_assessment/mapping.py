"""Read-only handoff to a future Official Prediction Selection Engine."""

from .exceptions import NonActionableMappingError
from .models import (
    ActionabilityStatus,
    FutureOfficialSelectionInput,
    MarketValueAssessment,
)


def to_future_official_selection_input(
    assessment: MarketValueAssessment,
) -> FutureOfficialSelectionInput:
    if (
        not isinstance(assessment, MarketValueAssessment)
        or assessment.actionability_status is not ActionabilityStatus.ACTIONABLE
    ):
        raise NonActionableMappingError(
            "Only actionable assessments map downstream."
        )
    return FutureOfficialSelectionInput(
        value_assessment_id=assessment.value_assessment_id,
        calibrated_assembly_id=assessment.calibrated_assembly_id,
        match_id=assessment.match_id,
        kickoff_timestamp=assessment.kickoff_timestamp,
        market_type=assessment.market_type,
        selection=assessment.selection,
        market_line=assessment.market_line,
        fair_probability=assessment.fair_probability,
        bookmaker_odds=assessment.bookmaker_decimal_odds,
        implied_probability=assessment.implied_probability,
        fair_odds=assessment.fair_decimal_odds,
        expected_value=assessment.expected_value,
        absolute_edge=assessment.absolute_probability_edge,
        relative_edge=assessment.relative_probability_edge,
        value_classification=assessment.value_classification,
        freshness=assessment.overall_freshness,
        source_provider=assessment.source_provider,
        bookmaker_id=assessment.bookmaker_id,
        source_model_artifact_id=assessment.source_model_artifact_id,
        source_model_version=assessment.source_model_version,
        calibration_set_id=assessment.calibration_set_id,
        calibration_set_fingerprint=assessment.calibration_set_fingerprint,
        calibrated_assembly_fingerprint=(
            assessment.calibrated_assembly_fingerprint
        ),
        odds_fingerprint=assessment.odds_fingerprint,
        assessment_fingerprint=assessment.assessment_fingerprint,
    )
