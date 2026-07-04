from dataclasses import dataclass


@dataclass
class Match:
    fixture_id: int
    home_team: str
    away_team: str
    league: str
    date: str