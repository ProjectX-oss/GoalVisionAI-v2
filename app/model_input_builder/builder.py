from decimal import Decimal

from app.feature_store import MatchFeatureSet

from .fingerprint import ModelInputFingerprint
from .models import (
    ModelInputSchema,
    PersistedSourceFeatureIdentity,
    PreparedModelInputVector,
)
from .policy import ModelInputBuilderPolicy
from .validation import ModelInputValidator


class DeterministicModelInputBuilder:
    """Creates a schema-ordered vector without inference or imputation."""

    def __init__(
        self,
        schema: ModelInputSchema,
        policy: ModelInputBuilderPolicy,
        validator: ModelInputValidator,
        fingerprints: ModelInputFingerprint,
    ) -> None:
        self.schema = schema
        self.policy = policy
        self._validator = validator
        self._fingerprints = fingerprints

    def build(
        self,
        feature_set: MatchFeatureSet,
        persisted: PersistedSourceFeatureIdentity | None,
    ) -> PreparedModelInputVector:
        self._validator.validate(feature_set, persisted, self.schema)
        ordered_names = self.schema.ordered_feature_names
        ordered_values = tuple(item.value for item in feature_set.ordered_feature_values)
        missingness_mask = tuple(item[1] for item in feature_set.missingness_indicators)
        missing_names = tuple(
            name
            for name, missing in zip(ordered_names, missingness_mask, strict=True)
            if missing
        )
        completeness = (
            Decimal(len(ordered_names) - len(missing_names))
            / Decimal(len(ordered_names))
        ).quantize(self.policy.decimal_quantum, rounding=self.policy.rounding)
        fingerprint = self._fingerprints.calculate(
            schema_name=self.schema.name,
            schema_version=self.schema.version,
            compatibility_version=self.schema.compatibility_version,
            ordered_feature_names=ordered_names,
            ordered_feature_values=ordered_values,
            missingness_mask=missingness_mask,
            source_feature_fingerprint=feature_set.feature_fingerprint,
        )
        return PreparedModelInputVector(
            source_feature_set=feature_set,
            schema=self.schema,
            ordered_feature_names=ordered_names,
            ordered_feature_values=ordered_values,
            missingness_mask=missingness_mask,
            missing_feature_names=missing_names,
            completeness_score=completeness,
            feature_metadata=self.schema.ordered_feature_metadata,
            feature_fingerprint=feature_set.feature_fingerprint,
            source_snapshot_fingerprint=feature_set.source_snapshot_fingerprint,
            source_feature_fingerprint=feature_set.feature_fingerprint,
            model_input_fingerprint=fingerprint,
        )
