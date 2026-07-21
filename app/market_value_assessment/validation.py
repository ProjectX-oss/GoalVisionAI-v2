"""Pre-calculation validation for calibrated and odds provenance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from app.calibrated_market_probabilities import (
    CalibratedMarketProbabilityAssembly,
)
from app.calibrated_market_probabilities.fingerprint import (
    assembly_fingerprint,
    digest as calibrated_digest,
)
from app.prediction_inference import OFFICIAL_TARGET_ORDER

from .exceptions import InvalidCalibrationError, ProvenanceMismatchError
from .models import MarketOddsSnapshot
from .policy import MarketValueAssessmentPolicy


def canonical_assessment_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProvenanceMismatchError(
            "Assessment timestamp must be timezone-aware."
        )
    if value.utcoffset() is None:
        raise ProvenanceMismatchError("Assessment timestamp must have a UTC offset.")
    return value.astimezone(timezone.utc)


def validate_calibrated_assembly(
    value: object,
    policy: MarketValueAssessmentPolicy,
) -> CalibratedMarketProbabilityAssembly:
    if not isinstance(value, CalibratedMarketProbabilityAssembly):
        raise InvalidCalibrationError("Calibrated assembly is required.")
    required_identifiers = (
        value.calibrated_assembly_id,
        value.inference_id,
        value.model_input_id,
        value.match_id,
        value.source_snapshot_id,
        value.source_feature_set_id,
        value.source_model_artifact_id,
        value.source_model_version,
        value.raw_inference_fingerprint,
        value.calibration_set_fingerprint,
        value.calibrated_assembly_fingerprint,
    )
    if any(not isinstance(item, str) or not item.strip() for item in required_identifiers):
        raise InvalidCalibrationError("Calibrated provenance is incomplete.")
    if value.assembly_policy_version not in policy.supported_assembly_policy_versions:
        raise InvalidCalibrationError("Calibrated assembly policy is unsupported.")
    if (
        not isinstance(value.calibration_effective_timestamp, datetime)
        or value.calibration_effective_timestamp.tzinfo is None
        or value.calibration_effective_timestamp.utcoffset() is None
    ):
        raise InvalidCalibrationError("Calibration timestamp is malformed.")

    targets = value.ordered_target_results
    if tuple(item.target for item in targets) != OFFICIAL_TARGET_ORDER:
        raise InvalidCalibrationError(
            "Calibrated targets are incomplete, duplicated, or reordered."
        )
    if any(
        not isinstance(item.calibrated_probability, Decimal)
        or not item.calibrated_probability.is_finite()
        or not Decimal(0) < item.calibrated_probability < Decimal(1)
        for item in targets
    ):
        raise InvalidCalibrationError("Calibrated probability is malformed.")

    summary = value.validation_summary
    if (
        summary.policy_version != value.assembly_policy_version
        or summary.target_count != len(OFFICIAL_TARGET_ORDER)
        or not summary.ordered_checks
        or any(not check.passed for check in summary.ordered_checks)
    ):
        raise InvalidCalibrationError("Calibrated validation summary is unsuccessful.")
    for item in targets:
        expected_target_fingerprint = calibrated_digest(
            {
                "version": "goalvision-calibrated-target-result-v1",
                "target": item.target.value,
                "raw": item.raw_probability,
                "calibrated": item.calibrated_probability,
                "artifact_id": item.calibration_artifact_id,
                "method": item.calibration_method.value,
                "calibration_version": item.calibration_model_version,
                "policy_version": item.calibration_policy_version,
                "report_reference": item.calibration_report_fingerprint,
                "diagnostics": item.diagnostics,
            }
        )
        if expected_target_fingerprint != item.target_result_fingerprint:
            raise InvalidCalibrationError(
                "Calibrated target fingerprint verification failed."
            )

    expected_assembly_fingerprint = assembly_fingerprint(
        inference_id=value.inference_id,
        raw_inference_fingerprint=value.raw_inference_fingerprint,
        model_artifact_id=value.source_model_artifact_id,
        model_version=value.source_model_version,
        calibration_identity=value.calibration_set_fingerprint,
        targets=targets,
        policy_version=value.assembly_policy_version,
        effective_timestamp=value.calibration_effective_timestamp,
    )
    if expected_assembly_fingerprint != value.calibrated_assembly_fingerprint:
        raise InvalidCalibrationError(
            "Calibrated assembly fingerprint verification failed."
        )
    expected_id = "calibrated-assembly-" + hashlib.sha256(
        expected_assembly_fingerprint.encode("utf-8")
    ).hexdigest()
    if value.calibrated_assembly_id != expected_id:
        raise InvalidCalibrationError("Calibrated assembly identity is malformed.")
    return value


def validate_provenance(
    assembly: CalibratedMarketProbabilityAssembly,
    odds: MarketOddsSnapshot,
    persisted_kickoff: datetime | None,
    assessment_timestamp: object,
    policy: MarketValueAssessmentPolicy,
) -> datetime:
    timestamp = canonical_assessment_timestamp(assessment_timestamp)
    if (
        persisted_kickoff is None
        or persisted_kickoff.tzinfo is None
        or persisted_kickoff.utcoffset() is None
    ):
        raise ProvenanceMismatchError("Persisted kickoff provenance is unavailable.")
    canonical_kickoff = persisted_kickoff.astimezone(timezone.utc)
    if odds.match_id != assembly.match_id or odds.kickoff_timestamp != canonical_kickoff:
        raise ProvenanceMismatchError(
            "Odds match or kickoff conflicts with calibrated provenance."
        )
    effective_times = (
        assembly.calibration_effective_timestamp.astimezone(timezone.utc),
        odds.odds_effective_timestamp,
        odds.registration_timestamp,
    )
    if timestamp < max(effective_times) or timestamp >= odds.kickoff_timestamp:
        raise ProvenanceMismatchError(
            "Assessment timestamp contradicts effective data, registration, or kickoff."
        )
    if (
        not policy.allow_odds_older_than_calibration
        and odds.odds_effective_timestamp < effective_times[0]
    ):
        raise ProvenanceMismatchError(
            "Odds predate calibration under the current policy."
        )
    return timestamp
