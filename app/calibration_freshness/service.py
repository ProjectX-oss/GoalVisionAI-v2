"""Read-only calibration integrity, evidence-recency, and review assessment."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json

from .models import (
    CalibrationActionabilityStatus,
    CalibrationEvidenceStatus,
    CalibrationFreshnessAssessment,
    CalibrationIntegrityStatus,
    CalibrationReviewStatus,
)
from .policy import CalibrationFreshnessPolicy


def assess_calibration_freshness(
    database,
    calibration,
    *,
    environment: str,
    assessment_timestamp: datetime,
    review_timestamp: datetime | None,
    policy: CalibrationFreshnessPolicy,
) -> CalibrationFreshnessAssessment:
    """Derive immutable evidence time from the exact persisted VALIDATION rows."""
    now = _utc(assessment_timestamp)
    environment = environment.upper()
    reasons: list[str] = []
    artifact_created = _parse(getattr(calibration.command, "calibration_timestamp", None))
    source_model_id = getattr(calibration.command, "source_model_artifact_id", "")
    integrity = CalibrationIntegrityStatus.VALID
    evidence_status = CalibrationEvidenceStatus.MISSING
    evidence_timestamp = None
    evidence_age = None
    controlled = "CONTROLLED_SYNTHETIC" in str(calibration.provenance_snapshot)

    row = database.connection.execute(
        """
        SELECT COUNT(*) AS row_count,
               COUNT(DISTINCT p.training_example_id) AS distinct_count,
               SUM(CASE WHEN p.example_fingerprint=e.example_fingerprint THEN 0 ELSE 1 END) AS mismatches,
               MAX(e.kickoff_timestamp) AS evidence_timestamp
        FROM historical_probability_calibration_predictions AS p
        LEFT JOIN historical_training_examples AS e
          ON e.training_example_id=p.training_example_id
        WHERE p.calibration_run_id=?
        """,
        (calibration.calibration_run_id,),
    ).fetchone()
    run = database.connection.execute(
        "SELECT validation_row_count,source_artifact_id,source_artifact_fingerprint "
        "FROM historical_probability_calibration_runs WHERE calibration_run_id=?",
        (calibration.calibration_run_id,),
    ).fetchone()
    if artifact_created is None:
        integrity = CalibrationIntegrityStatus.INVALID
        reasons.append("CALIBRATION_ARTIFACT_TIMESTAMP_MISSING")
    if (
        run is None
        or row is None
        or not row["row_count"]
        or row["row_count"] != row["distinct_count"]
        or row["row_count"] != run["validation_row_count"]
        or row["mismatches"]
        or run["source_artifact_id"] != source_model_id
        or run["source_artifact_fingerprint"]
        != getattr(calibration.command, "source_model_artifact_fingerprint", "")
    ):
        integrity = CalibrationIntegrityStatus.INVALID
        evidence_status = CalibrationEvidenceStatus.PROVENANCE_INVALID
        reasons.append("CALIBRATION_PROVENANCE_INVALID")
    else:
        evidence_timestamp = _parse(row["evidence_timestamp"])
        if evidence_timestamp is None:
            reasons.append("CALIBRATION_EVIDENCE_TIMESTAMP_MISSING")
        elif artifact_created is None or evidence_timestamp > artifact_created:
            integrity = CalibrationIntegrityStatus.INVALID
            evidence_status = CalibrationEvidenceStatus.PROVENANCE_INVALID
            reasons.append("CALIBRATION_PROVENANCE_INVALID")
        else:
            evidence_age = int((now - evidence_timestamp).total_seconds())
            if evidence_age < 0:
                evidence_status = CalibrationEvidenceStatus.PROVENANCE_INVALID
                reasons.append("CALIBRATION_PROVENANCE_INVALID")
            elif evidence_age > policy.lab_evidence_max_age_seconds:
                evidence_status = CalibrationEvidenceStatus.STALE
                reasons.append("CALIBRATION_EVIDENCE_STALE")
            else:
                evidence_status = CalibrationEvidenceStatus.FRESH

    reviewed_at = _utc(review_timestamp) if review_timestamp is not None else None
    review_expiry = (
        reviewed_at + timedelta(seconds=policy.lab_review_validity_seconds)
        if reviewed_at is not None else None
    )
    if reviewed_at is None:
        review_status = CalibrationReviewStatus.MISSING
        reasons.append("CALIBRATION_REVIEW_MISSING")
    elif reviewed_at > now or review_expiry is None or now > review_expiry:
        review_status = CalibrationReviewStatus.EXPIRED
        reasons.append("CALIBRATION_REVIEW_EXPIRED")
    else:
        review_status = CalibrationReviewStatus.VALID

    if environment not in policy.controlled_synthetic_allowed_environments:
        reasons.append("OFFICIAL_CALIBRATION_POLICY_UNSET")
    if controlled and environment not in policy.controlled_synthetic_allowed_environments:
        reasons.append("CONTROLLED_SYNTHETIC_EVIDENCE_NOT_AUTHORIZED")
    actionable = (
        integrity is CalibrationIntegrityStatus.VALID
        and evidence_status is CalibrationEvidenceStatus.FRESH
        and review_status is CalibrationReviewStatus.VALID
        and environment in policy.controlled_synthetic_allowed_environments
    )
    result = CalibrationFreshnessAssessment(
        policy.version, environment, calibration.artifact_set_id,
        calibration.artifact_set_fingerprint, source_model_id, artifact_created,
        evidence_timestamp, evidence_age, reviewed_at, review_expiry, integrity,
        evidence_status, review_status,
        CalibrationActionabilityStatus.ACTIONABLE_FOR_LAB if actionable
        else CalibrationActionabilityStatus.NON_ACTIONABLE,
        controlled, tuple(dict.fromkeys(reasons)), now, "",
    )
    return replace(result, assessment_fingerprint=_fingerprint(result))


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Freshness clocks must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _fingerprint(value: CalibrationFreshnessAssessment) -> str:
    material = asdict(value)
    material["assessment_fingerprint"] = ""
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
