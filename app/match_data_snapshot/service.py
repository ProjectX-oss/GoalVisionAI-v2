from datetime import datetime
from typing import Protocol

from .exceptions import SnapshotConflictError, SnapshotPersistenceError, SnapshotValidationError
from .models import (
    MatchDataSnapshotRegistrationCommand,
    MatchDataSnapshotRegistrationOutcome,
    MatchDataSnapshotVersion,
    PreparedMatchDataSnapshot,
    SnapshotLifecycleOutcome,
    SnapshotLifecycleResultStatus,
    SnapshotLifecycleState,
    SnapshotRegistrationStatus,
    SnapshotVersionRegistration,
)
from .validation import MatchDataSnapshotValidator


class MatchDataSnapshotRepository(Protocol):
    def register_snapshot(self, prepared: PreparedMatchDataSnapshot) -> SnapshotVersionRegistration: ...
    def find_by_content_fingerprint(self, fingerprint: str) -> MatchDataSnapshotVersion | None: ...
    def withdraw_snapshot(self, snapshot_id: str, reason_code: str, event_timestamp: datetime): ...
    def invalidate_snapshot(self, snapshot_id: str, reason_code: str, event_timestamp: datetime): ...
    def current_state(self, snapshot_id: str) -> SnapshotLifecycleState | None: ...


class MatchDataSnapshotService:
    """Validates and persists supplied facts without inference or fetching."""

    def __init__(self, repository: MatchDataSnapshotRepository, validator: MatchDataSnapshotValidator) -> None:
        self.repository = repository
        self._validator = validator

    def register_match_data_snapshot(
        self,
        command: MatchDataSnapshotRegistrationCommand,
    ) -> MatchDataSnapshotRegistrationOutcome:
        try:
            prepared = self._validator.prepare(command)
        except SnapshotValidationError as exc:
            return MatchDataSnapshotRegistrationOutcome(
                None, str(getattr(command, "match_id", "")), None, None, None,
                SnapshotRegistrationStatus.REJECTED_INVALID,
                exc.reason_codes, exc.explanations, None,
                command.snapshot_effective_timestamp,
                command.registration_timestamp,
            )
        try:
            existing = self.repository.find_by_content_fingerprint(prepared.content_fingerprint)
            if existing is not None:
                return self._outcome(
                    existing,
                    SnapshotRegistrationStatus.IDEMPOTENT_EXISTING,
                    ("IDENTICAL_SNAPSHOT_EXISTS",),
                    ("Identical immutable supplied facts already exist.",),
                )
            registration = self.repository.register_snapshot(prepared)
        except SnapshotConflictError as exc:
            return self._blocked(prepared, SnapshotRegistrationStatus.CONFLICT, "SNAPSHOT_CONFLICT", str(exc))
        except SnapshotPersistenceError:
            return self._blocked(
                prepared, SnapshotRegistrationStatus.PERSISTENCE_FAILURE,
                "SNAPSHOT_PERSISTENCE_FAILURE", "Snapshot persistence failed safely."
            )
        if registration.identical_existing:
            return self._outcome(
                registration.snapshot,
                SnapshotRegistrationStatus.IDEMPOTENT_EXISTING,
                ("IDENTICAL_SNAPSHOT_EXISTS",),
                ("Concurrent identical registration reused the existing snapshot.",),
            )
        previous = registration.previous_snapshot
        return self._outcome(
            registration.snapshot,
            SnapshotRegistrationStatus.SUPERSEDED_PREVIOUS if previous else SnapshotRegistrationStatus.REGISTERED,
            (("PREVIOUS_ACTIVE_SUPERSEDED",) if previous else ("SNAPSHOT_REGISTERED",)),
            (("Materially changed facts superseded the prior ACTIVE version.",) if previous else ("Snapshot version 1 was registered as ACTIVE.",)),
            previous.snapshot_id if previous else None,
        )

    def withdraw_snapshot(self, snapshot_id: str, *, reason_code: str, event_timestamp: datetime) -> SnapshotLifecycleOutcome:
        return self._transition(snapshot_id, SnapshotLifecycleState.WITHDRAWN, reason_code, event_timestamp)

    def invalidate_snapshot(self, snapshot_id: str, *, reason_code: str, event_timestamp: datetime) -> SnapshotLifecycleOutcome:
        return self._transition(snapshot_id, SnapshotLifecycleState.INVALIDATED, reason_code, event_timestamp)

    def _transition(
        self,
        snapshot_id: str,
        state: SnapshotLifecycleState,
        reason_code: str,
        timestamp: datetime,
    ) -> SnapshotLifecycleOutcome:
        try:
            reason = self._validator.normalize_reason_code(reason_code)
            timestamp = self._validator.normalize_event_timestamp(timestamp)
            current = self.repository.current_state(snapshot_id)
            if current is state:
                return SnapshotLifecycleOutcome(
                    snapshot_id, state, SnapshotLifecycleResultStatus.IDEMPOTENT_EXISTING,
                    reason, timestamp
                )
            event = (
                self.repository.withdraw_snapshot(snapshot_id, reason, timestamp)
                if state is SnapshotLifecycleState.WITHDRAWN
                else self.repository.invalidate_snapshot(snapshot_id, reason, timestamp)
            )
            return SnapshotLifecycleOutcome(
                snapshot_id, event.event_type, SnapshotLifecycleResultStatus.APPLIED,
                event.reason_code, event.event_timestamp
            )
        except (SnapshotValidationError, SnapshotConflictError):
            return SnapshotLifecycleOutcome(
                snapshot_id, None, SnapshotLifecycleResultStatus.CONFLICT,
                "INVALID_LIFECYCLE_TRANSITION", timestamp
            )
        except SnapshotPersistenceError:
            return SnapshotLifecycleOutcome(
                snapshot_id, None, SnapshotLifecycleResultStatus.PERSISTENCE_FAILURE,
                "SNAPSHOT_PERSISTENCE_FAILURE", timestamp
            )

    @staticmethod
    def _outcome(
        snapshot: MatchDataSnapshotVersion,
        status: SnapshotRegistrationStatus,
        reasons: tuple[str, ...],
        explanations: tuple[str, ...],
        previous_snapshot_id: str | None = None,
    ) -> MatchDataSnapshotRegistrationOutcome:
        command = snapshot.prepared.command
        return MatchDataSnapshotRegistrationOutcome(
            snapshot.snapshot_id, command.match_id,
            snapshot.logical_identity_fingerprint, snapshot.content_fingerprint,
            snapshot.snapshot_version, status, reasons, explanations,
            previous_snapshot_id, command.snapshot_effective_timestamp,
            command.registration_timestamp,
        )

    @staticmethod
    def _blocked(
        prepared: PreparedMatchDataSnapshot,
        status: SnapshotRegistrationStatus,
        reason: str,
        explanation: str,
    ) -> MatchDataSnapshotRegistrationOutcome:
        command = prepared.command
        return MatchDataSnapshotRegistrationOutcome(
            None, command.match_id, prepared.logical_identity_fingerprint,
            prepared.content_fingerprint, None, status, (reason,), (explanation,),
            None, command.snapshot_effective_timestamp, command.registration_timestamp,
        )


def register_match_data_snapshot(
    service: MatchDataSnapshotService,
    command: MatchDataSnapshotRegistrationCommand,
) -> MatchDataSnapshotRegistrationOutcome:
    """Explicit supplied-data boundary; performs no external I/O."""
    return service.register_match_data_snapshot(command)
