"""Typed API-Football quota interpretation using the provider's exact headers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


class FootballQuotaError(RuntimeError):
    """Raised when a bounded provider run cannot preserve its quota reserve."""


@dataclass(frozen=True, slots=True)
class FootballQuotaReport:
    daily_limit: int | None
    daily_remaining: int | None
    minute_limit: int | None
    minute_remaining: int | None
    exact_headers: tuple[tuple[str, str | None], ...]
    interpretation_status: str

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> "FootballQuotaReport":
        exact = (
            ("x-ratelimit-requests-limit", headers.get("x-ratelimit-requests-limit")),
            ("x-ratelimit-requests-remaining", headers.get("x-ratelimit-requests-remaining")),
            ("x-ratelimit-limit", headers.get("x-ratelimit-limit")),
            ("x-ratelimit-remaining", headers.get("x-ratelimit-remaining")),
        )
        values = tuple(_integer(value) for _, value in exact)
        ambiguous = (
            any(value is None for value in values)
            or values[1] > values[0]
            or values[3] > values[2]
        )
        return cls(*values, exact, "AMBIGUOUS" if ambiguous else "NORMALIZED")

    def require_capacity(self, *, additional_calls: int, daily_reserve: int) -> None:
        if (
            self.interpretation_status != "NORMALIZED"
            or self.daily_remaining is None
            or self.minute_remaining is None
        ):
            raise FootballQuotaError("API_FOOTBALL_QUOTA_AMBIGUOUS")
        if (
            self.daily_remaining - additional_calls < daily_reserve
            or self.minute_remaining < additional_calls
        ):
            raise FootballQuotaError("API_FOOTBALL_QUOTA_INSUFFICIENT")

    def as_dict(self) -> dict:
        return asdict(self)


def _integer(value: object) -> int | None:
    if not isinstance(value, str) or not value.strip().isdigit():
        return None
    result = int(value)
    return result if result >= 0 else None
