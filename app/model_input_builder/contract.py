"""Canonical, value-independent contract for live model inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .fingerprint import ModelInputFingerprint
from .schema import GOALVISION_MODEL_INPUT_V1


@dataclass(frozen=True, slots=True)
class LiveModelInputContract:
    schema_name: str
    schema_version: str
    schema_identifier: str
    compatibility_version: str
    fingerprint_version: str
    ordered_feature_names: tuple[str, ...]
    ordered_feature_types: tuple[str, ...]
    required_feature_names: tuple[str, ...]
    schema_fingerprint: str

    @property
    def feature_count(self) -> int:
        return len(self.ordered_feature_names)


def build_live_model_input_contract() -> LiveModelInputContract:
    schema = GOALVISION_MODEL_INPUT_V1
    material = {
        "schema_name": schema.name,
        "schema_version": schema.version,
        "schema_identifier": schema.identifier,
        "compatibility_version": schema.compatibility_version,
        "fingerprint_version": ModelInputFingerprint.VERSION,
        "features": tuple(
            (
                item.index,
                item.name,
                item.value_type.value,
                item.required_baseline,
                item.source_feature_schema,
            )
            for item in schema.ordered_feature_metadata
        ),
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return LiveModelInputContract(
        schema_name=schema.name,
        schema_version=schema.version,
        schema_identifier=schema.identifier,
        compatibility_version=schema.compatibility_version,
        fingerprint_version=ModelInputFingerprint.VERSION,
        ordered_feature_names=schema.ordered_feature_names,
        ordered_feature_types=tuple(
            item.value_type.value for item in schema.ordered_feature_metadata
        ),
        required_feature_names=tuple(
            item.name
            for item in schema.ordered_feature_metadata
            if item.required_baseline
        ),
        schema_fingerprint=hashlib.sha256(encoded).hexdigest(),
    )


LIVE_MODEL_INPUT_CONTRACT = build_live_model_input_contract()
