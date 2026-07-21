import hashlib
import json
from datetime import datetime, timezone

from app.match_data_snapshot import canonical_data

from .models import RawProbabilitySet, RegisteredPredictionModel


class PredictionInferenceFingerprint:
    """Canonical identity for one effective raw inference."""

    VERSION = "goalvision-prediction-inference-fingerprint-v1"

    def calculate(
        self,
        *,
        model_input_id: str,
        model_input_fingerprint: str,
        match_id: str,
        model: RegisteredPredictionModel,
        raw_probabilities: RawProbabilitySet,
        inference_timestamp: datetime,
        policy_version: str,
    ) -> str:
        if inference_timestamp.tzinfo is None:
            raise ValueError("Inference timestamp must be timezone-aware.")
        material = {
            "fingerprint_version": self.VERSION,
            "model_input_id": model_input_id,
            "model_input_fingerprint": model_input_fingerprint,
            "match_id": match_id,
            "model_artifact_id": model.model_artifact_id,
            "model_name": model.model_name,
            "model_version": model.model_version,
            "model_family": model.model_family,
            "input_schema_name": model.input_schema_name,
            "input_schema_version": model.input_schema_version,
            "compatibility_version": model.compatibility_version,
            "ordered_raw_probabilities": canonical_data(
                tuple(
                    (item.target.value, item.probability)
                    for item in raw_probabilities.ordered_probabilities
                )
            ),
            "inference_timestamp": _utc_timestamp(inference_timestamp),
            "policy_version": policy_version,
        }
        payload = json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
