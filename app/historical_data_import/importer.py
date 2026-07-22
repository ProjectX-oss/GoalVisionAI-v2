"""Explicit application service for supplied historical datasets."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .mapping import map_provider_dataset
from .models import HistoricalDataset, HistoricalImportResult
from .normalization import prepare_historical_dataset
from .policy import DEFAULT_HISTORICAL_IMPORT_POLICY, HistoricalImportPolicy
from .ports import HistoricalImportRepository


class HistoricalMatchImporter:
    """Normalize and atomically append one explicitly supplied dataset."""

    def __init__(
        self,
        repository: HistoricalImportRepository,
        policy: HistoricalImportPolicy = DEFAULT_HISTORICAL_IMPORT_POLICY,
    ) -> None:
        self._repository = repository
        self._policy = policy

    def import_dataset(
        self,
        dataset: HistoricalDataset,
        *,
        import_timestamp: datetime | str,
    ) -> HistoricalImportResult:
        prepared = prepare_historical_dataset(
            dataset,
            import_timestamp=import_timestamp,
            policy=self._policy,
        )
        return self._repository.append_import(prepared)

    def import_mapping(
        self,
        payload: Mapping[str, Any],
        *,
        import_timestamp: datetime | str,
    ) -> HistoricalImportResult:
        return self.import_dataset(
            map_provider_dataset(payload),
            import_timestamp=import_timestamp,
        )
