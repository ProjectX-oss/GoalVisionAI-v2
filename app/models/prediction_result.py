from dataclasses import dataclass


@dataclass(slots=True)
class PredictionResult:

    fixture_id: int

    winner_correct: bool

    over25_correct: bool

    btts_correct: bool

    home_goals: int

    away_goals: int