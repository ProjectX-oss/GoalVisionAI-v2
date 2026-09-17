"""Typed, immutable calibration freshness and review contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CalibrationIntegrityStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


class CalibrationEvidenceStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"


class CalibrationReviewStatus(str, Enum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    MISSING = "MISSING"


class CalibrationActionabilityStatus(str, Enum):
    ACTIONABLE_FOR_LAB = "ACTIONABLE_FOR_LAB"
    NON_ACTIONABLE = "NON_ACTIONABLE"


@dataclass(frozen=True, slots=True)
class CalibrationFreshnessAssessment:
    policy_version: str
    environment: str
    calibration_artifact_set_id: str
    calibration_artifact_fingerprint: str
    source_model_artifact_id: str
    artifact_created_timestamp: datetime | None
    evidence_timestamp: datetime | None
    evidence_age_seconds: int | None
    review_timestamp: datetime | None
    review_expiry_timestamp: datetime | None
    integrity_status: CalibrationIntegrityStatus
    evidence_status: CalibrationEvidenceStatus
    review_status: CalibrationReviewStatus
    actionability_status: CalibrationActionabilityStatus
    controlled_synthetic_evidence: bool
    ordered_reason_codes: tuple[str, ...]
    assessment_timestamp: datetime
    assessment_fingerprint: str
