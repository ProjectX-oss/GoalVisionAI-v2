import hashlib

from app.feature_store import MatchFeatureSet

from .builder import DeterministicModelInputBuilder
from .exceptions import (
    ModelInputConflictError,
    ModelInputPersistenceError,
    ModelInputValidationError,
)
from .models import (
    ModelInputGenerationOutcome,
    ModelInputGenerationStatus,
    ModelInputVector,
)
from .repository import SQLiteModelInputRepository


class PredictionModelInputBuilderService:
    """Validates, builds, and appends deterministic model-input vectors."""

    def __init__(
        self,
        repository: SQLiteModelInputRepository,
        builder: DeterministicModelInputBuilder,
    ) -> None:
        self.repository = repository
        self._builder = builder

    def generate_model_input(
        self,
        feature_set: MatchFeatureSet,
    ) -> ModelInputGenerationOutcome:
        try:
            persisted = self.repository.load_source_feature_identity(
                feature_set.feature_set_id
            )
            prepared = self._builder.build(feature_set, persisted)
        except ModelInputValidationError as exc:
            return self._outcome(
                ModelInputGenerationStatus.REJECTED_INVALID,
                None,
                exc.reason_code,
                exc.explanation,
            )
        except ModelInputPersistenceError:
            return self._outcome(
                ModelInputGenerationStatus.PERSISTENCE_FAILURE,
                None,
                "MODEL_INPUT_PERSISTENCE_FAILURE",
                "Model-input persistence failed safely.",
            )

        source = prepared.source_feature_set
        vector = ModelInputVector(
            model_input_id="model-input-" + hashlib.sha256(
                (
                    "goalvision-model-input-id-v1|"
                    + prepared.model_input_fingerprint
                ).encode("utf-8")
            ).hexdigest(),
            feature_set_id=source.feature_set_id,
            snapshot_id=source.snapshot_id,
            match_id=source.match_id,
            schema_name=prepared.schema.name,
            schema_version=prepared.schema.version,
            compatibility_version=prepared.schema.compatibility_version,
            ordered_feature_names=prepared.ordered_feature_names,
            ordered_feature_values=prepared.ordered_feature_values,
            missingness_mask=prepared.missingness_mask,
            missing_feature_names=prepared.missing_feature_names,
            completeness_score=prepared.completeness_score,
            feature_metadata=prepared.feature_metadata,
            feature_fingerprint=prepared.feature_fingerprint,
            source_snapshot_fingerprint=prepared.source_snapshot_fingerprint,
            source_feature_fingerprint=prepared.source_feature_fingerprint,
            model_input_fingerprint=prepared.model_input_fingerprint,
            created_timestamp=source.created_timestamp,
        )
        try:
            existing = self.repository.find_by_fingerprint(
                vector.model_input_fingerprint
            )
            if existing is not None:
                return self._outcome(
                    ModelInputGenerationStatus.IDEMPOTENT_EXISTING,
                    existing,
                    "IDENTICAL_MODEL_INPUT_EXISTS",
                    "Identical immutable model input already exists.",
                )
            stored, identical = self.repository.append_model_input(vector)
        except ModelInputConflictError as exc:
            return self._outcome(
                ModelInputGenerationStatus.CONFLICT,
                None,
                "MODEL_INPUT_CONFLICT",
                str(exc),
            )
        except ModelInputPersistenceError:
            return self._outcome(
                ModelInputGenerationStatus.PERSISTENCE_FAILURE,
                None,
                "MODEL_INPUT_PERSISTENCE_FAILURE",
                "Model-input persistence failed safely.",
            )
        if identical:
            return self._outcome(
                ModelInputGenerationStatus.IDEMPOTENT_EXISTING,
                stored,
                "IDENTICAL_MODEL_INPUT_EXISTS",
                "Concurrent identical generation reused the stored model input.",
            )
        return self._outcome(
            ModelInputGenerationStatus.GENERATED,
            stored,
            "MODEL_INPUT_GENERATED",
            "Versioned deterministic model input was appended.",
        )

    @staticmethod
    def _outcome(
        status: ModelInputGenerationStatus,
        model_input: ModelInputVector | None,
        reason_code: str,
        explanation: str,
    ) -> ModelInputGenerationOutcome:
        return ModelInputGenerationOutcome(
            status,
            model_input,
            (reason_code,),
            (explanation,),
        )


def generate_model_input(
    service: PredictionModelInputBuilderService,
    feature_set: MatchFeatureSet,
) -> ModelInputGenerationOutcome:
    """Explicit bridge from one feature set; performs no model inference."""
    return service.generate_model_input(feature_set)
