from dataclasses import dataclass


@dataclass(slots=True)
class BacktestResult:

    matches: int

    correct: int

    accuracy: float

    high_confidence: int

    high_correct: int

    high_accuracy: float