from app.football.client import FootballClient


class BacktestLoader:

    def __init__(self):

        self.client = FootballClient()

    async def load(
        self,
        league_id: int,
        season: int,
    ):

        matches = await self.client.finished_matches(
            league_id=league_id,
            season=season,
            last=500,
        )

        return matches

    async def close(self):

        await self.client.close()