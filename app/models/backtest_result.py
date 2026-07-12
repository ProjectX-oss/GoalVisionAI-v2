from dataclasses import dataclass


@dataclass(slots=True)
class BacktestResult:

    total_matches: int

    winner_correct: int

    winner_accuracy: float

    over25_correct: int

    over25_accuracy: float

    btts_correct: int

    btts_accuracy: float