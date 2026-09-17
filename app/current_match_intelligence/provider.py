"""API-Football Pro endpoint adapter for current-match intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class CurrentMatchProvider(Protocol):
    @property
    def request_count(self) -> int: ...
    def response_metadata(self) -> dict: ...
    def restrict_requests(self, maximum_calls: int, *, daily_reserve: int = 20) -> None: ...
    async def fixture(self, fixture_id: int) -> object: ...
    async def current_odds(self, fixture_id: int) -> object: ...
    async def last_matches(self, team_id: int, last: int = 10, *, league_id: int | None = None, season: int | None = None) -> object: ...
    async def lineup(self, fixture_id: int) -> object: ...
    async def injuries(self, fixture_id: int) -> object: ...
    async def team_statistics(self, team_id: int, league_id: int, season: int) -> object: ...
    async def fixture_statistics(self, fixture_id: int) -> object: ...


class ApiFootballCurrentMatchProvider:
    """Adds reviewed Pro endpoints without changing the existing client API."""

    def __init__(self, football_client: object) -> None:
        self.client = football_client

    @property
    def request_count(self) -> int:
        return int(getattr(self.client, "request_count", 0))

    def response_metadata(self) -> dict:
        value = getattr(self.client, "response_metadata", lambda: {})()
        return dict(value) if isinstance(value, dict) else {}

    def restrict_requests(self, maximum_calls: int, *, daily_reserve: int = 20) -> None:
        restrict = getattr(self.client, "restrict_requests", None)
        if restrict is not None:
            restrict(maximum_calls, daily_reserve=daily_reserve)

    async def fixture(self, fixture_id: int) -> object:
        return await self.client.fixture(fixture_id)

    async def current_odds(self, fixture_id: int) -> object:
        return await self.client.current_odds(fixture_id)

    async def last_matches(self, team_id: int, last: int = 10, *, league_id: int | None = None, season: int | None = None) -> object:
        return await self.client.last_matches(
            team_id, last=last, league_id=league_id, season=season
        )

    async def lineup(self, fixture_id: int) -> object:
        return await self._json("/fixtures/lineups", {"fixture": fixture_id})

    async def injuries(self, fixture_id: int) -> object:
        # A fixture query returns both teams and saves one request.
        return await self._json("/injuries", {"fixture": fixture_id})

    async def team_statistics(self, team_id: int, league_id: int, season: int) -> object:
        return await self._json(
            "/teams/statistics",
            {"team": team_id, "league": league_id, "season": season},
        )

    async def fixture_statistics(self, fixture_id: int) -> object:
        return await self._json("/fixtures/statistics", {"fixture": fixture_id})

    async def _json(self, endpoint: str, query: dict[str, object]) -> object:
        getter = getattr(self.client, "_get", None)
        if getter is None:
            raise RuntimeError("API_FOOTBALL_CLIENT_ENDPOINT_UNAVAILABLE")
        response = await getter(endpoint, params=query)
        return response.json()


def retrieved_at(provider: CurrentMatchProvider, fallback: datetime) -> datetime:
    raw = provider.response_metadata().get("retrieved_at_utc")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    return fallback.astimezone(timezone.utc)
