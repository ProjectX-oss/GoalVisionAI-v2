import asyncio
from datetime import datetime
from pathlib import Path

import httpx

from .configuration import resolve_api_football_credential
from .quota import FootballQuotaReport


class FootballRequestLimitError(RuntimeError):
    """Raised before an explicit bounded run can exceed its request ceiling."""


class FootballClient:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str | None = None, *, env_file: Path | str = Path(".env"), request_limit: int | None = None):

        api_key = resolve_api_football_credential(api_key, env_file=env_file)
        self._quota: FootballQuotaReport | None = None
        self._last_response_metadata: dict = {}
        self._request_count = 0
        self._request_limit = request_limit

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

    async def fixtures_by_date(self, date: str, *, timezone_name: str = "UTC"):
        response = await self._get(
            "/fixtures", params={"date": date, "timezone": timezone_name}
        )
        return response.json()

    async def fixtures_between(self, date_from: str, date_to: str, *, timezone_name: str = "UTC", league_id: int | None = None, season: int | None = None):
        if league_id is None or season is None:
            raise ValueError("API_FOOTBALL_RANGE_REQUIRES_LEAGUE_AND_SEASON")
        params: dict[str, object] = {"from": date_from, "to": date_to, "timezone": timezone_name}
        params["league"] = league_id
        params["season"] = season
        response = await self._get(
            "/fixtures", params=params
        )
        return response.json()

    async def account_status(self):
        response = await self._get("/status", params={})
        return response.json()

    async def leagues(self, *, current: bool = True):
        response = await self._get(
            "/leagues", params={"current": "true" if current else "false"}
        )
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

    def quota_snapshot(self) -> dict:
        return self._quota.as_dict() if self._quota is not None else {
            "daily_limit": None, "daily_remaining": None,
            "minute_limit": None, "minute_remaining": None,
            "exact_headers": (), "interpretation_status": "NOT_OBSERVED",
        }

    def response_metadata(self) -> dict:
        return dict(self._last_response_metadata)

    @property
    def request_count(self) -> int:
        return self._request_count

    async def _get(self, path: str, *, params: dict):
        for attempt in range(3):
            try:
                if self._request_limit is not None and self._request_count >= self._request_limit:
                    raise FootballRequestLimitError("API_FOOTBALL_REQUEST_LIMIT_REACHED")
                self._request_count += 1
                response = await self._client.get(path, params=params)
                observed_quota = FootballQuotaReport.from_headers(response.headers)
                if observed_quota.interpretation_status == "NORMALIZED":
                    self._quota = observed_quota
                payload = _safe_json(response)
                self._last_response_metadata = {
                    "endpoint": path,
                    "method": "GET",
                    "query": dict(sorted(params.items())),
                    "http_status": response.status_code,
                    "errors": payload.get("errors", {}) if isinstance(payload, dict) else {"response": "INVALID_JSON"},
                    "results": payload.get("results") if isinstance(payload, dict) else None,
                    "paging": payload.get("paging") if isinstance(payload, dict) else None,
                    "quota": observed_quota.as_dict(),
                }
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {408, 425, 500, 502, 503, 504} or attempt == 2:
                    raise
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 2: raise
            await asyncio.sleep(2 ** attempt)
        raise AssertionError("unreachable")


def _safe_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {}
