import hashlib
import json
from datetime import datetime, timezone

from app.match_data_snapshot import canonical_data

from .models import PredictionInferenceResult, RawProbabilitySet, RegisteredPredictionModel


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
        return self._calculate(
            model_input_id=model_input_id,
            model_input_fingerprint=model_input_fingerprint,
            match_id=match_id,
            model_artifact_id=model.model_artifact_id,
            model_name=model.model_name,
            model_version=model.model_version,
            model_family=model.model_family,
            input_schema_name=model.input_schema_name,
            input_schema_version=model.input_schema_version,
            compatibility_version=model.compatibility_version,
            raw_probabilities=raw_probabilities,
            inference_timestamp=inference_timestamp,
            policy_version=policy_version,
        )

    def calculate_for_result(self, result: PredictionInferenceResult) -> str:
        """Recalculate a persisted result without requiring its runtime adapter."""
        return self._calculate(
            model_input_id=result.model_input_id,
            model_input_fingerprint=result.model_input_fingerprint,
            match_id=result.match_id,
            model_artifact_id=result.model_artifact_id,
            model_name=result.model_name,
            model_version=result.model_version,
            model_family=result.model_family,
            input_schema_name=result.input_schema_name,
            input_schema_version=result.input_schema_version,
            compatibility_version=result.compatibility_version,
            raw_probabilities=result.raw_probabilities,
            inference_timestamp=result.inference_timestamp,
            policy_version=result.policy_version,
        )

    def _calculate(
        self, *, model_input_id: str, model_input_fingerprint: str,
        match_id: str, model_artifact_id: str, model_name: str,
        model_version: str, model_family: str, input_schema_name: str,
        input_schema_version: str, compatibility_version: str,
        raw_probabilities: RawProbabilitySet, inference_timestamp: datetime,
        policy_version: str,
    ) -> str:
        if inference_timestamp.tzinfo is None:
            raise ValueError("Inference timestamp must be timezone-aware.")
        material = {
            "fingerprint_version": self.VERSION,
            "model_input_id": model_input_id,
            "model_input_fingerprint": model_input_fingerprint,
            "match_id": match_id,
            "model_artifact_id": model_artifact_id,
            "model_name": model_name,
            "model_version": model_version,
            "model_family": model_family,
            "input_schema_name": input_schema_name,
            "input_schema_version": input_schema_version,
            "compatibility_version": compatibility_version,
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
