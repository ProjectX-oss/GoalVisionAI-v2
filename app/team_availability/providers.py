from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import (
    AvailabilityError,
    AvailabilityErrorCode,
    LineupObservation,
    PlayerAvailabilityObservation,
)


AvailabilityRecord = PlayerAvailabilityObservation | LineupObservation


@dataclass(frozen=True, slots=True)
class AvailabilityProviderBatch:
    records: tuple[AvailabilityRecord, ...]
    errors: tuple[AvailabilityError, ...] = ()


@runtime_checkable
class AvailabilityProvider(Protocol):
    @property
    def source_name(self) -> str: ...

    def observations(self) -> AvailabilityProviderBatch: ...


class StaticAvailabilityProvider:
    def __init__(
        self,
        source_name: str,
        records: tuple[AvailabilityRecord, ...],
        errors: tuple[AvailabilityError, ...] = (),
    ) -> None:
        self._source_name = source_name
        self._batch = AvailabilityProviderBatch(records, errors)

    @property
    def source_name(self) -> str:
        return self._source_name

    def observations(self) -> AvailabilityProviderBatch:
        return self._batch


class NullAvailabilityProvider:
    @property
    def source_name(self) -> str:
        return "NULL"

    def observations(self) -> AvailabilityProviderBatch:
        return AvailabilityProviderBatch(())


@dataclass(frozen=True, slots=True)
class ExistingFootballProviderCapabilities:
    confirmed_lineups: bool = False
    predicted_lineups: bool = False
    substitutes: bool = False
    formations: bool = False
    injuries: bool = False
    suspensions: bool = False
    doubtful_status: bool = False
    unavailable_players: bool = False
    player_minutes: bool = False
    recent_starting_history: bool = False
    coaches: bool = False
    squads: bool = False


class ExistingFootballApiAvailabilityAdapter:
    """Honest adapter for the currently implemented fixtures-only API surface.

    The repository's FootballClient does not call lineup, injury, player,
    coach, or squad endpoints. Fixture payloads therefore produce no
    availability records.
    """

    capabilities = ExistingFootballProviderCapabilities()

    def __init__(
        self,
        fixture_payloads: tuple[dict, ...] = (),
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        self._payloads = fixture_payloads
        self._occurred_at = occurred_at

    @property
    def source_name(self) -> str:
        return "API-FOOTBALL"

    def observations(self) -> AvailabilityProviderBatch:
        errors: list[AvailabilityError] = []
        for payload in self._payloads:
            if not isinstance(payload, dict) or not isinstance(
                payload.get("fixture"), dict
            ):
                if self._occurred_at is None:
                    continue
                errors.append(
                    AvailabilityError(
                        source=self.source_name,
                        fixture_id="",
                        team_id="",
                        player_reference="",
                        code=AvailabilityErrorCode.MALFORMED_PROVIDER_RECORD,
                        safe_message="Malformed fixture provider record was ignored.",
                        occurred_at=self._occurred_at,
                    )
                )
        return AvailabilityProviderBatch((), tuple(errors))
