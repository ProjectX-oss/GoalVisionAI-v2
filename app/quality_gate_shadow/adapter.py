from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.calibration import CalibrationScope
from app.models import Match
from app.pipeline import PredictionAssessment
from app.quality_gate import (
    EvidenceAssessment,
    EvidenceStatus,
    PublicationCandidate,
    QualityGateContext,
)

from .models import (
    ShadowAdaptation,
    ShadowEvaluationRequest,
    ShadowEvaluationStage,
)


CURRENTLY_UNAVAILABLE_CONTEXT_FIELDS = (
    "offered_odds",
    "odds_timestamp",
    "calibrated_probability",
    "calibration_method",
    "calibration_scope",
    "calibration_sample_size",
    "calibration_fit_timestamp",
    "calibration_training_cutoff",
    "model_version",
    "lineup_status",
    "injury_data_status",
    "market_consensus_probability",
    "market_disagreement",
    "exposure_limits_context",
    "model_sample_size",
)


@dataclass(frozen=True, slots=True)
class ShadowObservationFacts:
    offered_odds: Decimal
    odds_timestamp: datetime
    calibrated_probability: Decimal
    calibration_method: str
    calibration_scope: CalibrationScope
    calibration_sample_size: int
    calibration_fit_timestamp: datetime
    calibration_training_cutoff: datetime
    model_version: str
    confidence_score: Decimal | None
    uncertainty_score: Decimal | None
    reference_odds: Decimal | None
    expected_value: Decimal | None
    data_completeness_status: EvidenceStatus
    data_freshness_status: EvidenceStatus
    lineup_status: EvidenceStatus
    injury_data_status: EvidenceStatus
    market_consensus_probability: Decimal | None
    market_disagreement: Decimal | None
    current_exposure: Decimal
    daily_exposure: Decimal
    competition_exposure: Decimal
    correlated_exposure: Decimal
    sample_size: int
    context_calibration_sample_size: int
    evidence: tuple[EvidenceAssessment, ...]
    actually_published: bool = False
    actual_publication_timestamp: datetime | None = None
    actual_offered_odds: Decimal | None = None


class PredictionShadowContextAdapter:
    """Maps only supplied facts; current runtime omissions remain explicit."""

    def __init__(self, policy_version: str) -> None:
        self._policy_version = policy_version

    def adapt(
        self,
        match: Match,
        assessment: PredictionAssessment,
        observed_at: datetime,
        facts: ShadowObservationFacts | None = None,
        stage: ShadowEvaluationStage = ShadowEvaluationStage.INITIAL_CANDIDATE,
    ) -> ShadowAdaptation:
        if facts is None:
            return ShadowAdaptation(
                request=None,
                unavailable_fields=CURRENTLY_UNAVAILABLE_CONTEXT_FIELDS,
            )
        probability = self._selected_probability(match, assessment)
        prediction_id = self._prediction_id(match, assessment)
        candidate = PublicationCandidate(
            prediction_id=prediction_id,
            fixture_id=match.fixture_id,
            competition=match.league_name,
            kickoff_time=match.kickoff,
            prediction_timestamp=observed_at,
            market="Match Winner",
            selection=assessment.prediction.winner,
            raw_probability=probability,
            offered_odds=facts.offered_odds,
            odds_timestamp=facts.odds_timestamp,
            calibrated_probability=facts.calibrated_probability,
            reference_odds=facts.reference_odds,
            expected_value=facts.expected_value,
            model_version=facts.model_version,
            calibration_scope=facts.calibration_scope,
            calibration_method=facts.calibration_method,
            calibration_sample_size=facts.calibration_sample_size,
            calibration_fit_timestamp=facts.calibration_fit_timestamp,
            calibration_training_cutoff=facts.calibration_training_cutoff,
            confidence_score=facts.confidence_score,
            uncertainty_score=facts.uncertainty_score,
            product_scope="OFFICIAL",
        )
        context = QualityGateContext(
            evaluation_timestamp=observed_at,
            data_completeness_status=facts.data_completeness_status,
            data_freshness_status=facts.data_freshness_status,
            lineup_status=facts.lineup_status,
            injury_data_status=facts.injury_data_status,
            market_consensus_probability=facts.market_consensus_probability,
            market_disagreement=facts.market_disagreement,
            current_exposure=facts.current_exposure,
            daily_exposure=facts.daily_exposure,
            competition_exposure=facts.competition_exposure,
            correlated_exposure=facts.correlated_exposure,
            sample_size=facts.sample_size,
            calibration_sample_size=facts.context_calibration_sample_size,
            evidence=facts.evidence,
        )
        request = ShadowEvaluationRequest(
            shadow_evaluation_id=(
                f"shadow:{prediction_id}:{self._policy_version}:{stage.value}"
            ),
            stage=stage,
            candidate=candidate,
            context=context,
            policy_version=self._policy_version,
            actually_published=facts.actually_published,
            actual_publication_timestamp=facts.actual_publication_timestamp,
            actual_offered_odds=facts.actual_offered_odds,
            created_at=observed_at,
        )
        return ShadowAdaptation(request=request, unavailable_fields=())

    @staticmethod
    def _selected_probability(
        match: Match,
        assessment: PredictionAssessment,
    ) -> Decimal:
        percentage = (
            assessment.prediction.home_probability
            if assessment.prediction.winner == match.home_team_name
            else assessment.prediction.away_probability
        )
        return Decimal(str(percentage)) / Decimal("100")

    @staticmethod
    def _prediction_id(
        match: Match,
        assessment: PredictionAssessment,
    ) -> str:
        selection = "-".join(
            assessment.prediction.winner.strip().lower().split()
        )
        return f"official-{match.fixture_id}-match-winner-{selection}"
