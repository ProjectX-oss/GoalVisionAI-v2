import os
from dataclasses import dataclass


MODEL_MONITORING_ENABLED = "MODEL_MONITORING_ENABLED"


@dataclass(frozen=True, slots=True)
class ModelMonitoringConfig:
    enabled: bool = False

    @classmethod
    def from_environment(cls) -> "ModelMonitoringConfig":
        value = os.getenv(MODEL_MONITORING_ENABLED, "false").strip().lower()
        if value not in {"true", "false"}:
            raise ValueError("MODEL_MONITORING_ENABLED must be exactly true or false.")
        return cls(value == "true")


class NullMonitoringRuntime:
    def run_once(self) -> None:
        return None
