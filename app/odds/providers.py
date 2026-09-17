from typing import Protocol, runtime_checkable

from .models import OddsObservation


@runtime_checkable
class OddsProvider(Protocol):
    @property
    def source_name(self) -> str: ...

    def observations(self) -> tuple[OddsObservation, ...]: ...


class StaticOddsProvider:
    def __init__(
        self,
        source_name: str,
        observations: tuple[OddsObservation, ...],
    ) -> None:
        self._source_name = source_name
        self._observations = observations

    @property
    def source_name(self) -> str:
        return self._source_name

    def observations(self) -> tuple[OddsObservation, ...]:
        return self._observations


class NullOddsProvider:
    @property
    def source_name(self) -> str:
        return "NULL"

    def observations(self) -> tuple[OddsObservation, ...]:
        return ()
