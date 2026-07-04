from app.core.leagues import TOP_LEAGUES
from app.football.client import FootballClient
from app.models.match import Match


class FootballService:

    def __init__(self):
        self.client = FootballClient()

    async def get_today_matches(self):

        data = await self.client.fixtures()

        matches = []

        for item in data["response"]:

            league = item["league"]["name"]

            if league not in TOP_LEAGUES:
                continue

            matches.append(
                Match(
                    fixture_id=item["fixture"]["id"],
                    home_team=item["teams"]["home"]["name"],
                    away_team=item["teams"]["away"]["name"],
                    league=league,
                    date=item["fixture"]["date"],
                )
            )

        return matches