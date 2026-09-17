import os
from collections.abc import Mapping
from dataclasses import dataclass


FORM_FEATURE_INGESTION_ENABLED = "FORM_FEATURE_INGESTION_ENABLED"


@dataclass(frozen=True, slots=True)
class FormFeatureIngestionConfig:
    enabled: bool = False

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "FormFeatureIngestionConfig":
        values = os.environ if environment is None else environment
        raw = values.get(FORM_FEATURE_INGESTION_ENABLED, "false").strip().lower()
        if raw not in {"true", "false"}:
            raise ValueError(f"{FORM_FEATURE_INGESTION_ENABLED} must be exactly true or false.")
        return cls(raw == "true")
