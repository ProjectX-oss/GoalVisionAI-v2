from dataclasses import dataclass

from app.models import HistoricalMatch, Prediction, TeamContext
from app.quality_score import QualityScoreResult, QualitySignals


@dataclass(frozen=True, slots=True)
class PredictionSupportingData:
    h2h_history: tuple[HistoricalMatch, ...] | None = None
    rest_history: tuple[HistoricalMatch, ...] | None = None
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PredictionAssessment:
    prediction: Prediction
    quality_score: QualityScoreResult
    home_context: TeamContext
    away_context: TeamContext
    quality_signals: QualitySignals
    reason_codes: tuple[str, ...] = ()
    supporting_metadata: tuple[tuple[str, str], ...] = ()
