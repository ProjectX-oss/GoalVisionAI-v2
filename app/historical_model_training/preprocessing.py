"""TRAIN-only deterministic imputation and standard scaling."""

from __future__ import annotations

import math
from statistics import median

from app.historical_training_dataset import HistoricalTrainingExample

from .exceptions import PreprocessingError
from .fingerprint import sha256_fingerprint
from .models import FittedPreprocessing, PreprocessingFeature
from .policy import AllMissingFeaturePolicy, MissingValuePolicy, PreprocessingPolicy


def fit_preprocessing(
    examples: tuple[HistoricalTrainingExample, ...],
    feature_names: tuple[str, ...],
    policy: PreprocessingPolicy,
) -> FittedPreprocessing:
    if not examples:
        raise PreprocessingError("TRAIN contains no examples.")
    rows = tuple(tuple(None if value is None else float(value) for value in item.ordered_feature_vector) for item in examples)
    features = []
    for index, name in enumerate(feature_names):
        observed = sorted(row[index] for row in rows if row[index] is not None)
        missing_count = len(rows) - len(observed)
        if missing_count and policy.missing_value_policy is MissingValuePolicy.REJECT_ANY_MISSING_V1:
            raise PreprocessingError(f"Missing value rejected for feature {name}.")
        if not observed:
            if policy.all_missing_feature_policy is AllMissingFeaturePolicy.REJECT:
                raise PreprocessingError(f"All TRAIN values are missing for feature {name}.")
            imputation = 0.0
        else:
            imputation = float(median(observed))
        completed = tuple(imputation if row[index] is None else row[index] for row in rows)
        mean = math.fsum(completed) / len(completed)
        variance = math.fsum((value - mean) ** 2 for value in completed) / len(completed)
        scale = math.sqrt(variance)
        zero = scale == 0.0
        if zero:
            scale = 1.0
        row_payload = {
            "name": name, "index": index, "imputation": imputation,
            "missing_count": missing_count, "mean": mean, "scale": scale,
            "zero_variance": zero, "policy_version": policy.version,
        }
        features.append(PreprocessingFeature(
            feature_name=name, original_feature_index=index, transformed_feature_index=index,
            imputation_value=imputation, missing_training_count=missing_count,
            scaling_mean=mean, scaling_scale=scale, zero_variance=zero,
            row_fingerprint=sha256_fingerprint(row_payload),
        ))
    transformed = feature_names
    if policy.append_missingness_indicators:
        transformed += tuple(f"{name}__missing" for name in feature_names)
    fingerprint = sha256_fingerprint({
        "feature_names": feature_names, "features": tuple(features),
        "transformed_feature_names": transformed, "policy": policy,
    })
    return FittedPreprocessing(
        policy_version=policy.version, missing_value_policy=policy.missing_value_policy.value,
        scaling_policy=policy.scaling_policy.value,
        append_missingness_indicators=policy.append_missingness_indicators,
        original_feature_names=feature_names, transformed_feature_names=transformed,
        features=tuple(features), preprocessing_fingerprint=fingerprint,
    )


def transform_examples(
    examples: tuple[HistoricalTrainingExample, ...], fitted: FittedPreprocessing,
) -> tuple[tuple[float, ...], ...]:
    return tuple(transform_vector(item.ordered_feature_vector, item.missingness_mask, fitted) for item in examples)


def transform_vector(values, missingness_mask, fitted: FittedPreprocessing) -> tuple[float, ...]:
    if len(values) != len(fitted.features) or len(missingness_mask) != len(fitted.features):
        raise PreprocessingError("Feature vector is incompatible with persisted preprocessing.")
    transformed = []
    indicators = []
    for feature, value, missing in zip(fitted.features, values, missingness_mask):
        if missing != (value is None):
            raise PreprocessingError("Missingness mask is inconsistent with the vector.")
        raw = feature.imputation_value if missing else float(value)
        scaled = (raw - feature.scaling_mean) / feature.scaling_scale
        if not math.isfinite(scaled):
            raise PreprocessingError("Preprocessing produced a non-finite value.")
        transformed.append(scaled)
        indicators.append(1.0 if missing else 0.0)
    if fitted.append_missingness_indicators:
        transformed.extend(indicators)
    return tuple(transformed)
