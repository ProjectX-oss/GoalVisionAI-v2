"""Dependency-injection ports for historical import persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import HistoricalDataset, HistoricalImportResult, PreparedHistoricalDataset


class HistoricalImportRepository(Protocol):
    def append_import(self, dataset: PreparedHistoricalDataset) -> HistoricalImportResult:
        """Atomically append one prepared dataset or return its exact replay."""


class HistoricalImportService(Protocol):
    def import_dataset(
        self,
        dataset: HistoricalDataset,
        *,
        import_timestamp: datetime | str,
    ) -> HistoricalImportResult:
        """Normalize, validate, fingerprint, and atomically persist supplied history."""
