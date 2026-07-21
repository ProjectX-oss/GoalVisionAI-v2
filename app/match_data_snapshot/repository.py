import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal

from app.database import Database, MigrationManager

from .exceptions import SnapshotConflictError, SnapshotPersistenceError
from .models import (
    AggregateRecord,
    FormRecord,
    HeadToHeadRecord,
    MatchContextRecord,
    MatchDataSnapshotRegistrationCommand,
    MatchDataSnapshotVersion,
    MatchSnapshotStatus,
    OddsContextRecord,
    PreparedMatchDataSnapshot,
    SeasonAggregateRecord,
    SnapshotLifecycleEvent,
    SnapshotLifecycleState,
    SnapshotVersionRegistration,
    TeamAvailabilityRecord,
    VenueSplitRecord,
)
from .normalization import canonical_json


class SQLiteMatchDataSnapshotRepository:
    """Transaction-safe append-only snapshot history."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def register_snapshot(
        self,
        prepared: PreparedMatchDataSnapshot,
    ) -> SnapshotVersionRegistration:
        for attempt in range(100):
            try:
                return self._register_once(prepared)
            except SnapshotPersistenceError as exc:
                if not _locked(exc.__cause__) or attempt == 99:
                    raise
                time.sleep(0)
        raise SnapshotPersistenceError("Snapshot registration retry exhausted.")

    def _register_once(self, prepared: PreparedMatchDataSnapshot) -> SnapshotVersionRegistration:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._by_content(prepared.content_fingerprint)
            if existing is not None:
                self._connection.commit()
                return SnapshotVersionRegistration(existing, None, True)
            previous = self._active(prepared.logical_identity_fingerprint)
            if previous is not None and (
                prepared.command.snapshot_effective_timestamp
                < previous.prepared.command.snapshot_effective_timestamp
            ):
                raise SnapshotConflictError(
                    "An older effective snapshot cannot supersede the active version."
                )
            row = self._connection.execute(
                """
                SELECT COALESCE(MAX(snapshot_version), 0)
                FROM match_data_snapshot_versions
                WHERE logical_identity_fingerprint = ?
                """,
                (prepared.logical_identity_fingerprint,),
            ).fetchone()
            version = int(row[0]) + 1
            snapshot = MatchDataSnapshotVersion(
                _snapshot_id(prepared, version), version, prepared
            )
            self._insert_version(snapshot)
            if previous is not None:
                self._insert_event(self._event(
                    previous,
                    SnapshotLifecycleState.SUPERSEDED,
                    "MATERIAL_SNAPSHOT_CHANGE",
                    prepared.command.registration_timestamp,
                    None,
                    self._next_sequence(previous.snapshot_id),
                ))
            self._insert_event(self._event(
                snapshot,
                SnapshotLifecycleState.ACTIVE,
                "REGISTERED",
                prepared.command.registration_timestamp,
                previous.snapshot_id if previous is not None else None,
                1,
            ))
            self._connection.commit()
            return SnapshotVersionRegistration(snapshot, previous, False)
        except SnapshotConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise SnapshotPersistenceError("Snapshot append transaction failed.") from exc

    def find_by_content_fingerprint(self, fingerprint: str) -> MatchDataSnapshotVersion | None:
        try:
            return self._by_content(fingerprint)
        except sqlite3.DatabaseError as exc:
            raise SnapshotPersistenceError("Snapshot fingerprint lookup failed.") from exc

    def find_latest_active_snapshot(
        self,
        logical_identity_fingerprint: str,
    ) -> MatchDataSnapshotVersion | None:
        try:
            return self._active(logical_identity_fingerprint)
        except sqlite3.DatabaseError as exc:
            raise SnapshotPersistenceError("Active snapshot lookup failed.") from exc

    def find_snapshot_by_id(self, snapshot_id: str) -> MatchDataSnapshotVersion | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM match_data_snapshot_versions WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            return _from_row(row) if row is not None else None
        except sqlite3.DatabaseError as exc:
            raise SnapshotPersistenceError("Snapshot identity lookup failed.") from exc

    def list_snapshot_versions(
        self,
        logical_identity_fingerprint: str,
    ) -> tuple[MatchDataSnapshotVersion, ...]:
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM match_data_snapshot_versions
                WHERE logical_identity_fingerprint = ?
                ORDER BY snapshot_version, snapshot_id
                """,
                (logical_identity_fingerprint,),
            ).fetchall()
            return tuple(_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise SnapshotPersistenceError("Snapshot history lookup failed.") from exc

    def withdraw_snapshot(
        self,
        snapshot_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> SnapshotLifecycleEvent:
        return self._transition(
            snapshot_id, SnapshotLifecycleState.WITHDRAWN, reason_code, event_timestamp
        )

    def invalidate_snapshot(
        self,
        snapshot_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> SnapshotLifecycleEvent:
        return self._transition(
            snapshot_id, SnapshotLifecycleState.INVALIDATED, reason_code, event_timestamp
        )

    def list_active_snapshots_by_kickoff_window(
        self,
        start: datetime,
        end: datetime,
    ) -> tuple[MatchDataSnapshotVersion, ...]:
        try:
            if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
                raise ValueError("Kickoff window timestamps must be timezone-aware.")
            start = start.astimezone(timezone.utc)
            end = end.astimezone(timezone.utc)
            rows = self._connection.execute(
                """
                SELECT v.* FROM match_data_snapshot_versions v
                JOIN match_data_snapshot_lifecycle_events e
                  ON e.snapshot_id = v.snapshot_id
                WHERE e.event_sequence = (
                    SELECT MAX(e2.event_sequence)
                    FROM match_data_snapshot_lifecycle_events e2
                    WHERE e2.snapshot_id = v.snapshot_id
                )
                  AND e.event_type = 'ACTIVE'
                  AND v.kickoff_timestamp >= ? AND v.kickoff_timestamp <= ?
                ORDER BY v.kickoff_timestamp, v.match_id, v.snapshot_id
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return tuple(_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise SnapshotPersistenceError("Kickoff window lookup failed.") from exc

    def current_state(self, snapshot_id: str) -> SnapshotLifecycleState | None:
        row = self._connection.execute(
            """
            SELECT event_type FROM match_data_snapshot_lifecycle_events
            WHERE snapshot_id = ? ORDER BY event_sequence DESC LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        return SnapshotLifecycleState(row[0]) if row is not None else None

    def _transition(
        self,
        snapshot_id: str,
        state: SnapshotLifecycleState,
        reason_code: str,
        timestamp: datetime,
    ) -> SnapshotLifecycleEvent:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            snapshot = self.find_snapshot_by_id(snapshot_id)
            if snapshot is None:
                raise SnapshotConflictError("Snapshot does not exist.")
            latest = self._latest_event(snapshot_id)
            if latest is None:
                raise SnapshotConflictError("Snapshot lifecycle is missing.")
            if latest.event_type is state:
                self._connection.commit()
                return latest
            if latest.event_type is not SnapshotLifecycleState.ACTIVE:
                raise SnapshotConflictError("Only an ACTIVE snapshot can transition.")
            event = self._event(
                snapshot,
                state,
                reason_code,
                timestamp,
                None,
                latest.event_sequence + 1,
            )
            self._insert_event(event)
            self._connection.commit()
            return event
        except SnapshotConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise SnapshotPersistenceError("Snapshot lifecycle append failed.") from exc

    def _by_content(self, fingerprint: str) -> MatchDataSnapshotVersion | None:
        row = self._connection.execute(
            "SELECT * FROM match_data_snapshot_versions WHERE content_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def _active(self, logical: str) -> MatchDataSnapshotVersion | None:
        row = self._connection.execute(
            """
            SELECT v.* FROM match_data_snapshot_versions v
            JOIN match_data_snapshot_lifecycle_events e ON e.snapshot_id = v.snapshot_id
            WHERE v.logical_identity_fingerprint = ?
              AND e.event_sequence = (
                SELECT MAX(e2.event_sequence)
                FROM match_data_snapshot_lifecycle_events e2
                WHERE e2.snapshot_id = v.snapshot_id
              )
              AND e.event_type = 'ACTIVE'
            ORDER BY v.snapshot_version DESC LIMIT 1
            """,
            (logical,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def _insert_version(self, snapshot: MatchDataSnapshotVersion) -> None:
        command = snapshot.prepared.command
        self._connection.execute(
            """
            INSERT INTO match_data_snapshot_versions (
                snapshot_id, logical_identity_fingerprint, content_fingerprint,
                snapshot_version, match_id, source_provider, source_event_id,
                source_snapshot_id, kickoff_timestamp, effective_timestamp,
                source_updated_timestamp, registration_timestamp,
                lifecycle_state_at_creation, deterministic_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.logical_identity_fingerprint,
                snapshot.content_fingerprint,
                snapshot.snapshot_version,
                command.match_id,
                command.source_provider,
                command.source_event_id,
                command.source_snapshot_id,
                command.kickoff_timestamp.isoformat(),
                command.snapshot_effective_timestamp.isoformat(),
                command.source_updated_timestamp.isoformat(),
                command.registration_timestamp.isoformat(),
                SnapshotLifecycleState.ACTIVE.value,
                snapshot.prepared.deterministic_snapshot,
            ),
        )

    def _insert_event(self, event: SnapshotLifecycleEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO match_data_snapshot_lifecycle_events (
                event_id, snapshot_id, event_sequence, event_type, reason_code,
                previous_snapshot_id, event_timestamp, event_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.snapshot_id,
                event.event_sequence,
                event.event_type.value,
                event.reason_code,
                event.previous_snapshot_id,
                event.event_timestamp.isoformat(),
                event.event_snapshot,
            ),
        )

    def _latest_event(self, snapshot_id: str) -> SnapshotLifecycleEvent | None:
        row = self._connection.execute(
            """
            SELECT * FROM match_data_snapshot_lifecycle_events
            WHERE snapshot_id = ? ORDER BY event_sequence DESC LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        return _event_from_row(row) if row is not None else None

    def _next_sequence(self, snapshot_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(event_sequence), 0) FROM match_data_snapshot_lifecycle_events WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return int(row[0]) + 1

    @staticmethod
    def _event(
        snapshot: MatchDataSnapshotVersion,
        state: SnapshotLifecycleState,
        reason: str,
        timestamp: datetime,
        previous_snapshot_id: str | None,
        sequence: int,
    ) -> SnapshotLifecycleEvent:
        material = f"snapshot-event-v1|{snapshot.snapshot_id}|{sequence}|{state.value}|{reason}|{timestamp.isoformat()}|{previous_snapshot_id or ''}"
        event_id = "snapshot-event-" + hashlib.sha256(material.encode()).hexdigest()
        event_snapshot = canonical_json({
            "content_fingerprint": snapshot.content_fingerprint,
            "event_type": state.value,
            "previous_snapshot_id": previous_snapshot_id,
            "reason_code": reason,
            "snapshot_version": snapshot.snapshot_version,
        })
        return SnapshotLifecycleEvent(
            event_id, snapshot.snapshot_id, sequence, state, reason,
            previous_snapshot_id, timestamp, event_snapshot
        )


def _snapshot_id(prepared: PreparedMatchDataSnapshot, version: int) -> str:
    material = f"match-snapshot-v1|{prepared.logical_identity_fingerprint}|{prepared.content_fingerprint}|{version}"
    return "match-snapshot-" + hashlib.sha256(material.encode()).hexdigest()


def _from_row(row: sqlite3.Row) -> MatchDataSnapshotVersion:
    command = _command_from_json(row["deterministic_snapshot"])
    prepared = PreparedMatchDataSnapshot(
        row["logical_identity_fingerprint"],
        row["content_fingerprint"],
        command,
        row["deterministic_snapshot"],
    )
    return MatchDataSnapshotVersion(row["snapshot_id"], row["snapshot_version"], prepared)


def _command_from_json(payload: str) -> MatchDataSnapshotRegistrationCommand:
    data = json.loads(payload)
    dt = lambda value: datetime.fromisoformat(value) if value is not None else None
    dec = lambda value: Decimal(value) if value is not None else None

    def record(name: str, cls: type, decimal_fields: tuple[str, ...] = (), datetime_fields: tuple[str, ...] = ()):
        raw = data.get(name)
        if raw is None:
            return None
        for field in decimal_fields:
            raw[field] = dec(raw.get(field))
        for field in datetime_fields:
            raw[field] = dt(raw.get(field))
        return cls(**raw)

    def season(name: str):
        raw = data.get(name)
        if raw is None:
            return None
        raw["expected_goals_for"] = dec(raw.get("expected_goals_for"))
        raw["expected_goals_against"] = dec(raw.get("expected_goals_against"))
        raw["home_record"] = AggregateRecord(**raw["home_record"]) if raw.get("home_record") else None
        raw["away_record"] = AggregateRecord(**raw["away_record"]) if raw.get("away_record") else None
        return SeasonAggregateRecord(**raw)

    context = data.get("context")
    if context is not None:
        context["home_travel_distance"] = dec(context.get("home_travel_distance"))
        context["away_travel_distance"] = dec(context.get("away_travel_distance"))
        context = MatchContextRecord(**context)
    odds = data.get("odds_snapshot")
    if odds is not None:
        odds["market_line"] = dec(odds.get("market_line"))
        odds["decimal_odds"] = dec(odds["decimal_odds"])
        odds["odds_timestamp"] = dt(odds["odds_timestamp"])
        odds = OddsContextRecord(**odds)
    return MatchDataSnapshotRegistrationCommand(
        source_provider=data["source_provider"], source_event_id=data["source_event_id"],
        source_snapshot_id=data["source_snapshot_id"], match_id=data["match_id"],
        competition_id=data.get("competition_id"), competition_name=data["competition_name"],
        season_identifier=data["season_identifier"], home_team_id=data.get("home_team_id"),
        home_team_name=data["home_team_name"], away_team_id=data.get("away_team_id"),
        away_team_name=data["away_team_name"], kickoff_timestamp=dt(data["kickoff_timestamp"]),
        snapshot_effective_timestamp=dt(data["snapshot_effective_timestamp"]),
        source_updated_timestamp=dt(data["source_updated_timestamp"]),
        registration_timestamp=dt(data["registration_timestamp"]),
        scheduled_status=MatchSnapshotStatus(data["scheduled_status"]),
        postponed_indicator=data["postponed_indicator"], cancelled_indicator=data["cancelled_indicator"],
        neutral_venue_indicator=data["neutral_venue_indicator"], venue=data.get("venue"),
        home_recent_form=record("home_recent_form", FormRecord, ("expected_goals_for", "expected_goals_against", "possession")),
        away_recent_form=record("away_recent_form", FormRecord, ("expected_goals_for", "expected_goals_against", "possession")),
        home_venue_split=record("home_venue_split", VenueSplitRecord, ("expected_goals_for", "expected_goals_against")),
        away_venue_split=record("away_venue_split", VenueSplitRecord, ("expected_goals_for", "expected_goals_against")),
        home_season_aggregate=season("home_season_aggregate"), away_season_aggregate=season("away_season_aggregate"),
        head_to_head=record("head_to_head", HeadToHeadRecord, (), ("most_recent_match_timestamp",)),
        home_availability=record("home_availability", TeamAvailabilityRecord, (), ("lineup_source_timestamp", "injury_source_timestamp")),
        away_availability=record("away_availability", TeamAvailabilityRecord, (), ("lineup_source_timestamp", "injury_source_timestamp")),
        context=context, odds_snapshot=odds, is_live=data["is_live"],
    )


def _event_from_row(row: sqlite3.Row) -> SnapshotLifecycleEvent:
    return SnapshotLifecycleEvent(
        row["event_id"], row["snapshot_id"], row["event_sequence"],
        SnapshotLifecycleState(row["event_type"]), row["reason_code"],
        row["previous_snapshot_id"], datetime.fromisoformat(row["event_timestamp"]),
        row["event_snapshot"],
    )


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.DatabaseError:
        pass


def _locked(error: BaseException | None) -> bool:
    return isinstance(error, sqlite3.OperationalError) and "locked" in str(error).lower()
