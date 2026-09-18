"""Reviewed LIVE safety shell, independent of automatically learned model artifacts."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LivePolicy:
    version: str = 'LAB_LIVE_SINGLE_V1'
    state_age_seconds: int = 30
    quote_age_seconds: int = 20
    event_age_seconds: int = 30
    max_uncertainty: float = .12
    max_market_divergence: float = .22
    selections_per_fixture: int = 3
    rebet_minutes: int = 15
    rebet_relative_price: float = .15
    max_fixtures_per_scan: int = 10
    minimum_history: int = 5
    # Only regulation-time active halves; never extra time, penalties or delayed fixtures.
    active_statuses: tuple[str,...] = ('1H','2H')


POLICY=LivePolicy()
