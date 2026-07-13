from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupportingMetric:
    code: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class PredictionExplanation:
    short_summary: str
    positive_factors: tuple[str, ...]
    risk_factors: tuple[str, ...]
    missing_data: tuple[str, ...]
    reason_codes: tuple[str, ...]
    supporting_metrics: tuple[SupportingMetric, ...]
