from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExplanationConfig:
    component_advantage_margin: float
    normalized_advantage_margin: float


DEFAULT_EXPLANATION_CONFIG = ExplanationConfig(
    component_advantage_margin=5.0,
    normalized_advantage_margin=0.05,
)
