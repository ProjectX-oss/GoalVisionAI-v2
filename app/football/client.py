from datetime import datetime

import httpx

from app.config import FOOTBALL_API_KEY


class FootballClient:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self):

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "x-apisports-key": FOOTBALL_API_KEY,
            },
            timeout=httpx.Timeout(
                timeout=30.0,
                connect=10.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )

    async def fixtures(self):

        today = datetime.now().strftime("%Y-%m-%d")

        response = await self._client.get(
            "/fixtures",
            params={
                "date": today,
            },
        )

        response.raise_for_status()

        return response.json()

    async def last_matches(
        self,
        team_id: int,
        last: int = 5,
    ):

        response = await self._client.get(
            "/fixtures",
            params={
                "team": team_id,
                "last": last,
            },
        )

        response.raise_for_status()

        return response.json()["response"]

    async def finished_matches(
        self,
        league_id: int,
        season: int,
        last: int = 100,
    ):

        response = await self._client.get(
            "/fixtures",
            params={
                "league": league_id,
                "season": season,
                "status": "FT",
                "last": last,
            },
        )

        response.raise_for_status()

        return response.json()["response"]

    async def standings(
        self,
        league_id: int,
        season: int,
    ):

        response = await self._client.get(
            "/standings",
            params={
                "league": league_id,
                "season": season,
            },
        )

        response.raise_for_status()

        return response.json()["response"]

    async def h2h(
        self,
        home_team: int,
        away_team: int,
        last: int = 5,
    ):

        response = await self._client.get(
            "/fixtures/headtohead",
            params={
                "h2h": f"{home_team}-{away_team}",
                "last": last,
            },
        )

        response.raise_for_status()

        return response.json()["response"]

    async def close(self):

        await self._client.aclose()
