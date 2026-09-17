import re
from datetime import datetime
from decimal import Decimal

from app.model_input_builder import (
    GOALVISION_MODEL_INPUT_V1,
    ModelInputFingerprint,
    ModelInputVector,
)

from .exceptions import IncompatibleModelError, InferenceInputValidationError, InvalidModelOutputError
from .models import (
    InferenceValidationSummary,
    MissingValueSupport,
    ModelAdapterOutput,
    PredictionTarget,
    ProbabilityValidationCheck,
    RawProbability,
    RawProbabilitySet,
    RegisteredPredictionModel,
    PersistedModelInputIdentity,
)
from .policy import PredictionInferencePolicy


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PredictionInferenceInputValidator:
    """Validates immutable model-input content, provenance, and adapter contract."""

    def validate(
        self,
        model_input: ModelInputVector | None,
        persisted: PersistedModelInputIdentity | None,
        model: RegisteredPredictionModel,
        inference_timestamp: datetime,
        policy: PredictionInferencePolicy,
    ) -> ModelInputVector:
        if not isinstance(model_input, ModelInputVector):
            self._invalid("MODEL_INPUT_REQUIRED", "An immutable ModelInputVector is required.")
        assert model_input is not None
        if persisted is None:
            self._invalid("MODEL_INPUT_NOT_PERSISTED", "Model input is not persisted.")
        assert persisted is not None
        if not isinstance(inference_timestamp, datetime) or inference_timestamp.tzinfo is None:
            self._invalid("INVALID_INFERENCE_TIMESTAMP", "Inference timestamp must be timezone-aware.")
        if model_input.created_timestamp.tzinfo is None:
            self._invalid("INVALID_MODEL_INPUT_TIMESTAMP", "Model-input timestamp must be timezone-aware.")
        if inference_timestamp < model_input.created_timestamp:
            self._invalid("INFERENCE_TIMESTAMP_BEFORE_INPUT", "Inference timestamp precedes the model-input effective timestamp.")

        if model_input.schema_name != policy.supported_input_schema_name:
            self._invalid("UNSUPPORTED_INPUT_SCHEMA", "Model-input schema is unsupported.")
        if model_input.schema_version != policy.supported_input_schema_version:
            self._invalid("UNSUPPORTED_INPUT_SCHEMA_VERSION", "Model-input schema version is unsupported.")
        if model_input.compatibility_version not in policy.supported_compatibility_versions:
            self._invalid("UNSUPPORTED_COMPATIBILITY_VERSION", "Model-input compatibility version is unsupported.")
        self._persisted_identity(model_input, persisted)

        expected = GOALVISION_MODEL_INPUT_V1.ordered_feature_names
        if len(model_input.ordered_feature_names) != len(expected):
            self._invalid("INVALID_FEATURE_COUNT", "Ordered feature count is invalid.")
        if len(set(model_input.ordered_feature_names)) != len(model_input.ordered_feature_names):
            self._invalid("DUPLICATE_FEATURE_NAME", "Ordered feature names contain duplicates.")
        if model_input.ordered_feature_names != expected:
            self._invalid("INVALID_FEATURE_ORDER", "Feature ordering differs from the model schema.")
        if len(model_input.ordered_feature_values) != len(expected):
            self._invalid("INVALID_FEATURE_VALUE_COUNT", "Ordered feature value count is invalid.")
        if len(model_input.missingness_mask) != len(expected):
            self._invalid("INVALID_MISSINGNESS_LENGTH", "Missingness mask length is invalid.")

        missing_names: list[str] = []
        for name, value, missing in zip(
            model_input.ordered_feature_names,
            model_input.ordered_feature_values,
            model_input.missingness_mask,
            strict=True,
        ):
            if not isinstance(missing, bool):
                self._invalid("UNSUPPORTED_MISSINGNESS_STATE", f"Missingness for {name} must be boolean.")
            if missing != (value is None):
                self._invalid("MISSINGNESS_VALUE_MISMATCH", f"Missingness and value disagree for {name}.")
            if missing:
                missing_names.append(name)
                if name in policy.required_feature_names:
                    self._invalid("REQUIRED_BASELINE_FEATURE_MISSING", f"Required baseline feature {name} is missing.")
        if tuple(missing_names) != model_input.missing_feature_names:
            self._invalid("MISSING_FEATURE_LIST_MISMATCH", "Missing-feature list does not match the ordered mask.")
        if missing_names and model.missing_value_support is MissingValueSupport.NONE:
            self._incompatible("MODEL_MISSINGNESS_UNSUPPORTED", "Selected model does not support missing optional features.")

        recalculated = ModelInputFingerprint().calculate(
            schema_name=model_input.schema_name,
            schema_version=model_input.schema_version,
            compatibility_version=model_input.compatibility_version,
            ordered_feature_names=model_input.ordered_feature_names,
            ordered_feature_values=model_input.ordered_feature_values,
            missingness_mask=model_input.missingness_mask,
            source_feature_fingerprint=model_input.source_feature_fingerprint,
        )
        if not _SHA256.fullmatch(model_input.model_input_fingerprint) or recalculated != model_input.model_input_fingerprint:
            self._invalid("MODEL_INPUT_FINGERPRINT_MISMATCH", "Model-input content does not match its canonical fingerprint.")

        self._adapter_metadata(model, policy)
        return model_input

    @classmethod
    def _persisted_identity(cls, value: ModelInputVector, persisted: PersistedModelInputIdentity) -> None:
        comparisons = (
            (value.model_input_id, persisted.model_input_id, "MODEL_INPUT_ID_MISMATCH"),
            (value.feature_set_id, persisted.feature_set_id, "FEATURE_SET_ID_MISMATCH"),
            (value.snapshot_id, persisted.snapshot_id, "SNAPSHOT_ID_MISMATCH"),
            (value.match_id, persisted.match_id, "MATCH_ID_MISMATCH"),
            (value.schema_name, persisted.schema_name, "PERSISTED_SCHEMA_MISMATCH"),
            (value.schema_version, persisted.schema_version, "PERSISTED_SCHEMA_VERSION_MISMATCH"),
            (value.compatibility_version, persisted.compatibility_version, "PERSISTED_COMPATIBILITY_MISMATCH"),
            (value.feature_fingerprint, persisted.feature_fingerprint, "FEATURE_FINGERPRINT_MISMATCH"),
            (value.source_snapshot_fingerprint, persisted.source_snapshot_fingerprint, "SOURCE_SNAPSHOT_FINGERPRINT_MISMATCH"),
            (value.source_feature_fingerprint, persisted.source_feature_fingerprint, "SOURCE_FEATURE_FINGERPRINT_MISMATCH"),
            (value.model_input_fingerprint, persisted.model_input_fingerprint, "PERSISTED_FINGERPRINT_MISMATCH"),
            (value.created_timestamp, persisted.effective_timestamp, "PERSISTED_TIMESTAMP_MISMATCH"),
        )
        for actual, expected, code in comparisons:
            if actual != expected:
                cls._invalid(code, "Model-input source provenance is inconsistent with persistence.")

    @classmethod
    def _adapter_metadata(cls, model: RegisteredPredictionModel, policy: PredictionInferencePolicy) -> None:
        adapter = model.adapter
        comparisons = (
            (getattr(adapter, "model_artifact_id"), model.model_artifact_id),
            (getattr(adapter, "model_name"), model.model_name),
            (getattr(adapter, "model_version"), model.model_version),
            (getattr(adapter, "model_family"), model.model_family),
            (getattr(adapter, "input_schema_name"), model.input_schema_name),
            (getattr(adapter, "input_schema_version"), model.input_schema_version),
            (getattr(adapter, "compatibility_version"), model.compatibility_version),
            (getattr(adapter, "supported_targets"), model.supported_targets),
            (getattr(adapter, "missing_value_support"), model.missing_value_support),
        )
        if any(actual != expected for actual, expected in comparisons):
            cls._incompatible("MODEL_ADAPTER_METADATA_CONFLICT", "Adapter metadata conflicts with its immutable registry entry.")
        if model.supported_targets != policy.required_targets:
            cls._incompatible("MODEL_TARGET_SUPPORT_INCOMPLETE", "Model does not support every required Official target.")

    @staticmethod
    def _invalid(code: str, explanation: str) -> None:
        raise InferenceInputValidationError(code, explanation)

    @staticmethod
    def _incompatible(code: str, explanation: str) -> None:
        raise IncompatibleModelError(code, explanation)


class RawProbabilityValidator:
    """Converts adapter values to canonical Decimals and fails closed on inconsistency."""

    def validate(
        self,
        outputs: tuple[ModelAdapterOutput, ...],
        policy: PredictionInferencePolicy,
    ) -> tuple[RawProbabilitySet, InferenceValidationSummary]:
        if not isinstance(outputs, tuple):
            self._invalid("MALFORMED_ADAPTER_OUTPUT", "Adapter output must be an ordered tuple.")
        values: dict[PredictionTarget, Decimal] = {}
        for output in outputs:
            if not isinstance(output, ModelAdapterOutput):
                self._invalid("MALFORMED_ADAPTER_OUTPUT", "Every output must be a ModelAdapterOutput.")
            if not isinstance(output.target, PredictionTarget):
                self._invalid("UNKNOWN_TARGET", "Adapter returned an unknown or untyped target.")
            if output.target in values:
                self._invalid("DUPLICATE_TARGET", f"Adapter returned duplicate target {output.target.value}.")
            values[output.target] = self._decimal(output.value, output.target, policy)
        unknown = tuple(target for target in values if target not in policy.required_targets)
        if unknown:
            self._invalid("UNKNOWN_TARGET", f"Adapter returned unknown target {unknown[0].value}.")
        missing = tuple(target for target in policy.required_targets if target not in values)
        if missing:
            self._invalid("MISSING_TARGET", f"Adapter omitted required target {missing[0].value}.")

        canonical = {
            target: values[target].quantize(policy.probability_quantum, rounding=policy.rounding)
            for target in policy.required_targets
        }
        ordered = RawProbabilitySet(tuple(RawProbability(target, canonical[target]) for target in policy.required_targets))
        checks = (
            self._sum_check("MATCH_RESULT_SUM", canonical, (PredictionTarget.HOME_WIN, PredictionTarget.DRAW, PredictionTarget.AWAY_WIN), policy.group_sum_tolerance),
            self._sum_check("TOTAL_1_5_SUM", canonical, (PredictionTarget.OVER_1_5, PredictionTarget.UNDER_1_5), policy.group_sum_tolerance),
            self._sum_check("TOTAL_2_5_SUM", canonical, (PredictionTarget.OVER_2_5, PredictionTarget.UNDER_2_5), policy.group_sum_tolerance),
            self._sum_check("TOTAL_3_5_SUM", canonical, (PredictionTarget.OVER_3_5, PredictionTarget.UNDER_3_5), policy.group_sum_tolerance),
            self._sum_check("BTTS_SUM", canonical, (PredictionTarget.BTTS_YES, PredictionTarget.BTTS_NO), policy.group_sum_tolerance),
            self._monotonic_check("OVER_TOTALS_MONOTONIC", canonical[PredictionTarget.OVER_1_5], canonical[PredictionTarget.OVER_2_5], canonical[PredictionTarget.OVER_3_5], policy.monotonicity_tolerance, descending=True),
            self._monotonic_check("UNDER_TOTALS_MONOTONIC", canonical[PredictionTarget.UNDER_1_5], canonical[PredictionTarget.UNDER_2_5], canonical[PredictionTarget.UNDER_3_5], policy.monotonicity_tolerance, descending=False),
        )
        failed = next((check for check in checks if not check.passed), None)
        if failed is not None:
            self._invalid(failed.code, f"Probability consistency check {failed.code} failed.")
        return ordered, InferenceValidationSummary(policy.version, len(ordered.ordered_probabilities), checks)

    @staticmethod
    def _decimal(
        value: object,
        target: PredictionTarget,
        policy: PredictionInferencePolicy,
    ) -> Decimal:
        if not isinstance(value, Decimal):
            raise InvalidModelOutputError("MALFORMED_DECIMAL", f"{target.value} must be a Decimal.")
        if not value.is_finite():
            raise InvalidModelOutputError("NON_FINITE_PROBABILITY", f"{target.value} must be finite.")
        if value < policy.minimum_probability or value > policy.maximum_probability:
            raise InvalidModelOutputError(
                "PROBABILITY_OUT_OF_RANGE",
                f"{target.value} is outside the configured probability range.",
            )
        return value

    @staticmethod
    def _sum_check(code: str, values: dict[PredictionTarget, Decimal], targets: tuple[PredictionTarget, ...], tolerance: Decimal) -> ProbabilityValidationCheck:
        observed = sum((values[target] for target in targets), Decimal(0))
        return ProbabilityValidationCheck(code, abs(observed - Decimal(1)) <= tolerance, observed, tolerance)

    @staticmethod
    def _monotonic_check(code: str, first: Decimal, second: Decimal, third: Decimal, tolerance: Decimal, *, descending: bool) -> ProbabilityValidationCheck:
        if descending:
            passed = first + tolerance >= second and second + tolerance >= third
        else:
            passed = first <= second + tolerance and second <= third + tolerance
        violation = max(second - first, third - second, Decimal(0)) if descending else max(first - second, second - third, Decimal(0))
        return ProbabilityValidationCheck(code, passed, violation, tolerance)

    @staticmethod
    def _invalid(code: str, explanation: str) -> None:
        raise InvalidModelOutputError(code, explanation)
