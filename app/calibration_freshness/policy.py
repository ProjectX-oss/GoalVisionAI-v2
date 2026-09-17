"""Centralized policy separating model evidence from live market data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalibrationFreshnessPolicy:
    version: str = "calibration-freshness-policy-v2"
    lab_evidence_max_age_seconds: int = 366 * 24 * 60 * 60
    lab_review_validity_seconds: int = 24 * 60 * 60
    official_evidence_max_age_seconds: int | None = None
    controlled_synthetic_allowed_environments: tuple[str, ...] = ("LAB", "STAGING")

    def __post_init__(self) -> None:
        if self.lab_evidence_max_age_seconds <= 0:
            raise ValueError("Lab calibration evidence lifetime must be positive.")
        if self.lab_review_validity_seconds <= 0:
            raise ValueError("Lab calibration review lifetime must be positive.")
        if self.official_evidence_max_age_seconds is not None:
            raise ValueError("Official calibration freshness remains fail-closed in v2.")


DEFAULT_CALIBRATION_FRESHNESS_POLICY = CalibrationFreshnessPolicy()
