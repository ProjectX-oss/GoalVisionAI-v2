from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import (
    FormFeatureError,
    FormFeatureErrorCode,
    HistoricalMatchObservation,
)
from .normalization import normalize_identifier, normalize_source, normalize_text


@dataclass(frozen=True, slots=True)
class HistoricalMatchProviderBatch:
    observations: tuple[HistoricalMatchObservation, ...]
    errors: tuple[FormFeatureError, ...] = ()


@runtime_checkable
class HistoricalMatchProvider(Protocol):
    @property
    def source_name(self) -> str: ...

    def historical_matches(self) -> HistoricalMatchProviderBatch: ...


class NullHistoricalMatchProvider:
    @property
    def source_name(self) -> str:
        return "NULL"

    def historical_matches(self) -> HistoricalMatchProviderBatch:
        return HistoricalMatchProviderBatch(())


class StaticHistoricalMatchProvider:
    def __init__(
        self,
        source_name: str,
        observations: tuple[HistoricalMatchObservation, ...],
        errors: tuple[FormFeatureError, ...] = (),
    ) -> None:
        self._source_name = source_name
        self._batch = HistoricalMatchProviderBatch(observations, errors)

    @property
    def source_name(self) -> str:
        return self._source_name

    def historical_matches(self) -> HistoricalMatchProviderBatch:
        return self._batch


class ExistingFootballHistoricalAdapter:
    """Maps only fields returned by the repository's finished-fixtures calls."""

    def __init__(
        self,
        payloads: tuple[object, ...],
        *,
        observed_at: datetime,
        created_at: datetime | None = None,
    ) -> None:
        self._payloads = payloads
        self._observed_at = observed_at
        self._created_at = created_at or observed_at

    @property
    def source_name(self) -> str:
        return "API-FOOTBALL"

    def historical_matches(self) -> HistoricalMatchProviderBatch:
        observations: list[HistoricalMatchObservation] = []
        errors: list[FormFeatureError] = []
        for raw in self._payloads:
            try:
                if not isinstance(raw, dict):
                    raise TypeError("Fixture record must be an object.")
                fixture = raw["fixture"]
                league = raw["league"]
                teams = raw["teams"]
                goals = raw["goals"]
                kickoff = datetime.fromisoformat(
                    str(fixture["date"]).replace("Z", "+00:00")
                )
                observations.append(
                    HistoricalMatchObservation(
                        fixture_id=normalize_identifier(
                            fixture["id"], "Fixture ID"
                        ),
                        competition=normalize_text(
                            league["name"], "Competition"
                        ),
                        kickoff_time=kickoff,
                        home_team_id=normalize_identifier(
                            teams["home"]["id"], "Home team"
                        ),
                        away_team_id=normalize_identifier(
                            teams["away"]["id"], "Away team"
                        ),
                        home_goals=int(goals["home"]),
                        away_goals=int(goals["away"]),
                        match_status=normalize_text(
                            fixture["status"]["short"], "Match status"
                        ).upper(),
                        observed_at=self._observed_at,
                        home_xg=None,
                        away_xg=None,
                        home_shots=None,
                        away_shots=None,
                        home_red_cards=None,
                        away_red_cards=None,
                        penalties=None,
                        source_name=normalize_source(self.source_name),
                        source_reference=f"fixture:{fixture['id']}",
                        created_at=self._created_at,
                    )
                )
            except Exception:
                fixture_id = ""
                if isinstance(raw, dict):
                    fixture_id = str(raw.get("fixture", {}).get("id", ""))
                errors.append(
                    FormFeatureError(
                        fixture_id=fixture_id,
                        code=FormFeatureErrorCode.MALFORMED_PROVIDER_RECORD,
                        safe_message="Malformed historical fixture was ignored.",
                        occurred_at=self._observed_at,
                    )
                )
        return HistoricalMatchProviderBatch(
            tuple(observations),
            tuple(sorted(errors, key=lambda item: (item.fixture_id, item.code.value))),
        )
