from typing import Protocol

from app.results import FinishedMatchResult


class FixtureResultProvider(Protocol):
    def load_fixture(self, fixture_id: int) -> tuple[FinishedMatchResult, ...]:
        """Return zero or more snapshots for one deduplicated fixture request."""
        ...
