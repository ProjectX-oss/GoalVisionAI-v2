import asyncio

from app.collector import StandingsCollector
from app.logger import logger


class StandingsService:

    def __init__(self, football):

        self.football = football

        self.collector = StandingsCollector()

        self.tables = {}

    async def load(self, matches):

        leagues = {
            (m.league_id, m.season)
            for m in matches
        }

        responses = await asyncio.gather(

            *[
                self.football.client.standings(
                    league_id,
                    season,
                )
                for league_id, season in leagues
            ],
            return_exceptions=True,

        )

        self.tables.clear()

        for key, response in zip(
            leagues,
            responses,
        ):

            if isinstance(response, Exception):
                logger.error(
                    "Unable to load standings for league %d season %d: %s",
                    key[0],
                    key[1],
                    response,
                )
                self.tables[key] = {}
            else:
                self.tables[key] = self.collector.collect(
                    response
                )

    def get(
        self,
        league_id,
        season,
    ):

        return self.tables.get(
            (
                league_id,
                season,
            )
        )

    def clear(self):

        self.tables.clear()
