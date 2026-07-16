import os
from collections.abc import Mapping
from dataclasses import dataclass


ODDS_INGESTION_ENABLED = "ODDS_INGESTION_ENABLED"


@dataclass(frozen=True, slots=True)
class OddsIngestionConfig:
    enabled: bool = False

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "OddsIngestionConfig":
        values = os.environ if environment is None else environment
        raw = values.get(ODDS_INGESTION_ENABLED, "false").strip().lower()
        if raw not in {"true", "false"}:
            raise ValueError(f"{ODDS_INGESTION_ENABLED} must be exactly true or false.")
        return cls(enabled=raw == "true")
