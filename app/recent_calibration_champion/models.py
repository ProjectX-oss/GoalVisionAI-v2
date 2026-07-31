"""Immutable read-only recent champion inspection contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChampionFreshnessReport:
    schema_version: str
    environment: str
    scope: str
    champion_generation_id: str
    champion_generation_number: int
    model_artifact_id: str
    model_fingerprint: str
    calibration_id: str
    calibration_fingerprint: str
    calibration_freshness_reference_timestamp: str
    controlled_clock_timestamp: str
    calibration_age_seconds: int
    maximum_allowed_age_seconds: int
    freshness_status: str
    live_schema_id: str
    live_schema_version: str
    feature_count: int
    schema_fingerprint: str
    compatibility_status: str
    audit_status: str
    audit_fingerprint: str
    report_fingerprint: str
