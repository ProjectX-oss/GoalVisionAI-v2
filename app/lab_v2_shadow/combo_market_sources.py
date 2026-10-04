"""Bounded current-quote reader for the second COMBO lane; no research model I/O."""
from __future__ import annotations

from datetime import datetime
from time import monotonic

from .combo_agreement_sources import current_consensus
from .combo_market import evidence


class Inputs:
    def __init__(self, repository: object) -> None:
        self.repository = repository
        self.deadline: float | None = None
        self.consensuses: dict = {}

    def score(self, candidate: dict, *, now: datetime) -> dict:
        if self.deadline is None:
            self.deadline = monotonic() + 10
        self._check_budget()
        key = (candidate["fixture_id"], candidate["quote_provenance_fingerprint"],
               candidate["goalvision_retrieved_at_utc"])
        if key not in self.consensuses:
            self.consensuses[key] = current_consensus(self.repository, candidate, now=now)
        result = evidence(candidate, self.consensuses[key], now=now)
        self._check_budget()
        return result

    def _check_budget(self) -> None:
        if self.deadline is not None and monotonic() > self.deadline:
            raise ValueError("COMBO_MARKET_BUDGET_EXHAUSTED")
