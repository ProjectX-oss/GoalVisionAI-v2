import hashlib
from datetime import datetime

from app.prediction_inference import PredictionInferenceResult
from app.probability_calibration import ProbabilityCalibrationRequest, ProbabilityOrderingError

from .calibration_registry import CalibrationRegistry
from .exceptions import (
    CalibratedAssemblyConflictError, CalibratedAssemblyPersistenceError,
    IncompleteCalibrationSetError, IncompatibleCalibrationError,
    InvalidCalibratedOutputError, InvalidInferenceError,
)
from .fingerprint import assembly_fingerprint, report_fingerprint, target_result_fingerprint
from .models import (
    CalibratedAssemblyOutcome, CalibratedAssemblyStatus,
    CalibratedMarketProbabilityAssembly, CalibratedTargetResult,
    CalibrationTargetMapping,
)
from .policy import CalibratedMarketProbabilityPolicy
from .ports import (
    CalibratedAssemblyRepository, CalibrationSetRepository,
    ProbabilityCalibrationEngineFactory, RawInferenceReader,
)
from .validation import CalibratedAssemblyValidator


class CalibratedMarketProbabilityService:
    def __init__(
        self, inference_reader: RawInferenceReader, registry: CalibrationRegistry,
        calibration_set_repository: CalibrationSetRepository,
        assembly_repository: CalibratedAssemblyRepository,
        engine_factory: ProbabilityCalibrationEngineFactory,
        policy: CalibratedMarketProbabilityPolicy,
    ) -> None:
        self.inference_reader = inference_reader
        self.registry = registry
        self.calibration_set_repository = calibration_set_repository
        self.assembly_repository = assembly_repository
        self.engine_factory = engine_factory
        self.policy = policy
        self.validator = CalibratedAssemblyValidator()

    def generate(
        self, inference: PredictionInferenceResult | None, *,
        calibration_effective_timestamp: datetime,
        calibration_set_id: str | None = None,
        explicit_calibration_map: tuple[CalibrationTargetMapping, ...] | None = None,
    ) -> CalibratedAssemblyOutcome:
        inference_id = inference.inference_id if isinstance(inference, PredictionInferenceResult) else ""
        match_id = inference.match_id if isinstance(inference, PredictionInferenceResult) else ""
        artifact_id = inference.model_artifact_id if isinstance(inference, PredictionInferenceResult) else ""
        model_version = inference.model_version if isinstance(inference, PredictionInferenceResult) else ""
        try:
            persisted = self.inference_reader.load_inference_by_id(inference_id)
            source = self.validator.validate_inference(inference, persisted, calibration_effective_timestamp, self.policy)
        except InvalidInferenceError as exc:
            return self._failure(CalibratedAssemblyStatus.REJECTED_INVALID_INFERENCE, inference_id, match_id, artifact_id, model_version, calibration_set_id, calibration_effective_timestamp, exc.code, exc.explanation)
        except CalibratedAssemblyPersistenceError:
            return self._failure(CalibratedAssemblyStatus.PERSISTENCE_FAILURE, inference_id, match_id, artifact_id, model_version, calibration_set_id, calibration_effective_timestamp, "CALIBRATED_ASSEMBLY_PERSISTENCE_FAILURE", "Persistence failed safely.")
        try:
            plan = self.registry.resolve(source, calibration_set_id=calibration_set_id, explicit_map=explicit_calibration_map)
        except IncompleteCalibrationSetError as exc:
            return self._failure(CalibratedAssemblyStatus.REJECTED_INCOMPLETE_CALIBRATION_SET, inference_id, match_id, artifact_id, model_version, calibration_set_id, calibration_effective_timestamp, "INCOMPLETE_CALIBRATION_SET", str(exc))
        except IncompatibleCalibrationError as exc:
            return self._failure(CalibratedAssemblyStatus.REJECTED_INCOMPATIBLE_CALIBRATION, inference_id, match_id, artifact_id, model_version, calibration_set_id, calibration_effective_timestamp, "INCOMPATIBLE_CALIBRATION", str(exc))

        policy_versions = {item.calibration_policy_version for item in plan.ordered_artifacts}
        if len(policy_versions) != 1 and not self.policy.allow_mixed_calibration_policy_versions:
            return self._failure(CalibratedAssemblyStatus.REJECTED_INCOMPATIBLE_CALIBRATION, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, "MIXED_CALIBRATION_POLICIES", "Calibration policy versions cannot be mixed in v1.")
        try:
            if plan.set_definition is not None:
                self.calibration_set_repository.append_calibration_set(plan.set_definition)
        except CalibratedAssemblyConflictError as exc:
            return self._failure(CalibratedAssemblyStatus.CONFLICT, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, "CALIBRATION_SET_CONFLICT", str(exc))
        except CalibratedAssemblyPersistenceError:
            return self._failure(CalibratedAssemblyStatus.PERSISTENCE_FAILURE, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, "CALIBRATION_SET_PERSISTENCE_FAILURE", "Calibration-set persistence failed safely.")

        results = []
        try:
            for artifact in plan.ordered_artifacts:
                raw = source.raw_probabilities.probability_for(artifact.target)
                run_id = _id("calibration-run", source.inference_fingerprint, artifact.artifact_id, calibration_effective_timestamp.isoformat())
                request = ProbabilityCalibrationRequest(run_id, raw, artifact.historical_data, calibration_effective_timestamp, source.model_version)
                report = self.engine_factory.build(artifact.config).calibrate(request)
                calibrated = report.calibrated_probability.quantize(self.policy.probability_quantum, rounding=self.policy.rounding)
                report_reference = report_fingerprint(report)
                diagnostics = ("CALIBRATION_SUCCEEDED",)
                target_fingerprint = target_result_fingerprint(
                    target=artifact.target.value, raw=raw, calibrated=calibrated,
                    artifact=artifact, report_reference=report_reference,
                    diagnostics=diagnostics,
                )
                results.append(CalibratedTargetResult(
                    artifact.target, raw, calibrated, artifact.artifact_id,
                    artifact.method, artifact.calibration_model_version,
                    artifact.calibration_policy_version, report_reference,
                    artifact.quality_metadata_reference, None, diagnostics,
                    target_fingerprint,
                ))
        except (ValueError, ProbabilityOrderingError) as exc:
            return self._failure(CalibratedAssemblyStatus.CALIBRATION_EXECUTION_FAILED, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, "CALIBRATION_EXECUTION_FAILED", str(exc))

        ordered_results = tuple(results)
        try:
            validation = self.validator.validate_outputs(ordered_results, self.policy)
        except InvalidCalibratedOutputError as exc:
            return self._failure(CalibratedAssemblyStatus.REJECTED_INVALID_CALIBRATED_OUTPUT, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, exc.code, exc.explanation)
        fingerprint = assembly_fingerprint(
            inference_id=source.inference_id, raw_inference_fingerprint=source.inference_fingerprint,
            model_artifact_id=source.model_artifact_id, model_version=source.model_version,
            calibration_identity=plan.calibration_set_fingerprint, targets=ordered_results,
            policy_version=self.policy.version, effective_timestamp=calibration_effective_timestamp,
        )
        assembly = CalibratedMarketProbabilityAssembly(
            _id("calibrated-assembly", fingerprint), source.inference_id,
            source.model_input_id, source.match_id, source.source_snapshot_id,
            source.source_feature_set_id, source.model_artifact_id, source.model_name,
            source.model_version, source.inference_fingerprint, plan.calibration_set_id,
            plan.calibration_set_fingerprint, self.policy.version,
            calibration_effective_timestamp, calibration_effective_timestamp,
            ordered_results, validation, fingerprint,
        )
        try:
            existing = self.assembly_repository.find_by_assembly_fingerprint(fingerprint)
            if existing:
                return self._success(CalibratedAssemblyStatus.IDEMPOTENT_EXISTING, existing, "IDENTICAL_CALIBRATED_ASSEMBLY_EXISTS")
            stored, identical = self.assembly_repository.append_calibrated_assembly(assembly)
        except CalibratedAssemblyConflictError as exc:
            return self._failure(CalibratedAssemblyStatus.CONFLICT, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, "CALIBRATED_ASSEMBLY_CONFLICT", str(exc), fingerprint)
        except CalibratedAssemblyPersistenceError:
            return self._failure(CalibratedAssemblyStatus.PERSISTENCE_FAILURE, inference_id, match_id, artifact_id, model_version, plan.calibration_set_id, calibration_effective_timestamp, "CALIBRATED_ASSEMBLY_PERSISTENCE_FAILURE", "Persistence failed safely.", fingerprint)
        return self._success(CalibratedAssemblyStatus.IDEMPOTENT_EXISTING if identical else CalibratedAssemblyStatus.GENERATED, stored, "IDENTICAL_CALIBRATED_ASSEMBLY_EXISTS" if identical else "CALIBRATED_ASSEMBLY_GENERATED")

    def _success(self, status: CalibratedAssemblyStatus, value: CalibratedMarketProbabilityAssembly, code: str) -> CalibratedAssemblyOutcome:
        return CalibratedAssemblyOutcome(value.calibrated_assembly_id, value.inference_id, value.match_id, value.source_model_artifact_id, value.source_model_version, value.calibration_set_id, value.calibrated_assembly_fingerprint, status, (code,), ("Complete calibrated market probability assembly is available.",), value.ordered_target_results, value.calibration_effective_timestamp, value.assembly_policy_version)

    def _failure(self, status: CalibratedAssemblyStatus, inference_id: str, match_id: str, artifact_id: str, model_version: str, set_id: str | None, timestamp: datetime, code: str, explanation: str, fingerprint: str | None = None) -> CalibratedAssemblyOutcome:
        return CalibratedAssemblyOutcome(None, inference_id, match_id, artifact_id, model_version, set_id, fingerprint, status, (code,), (explanation,), (), timestamp, self.policy.version)


def generate_calibrated_market_probabilities(
    service: CalibratedMarketProbabilityService,
    inference: PredictionInferenceResult | None, *,
    calibration_effective_timestamp: datetime,
    calibration_set_id: str | None = None,
    explicit_calibration_map: tuple[CalibrationTargetMapping, ...] | None = None,
) -> CalibratedAssemblyOutcome:
    return service.generate(inference, calibration_effective_timestamp=calibration_effective_timestamp, calibration_set_id=calibration_set_id, explicit_calibration_map=explicit_calibration_map)


def _id(prefix: str, *parts: str) -> str:
    return prefix + "-" + hashlib.sha256("|".join(parts).encode()).hexdigest()
