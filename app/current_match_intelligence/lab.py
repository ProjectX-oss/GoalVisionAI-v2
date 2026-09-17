"""Read-only exposure to Real Match Lab and future model-input construction."""

from __future__ import annotations

from datetime import datetime

from .features import future_feature_vector
from .repository import SQLiteCurrentMatchIntelligenceRepository


class RealMatchLabIntelligenceBridge:
    """Resolve only evidence available at the Lab analysis cutoff."""

    def __init__(self, repository: SQLiteCurrentMatchIntelligenceRepository) -> None:
        self.repository = repository

    def context_for_analysis(
        self, fixture_id: str, *, analysis_at: datetime
    ) -> dict[str, object]:
        snapshot = self.repository.latest_for_fixture(
            fixture_id, at_or_before=analysis_at
        )
        if snapshot is None:
            return {
                "status": "MISSING", "fixture_id": fixture_id,
                "snapshot_id": None, "future_feature_contract": None,
                "missing_data": ("CURRENT_MATCH_INTELLIGENCE_SNAPSHOT",),
            }
        vector = future_feature_vector(snapshot)
        return {
            "status": "AVAILABLE",
            "fixture_id": fixture_id,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_version": snapshot.version,
            "content_fingerprint": snapshot.content_fingerprint,
            "freshness": snapshot.freshness,
            "missing_data": snapshot.missing_data,
            "blockers": snapshot.blockers,
            "future_feature_contract": vector,
            "live_78_consumption": "NOT_CONNECTED",
        }
