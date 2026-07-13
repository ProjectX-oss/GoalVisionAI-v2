from datetime import datetime

import httpx

from app.core.leagues import TOP_LEAGUES
from app.football.cache import TeamCache
from app.football.client import FootballClient
from app.logger import logger
from app.models import Match


class FootballService:

    def __init__(self):

        self.client = FootballClient()
        self.cache = TeamCache()

    async def get_today_matches(self) -> list[Match]:

        try:
            data = await self.client.fixtures()
        except httpx.HTTPError as error:
            logger.error(
                "Unable to load today's matches from the football API: %s",
                error,
            )
            return []

        matches = []

        for item in data["response"]:

            league_name = item["league"]["name"]

            if league_name not in TOP_LEAGUES:
                continue

            matches.append(

                Match(

                    fixture_id=item["fixture"]["id"],

                    league_id=item["league"]["id"],

                    league_name=league_name,

                    season=item["league"]["season"],

                    home_team_id=item["teams"]["home"]["id"],

                    home_team_name=item["teams"]["home"]["name"],

                    away_team_id=item["teams"]["away"]["id"],

                    away_team_name=item["teams"]["away"]["name"],

                    kickoff=datetime.fromisoformat(
                        item["fixture"]["date"].replace(
                            "Z",
                            "+00:00",
                        )
                    ),

                    status=item["fixture"]["status"]["short"],

                )

            )

        return matches

    async def load_team_form(
        self,
        team_id: int,
    ):

        if self.cache.has(team_id):
            return self.cache.get(team_id)

        try:
            fixtures = await self.client.last_matches(team_id)
        except httpx.HTTPError as error:
            logger.error(
                "Unable to load recent matches for team %d: %s",
                team_id,
                error,
            )
            return []

        self.cache.save(
            team_id,
            fixtures,
        )

        return fixtures

    def clear_cache(self):

        self.cache.clear()

    def cached_team_form(self, team_id: int) -> list[dict]:
        """Return already-loaded raw team history without making an API call."""
        fixtures = self.cache.get(team_id)
        return list(fixtures) if fixtures else []
