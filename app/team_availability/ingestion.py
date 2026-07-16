from dataclasses import replace
from datetime import datetime, timezone

from .models import (
    AvailabilityError,
    AvailabilityErrorCode,
    AvailabilityIngestionReport,
    LineupObservation,
    PlayerAvailabilityObservation,
)
from .providers import AvailabilityProvider
from .repository import SQLiteTeamAvailabilityRepository
from .normalization import (
    normalize_formation,
    normalize_identifier,
    normalize_player,
    normalize_position,
    normalize_reason,
    normalize_source_name,
    normalize_team,
)
from .validation import AvailabilityValidator


class AvailabilityIngestionService:
    def __init__(
        self,
        repository: SQLiteTeamAvailabilityRepository,
        validator: AvailabilityValidator | None = None,
    ) -> None:
        self._repository = repository
        self._validator = validator or AvailabilityValidator()

    def ingest(
        self,
        providers: tuple[AvailabilityProvider, ...],
        *,
        kickoff_by_fixture: dict[str, datetime] | None = None,
        occurred_at: datetime | None = None,
    ) -> AvailabilityIngestionReport:
        now = occurred_at or datetime.now(timezone.utc)
        kickoffs = kickoff_by_fixture or {}
        received = inserted = duplicates = 0
        errors: list[AvailabilityError] = []
        fixtures: set[str] = set()
        teams: set[str] = set()
        sources: set[str] = set()
        timestamps: list[datetime] = []
        for provider in providers:
            sources.add(provider.source_name)
            try:
                batch = provider.observations()
                errors.extend(batch.errors)
            except Exception:
                errors.append(self._error(
                    provider.source_name,
                    "",
                    "",
                    "",
                    AvailabilityErrorCode.PROVIDER_ERROR,
                    "Availability provider failed safely.",
                    now,
                ))
                continue
            for record in batch.records:
                received += 1
                try:
                    record = self._normalize(record)
                    source = self._repository.get_source(record.source_name)
                    if isinstance(record, PlayerAvailabilityObservation):
                        valid = self._validator.validate_player(record, source)
                        stored = self._repository.insert_player(valid)
                    elif isinstance(record, LineupObservation):
                        kickoff = kickoffs.get(record.fixture_id)
                        if kickoff is None:
                            raise ValueError("Fixture kickoff is required for lineup.")
                        valid = self._validator.validate_lineup(
                            record,
                            source,
                            kickoff=kickoff,
                        )
                        stored = self._repository.insert_lineup(valid)
                    else:
                        raise TypeError("Provider record type is malformed.")
                    fixtures.add(record.fixture_id)
                    teams.add(record.team.team_id)
                    timestamps.append(record.observed_at)
                    if stored:
                        inserted += 1
                    else:
                        duplicates += 1
                        errors.append(self._error(
                            record.source_name,
                            record.fixture_id,
                            record.team.team_id,
                            self._player_reference(record),
                            AvailabilityErrorCode.DUPLICATE_OBSERVATION,
                            "Duplicate availability observation was ignored.",
                            now,
                        ))
                except Exception as exc:
                    errors.append(self._from_exception(record, exc, now))
        return AvailabilityIngestionReport(
            records_received=received,
            records_inserted=inserted,
            duplicate_records=duplicates,
            rejected_records=len(errors) - duplicates,
            fixtures_processed=tuple(sorted(fixtures)),
            teams_processed=tuple(sorted(teams)),
            sources_processed=tuple(sorted(sources)),
            observation_time_range=(
                (min(timestamps), max(timestamps)) if timestamps else None
            ),
            ordered_errors=tuple(errors),
        )

    @staticmethod
    def _normalize(record: object):
        if isinstance(record, PlayerAvailabilityObservation):
            return replace(
                record,
                fixture_id=normalize_identifier(record.fixture_id, "Fixture ID"),
                team=normalize_team(record.team.team_id, record.team.team_name),
                player=normalize_player(
                    record.player.player_id,
                    record.player.player_name,
                ),
                reason=normalize_reason(record.reason),
                source_name=normalize_source_name(record.source_name),
            )
        if isinstance(record, LineupObservation):
            return replace(
                record,
                fixture_id=normalize_identifier(record.fixture_id, "Fixture ID"),
                team=normalize_team(record.team.team_id, record.team.team_name),
                source_name=normalize_source_name(record.source_name),
                formation=(
                    normalize_formation(record.formation)
                    if record.formation is not None
                    else None
                ),
                players=tuple(
                    replace(
                        item,
                        player=normalize_player(
                            item.player.player_id,
                            item.player.player_name,
                        ),
                        position=normalize_position(item.position),
                    )
                    for item in record.players
                ),
            )
        raise TypeError("Provider record type is malformed.")

    def _from_exception(
        self,
        record: object,
        exc: Exception,
        occurred_at: datetime,
    ) -> AvailabilityError:
        text = str(exc).lower()
        if isinstance(exc, LookupError):
            code = AvailabilityErrorCode.UNKNOWN_SOURCE
        elif isinstance(exc, PermissionError):
            code = AvailabilityErrorCode.DISABLED_SOURCE
        elif isinstance(exc, TypeError):
            code = AvailabilityErrorCode.MALFORMED_PROVIDER_RECORD
        elif "kickoff" in text or "cutoff" in text:
            code = AvailabilityErrorCode.AFTER_KICKOFF
        elif "player" in text:
            code = AvailabilityErrorCode.INVALID_PLAYER
        elif "team" in text:
            code = AvailabilityErrorCode.INVALID_TEAM
        elif "fixture" in text:
            code = AvailabilityErrorCode.INVALID_FIXTURE
        elif "timestamp" in text:
            code = AvailabilityErrorCode.INVALID_TIMESTAMP
        elif "lineup" in text:
            code = AvailabilityErrorCode.INVALID_LINEUP
        else:
            code = AvailabilityErrorCode.PERSISTENCE_ERROR
        return self._error(
            str(getattr(record, "source_name", "")),
            str(getattr(record, "fixture_id", "")),
            str(getattr(getattr(record, "team", None), "team_id", "")),
            self._player_reference(record),
            code,
            "Availability record was rejected safely.",
            occurred_at,
        )

    @staticmethod
    def _player_reference(record: object) -> str:
        player = getattr(record, "player", None)
        return str(getattr(player, "identity_key", ""))

    @staticmethod
    def _error(
        source: str,
        fixture_id: str,
        team_id: str,
        player_reference: str,
        code: AvailabilityErrorCode,
        message: str,
        occurred_at: datetime,
    ) -> AvailabilityError:
        return AvailabilityError(
            source,
            fixture_id,
            team_id,
            player_reference,
            code,
            message,
            occurred_at,
        )
