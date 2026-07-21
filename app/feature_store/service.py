import hashlib
from datetime import datetime
from typing import Protocol

from app.match_data_snapshot import MatchDataSnapshotVersion, SnapshotLifecycleState

from .exceptions import (
    FeatureStoreConflictError,
    FeatureStorePersistenceError,
    FeatureValidationError,
    InvalidSourceSnapshotError,
    UnsupportedFeatureSchemaError,
)
from .extractors import OfficialPrematchFeatureExtractor
from .fingerprint import FeatureSetFingerprint
from .models import (
    FeatureGenerationOutcome,
    FeatureGenerationRequest,
    FeatureGenerationStatus,
    MatchFeatureSet,
)
from .policy import FeatureStorePolicy
from .validation import FeatureStoreValidator


class FeatureSetRepository(Protocol):
    def append_feature_set(self, feature_set: MatchFeatureSet) -> tuple[MatchFeatureSet, bool]: ...
    def find_by_feature_fingerprint(self, fingerprint: str) -> MatchFeatureSet | None: ...


class SnapshotStateReader(Protocol):
    def current_state(self, snapshot_id: str) -> SnapshotLifecycleState | None: ...


class FeatureStoreService:
    """Derives one versioned model-ready vector from supplied snapshot facts."""

    def __init__(
        self,
        repository: FeatureSetRepository,
        snapshot_states: SnapshotStateReader,
        extractor: OfficialPrematchFeatureExtractor,
        validator: FeatureStoreValidator,
        fingerprints: FeatureSetFingerprint,
        policy: FeatureStorePolicy,
    ) -> None:
        self.repository = repository
        self._snapshot_states = snapshot_states
        self._extractor = extractor
        self._validator = validator
        self._fingerprints = fingerprints
        self._policy = policy

    def generate_match_feature_set(
        self,
        snapshot: MatchDataSnapshotVersion,
        *,
        schema_version: str,
        feature_timestamp: datetime,
        historical_replay: bool = False,
        model_compatibility_version: str | None = None,
    ) -> FeatureGenerationOutcome:
        request = FeatureGenerationRequest(
            snapshot, schema_version, feature_timestamp, historical_replay,
            model_compatibility_version or self._policy.model_compatibility_version,
        )
        try:
            state = self._snapshot_states.current_state(snapshot.snapshot_id)
            self._validator.validate_request(request, state)
            values, missingness, quality = self._extractor.extract(snapshot)
            self._validator.validate_features(values)
        except UnsupportedFeatureSchemaError as exc:
            return self._rejected(FeatureGenerationStatus.REJECTED_UNSUPPORTED_SCHEMA, "UNSUPPORTED_FEATURE_SCHEMA", str(exc))
        except (InvalidSourceSnapshotError, FeatureValidationError) as exc:
            return self._rejected(FeatureGenerationStatus.REJECTED_INVALID_SNAPSHOT, "INVALID_SOURCE_SNAPSHOT", str(exc))
        except FeatureStorePersistenceError:
            return self._rejected(FeatureGenerationStatus.PERSISTENCE_FAILURE, "FEATURE_STORE_PERSISTENCE_FAILURE", "Feature persistence failed safely.")

        fingerprint = self._fingerprints.calculate(
            snapshot_id=snapshot.snapshot_id,
            source_snapshot_fingerprint=snapshot.content_fingerprint,
            schema_name=self._policy.schema_name,
            schema_version=self._policy.schema_version,
            model_compatibility_version=request.model_compatibility_version,
            values=values,
            missingness=missingness,
            quality=quality,
            feature_timestamp=feature_timestamp,
        )
        feature_set = MatchFeatureSet(
            feature_set_id="match-feature-set-" + hashlib.sha256(
                f"match-feature-set-v1|{fingerprint}".encode()
            ).hexdigest(),
            snapshot_id=snapshot.snapshot_id,
            match_id=snapshot.match_id,
            feature_schema_name=self._policy.schema_name,
            feature_schema_version=self._policy.schema_version,
            model_compatibility_version=request.model_compatibility_version,
            feature_timestamp=feature_timestamp,
            ordered_feature_values=values,
            missingness_indicators=missingness,
            data_quality_summary=quality,
            source_snapshot_fingerprint=snapshot.content_fingerprint,
            feature_fingerprint=fingerprint,
            created_timestamp=feature_timestamp,
        )
        try:
            existing = self.repository.find_by_feature_fingerprint(fingerprint)
            if existing is not None:
                return FeatureGenerationOutcome(
                    FeatureGenerationStatus.IDEMPOTENT_EXISTING, existing,
                    ("IDENTICAL_FEATURE_SET_EXISTS",),
                    ("Identical deterministic feature content already exists.",),
                )
            stored, identical = self.repository.append_feature_set(feature_set)
        except FeatureStoreConflictError as exc:
            return self._rejected(FeatureGenerationStatus.CONFLICT, "FEATURE_SET_CONFLICT", str(exc))
        except FeatureStorePersistenceError:
            return self._rejected(FeatureGenerationStatus.PERSISTENCE_FAILURE, "FEATURE_STORE_PERSISTENCE_FAILURE", "Feature persistence failed safely.")
        return FeatureGenerationOutcome(
            FeatureGenerationStatus.IDEMPOTENT_EXISTING if identical else FeatureGenerationStatus.GENERATED,
            stored,
            (("IDENTICAL_FEATURE_SET_EXISTS",) if identical else ("FEATURE_SET_GENERATED",)),
            (("Concurrent identical feature generation reused the existing record.",) if identical else ("Deterministic feature set was generated and appended.",)),
        )

    @staticmethod
    def _rejected(status: FeatureGenerationStatus, reason: str, explanation: str) -> FeatureGenerationOutcome:
        return FeatureGenerationOutcome(status, None, (reason,), (explanation,))


def generate_match_feature_set(
    service: FeatureStoreService,
    snapshot: MatchDataSnapshotVersion,
    *,
    schema_version: str,
    feature_timestamp: datetime,
    historical_replay: bool = False,
    model_compatibility_version: str | None = None,
) -> FeatureGenerationOutcome:
    """Explicit deterministic feature boundary; never generates a prediction."""
    return service.generate_match_feature_set(
        snapshot,
        schema_version=schema_version,
        feature_timestamp=feature_timestamp,
        historical_replay=historical_replay,
        model_compatibility_version=model_compatibility_version,
    )
