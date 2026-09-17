from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from .models import (
    FinishedMatchResult,
    PublishedPredictionReference,
    ResolvedPredictionResult,
)
from .repository import PredictionResultRepository
from .resolver import PredictionResultResolver


class PredictionResultResolutionService:
    def __init__(
        self,
        resolver: PredictionResultResolver,
        repository: PredictionResultRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._resolver = resolver
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve_one(
        self,
        prediction: PublishedPredictionReference,
        match: FinishedMatchResult | None,
    ) -> ResolvedPredictionResult:
        existing = self._repository.get_resolved(prediction.prediction_id)
        if existing is not None:
            return existing

        result = self._resolver.resolve(prediction, match, self._clock())
        if result.is_terminal:
            return self._repository.store_if_absent(result)
        return result

    def resolve_pending(
        self,
        matches: Mapping[int, FinishedMatchResult],
    ) -> tuple[ResolvedPredictionResult, ...]:
        return tuple(
            self.resolve_one(prediction, matches.get(prediction.fixture_id))
            for prediction in self._repository.load_pending()
        )
