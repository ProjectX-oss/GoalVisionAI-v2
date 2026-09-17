class FeatureStoreError(Exception):
    """Base error for deterministic model feature storage."""


class InvalidSourceSnapshotError(FeatureStoreError, ValueError):
    """Snapshot is unsafe or insufficient for feature extraction."""


class UnsupportedFeatureSchemaError(FeatureStoreError, ValueError):
    """Requested feature schema is not supported."""


class FeatureValidationError(FeatureStoreError, ValueError):
    """Calculated feature material violates its declared contract."""


class FeatureStoreConflictError(FeatureStoreError):
    """Persisted feature history conflicts with the requested append."""


class FeatureStorePersistenceError(FeatureStoreError):
    """Feature history could not be read or appended safely."""
