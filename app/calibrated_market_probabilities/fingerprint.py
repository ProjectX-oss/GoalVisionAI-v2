import hashlib
import json

from app.match_data_snapshot import canonical_data
from app.probability_calibration import ProbabilityCalibrationReport

from .models import (
    CalibratedTargetResult,
    CalibrationArtifact,
    CalibrationSetDefinition,
    CalibrationTargetMapping,
)


def digest(material: dict[str, object]) -> str:
    payload = json.dumps(canonical_data(material), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def calibration_set_fingerprint(
    *, set_id: str, set_version: str, source_model_artifact_id: str,
    compatible_versions: tuple[str, ...], mappings: tuple[CalibrationTargetMapping, ...],
    artifacts: tuple[CalibrationArtifact, ...], policy_version: str,
    effective_timestamp: object,
) -> str:
    return digest({
        "version": "goalvision-calibration-set-fingerprint-v1",
        "calibration_set_id": set_id,
        "set_version": set_version,
        "source_model_artifact_id": source_model_artifact_id,
        "compatible_source_model_versions": compatible_versions,
        "ordered_mappings": tuple((item.target.value, item.calibration_artifact_id) for item in mappings),
        "artifact_metadata": tuple(_artifact_identity(item) for item in artifacts),
        "policy_version": policy_version,
        "effective_timestamp": effective_timestamp,
    })


def explicit_map_fingerprint(artifacts: tuple[CalibrationArtifact, ...]) -> str:
    return digest({
        "version": "goalvision-explicit-calibration-map-v1",
        "ordered_artifacts": tuple(_artifact_identity(item) for item in artifacts),
    })


def report_fingerprint(report: ProbabilityCalibrationReport) -> str:
    return digest({
        "version": "goalvision-calibration-report-reference-v1",
        "run_id": report.calibration_run_id,
        "raw_probability": report.raw_probability,
        "calibrated_probability": report.calibrated_probability,
        "method": report.calibration_method.value,
        "model_version": report.model_version,
        "calibration_version": report.calibration_version,
        "timestamp": report.timestamp,
        "metrics": report.metric_summary,
    })


def target_result_fingerprint(
    *, target: object, raw: object, calibrated: object, artifact: CalibrationArtifact,
    report_reference: str, diagnostics: tuple[str, ...],
) -> str:
    return digest({
        "version": "goalvision-calibrated-target-result-v1",
        "target": target, "raw": raw, "calibrated": calibrated,
        "artifact_id": artifact.artifact_id, "method": artifact.method.value,
        "calibration_version": artifact.calibration_model_version,
        "policy_version": artifact.calibration_policy_version,
        "report_reference": report_reference, "diagnostics": diagnostics,
    })


def assembly_fingerprint(
    *, inference_id: str, raw_inference_fingerprint: str, model_artifact_id: str,
    model_version: str, calibration_identity: str,
    targets: tuple[CalibratedTargetResult, ...], policy_version: str,
    effective_timestamp: object,
) -> str:
    return digest({
        "version": "goalvision-calibrated-assembly-v1",
        "inference_id": inference_id,
        "raw_inference_fingerprint": raw_inference_fingerprint,
        "model_artifact_id": model_artifact_id,
        "model_version": model_version,
        "calibration_identity": calibration_identity,
        "ordered_target_fingerprints": tuple(item.target_result_fingerprint for item in targets),
        "policy_version": policy_version,
        "effective_timestamp": effective_timestamp,
    })


def _artifact_identity(value: CalibrationArtifact) -> tuple[object, ...]:
    return (
        value.artifact_id, value.target.value, value.method.value,
        value.calibration_model_version, value.source_model_artifact_id,
        value.compatible_source_model_versions, value.input_probability_schema,
        value.input_probability_schema_version, value.calibration_policy_version,
        value.training_data_cutoff, value.fitted_timestamp,
        value.quality_metadata_reference, value.compatibility_metadata,
        value.config, value.historical_data,
    )
