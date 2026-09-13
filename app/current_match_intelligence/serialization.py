"""Lossless conversion from persisted canonical documents."""

from __future__ import annotations

from datetime import datetime

from .models import (
    ApiCallEvidence,
    CurrentMatchIntelligenceSnapshot,
    DataClass,
    FieldProvenance,
    FreshnessEvidence,
    FreshnessStatus,
    IntelligenceField,
)


def snapshot_from_document(raw: dict) -> CurrentMatchIntelligenceSnapshot:
    fields = tuple(
        IntelligenceField(
            name=item["name"],
            data_class=DataClass(item["data_class"]),
            value=item["value"],
            provenance=tuple(
                FieldProvenance(
                    provider=p["provider"], endpoint=p["endpoint"],
                    retrieved_at=_datetime(p["retrieved_at"]),
                    provider_timestamp=(_datetime(p["provider_timestamp"])
                                        if p.get("provider_timestamp") else None),
                    fixture_id=p["fixture_id"], team_id=p.get("team_id"),
                    player_id=p.get("player_id"),
                )
                for p in item["provenance"]
            ),
        )
        for item in raw["fields"]
    )
    freshness = tuple(
        FreshnessEvidence(
            signal=item["signal"], status=FreshnessStatus(item["status"]),
            evaluated_at=_datetime(item["evaluated_at"]),
            newest_retrieved_at=(_datetime(item["newest_retrieved_at"])
                                 if item.get("newest_retrieved_at") else None),
            expires_at=(_datetime(item["expires_at"])
                        if item.get("expires_at") else None),
            policy_seconds=int(item["policy_seconds"]),
        )
        for item in raw["freshness"]
    )
    calls = tuple(ApiCallEvidence(**item) for item in raw["api_calls"])
    return CurrentMatchIntelligenceSnapshot(
        schema_version=raw["schema_version"], snapshot_id=raw["snapshot_id"],
        fixture_id=raw["fixture_id"], version=int(raw["version"]),
        kickoff_utc=_datetime(raw["kickoff_utc"]),
        evaluated_at=_datetime(raw["evaluated_at"]), fields=fields,
        freshness=freshness, missing_data=tuple(raw["missing_data"]),
        blockers=tuple(raw["blockers"]), api_calls=calls,
        content_fingerprint=raw["content_fingerprint"],
    )


def _datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)
