import hashlib
import json

from app.match_data_snapshot import canonical_data, canonical_json

from .models import DataQualitySummary, FeatureValue


class FeatureSetFingerprint:
    VERSION = "match-feature-set-fingerprint-v1"

    def calculate(
        self,
        *,
        snapshot_id: str,
        source_snapshot_fingerprint: str,
        schema_name: str,
        schema_version: str,
        model_compatibility_version: str,
        values: tuple[FeatureValue, ...],
        missingness: tuple[tuple[str, bool], ...],
        quality: DataQualitySummary,
        feature_timestamp,
    ) -> str:
        material = {
            "version": self.VERSION,
            "source_snapshot_id": snapshot_id,
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
            "feature_schema": schema_name,
            "schema_version": schema_version,
            "model_compatibility_version": model_compatibility_version,
            "ordered_feature_values": canonical_data(values),
            "missingness_indicators": canonical_data(missingness),
            "data_quality_summary": canonical_data(quality),
            "feature_timestamp": canonical_data(feature_timestamp),
        }
        payload = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def serialize_values(values: tuple[FeatureValue, ...]) -> str:
        return canonical_json(values)

    @staticmethod
    def serialize_missingness(values: tuple[tuple[str, bool], ...]) -> str:
        return canonical_json(values)

    @staticmethod
    def serialize_quality(value: DataQualitySummary) -> str:
        return canonical_json(value)
