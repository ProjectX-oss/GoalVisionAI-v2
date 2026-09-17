from dataclasses import dataclass


@dataclass(slots=True)
class TeamStats:

    team_id: int

    league_id: int

    season: int

    played: int

    wins: int
    draws: int
    losses: int

    goals_for: int
    goals_against: int

    home_played: int
    home_wins: int
    home_draws: int
    home_losses: int

    away_played: int
    away_wins: int
    away_draws: int
    away_losses: int

    form: str