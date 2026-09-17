from dataclasses import dataclass


@dataclass(slots=True)
class TeamRating:

    form: float

    attack: float

    defense: float

    momentum: float

    total: float