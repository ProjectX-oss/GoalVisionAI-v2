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
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
)
from app.market_value_assessment import (
    DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY,
)
from app.model_activation import (
    ActivationStatus,
    build_runtime_champion_resolver,
)
from app.model_activation_audit import ModelActivationAuditService
from app.model_activation_audit.repository import ReadOnlyAuditRepository

from .models import ChampionFreshnessReport


REPORT_SCHEMA_VERSION = "goalvision-live-78-champion-freshness-report-v1"


class ChampionFreshnessError(RuntimeError):
    """Raised when any report input or persisted reference fails closed."""


def calibration_freshness_status(
    reference_timestamp: datetime,
    controlled_now: datetime,
) -> tuple[int, int, str]:
    """Classify the exact runtime freshness reference under current policy."""
    reference = _utc(reference_timestamp)
    now = _utc(controlled_now)
    age = int((now - reference).total_seconds())
    maximum = DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY.calibrated_aging_seconds
    if age < 0 or age > maximum:
        raise ChampionFreshnessError("The active champion calibration is not fresh.")
    status = (
        "FRESH"
        if age
        <= DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY.calibrated_fresh_seconds
        else "AGING"
    )
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
    reference_at = _parse_utc(calibration.command.calibration_timestamp)
    age, maximum, freshness = calibration_freshness_status(reference_at, now)
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
        _format_utc(reference_at),
        _format_utc(now),
        age,
        maximum,
        freshness,
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
