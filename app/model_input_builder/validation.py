import re
from decimal import Decimal

from app.feature_store import FeatureSetFingerprint, FeatureValueType, MatchFeatureSet

from .exceptions import ModelInputValidationError
from .models import ModelInputSchema, PersistedSourceFeatureIdentity


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ModelInputValidator:
    """Validates Feature Store provenance and the complete ordered payload."""

    def validate(
        self,
        feature_set: MatchFeatureSet,
        persisted: PersistedSourceFeatureIdentity | None,
        schema: ModelInputSchema,
    ) -> None:
        if not isinstance(feature_set, MatchFeatureSet):
            self._invalid("UNSUPPORTED_SOURCE_OBJECT", "Input must be an immutable MatchFeatureSet.")
        if persisted is None:
            self._invalid("SOURCE_FEATURE_NOT_PERSISTED", "Source feature set is not persisted.")
        assert persisted is not None
        if (
            feature_set.feature_schema_name != schema.source_feature_schema_name
            or persisted.feature_schema_name != schema.source_feature_schema_name
        ):
            self._invalid("UNSUPPORTED_FEATURE_SCHEMA", "Feature schema is unsupported.")
        if (
            feature_set.feature_schema_version != schema.source_feature_schema_version
            or persisted.feature_schema_version != schema.source_feature_schema_version
        ):
            self._invalid(
                "INCOMPATIBLE_FEATURE_SCHEMA_VERSION",
                "Feature schema version is incompatible with this model-input schema.",
            )
        if (
            feature_set.model_compatibility_version != schema.compatibility_version
            or persisted.compatibility_version != schema.compatibility_version
        ):
            self._invalid(
                "INCOMPATIBLE_COMPATIBILITY_VERSION",
                "Feature compatibility version is unsupported.",
            )
        if feature_set.feature_set_id != persisted.feature_set_id:
            self._invalid("FEATURE_SET_ID_MISMATCH", "Feature-set identity does not match persistence.")
        if feature_set.snapshot_id != persisted.snapshot_id:
            self._invalid("SNAPSHOT_ID_MISMATCH", "Source snapshot identity does not match persistence.")
        if feature_set.match_id != persisted.match_id:
            self._invalid("MATCH_ID_MISMATCH", "Match identity does not match persistence.")
        if feature_set.created_timestamp != persisted.created_timestamp:
            self._invalid(
                "SOURCE_CREATION_TIMESTAMP_MISMATCH",
                "Source feature creation timestamp does not match persistence.",
            )
        if not _SHA256.fullmatch(feature_set.source_snapshot_fingerprint):
            self._invalid("MALFORMED_SNAPSHOT_FINGERPRINT", "Snapshot fingerprint must be SHA-256.")
        if feature_set.source_snapshot_fingerprint != persisted.source_snapshot_fingerprint:
            self._invalid(
                "SNAPSHOT_FINGERPRINT_MISMATCH",
                "Source snapshot fingerprint does not match persisted feature provenance.",
            )
        if not _SHA256.fullmatch(feature_set.feature_fingerprint):
            self._invalid("MALFORMED_FEATURE_FINGERPRINT", "Feature fingerprint must be SHA-256.")
        if feature_set.feature_fingerprint != persisted.feature_fingerprint:
            self._invalid(
                "FEATURE_FINGERPRINT_MISMATCH",
                "Source feature fingerprint does not match persistence.",
            )

        names = tuple(item.name for item in feature_set.ordered_feature_values)
        if len(names) != len(set(names)):
            self._invalid("DUPLICATE_FEATURE_NAME", "Feature names must be unique.")
        expected_names = schema.ordered_feature_names
        unknown = tuple(name for name in names if name not in expected_names)
        if unknown:
            self._invalid("UNKNOWN_FEATURE", f"Unknown feature: {unknown[0]}.")
        if names != expected_names:
            self._invalid(
                "INVALID_FEATURE_ORDER",
                "Feature names do not match the versioned schema order.",
            )
        missingness = feature_set.missingness_indicators
        if len(missingness) != len(names):
            self._invalid("INVALID_MISSINGNESS_LENGTH", "Missingness mask length is invalid.")
        missing_names = tuple(item[0] for item in missingness)
        if missing_names != names:
            self._invalid("INVALID_MISSINGNESS_ORDER", "Missingness names must match feature order.")

        for value, missing, metadata in zip(
            feature_set.ordered_feature_values,
            missingness,
            schema.ordered_feature_metadata,
            strict=True,
        ):
            missing_state = missing[1]
            if not isinstance(missing_state, bool):
                self._invalid(
                    "UNSUPPORTED_MISSINGNESS_STATE",
                    f"Missingness for {value.name} must be boolean.",
                )
            if missing_state != (value.value is None):
                self._invalid(
                    "MISSINGNESS_VALUE_MISMATCH",
                    f"Missingness and value disagree for {value.name}.",
                )
            if metadata.required_baseline and missing_state:
                self._invalid(
                    "REQUIRED_BASELINE_FEATURE_MISSING",
                    f"Required baseline feature {value.name} is missing.",
                )
            self._value(value.name, value.value, metadata.value_type)

        recalculated = FeatureSetFingerprint().calculate(
            snapshot_id=feature_set.snapshot_id,
            source_snapshot_fingerprint=feature_set.source_snapshot_fingerprint,
            schema_name=feature_set.feature_schema_name,
            schema_version=feature_set.feature_schema_version,
            model_compatibility_version=feature_set.model_compatibility_version,
            values=feature_set.ordered_feature_values,
            missingness=feature_set.missingness_indicators,
            quality=feature_set.data_quality_summary,
            feature_timestamp=feature_set.feature_timestamp,
        )
        if recalculated != feature_set.feature_fingerprint:
            self._invalid(
                "FEATURE_FINGERPRINT_MISMATCH",
                "Feature content does not match its canonical fingerprint.",
            )

    @classmethod
    def _value(
        cls,
        name: str,
        value: Decimal | int | bool | None,
        value_type: FeatureValueType,
    ) -> None:
        if value is None:
            return
        if value_type is FeatureValueType.DECIMAL:
            if not isinstance(value, Decimal) or not value.is_finite():
                cls._invalid("MALFORMED_DECIMAL_VALUE", f"{name} must be a finite Decimal.")
        elif value_type is FeatureValueType.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                cls._invalid("MALFORMED_INTEGER_VALUE", f"{name} must be an integer.")
        elif not isinstance(value, bool):
            cls._invalid("MALFORMED_BOOLEAN_VALUE", f"{name} must be boolean.")

    @staticmethod
    def _invalid(reason_code: str, explanation: str) -> None:
        raise ModelInputValidationError(reason_code, explanation)
