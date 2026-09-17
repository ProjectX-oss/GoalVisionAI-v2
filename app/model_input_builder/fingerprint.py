import hashlib
import json

from app.match_data_snapshot import canonical_data


class ModelInputFingerprint:
    VERSION = "goalvision-model-input-fingerprint-v1"

    def calculate(
        self,
        *,
        schema_name: str,
        schema_version: str,
        compatibility_version: str,
        ordered_feature_names: tuple[str, ...],
        ordered_feature_values: tuple[object, ...],
        missingness_mask: tuple[bool, ...],
        source_feature_fingerprint: str,
    ) -> str:
        material = {
            "fingerprint_version": self.VERSION,
            "schema": schema_name,
            "schema_version": schema_version,
            "compatibility_version": compatibility_version,
            "ordered_feature_names": canonical_data(ordered_feature_names),
            "ordered_feature_values": canonical_data(ordered_feature_values),
            "missingness_mask": canonical_data(missingness_mask),
            "source_feature_fingerprint": source_feature_fingerprint,
        }
        payload = json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
