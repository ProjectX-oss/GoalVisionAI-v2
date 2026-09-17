"""Fail-closed compatibility and freshness inspection for staging champions."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json

from app.historical_model_training import (
    LIVE_TRAINING_FEATURE_CONTRACT,
    SQLiteHistoricalModelTrainingRepository,
)
from app.calibration_freshness import (
    CalibrationActionabilityStatus,
    DEFAULT_CALIBRATION_FRESHNESS_POLICY,
    assess_calibration_freshness,
)
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
)
from app.model_activation import (
    ActivationStatus,
    build_runtime_champion_resolver,
)
from app.model_activation_audit import ModelActivationAuditService
from app.model_activation_audit.repository import ReadOnlyAuditRepository

from .models import ChampionFreshnessReport


REPORT_SCHEMA_VERSION = "goalvision-live-78-champion-freshness-report-v2"


class ChampionFreshnessError(RuntimeError):
    """Raised when any report input or persisted reference fails closed."""


def calibration_freshness_status(
    reference_timestamp: datetime,
    controlled_now: datetime,
) -> tuple[int, int, str]:
    """Classify a calibration *evidence* timestamp under the Lab v2 policy."""
    reference = _utc(reference_timestamp)
    now = _utc(controlled_now)
    age = int((now - reference).total_seconds())
    maximum = DEFAULT_CALIBRATION_FRESHNESS_POLICY.lab_evidence_max_age_seconds
    if age < 0 or age > maximum:
        raise ChampionFreshnessError("The active champion calibration is not fresh.")
    status = "FRESH"
    return age, maximum, status


def inspect_active_champion_freshness(
    database,
    *,
    environment: str,
    scope: str,
    controlled_now: datetime,
    source_commit: str,
) -> ChampionFreshnessReport:
    """Resolve and independently verify the active staging champion."""
    if environment.upper() not in {"LAB", "STAGING"}:
        raise ChampionFreshnessError("Freshness inspection is Lab/staging-only.")
    now = _utc(controlled_now)
    resolution = build_runtime_champion_resolver(database, migrate=False).resolve(scope)
    if (
        resolution.status is not ActivationStatus.CHAMPION_RESOLVED
        or resolution.champion_generation is None
    ):
        raise ChampionFreshnessError("The active champion does not resolve safely.")
    generation = resolution.champion_generation
    reference = generation.artifact
    model = SQLiteHistoricalModelTrainingRepository(
        database, migrate=False
    ).load_model_artifact(reference.model_artifact_id)
    calibration = SQLiteHistoricalProbabilityCalibrationRepository(
        database, migrate=False
    ).load_calibration_artifact_set(reference.calibration_artifact_set_id)
    if model is None or calibration is None:
        raise ChampionFreshnessError("Champion model or calibration metadata is missing.")
    contract = LIVE_TRAINING_FEATURE_CONTRACT
    compatible = (
        reference.model_artifact_fingerprint == model.artifact_fingerprint
        and reference.calibration_artifact_set_fingerprint
        == calibration.artifact_set_fingerprint
        and calibration.command.source_model_artifact_id == model.artifact_id
        and model.feature_schema_version == contract.schema_version
        and model.feature_schema_fingerprint == contract.schema_fingerprint
        and model.ordered_feature_names == contract.ordered_feature_names
        and len(model.ordered_feature_names) == 78
    )
    if not compatible:
        raise ChampionFreshnessError("The active champion is not live-78 compatible.")
    audit_repository = ReadOnlyAuditRepository(str(database.path))
    try:
        audit = ModelActivationAuditService(audit_repository).audit(
            source_commit=source_commit,
            generated_timestamp_utc=now.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            environment=environment,
            scope=scope,
        )
    finally:
        audit_repository.close()
    if audit.overall_status.value != "AUDIT_PASSED":
        raise ChampionFreshnessError("Independent activation audit did not pass.")
    freshness_assessment = assess_calibration_freshness(
        database,
        calibration,
        environment=environment,
        assessment_timestamp=now,
        review_timestamp=_parse_utc(audit.generated_timestamp_utc),
        policy=DEFAULT_CALIBRATION_FRESHNESS_POLICY,
    )
    if (
        freshness_assessment.actionability_status
        is not CalibrationActionabilityStatus.ACTIONABLE_FOR_LAB
    ):
        raise ChampionFreshnessError(
            "The active champion calibration is non-actionable: "
            + "|".join(freshness_assessment.ordered_reason_codes)
        )
    reference_at = freshness_assessment.evidence_timestamp
    if reference_at is None or freshness_assessment.artifact_created_timestamp is None:
        raise ChampionFreshnessError("Calibration freshness provenance is missing.")
    age = freshness_assessment.evidence_age_seconds
    if age is None:
        raise ChampionFreshnessError("Calibration evidence age is unavailable.")
    maximum = DEFAULT_CALIBRATION_FRESHNESS_POLICY.lab_evidence_max_age_seconds
    report = ChampionFreshnessReport(
        REPORT_SCHEMA_VERSION,
        environment.upper(),
        scope,
        generation.champion_generation_id,
        generation.generation_number,
        model.artifact_id,
        model.artifact_fingerprint,
        calibration.artifact_set_id,
        calibration.artifact_set_fingerprint,
        _format_utc(freshness_assessment.artifact_created_timestamp),
        _format_utc(reference_at),
        _format_utc(reference_at),
        _format_utc(now),
        age,
        maximum,
        freshness_assessment.evidence_status.value,
        freshness_assessment.integrity_status.value,
        _format_utc(freshness_assessment.review_timestamp),
        _format_utc(freshness_assessment.review_expiry_timestamp),
        freshness_assessment.review_status.value,
        freshness_assessment.actionability_status.value,
        freshness_assessment.ordered_reason_codes,
        contract.schema_identifier,
        contract.schema_version,
        contract.feature_count,
        contract.schema_fingerprint,
        "COMPATIBLE",
        audit.overall_status.value,
        audit.audit_fingerprint,
        "",
    )
    return replace(report, report_fingerprint=_fingerprint(report))


def _fingerprint(report: ChampionFreshnessReport) -> str:
    material = {**asdict(report), "report_fingerprint": ""}
    return hashlib.sha256(
        json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ChampionFreshnessError("Calibration freshness timestamp is missing.") from exc
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ChampionFreshnessError("The controlled clock must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
