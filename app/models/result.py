from dataclasses import dataclass


@dataclass(slots=True)
class Result:

    fixture_id: int

    home_goals: int

    away_goals: int

    winner: str

    finished: bool