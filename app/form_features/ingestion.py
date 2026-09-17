from dataclasses import replace
from datetime import datetime, timezone

from .models import (
    FormFeatureError,
    FormFeatureErrorCode,
    FormFeatureReport,
    HistoricalMatchObservation,
)
from .providers import HistoricalMatchProvider
from .repository import SQLiteFormFeatureRepository
from .normalization import (
    normalize_identifier,
    normalize_source,
    normalize_text,
)


class HistoricalMatchIngestionService:
    def __init__(self, repository: SQLiteFormFeatureRepository) -> None:
        self._repository = repository

    def ingest(
        self,
        providers: tuple[HistoricalMatchProvider, ...],
        *,
        evaluation_timestamp: datetime,
        occurred_at: datetime | None = None,
    ) -> FormFeatureReport:
        now = occurred_at or datetime.now(timezone.utc)
        received = inserted = duplicates = rejected = 0
        competitions: set[str] = set()
        teams: set[str] = set()
        fixtures: set[str] = set()
        timestamps: list[datetime] = []
        errors: list[FormFeatureError] = []
        for provider in providers:
            try:
                batch = provider.historical_matches()
                errors.extend(batch.errors)
            except Exception:
                errors.append(self._error("", FormFeatureErrorCode.PERSISTENCE_ERROR, now))
                continue
            for item in batch.observations:
                received += 1
                try:
                    item = self._normalize(item)
                    self._validate(item, evaluation_timestamp)
                    enabled = self._repository.source_enabled(item.source_name)
                    if enabled is None:
                        raise LookupError("Unknown source.")
                    if not enabled:
                        raise PermissionError("Disabled source.")
                    if self._repository.insert(item):
                        inserted += 1
                    else:
                        duplicates += 1
                        errors.append(
                            self._error(
                                item.fixture_id,
                                FormFeatureErrorCode.DUPLICATE_OBSERVATION,
                                now,
                            )
                        )
                    competitions.add(item.competition)
                    teams.update((item.home_team_id, item.away_team_id))
                    fixtures.add(item.fixture_id)
                    timestamps.append(item.kickoff_time)
                except Exception as exc:
                    rejected += 1
                    errors.append(self._from_exception(item.fixture_id, exc, now))
        return FormFeatureReport(
            received,
            inserted,
            duplicates,
            rejected + len(tuple(error for error in errors if error.code is FormFeatureErrorCode.MALFORMED_PROVIDER_RECORD)),
            tuple(sorted(competitions)),
            tuple(sorted(teams)),
            tuple(sorted(fixtures)),
            (min(timestamps), max(timestamps)) if timestamps else None,
            tuple(sorted(errors, key=lambda item: (item.fixture_id, item.code.value))),
        )

    @staticmethod
    def _normalize(
        item: HistoricalMatchObservation,
    ) -> HistoricalMatchObservation:
        return replace(
            item,
            fixture_id=normalize_identifier(item.fixture_id, "Fixture ID"),
            competition=normalize_text(item.competition, "Competition"),
            home_team_id=normalize_identifier(item.home_team_id, "Home team"),
            away_team_id=normalize_identifier(item.away_team_id, "Away team"),
            match_status=normalize_text(item.match_status, "Match status").upper(),
            source_name=normalize_source(item.source_name),
        )

    @staticmethod
    def _validate(item: HistoricalMatchObservation, evaluation: datetime) -> None:
        if evaluation.tzinfo is None or evaluation.utcoffset() is None:
            raise ValueError("Evaluation timestamp is invalid.")
        if not item.completed:
            raise RuntimeError("Match is incomplete.")
        if item.kickoff_time >= evaluation or item.observed_at > evaluation:
            raise OverflowError("Match is in the future.")

    def _from_exception(
        self,
        fixture_id: str,
        exc: Exception,
        now: datetime,
    ) -> FormFeatureError:
        if isinstance(exc, LookupError):
            code = FormFeatureErrorCode.UNKNOWN_SOURCE
        elif isinstance(exc, PermissionError):
            code = FormFeatureErrorCode.DISABLED_SOURCE
        elif isinstance(exc, OverflowError):
            code = FormFeatureErrorCode.FUTURE_MATCH
        elif isinstance(exc, RuntimeError):
            code = FormFeatureErrorCode.INCOMPLETE_MATCH
        elif isinstance(exc, ValueError):
            code = FormFeatureErrorCode.INVALID_TIMESTAMP
        else:
            code = FormFeatureErrorCode.PERSISTENCE_ERROR
        return self._error(fixture_id, code, now)

    @staticmethod
    def _error(
        fixture_id: str,
        code: FormFeatureErrorCode,
        now: datetime,
    ) -> FormFeatureError:
        return FormFeatureError(
            fixture_id,
            code,
            "Historical match record was handled safely.",
            now,
        )
