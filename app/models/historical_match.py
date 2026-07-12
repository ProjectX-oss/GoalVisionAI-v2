from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class HistoricalMatch:

    fixture_id: int

    league_id: int

    season: int

    home_team_id: int
    away_team_id: int

    home_goals: int
    away_goals: int

    kickoff: datetime

    status: str