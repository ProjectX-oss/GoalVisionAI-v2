from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Match:
    fixture_id: int

    league_id: int
    league_name: str
    season: int

    home_team_id: int
    home_team_name: str

    away_team_id: int
    away_team_name: str

    kickoff: datetime

    status: str