from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class HistoryPrediction:

    fixture_id: int

    league: str

    home_team: str

    away_team: str

    predicted_winner: str

    home_probability: float

    away_probability: float

    confidence: str

    algorithm_version: str

    created_at: datetime