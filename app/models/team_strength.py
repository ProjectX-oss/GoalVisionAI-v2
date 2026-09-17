from dataclasses import dataclass


@dataclass(slots=True)
class TeamStrength:

    # Core
    attack: float
    defense: float
    form: float
    momentum: float

    # Venue
    home: float
    away: float

    # Goals
    goal_difference: float

    # Defensive quality
    clean_sheet: float

    # Offensive stability
    failed_to_score: float

    # Season strength
    league_position: float

    # Performance
    home_points: float
    away_points: float

    # Recent trend
    recent_goal_difference: float
    recent_points: float