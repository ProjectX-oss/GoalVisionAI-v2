from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class PublicationIdentity:
    fixture_id: int
    market: str
    selection: str
    product_scope: str

    @classmethod
    def create(
        cls,
        fixture_id: int,
        market: str,
        selection: str,
        product_scope: str,
    ) -> "PublicationIdentity":
        return cls(
            fixture_id=fixture_id,
            market=" ".join(market.strip().upper().split()),
            selection=" ".join(selection.strip().upper().split()),
            product_scope=" ".join(product_scope.strip().upper().split()),
        )


@runtime_checkable
class DuplicatePublicationChecker(Protocol):
    def is_active(self, identity: PublicationIdentity) -> bool: ...


class InMemoryDuplicatePublicationChecker:
    def __init__(self, active: tuple[PublicationIdentity, ...] = ()) -> None:
        self._active = frozenset(active)

    def is_active(self, identity: PublicationIdentity) -> bool:
        return identity in self._active
