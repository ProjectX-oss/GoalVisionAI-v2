from dataclasses import dataclass

from app.prediction_inference import PredictionInferenceResult, PredictionTarget
from app.probability_calibration import CalibrationMethod

from .exceptions import CalibrationRegistryError, IncompleteCalibrationSetError, IncompatibleCalibrationError
from .fingerprint import calibration_set_fingerprint, explicit_map_fingerprint
from .models import CalibrationArtifact, CalibrationSetDefinition, CalibrationTargetMapping, ResolvedCalibrationPlan
from .policy import CalibratedMarketProbabilityPolicy


@dataclass(frozen=True, slots=True)
class CalibrationRegistry:
    policy: CalibratedMarketProbabilityPolicy
    artifacts: tuple[CalibrationArtifact, ...] = ()
    calibration_sets: tuple[CalibrationSetDefinition, ...] = ()

    def register_artifact(self, artifact: CalibrationArtifact) -> "CalibrationRegistry":
        self._validate_artifact(artifact)
        if any(item.artifact_id == artifact.artifact_id for item in self.artifacts):
            raise CalibrationRegistryError("Calibration artifact ID is already registered.")
        if artifact.active and any(
            item.active and item.target is artifact.target
            and item.source_model_artifact_id == artifact.source_model_artifact_id
            and set(item.compatible_source_model_versions).intersection(artifact.compatible_source_model_versions)
            for item in self.artifacts
        ):
            raise CalibrationRegistryError("A conflicting active calibration mapping exists.")
        return CalibrationRegistry(self.policy, self.artifacts + (artifact,), self.calibration_sets)

    def define_set(
        self, *, calibration_set_id: str, set_name: str, set_version: str,
        source_model_artifact_id: str, compatible_source_model_versions: tuple[str, ...],
        mappings: tuple[CalibrationTargetMapping, ...], policy_version: str,
        active: bool, created_timestamp: object, effective_timestamp: object,
    ) -> "CalibrationRegistry":
        string_values = (
            calibration_set_id, set_name, set_version,
            source_model_artifact_id, policy_version,
        )
        if any(not isinstance(value, str) or not value.strip() for value in string_values):
            raise CalibrationRegistryError("Calibration set identity metadata is required.")
        if not compatible_source_model_versions:
            raise CalibrationRegistryError("Calibration set model compatibility is required.")
        if policy_version not in self.policy.supported_calibration_policy_versions:
            raise CalibrationRegistryError("Calibration set policy version is unsupported.")
        for value in (created_timestamp, effective_timestamp):
            if not hasattr(value, "tzinfo") or value.tzinfo is None:
                raise CalibrationRegistryError("Calibration set timestamps must be timezone-aware.")
        artifacts = self._resolve_mappings(mappings, allow_inactive=True)
        if any(item.source_model_artifact_id != source_model_artifact_id for item in artifacts):
            raise IncompatibleCalibrationError("Calibration artifact source model is incompatible with set.")
        if any(not set(item.compatible_source_model_versions).intersection(compatible_source_model_versions) for item in artifacts):
            raise IncompatibleCalibrationError("Calibration artifact model versions are incompatible with set.")
        fingerprint = calibration_set_fingerprint(
            set_id=calibration_set_id, set_version=set_version,
            source_model_artifact_id=source_model_artifact_id,
            compatible_versions=compatible_source_model_versions, mappings=mappings,
            artifacts=artifacts, policy_version=policy_version,
            effective_timestamp=effective_timestamp,
        )
        definition = CalibrationSetDefinition(
            calibration_set_id, set_name, set_version, source_model_artifact_id,
            compatible_source_model_versions, mappings, policy_version, active,
            created_timestamp, effective_timestamp, fingerprint,
        )
        if any(item.calibration_set_id == calibration_set_id for item in self.calibration_sets):
            raise CalibrationRegistryError("Calibration set ID is already registered.")
        return CalibrationRegistry(self.policy, self.artifacts, self.calibration_sets + (definition,))

    def resolve(
        self, inference: PredictionInferenceResult, *, calibration_set_id: str | None,
        explicit_map: tuple[CalibrationTargetMapping, ...] | None,
    ) -> ResolvedCalibrationPlan:
        if (calibration_set_id is None) == (explicit_map is None):
            raise IncompleteCalibrationSetError("Choose exactly one calibration resolution mode.")
        if explicit_map is not None:
            artifacts = self._resolve_mappings(explicit_map, allow_inactive=self.policy.allow_explicit_inactive_artifacts)
            self._compatible(inference, artifacts)
            return ResolvedCalibrationPlan(None, explicit_map_fingerprint(artifacts), artifacts, None)
        definition = next((item for item in self.calibration_sets if item.calibration_set_id == calibration_set_id), None)
        if definition is None:
            raise IncompleteCalibrationSetError("Unknown calibration set.")
        if not definition.active:
            raise IncompatibleCalibrationError("Inactive calibration sets are not automatically selectable.")
        if definition.source_model_artifact_id != inference.model_artifact_id or inference.model_version not in definition.compatible_source_model_versions:
            raise IncompatibleCalibrationError("Calibration set is incompatible with source model.")
        artifacts = self._resolve_mappings(definition.ordered_target_mappings, allow_inactive=False)
        self._compatible(inference, artifacts)
        return ResolvedCalibrationPlan(definition.calibration_set_id, definition.calibration_set_fingerprint, artifacts, definition)

    def _resolve_mappings(self, mappings: tuple[CalibrationTargetMapping, ...], *, allow_inactive: bool) -> tuple[CalibrationArtifact, ...]:
        if not isinstance(mappings, tuple) or tuple(item.target for item in mappings) != self.policy.target_order:
            raise IncompleteCalibrationSetError("Calibration mapping must cover canonical targets exactly once.")
        resolved = []
        for mapping in mappings:
            artifact = next((item for item in self.artifacts if item.artifact_id == mapping.calibration_artifact_id), None)
            if artifact is None:
                raise IncompleteCalibrationSetError("Calibration mapping references an unknown artifact.")
            if artifact.target is not mapping.target:
                raise IncompatibleCalibrationError("Calibration artifact target conflicts with mapping.")
            if not artifact.active and not allow_inactive:
                raise IncompatibleCalibrationError("Inactive calibration artifact cannot be selected.")
            resolved.append(artifact)
        return tuple(resolved)

    @staticmethod
    def _compatible(inference: PredictionInferenceResult, artifacts: tuple[CalibrationArtifact, ...]) -> None:
        if any(item.source_model_artifact_id != inference.model_artifact_id for item in artifacts):
            raise IncompatibleCalibrationError("Calibration artifact source model is incompatible.")
        if any(inference.model_version not in item.compatible_source_model_versions for item in artifacts):
            raise IncompatibleCalibrationError("Calibration artifact source model version is incompatible.")

    def _validate_artifact(self, value: CalibrationArtifact) -> None:
        if not value.artifact_id.strip() or not isinstance(value.target, PredictionTarget):
            raise CalibrationRegistryError("Calibration artifact identity/target is invalid.")
        if not isinstance(value.method, CalibrationMethod) or value.config.method is not value.method:
            raise CalibrationRegistryError("Calibration method is unsupported or conflicts with config.")
        if value.input_probability_schema != self.policy.input_probability_schema or value.input_probability_schema_version != self.policy.input_probability_schema_version:
            raise CalibrationRegistryError("Calibration input probability schema is unsupported.")
        if value.calibration_policy_version not in self.policy.supported_calibration_policy_versions:
            raise CalibrationRegistryError("Calibration policy version is unsupported.")
        if not value.compatible_source_model_versions:
            raise CalibrationRegistryError("Compatible source model versions are required.")
