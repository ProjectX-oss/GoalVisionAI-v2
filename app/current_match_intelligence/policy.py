"""Independent freshness and bounded-enrichment policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class IntelligenceFreshnessPolicy:
    fixture: timedelta = timedelta(hours=24)
    confirmed_lineup: timedelta = timedelta(minutes=30)
    unavailable_lineup: timedelta = timedelta(minutes=15)
    injuries: timedelta = timedelta(hours=4)
    team_statistics: timedelta = timedelta(hours=6)
    team_history: timedelta = timedelta(hours=6)
    historical_fixture_statistics: timedelta = timedelta(days=30)
    historical_lineup: timedelta = timedelta(days=30)
    odds: timedelta = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class IntelligenceBudgetPolicy:
    maximum_api_calls: int = 40
    recent_match_window: int = 10
    detailed_match_window: int = 3
    maximum_enriched_fixtures: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_api_calls <= 40:
            raise ValueError("Current Match Intelligence cannot exceed 40 API calls.")
        if self.recent_match_window < 1 or self.detailed_match_window < 0:
            raise ValueError("Invalid enrichment windows.")
        if self.maximum_enriched_fixtures < 1:
            raise ValueError("At least one enrichment target is required.")
