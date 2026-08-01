import asyncio
import os
from datetime import datetime

import httpx

class FootballClient:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str | None = None):

        api_key = (api_key or os.getenv("FOOTBALL_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("FOOTBALL_API_KEY not found.")
        self._quota: dict[str, str | None] = {}

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "x-apisports-key": api_key,
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

        response = await self._get(
            "/fixtures",
            params={
                "date": today,
            },
        )

        response.raise_for_status()

        return response.json()

    async def fixture(self, fixture_id: int):
        response = await self._get("/fixtures", params={"id": fixture_id})
        return response.json()

    async def current_odds(self, fixture_id: int):
        response = await self._get("/odds", params={"fixture": fixture_id})
        return response.json()

    async def last_matches(
        self,
        team_id: int,
        last: int = 5,
    ):

        response = await self._get(
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

        response = await self._get(
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

        response = await self._get(
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

        response = await self._get(
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

    def quota_snapshot(self) -> dict[str, str | None]:
        return dict(self._quota)

    async def _get(self, path: str, *, params: dict):
        for attempt in range(3):
            try:
                response = await self._client.get(path, params=params)
                response.raise_for_status()
                self._quota = {
                    "requests_remaining": response.headers.get("x-ratelimit-requests-remaining"),
                    "daily_remaining": response.headers.get("x-ratelimit-remaining"),
                }
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {408, 425, 500, 502, 503, 504} or attempt == 2:
                    raise
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 2: raise
            await asyncio.sleep(2 ** attempt)
        raise AssertionError("unreachable")
