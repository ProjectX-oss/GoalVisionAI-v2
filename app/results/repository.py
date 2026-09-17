from typing import Protocol

from .models import PublishedPredictionReference, ResolvedPredictionResult


class PredictionResultRepository(Protocol):
    def save_published(
        self,
        prediction: PublishedPredictionReference,
    ) -> PublishedPredictionReference:
        ...

    def load_pending(self) -> tuple[PublishedPredictionReference, ...]:
        ...

    def get_published(
        self,
        prediction_id: str,
    ) -> PublishedPredictionReference | None:
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

    def load_history(self) -> tuple[ResolvedPredictionResult, ...]:
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
        self.save_published(prediction)

    def save_published(
        self,
        prediction: PublishedPredictionReference,
    ) -> PublishedPredictionReference:
        existing = self._predictions.get(prediction.prediction_id)
        if existing is not None and existing != prediction:
            raise ValueError("Prediction ID already has different published data.")
        self._predictions[prediction.prediction_id] = prediction
        return prediction

    def load_pending(self) -> tuple[PublishedPredictionReference, ...]:
        return tuple(
            prediction
            for prediction_id, prediction in self._predictions.items()
            if prediction_id not in self._results
        )

    def get_published(
        self,
        prediction_id: str,
    ) -> PublishedPredictionReference | None:
        return self._predictions.get(prediction_id)

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
        prediction = self._predictions.get(result.prediction_id)
        if prediction is None:
            raise ValueError("Cannot settle an unpublished prediction.")
        if prediction.fixture_id != result.fixture_id:
            raise ValueError("Settlement fixture does not match the prediction.")
        return self._results.setdefault(result.prediction_id, result)

    def load_history(self) -> tuple[ResolvedPredictionResult, ...]:
        return tuple(
            sorted(
                self._results.values(),
                key=lambda result: (
                    result.resolved_at,
                    result.prediction_id,
                ),
            )
        )
