from datetime import datetime
from typing import Protocol, runtime_checkable

from app.model_input_builder import ModelInputVector

from .models import (
    MissingValueSupport,
    ModelAdapterOutput,
    PersistedModelInputIdentity,
    PredictionInferenceResult,
    PredictionTarget,
)


@runtime_checkable
class PredictionModelAdapter(Protocol):
    @property
    def model_artifact_id(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    @property
    def model_family(self) -> str: ...

    @property
    def input_schema_name(self) -> str: ...

    @property
    def input_schema_version(self) -> str: ...

    @property
    def compatibility_version(self) -> str: ...

    @property
    def supported_targets(self) -> tuple[PredictionTarget, ...]: ...

    @property
    def missing_value_support(self) -> MissingValueSupport: ...

    def validate_compatibility(self, model_input: ModelInputVector) -> None: ...

    def infer(self, model_input: ModelInputVector) -> tuple[ModelAdapterOutput, ...]: ...


@runtime_checkable
class PredictionInferenceRepository(Protocol):
    def append_inference_result(
        self,
        result: PredictionInferenceResult,
    ) -> tuple[PredictionInferenceResult, bool]: ...

    def find_by_inference_fingerprint(
        self,
        fingerprint: str,
    ) -> PredictionInferenceResult | None: ...

    def find_for_model_input_and_artifact(
        self,
        model_input_id: str,
        model_artifact_id: str,
    ) -> PredictionInferenceResult | None: ...

    def find_latest_for_match_and_model(
        self,
        match_id: str,
        model_artifact_id: str,
    ) -> PredictionInferenceResult | None: ...

    def list_inferences_for_model_input(
        self,
        model_input_id: str,
    ) -> tuple[PredictionInferenceResult, ...]: ...

    def load_inference_by_id(
        self,
        inference_id: str,
    ) -> PredictionInferenceResult | None: ...

    def load_model_input_identity(
        self,
        model_input_id: str,
    ) -> PersistedModelInputIdentity | None: ...
