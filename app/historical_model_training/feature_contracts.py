"""Supported immutable training feature contracts."""

from __future__ import annotations

from dataclasses import dataclass

from app.historical_training_dataset import (
    FEATURE_SCHEMA_VERSION,
    HISTORICAL_TRAINING_FEATURES_V1,
)
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT

from .fingerprint import sha256_fingerprint


@dataclass(frozen=True, slots=True)
class TrainingFeatureContract:
    schema_identifier: str
    schema_version: str
    compatibility_version: str
    fingerprint_version: str
    ordered_feature_names: tuple[str, ...]
    schema_fingerprint: str
    required_feature_names: tuple[str, ...] = ()

    @property
    def feature_count(self) -> int:
        return len(self.ordered_feature_names)


LEGACY_FEATURE_NAMES = tuple(item.name for item in HISTORICAL_TRAINING_FEATURES_V1)
LEGACY_FEATURE_SCHEMA_FINGERPRINT = sha256_fingerprint({
    "schema_version": FEATURE_SCHEMA_VERSION,
    "features": tuple(
        (item.index, item.name, item.data_type.value)
        for item in HISTORICAL_TRAINING_FEATURES_V1
    ),
})
LEGACY_TRAINING_FEATURE_CONTRACT = TrainingFeatureContract(
    schema_identifier=FEATURE_SCHEMA_VERSION,
    schema_version=FEATURE_SCHEMA_VERSION,
    compatibility_version="historical-training-only-v1",
    fingerprint_version="historical-training-schema-fingerprint-v1",
    ordered_feature_names=LEGACY_FEATURE_NAMES,
    schema_fingerprint=LEGACY_FEATURE_SCHEMA_FINGERPRINT,
)
LIVE_TRAINING_FEATURE_CONTRACT = TrainingFeatureContract(
    schema_identifier=LIVE_MODEL_INPUT_CONTRACT.schema_identifier,
    schema_version=LIVE_MODEL_INPUT_CONTRACT.schema_version,
    compatibility_version=LIVE_MODEL_INPUT_CONTRACT.compatibility_version,
    fingerprint_version=LIVE_MODEL_INPUT_CONTRACT.fingerprint_version,
    ordered_feature_names=LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names,
    schema_fingerprint=LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint,
    required_feature_names=LIVE_MODEL_INPUT_CONTRACT.required_feature_names,
)
SUPPORTED_TRAINING_FEATURE_CONTRACTS = (
    LEGACY_TRAINING_FEATURE_CONTRACT,
    LIVE_TRAINING_FEATURE_CONTRACT,
)


def resolve_training_feature_contract(
    schema_version: str,
    schema_fingerprint: str,
    ordered_feature_names: tuple[str, ...],
) -> TrainingFeatureContract:
    matches = tuple(
        item
        for item in SUPPORTED_TRAINING_FEATURE_CONTRACTS
        if item.schema_version == schema_version
        and item.schema_fingerprint == schema_fingerprint
        and item.ordered_feature_names == tuple(ordered_feature_names)
    )
    if len(matches) != 1:
        raise ValueError("Feature schema declaration is unsupported or internally inconsistent.")
    return matches[0]
