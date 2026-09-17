from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from .models import BacktestMetrics, HistoricalEvaluationRecord


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """Leakage-safe temporal boundaries for one future evaluation fold."""

    training_start: datetime
    training_end: datetime
    evaluation_start: datetime
    evaluation_end: datetime

    def __post_init__(self) -> None:
        values = (
            self.training_start,
            self.training_end,
            self.evaluation_start,
            self.evaluation_end,
        )
        if any(value.tzinfo is None or value.utcoffset() is None for value in values):
            raise ValueError("Walk-forward timestamps must be timezone-aware.")
        if self.training_start >= self.training_end:
            raise ValueError("Training window must have positive duration.")
        if self.training_end > self.evaluation_start:
            raise ValueError("Training window must not overlap future evaluation data.")
        if self.evaluation_start >= self.evaluation_end:
            raise ValueError("Evaluation window must have positive duration.")


@dataclass(frozen=True, slots=True)
class WalkForwardFoldResult:
    window: WalkForwardWindow
    metrics: BacktestMetrics


@runtime_checkable
class WalkForwardWindowProvider(Protocol):
    """Extension point for expanding, rolling, or custom temporal windows."""

    def windows(self) -> Sequence[WalkForwardWindow]: ...


@runtime_checkable
class WalkForwardEvaluator(Protocol):
    """Evaluation-only interface; implementations must not train models."""

    def evaluate(
        self,
        records: Sequence[HistoricalEvaluationRecord],
        window: WalkForwardWindow,
    ) -> WalkForwardFoldResult: ...
