from dataclasses import dataclass


@dataclass(slots=True)
class LeagueTable:

    team_id: int

    position: int

    played: int

    points: int

    wins: int

    draws: int

    losses: int

    goals_for: int

    goals_against: int

    goal_difference: int