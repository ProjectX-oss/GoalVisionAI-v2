import hashlib
from datetime import datetime

from app.model_input_builder import ModelInputVector

from .exceptions import (
    IncompatibleModelError,
    InferenceConflictError,
    InferenceInputValidationError,
    InferencePersistenceError,
    InvalidModelOutputError,
    ModelAdapterCompatibilityError,
    ModelAdapterExecutionError,
    ModelRegistryError,
)
from .fingerprint import PredictionInferenceFingerprint
from .model_registry import PredictionModelRegistry
from .models import (
    InferenceGenerationOutcome,
    InferenceGenerationStatus,
    PredictionInferenceResult,
    RegisteredPredictionModel,
)
from .policy import PredictionInferencePolicy
from .ports import PredictionInferenceRepository
from .validation import PredictionInferenceInputValidator, RawProbabilityValidator


class PredictionInferenceService:
    """Explicit deterministic boundary from one model input to raw probabilities."""

    def __init__(
        self,
        repository: PredictionInferenceRepository,
        registry: PredictionModelRegistry,
        policy: PredictionInferencePolicy,
        input_validator: PredictionInferenceInputValidator,
        output_validator: RawProbabilityValidator,
        fingerprints: PredictionInferenceFingerprint,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.policy = policy
        self._input_validator = input_validator
        self._output_validator = output_validator
        self._fingerprints = fingerprints

    def generate_raw_prediction(
        self,
        model_input: ModelInputVector | None,
        *,
        model_artifact_id: str | None,
        inference_timestamp: datetime,
    ) -> InferenceGenerationOutcome:
        if isinstance(model_input, ModelInputVector):
            model_input_id = model_input.model_input_id
            match_id = model_input.match_id
        else:
            model_input_id = ""
            match_id = ""
        try:
            model = self.registry.select(model_artifact_id)
        except ModelRegistryError as exc:
            return self._outcome(
                InferenceGenerationStatus.REJECTED_INCOMPATIBLE_MODEL,
                model_input_id,
                match_id,
                model_artifact_id or "",
                "",
                inference_timestamp,
                "UNKNOWN_MODEL_ARTIFACT",
                str(exc),
            )
        try:
            persisted = self.repository.load_model_input_identity(model_input_id)
            validated = self._input_validator.validate(
                model_input, persisted, model, inference_timestamp, self.policy
            )
        except InferenceInputValidationError as exc:
            return self._error_outcome(
                InferenceGenerationStatus.REJECTED_INVALID_INPUT,
                model_input_id,
                match_id,
                model,
                inference_timestamp,
                exc,
            )
        except IncompatibleModelError as exc:
            return self._error_outcome(
                InferenceGenerationStatus.REJECTED_INCOMPATIBLE_MODEL,
                model_input_id,
                match_id,
                model,
                inference_timestamp,
                exc,
            )
        except InferencePersistenceError:
            return self._outcome(
                InferenceGenerationStatus.PERSISTENCE_FAILURE,
                model_input_id,
                match_id,
                model.model_artifact_id,
                model.model_version,
                inference_timestamp,
                "INFERENCE_PERSISTENCE_FAILURE",
                "Inference persistence failed safely.",
            )

        try:
            model.adapter.validate_compatibility(validated)
        except ModelAdapterCompatibilityError as exc:
            return self._outcome(
                InferenceGenerationStatus.REJECTED_INCOMPATIBLE_MODEL,
                model_input_id,
                match_id,
                model.model_artifact_id,
                model.model_version,
                inference_timestamp,
                "MODEL_ADAPTER_INCOMPATIBLE",
                str(exc),
            )
        try:
            adapter_output = model.adapter.infer(validated)
        except ModelAdapterExecutionError as exc:
            return self._outcome(
                InferenceGenerationStatus.MODEL_EXECUTION_FAILED,
                model_input_id,
                match_id,
                model.model_artifact_id,
                model.model_version,
                inference_timestamp,
                "MODEL_EXECUTION_FAILED",
                str(exc),
            )
        try:
            raw_probabilities, validation = self._output_validator.validate(
                adapter_output,
                self.policy,
            )
        except InvalidModelOutputError as exc:
            return self._error_outcome(
                InferenceGenerationStatus.REJECTED_INVALID_OUTPUT,
                model_input_id,
                match_id,
                model,
                inference_timestamp,
                exc,
            )

        fingerprint = self._fingerprints.calculate(
            model_input_id=validated.model_input_id,
            model_input_fingerprint=validated.model_input_fingerprint,
            match_id=validated.match_id,
            model=model,
            raw_probabilities=raw_probabilities,
            inference_timestamp=inference_timestamp,
            policy_version=self.policy.version,
        )
        result = PredictionInferenceResult(
            inference_id=_inference_id(fingerprint),
            model_input_id=validated.model_input_id,
            match_id=validated.match_id,
            source_snapshot_id=validated.snapshot_id,
            source_feature_set_id=validated.feature_set_id,
            model_artifact_id=model.model_artifact_id,
            model_name=model.model_name,
            model_version=model.model_version,
            model_family=model.model_family,
            input_schema_name=model.input_schema_name,
            input_schema_version=model.input_schema_version,
            compatibility_version=model.compatibility_version,
            policy_version=self.policy.version,
            inference_timestamp=inference_timestamp,
            created_timestamp=inference_timestamp,
            raw_probabilities=raw_probabilities,
            validation_summary=validation,
            model_input_fingerprint=validated.model_input_fingerprint,
            inference_fingerprint=fingerprint,
        )
        try:
            existing = self.repository.find_by_inference_fingerprint(fingerprint)
            if existing is not None:
                return self._success_outcome(
                    InferenceGenerationStatus.IDEMPOTENT_EXISTING,
                    existing,
                    "IDENTICAL_INFERENCE_EXISTS",
                    "Identical immutable inference already exists.",
                )
            stored, identical = self.repository.append_inference_result(result)
        except InferenceConflictError as exc:
            return self._outcome(
                InferenceGenerationStatus.CONFLICT,
                model_input_id,
                match_id,
                model.model_artifact_id,
                model.model_version,
                inference_timestamp,
                "INFERENCE_CONFLICT",
                str(exc),
                fingerprint=fingerprint,
            )
        except InferencePersistenceError:
            return self._outcome(
                InferenceGenerationStatus.PERSISTENCE_FAILURE,
                model_input_id,
                match_id,
                model.model_artifact_id,
                model.model_version,
                inference_timestamp,
                "INFERENCE_PERSISTENCE_FAILURE",
                "Inference persistence failed safely.",
                fingerprint=fingerprint,
            )
        if identical:
            return self._success_outcome(
                InferenceGenerationStatus.IDEMPOTENT_EXISTING,
                stored,
                "IDENTICAL_INFERENCE_EXISTS",
                "Concurrent identical inference reused the stored result.",
            )
        return self._success_outcome(
            InferenceGenerationStatus.GENERATED,
            stored,
            "RAW_INFERENCE_GENERATED",
            "Immutable raw prediction inference was appended.",
        )

    def _error_outcome(
        self,
        status: InferenceGenerationStatus,
        model_input_id: str,
        match_id: str,
        model: RegisteredPredictionModel,
        timestamp: datetime,
        exc: InferenceInputValidationError
        | IncompatibleModelError
        | InvalidModelOutputError,
    ) -> InferenceGenerationOutcome:
        return self._outcome(
            status,
            model_input_id,
            match_id,
            model.model_artifact_id,
            model.model_version,
            timestamp,
            exc.reason_code,
            exc.explanation,
        )

    def _success_outcome(
        self,
        status: InferenceGenerationStatus,
        result: PredictionInferenceResult,
        code: str,
        explanation: str,
    ) -> InferenceGenerationOutcome:
        return InferenceGenerationOutcome(
            inference_id=result.inference_id,
            model_input_id=result.model_input_id,
            match_id=result.match_id,
            model_artifact_id=result.model_artifact_id,
            model_version=result.model_version,
            inference_fingerprint=result.inference_fingerprint,
            final_status=status,
            ordered_reason_codes=(code,),
            explanations=(explanation,),
            raw_probability_set=result.raw_probabilities,
            inference_timestamp=result.inference_timestamp,
            policy_version=result.policy_version,
        )

    def _outcome(
        self,
        status: InferenceGenerationStatus,
        model_input_id: str,
        match_id: str,
        artifact_id: str,
        version: str,
        timestamp: datetime,
        code: str,
        explanation: str,
        *,
        fingerprint: str | None = None,
    ) -> InferenceGenerationOutcome:
        return InferenceGenerationOutcome(
            inference_id=None,
            model_input_id=model_input_id,
            match_id=match_id,
            model_artifact_id=artifact_id,
            model_version=version,
            inference_fingerprint=fingerprint,
            final_status=status,
            ordered_reason_codes=(code,),
            explanations=(explanation,),
            raw_probability_set=None,
            inference_timestamp=timestamp,
            policy_version=self.policy.version,
        )


def generate_raw_prediction(
    service: PredictionInferenceService,
    model_input: ModelInputVector | None,
    *,
    model_artifact_id: str | None,
    inference_timestamp: datetime,
) -> InferenceGenerationOutcome:
    """Run one explicitly timed, explicitly selected raw model inference."""
    return service.generate_raw_prediction(
        model_input,
        model_artifact_id=model_artifact_id,
        inference_timestamp=inference_timestamp,
    )


def _inference_id(fingerprint: str) -> str:
    material = ("goalvision-inference-id-v1|" + fingerprint).encode("utf-8")
    return "inference-" + hashlib.sha256(material).hexdigest()
