from dataclasses import dataclass


@dataclass(slots=True)
class Prediction:

    winner: str

    home_probability: float

    away_probability: float

    confidence: str

    rating_difference: float