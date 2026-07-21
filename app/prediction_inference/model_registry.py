from dataclasses import dataclass

from .exceptions import ModelRegistryError
from .models import PredictionTarget, RegisteredPredictionModel
from .policy import PredictionInferencePolicy
from .ports import PredictionModelAdapter


@dataclass(frozen=True, slots=True)
class PredictionModelRegistry:
    """Functional registry with explicit artifact and active-model selection."""

    policy: PredictionInferencePolicy
    _registered_models: tuple[RegisteredPredictionModel, ...] = ()
    _active_official_artifact_id: str | None = None

    @property
    def registered_models(self) -> tuple[RegisteredPredictionModel, ...]:
        return self._registered_models

    @property
    def active_official_artifact_id(self) -> str | None:
        return self._active_official_artifact_id

    def register(
        self,
        adapter: PredictionModelAdapter,
        *,
        active_official: bool = False,
    ) -> "PredictionModelRegistry":
        registered = self._registration(adapter)
        if any(
            item.model_artifact_id == registered.model_artifact_id
            for item in self._registered_models
        ):
            raise ModelRegistryError("Model artifact ID is already registered.")
        if any(
            (item.model_name, item.model_version)
            == (registered.model_name, registered.model_version)
            for item in self._registered_models
        ):
            raise ModelRegistryError("Model name/version is already registered.")
        active = self._active_official_artifact_id
        if active_official:
            if active is not None and active != registered.model_artifact_id:
                raise ModelRegistryError(
                    "An active Official pre-match model is already configured."
                )
            active = registered.model_artifact_id
        return PredictionModelRegistry(
            self.policy,
            self._registered_models + (registered,),
            active,
        )

    def with_active_official(
        self,
        model_artifact_id: str,
    ) -> "PredictionModelRegistry":
        self.select(model_artifact_id)
        return PredictionModelRegistry(
            self.policy,
            self._registered_models,
            model_artifact_id,
        )

    def select(
        self,
        model_artifact_id: str | None = None,
    ) -> RegisteredPredictionModel:
        selected = model_artifact_id or self._active_official_artifact_id
        if selected is None:
            raise ModelRegistryError(
                "Model selection requires an artifact ID or configured active model."
            )
        for item in self._registered_models:
            if item.model_artifact_id == selected:
                return item
        raise ModelRegistryError("Unknown model artifact ID.")

    def _registration(
        self,
        adapter: PredictionModelAdapter,
    ) -> RegisteredPredictionModel:
        string_values = (
            ("artifact ID", adapter.model_artifact_id),
            ("name", adapter.model_name),
            ("version", adapter.model_version),
            ("family", adapter.model_family),
            ("input schema name", adapter.input_schema_name),
            ("input schema version", adapter.input_schema_version),
            ("compatibility version", adapter.compatibility_version),
        )
        if any(
            not isinstance(value, str) or not value.strip()
            for _, value in string_values
        ):
            raise ModelRegistryError("All model adapter metadata strings are required.")
        if adapter.input_schema_name != self.policy.supported_input_schema_name:
            raise ModelRegistryError("Model adapter input schema is unsupported.")
        if adapter.input_schema_version != self.policy.supported_input_schema_version:
            raise ModelRegistryError("Model adapter input schema version is unsupported.")
        if (
            adapter.compatibility_version
            not in self.policy.supported_compatibility_versions
        ):
            raise ModelRegistryError("Model adapter compatibility version is unsupported.")
        targets = adapter.supported_targets
        if not isinstance(targets, tuple) or any(
            not isinstance(target, PredictionTarget)
            for target in targets
        ):
            raise ModelRegistryError("Model supported targets must be typed and ordered.")
        if len(targets) != len(set(targets)):
            raise ModelRegistryError("Model supported targets contain duplicates.")
        if targets != self.policy.required_targets:
            raise ModelRegistryError(
                "Model must support every Official target in canonical order."
            )
        if (
            adapter.missing_value_support
            not in self.policy.allowed_missing_value_support
        ):
            raise ModelRegistryError("Model missing-value support is unsupported.")
        return RegisteredPredictionModel(
            model_artifact_id=adapter.model_artifact_id,
            model_name=adapter.model_name,
            model_version=adapter.model_version,
            model_family=adapter.model_family,
            input_schema_name=adapter.input_schema_name,
            input_schema_version=adapter.input_schema_version,
            compatibility_version=adapter.compatibility_version,
            supported_targets=targets,
            missing_value_support=adapter.missing_value_support,
            adapter=adapter,
        )
