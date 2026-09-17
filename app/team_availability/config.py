import os
from collections.abc import Mapping
from dataclasses import dataclass


TEAM_AVAILABILITY_INGESTION_ENABLED = "TEAM_AVAILABILITY_INGESTION_ENABLED"


@dataclass(frozen=True, slots=True)
class TeamAvailabilityIngestionConfig:
    enabled: bool = False

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "TeamAvailabilityIngestionConfig":
        values = os.environ if environment is None else environment
        raw = values.get(
            TEAM_AVAILABILITY_INGESTION_ENABLED,
            "false",
        ).strip().lower()
        if raw not in {"true", "false"}:
            raise ValueError(
                f"{TEAM_AVAILABILITY_INGESTION_ENABLED} must be exactly true or false."
            )
        return cls(raw == "true")
