from datetime import datetime, timezone

from .models import (
    OddsErrorCode,
    OddsIngestionReport,
    OddsObservation,
    OddsObservationError,
)
from .providers import OddsProvider
from .repository import SQLiteOddsRepository
from .validation import OddsObservationValidator


class OddsIngestionService:
    def __init__(
        self,
        repository: SQLiteOddsRepository,
        validator: OddsObservationValidator | None = None,
    ) -> None:
        self._repository = repository
        self._validator = validator or OddsObservationValidator()

    def ingest(
        self,
        providers: tuple[OddsProvider, ...],
        *,
        occurred_at: datetime | None = None,
    ) -> OddsIngestionReport:
        now = occurred_at or datetime.now(timezone.utc)
        received = inserted = duplicates = 0
        errors: list[OddsObservationError] = []
        sources: set[str] = set()
        fixtures: set[str] = set()
        times: list[datetime] = []
        for provider in providers:
            sources.add(provider.source_name)
            try:
                observations = provider.observations()
            except Exception:
                errors.append(self._error(
                    provider.source_name,
                    "",
                    "",
                    "",
                    OddsErrorCode.PROVIDER_ERROR,
                    "Odds provider failed safely.",
                    now,
                ))
                continue
            for raw in observations:
                received += 1
                source_name = str(getattr(raw, "source_name", provider.source_name))
                fixture_id = str(getattr(raw, "fixture_id", ""))
                market = str(getattr(getattr(raw, "market", ""), "value", getattr(raw, "market", "")))
                selection_value = getattr(raw, "selection", "")
                selection = str(getattr(selection_value, "selection_id", selection_value))
                try:
                    if not isinstance(raw, OddsObservation):
                        raise TypeError("Provider returned an invalid observation type.")
                    source = self._repository.get_source(raw.source_name)
                    normalized = self._validator.validate(raw, source)
                    fixtures.add(normalized.fixture_id)
                    times.append(normalized.observed_at)
                    if self._repository.insert_observation(normalized):
                        inserted += 1
                    else:
                        duplicates += 1
                        errors.append(self._error(
                            source_name,
                            fixture_id,
                            market,
                            selection,
                            OddsErrorCode.DUPLICATE_OBSERVATION,
                            "Duplicate odds observation was ignored.",
                            now,
                        ))
                except Exception as exc:
                    if isinstance(exc, TypeError):
                        code = OddsErrorCode.INVALID_ODDS
                    elif isinstance(exc, LookupError):
                        code = OddsErrorCode.UNKNOWN_SOURCE
                    elif isinstance(exc, PermissionError):
                        code = OddsErrorCode.DISABLED_SOURCE
                    elif isinstance(exc, RuntimeError):
                        code = OddsErrorCode.AFTER_KICKOFF
                    elif "commission" in str(exc).lower():
                        code = OddsErrorCode.INVALID_COMMISSION
                    elif "timestamp" in str(exc).lower():
                        code = OddsErrorCode.INVALID_TIMESTAMP
                    elif isinstance(exc, ValueError):
                        code = OddsErrorCode.INVALID_ODDS
                    else:
                        code = OddsErrorCode.PERSISTENCE_ERROR
                    errors.append(self._error(
                        source_name,
                        fixture_id,
                        market,
                        selection,
                        code,
                        self._safe_message(code),
                        now,
                    ))
        return OddsIngestionReport(
            received_count=received,
            inserted_count=inserted,
            duplicate_count=duplicates,
            rejected_count=len(errors) - duplicates,
            ordered_errors=tuple(errors),
            sources_processed=tuple(sorted(sources)),
            fixtures_processed=tuple(sorted(fixtures)),
            observation_time_range=(
                (min(times), max(times)) if times else None
            ),
        )

    @staticmethod
    def _safe_message(code: OddsErrorCode) -> str:
        return {
            OddsErrorCode.UNKNOWN_SOURCE: "Odds source is unknown.",
            OddsErrorCode.DISABLED_SOURCE: "Odds source is disabled.",
            OddsErrorCode.AFTER_KICKOFF: "Odds observation is outside the kickoff policy.",
            OddsErrorCode.INVALID_COMMISSION: "Odds commission is invalid.",
            OddsErrorCode.INVALID_TIMESTAMP: "Odds timestamp is invalid.",
            OddsErrorCode.INVALID_ODDS: "Odds observation is invalid.",
        }.get(code, "Odds observation could not be persisted safely.")

    @staticmethod
    def _error(
        source: str,
        fixture_id: str,
        market: str,
        selection: str,
        code: OddsErrorCode,
        message: str,
        occurred_at: datetime,
    ) -> OddsObservationError:
        return OddsObservationError(
            source=source,
            fixture_id=fixture_id,
            market=market,
            selection=selection,
            code=code,
            safe_message=message,
            occurred_at=occurred_at,
        )
