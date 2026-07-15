import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


QUALITY_GATE_SHADOW_ENABLED = "QUALITY_GATE_SHADOW_ENABLED"
QUALITY_GATE_SHADOW_DATABASE_PATH = "QUALITY_GATE_SHADOW_DATABASE_PATH"


@dataclass(frozen=True, slots=True)
class ShadowModeConfig:
    enabled: bool = False
    database_path: Path = Path("data/goalvision.db")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ShadowModeConfig":
        values = os.environ if environment is None else environment
        raw = values.get(QUALITY_GATE_SHADOW_ENABLED, "false")
        normalized = raw.strip().lower()
        if normalized == "true":
            enabled = True
        elif normalized == "false":
            enabled = False
        else:
            raise ValueError(
                f"{QUALITY_GATE_SHADOW_ENABLED} must be exactly true or false."
            )
        database_path = Path(
            values.get(
                QUALITY_GATE_SHADOW_DATABASE_PATH,
                "data/goalvision.db",
            )
        )
        if not str(database_path).strip():
            raise ValueError("Shadow database path must not be empty.")
        return cls(enabled=enabled, database_path=database_path)
