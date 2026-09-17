from dataclasses import dataclass


@dataclass(slots=True)
class FormSnapshot:

    team_id: int

    games: int

    wins: int
    draws: int
    losses: int

    goals_for: int
    goals_against: int

    goal_difference: int

    home_games: int
    away_games: int

    home_wins: int
    home_draws: int
    home_losses: int

    away_wins: int
    away_draws: int
    away_losses: int

    clean_sheets: int
    failed_to_score: int

    points: int

    attack: float
    defense: float

    win_rate: float

    momentum: float