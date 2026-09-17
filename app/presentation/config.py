from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresentationConfig:
    show_quality_score: bool = False
    maximum_positive_factors: int = 3
    maximum_risk_factors: int = 2

    def __post_init__(self) -> None:
        if self.maximum_positive_factors < 1:
            raise ValueError("At least one positive factor must be allowed.")
        if self.maximum_risk_factors < 1:
            raise ValueError("At least one risk factor must be allowed.")


DEFAULT_PRESENTATION_CONFIG = PresentationConfig()
