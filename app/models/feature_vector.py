from dataclasses import dataclass


@dataclass(slots=True)
class FeatureVector:

    team_id: int

    # Core
    form: float
    attack: float
    defense: float
    momentum: float

    # Venue
    home_strength: float
    away_strength: float

    # Results
    win_rate: float
    points_per_game: float

    # Goals
    goals_for: float
    goals_against: float
    goal_difference: float

    # League
    league_position: float

    # Recovery
    rest_days: float

    # Extra Features
    clean_sheet_rate: float
    failed_to_score_rate: float

    home_points_per_game: float
    away_points_per_game: float

    recent_goal_difference: float
    recent_points_per_game: float