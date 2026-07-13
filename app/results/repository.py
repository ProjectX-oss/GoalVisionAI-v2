from typing import Protocol

from .models import PublishedPredictionReference, ResolvedPredictionResult


class PredictionResultRepository(Protocol):
    def load_pending(self) -> tuple[PublishedPredictionReference, ...]:
        ...

    def get_resolved(
        self,
        prediction_id: str,
    ) -> ResolvedPredictionResult | None:
        ...

    def store_if_absent(
        self,
        result: ResolvedPredictionResult,
    ) -> ResolvedPredictionResult:
        """Atomically store a terminal result or return the existing result."""
        ...


class InMemoryPredictionResultRepository:
    def __init__(
        self,
        predictions: tuple[PublishedPredictionReference, ...] = (),
    ) -> None:
        self._predictions = {
            prediction.prediction_id: prediction for prediction in predictions
        }
        self._results: dict[str, ResolvedPredictionResult] = {}

    def add_pending(self, prediction: PublishedPredictionReference) -> None:
        self._predictions[prediction.prediction_id] = prediction

    def load_pending(self) -> tuple[PublishedPredictionReference, ...]:
        return tuple(
            prediction
            for prediction_id, prediction in self._predictions.items()
            if prediction_id not in self._results
        )

    def get_resolved(
        self,
        prediction_id: str,
    ) -> ResolvedPredictionResult | None:
        return self._results.get(prediction_id)

    def store_if_absent(
        self,
        result: ResolvedPredictionResult,
    ) -> ResolvedPredictionResult:
        if not result.is_terminal:
            raise ValueError("Only terminal prediction results may be stored.")
        return self._results.setdefault(result.prediction_id, result)
