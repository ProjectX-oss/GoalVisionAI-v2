"""Safe persisted-parameter inference compatibility adapter."""

from __future__ import annotations

import json
from decimal import Decimal

from app.prediction_inference.models import OFFICIAL_TARGET_ORDER, RawProbability, RawProbabilitySet

from .estimators import BTTS, MATCH_RESULT, TOTAL_GOALS_BUCKET, predict_estimator
from .exceptions import InvalidProbabilityError
from .models import ArtifactPrediction, ModelArtifact
from .preprocessing import transform_vector
from .feature_contracts import (
    LEGACY_TRAINING_FEATURE_CONTRACT,
    resolve_training_feature_contract,
)
from .validation import validate_raw_probabilities


def predict_raw_probabilities(
    artifact: ModelArtifact,
    ordered_feature_vector,
    missingness_mask,
    *,
    feature_schema_version: str,
    feature_schema_fingerprint: str,
    ordered_feature_names: tuple[str, ...],
) -> ArtifactPrediction:
    if artifact.artifact_id != "PENDING" and artifact.artifact_id != f"historical-model-artifact-{artifact.artifact_fingerprint}":
        raise InvalidProbabilityError("Artifact identity and fingerprint are inconsistent.")
    if artifact.artifact_format_version != "goalvision_safe_model_artifact_v1":
        raise InvalidProbabilityError("Artifact format is unsupported.")
    if feature_schema_version != artifact.feature_schema_version or feature_schema_fingerprint != artifact.feature_schema_fingerprint:
        raise InvalidProbabilityError("Artifact feature schema is incompatible.")
    if ordered_feature_names != artifact.ordered_feature_names:
        raise InvalidProbabilityError("Artifact feature order is incompatible.")
    try:
        contract = resolve_training_feature_contract(
            artifact.feature_schema_version,
            artifact.feature_schema_fingerprint,
            artifact.ordered_feature_names,
        )
    except ValueError as exc:
        raise InvalidProbabilityError("Feature schema fingerprint is invalid.") from exc
    if len(ordered_feature_vector) != contract.feature_count or len(missingness_mask) != contract.feature_count:
        raise InvalidProbabilityError("Feature vector or missingness-mask length is incompatible.")
    if artifact.preprocessing.original_feature_names != contract.ordered_feature_names:
        raise InvalidProbabilityError("Artifact preprocessing input contract is incompatible.")
    if contract is not LEGACY_TRAINING_FEATURE_CONTRACT:
        try:
            compatibility = json.loads(artifact.compatibility_snapshot)
        except (TypeError, ValueError) as exc:
            raise InvalidProbabilityError("Artifact compatibility metadata is malformed.") from exc
        expected = {
            "input_schema_identifier": contract.schema_identifier,
            "feature_schema_version": contract.schema_version,
            "feature_schema_fingerprint": contract.schema_fingerprint,
            "feature_count": contract.feature_count,
            "compatibility_version": contract.compatibility_version,
            "fingerprint_version": contract.fingerprint_version,
        }
        if any(compatibility.get(key) != value for key, value in expected.items()):
            raise InvalidProbabilityError("Artifact compatibility metadata is inconsistent.")
    row = transform_vector(ordered_feature_vector, missingness_mask, artifact.preprocessing)
    estimators = {item.estimator_identity: item for item in artifact.estimators}
    result = predict_estimator(estimators[MATCH_RESULT], row)
    totals = predict_estimator(estimators[TOTAL_GOALS_BUCKET], row)
    btts = predict_estimator(estimators[BTTS], row)
    over_1_5 = Decimal(str(math_sum(totals[1:])))
    over_2_5 = Decimal(str(math_sum(totals[2:])))
    over_3_5 = Decimal(str(totals[3]))
    values = {
        "HOME_WIN": Decimal(str(result[0])), "DRAW": Decimal(str(result[1])),
        "AWAY_WIN": Decimal(str(result[2])), "OVER_1_5": over_1_5,
        "UNDER_1_5": Decimal(1) - over_1_5, "OVER_2_5": over_2_5,
        "UNDER_2_5": Decimal(1) - over_2_5, "OVER_3_5": over_3_5,
        "UNDER_3_5": Decimal(1) - over_3_5, "BTTS_YES": Decimal(str(btts[1])),
        "BTTS_NO": Decimal(1) - Decimal(str(btts[1])),
    }
    probabilities = RawProbabilitySet(tuple(RawProbability(target, values[target.value]) for target in OFFICIAL_TARGET_ORDER))
    validate_raw_probabilities(probabilities)
    return ArtifactPrediction(artifact.artifact_id, artifact.artifact_fingerprint, probabilities)


def math_sum(values) -> float:
    import math
    return math.fsum(values)
