import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import RiskProductScope

from .exceptions import (
    CandidateRegistryConflictError,
    CandidateRegistryPersistenceError,
)
from .fingerprint import canonical_decimal
from .models import (
    CandidateLifecycleEvent,
    CandidateLifecycleState,
    CandidateVersionRegistration,
    OfficialCandidateMarket,
    OfficialCandidateMarketIdentity,
    OfficialPredictionCandidateVersion,
    OfficialPredictionReasoningFact,
    PreparedOfficialPredictionCandidate,
    ReasoningFactType,
)


class SQLiteOfficialPredictionCandidateRepository:
    """Append-only candidate versions and lifecycle events."""

    _FILTERS = {
        "competition_id": "competition_id",
        "market": "normalized_market",
        "model_version": "model_version",
        "prediction_id": "prediction_id",
    }

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def register_candidate_version(
        self,
        candidate: PreparedOfficialPredictionCandidate,
    ) -> CandidateVersionRegistration:
        for attempt in range(100):
            try:
                return self._register_candidate_version_once(candidate)
            except CandidateRegistryPersistenceError as exc:
                if not _locked(exc.__cause__) or attempt == 99:
                    raise
                time.sleep(0)
        raise CandidateRegistryPersistenceError("Candidate registration retry exhausted.")

    def _register_candidate_version_once(
        self,
        candidate: PreparedOfficialPredictionCandidate,
    ) -> CandidateVersionRegistration:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._by_content(candidate.content_fingerprint)
            if existing is not None:
                if (
                    existing.prepared.normalized_snapshot
                    != candidate.normalized_snapshot
                ):
                    raise CandidateRegistryConflictError(
                        "Content fingerprint conflicts with different immutable facts."
                    )
                self._connection.commit()
                return CandidateVersionRegistration(existing, None, True)
            previous = self._active(candidate.logical_identity_fingerprint)
            if (
                previous is not None
                and candidate.registration_timestamp
                < previous.prepared.registration_timestamp
            ):
                raise CandidateRegistryConflictError(
                    "Candidate registration timestamp precedes the active version."
                )
            row = self._connection.execute(
                """
                SELECT COALESCE(MAX(candidate_version), 0)
                FROM official_prediction_candidate_versions
                WHERE logical_identity_fingerprint = ?
                """,
                (candidate.logical_identity_fingerprint,),
            ).fetchone()
            version = int(row[0]) + 1
            registry_id = _candidate_id(candidate, version)
            versioned = OfficialPredictionCandidateVersion(
                registry_candidate_id=registry_id,
                candidate_version=version,
                prepared=candidate,
            )
            self._insert_candidate(versioned)
            if previous is not None:
                superseded = self._make_event(
                    previous,
                    CandidateLifecycleState.SUPERSEDED,
                    "MATERIAL_CANDIDATE_CHANGE",
                    candidate.registration_timestamp,
                    previous_candidate_id=None,
                    event_sequence=self._next_sequence(previous.registry_candidate_id),
                )
                self._insert_event(superseded)
            ready = self._make_event(
                versioned,
                CandidateLifecycleState.READY,
                "REGISTERED",
                candidate.registration_timestamp,
                previous_candidate_id=(
                    previous.registry_candidate_id if previous is not None else None
                ),
                event_sequence=1,
            )
            self._insert_event(ready)
            self._connection.commit()
        except CandidateRegistryConflictError:
            _rollback_safely(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback_safely(self._connection)
            raise CandidateRegistryPersistenceError(
                "Candidate version transaction failed."
            ) from exc
        return CandidateVersionRegistration(versioned, previous, False)

    def find_by_content_fingerprint(
        self,
        content_fingerprint: str,
    ) -> OfficialPredictionCandidateVersion | None:
        for attempt in range(100):
            try:
                return self._by_content(content_fingerprint)
            except sqlite3.OperationalError as exc:
                if not _locked(exc) or attempt == 99:
                    raise CandidateRegistryPersistenceError(
                        "Candidate fingerprint lookup failed."
                    ) from exc
                time.sleep(0)
            except sqlite3.DatabaseError as exc:
                raise CandidateRegistryPersistenceError(
                    "Candidate fingerprint lookup failed."
                ) from exc
        raise CandidateRegistryPersistenceError("Candidate lookup retry exhausted.")

    def find_active_ready_by_logical_identity(
        self,
        logical_identity_fingerprint: str,
    ) -> OfficialPredictionCandidateVersion | None:
        try:
            return self._active(logical_identity_fingerprint)
        except sqlite3.DatabaseError as exc:
            raise CandidateRegistryPersistenceError(
                "Active READY candidate lookup failed."
            ) from exc

    def find_candidate_by_id(
        self,
        registry_candidate_id: str,
    ) -> OfficialPredictionCandidateVersion | None:
        try:
            row = self._connection.execute(
                """
                SELECT * FROM official_prediction_candidate_versions
                WHERE registry_candidate_id = ?
                """,
                (registry_candidate_id,),
            ).fetchone()
            return _candidate_from_row(row) if row is not None else None
        except sqlite3.DatabaseError as exc:
            raise CandidateRegistryPersistenceError(
                "Candidate identity lookup failed."
            ) from exc

    def list_candidate_versions(
        self,
        logical_identity_fingerprint: str,
    ) -> tuple[OfficialPredictionCandidateVersion, ...]:
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM official_prediction_candidate_versions
                WHERE logical_identity_fingerprint = ?
                ORDER BY candidate_version, registry_candidate_id
                """,
                (logical_identity_fingerprint,),
            ).fetchall()
            return tuple(_candidate_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise CandidateRegistryPersistenceError(
                "Candidate version history lookup failed."
            ) from exc

    def append_lifecycle_event(
        self,
        event: CandidateLifecycleEvent,
    ) -> CandidateLifecycleEvent:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            candidate = self._candidate_by_id(event.registry_candidate_id)
            if candidate is None:
                raise CandidateRegistryConflictError("Lifecycle candidate is missing.")
            latest = self._latest_event(event.registry_candidate_id)
            if latest is None or latest.event_type is not CandidateLifecycleState.READY:
                raise CandidateRegistryConflictError(
                    "Only an active READY candidate can transition."
                )
            if event.event_type not in {
                CandidateLifecycleState.WITHDRAWN,
                CandidateLifecycleState.INVALIDATED,
            }:
                raise CandidateRegistryConflictError(
                    "Historical candidate versions cannot be reactivated in place."
                )
            expected = self._make_event(
                candidate,
                event.event_type,
                event.reason_code,
                event.event_timestamp,
                previous_candidate_id=None,
                event_sequence=latest.event_sequence + 1,
            )
            if event != expected:
                raise CandidateRegistryConflictError(
                    "Lifecycle event does not match its canonical append material."
                )
            self._insert_event(event)
            self._connection.commit()
        except CandidateRegistryConflictError:
            _rollback_safely(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback_safely(self._connection)
            raise CandidateRegistryPersistenceError(
                "Lifecycle event append failed."
            ) from exc
        return self._event(event.event_id)

    def withdraw_candidate(
        self,
        registry_candidate_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleEvent:
        return self._transition(
            registry_candidate_id,
            CandidateLifecycleState.WITHDRAWN,
            reason_code,
            event_timestamp,
        )

    def invalidate_candidate(
        self,
        registry_candidate_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleEvent:
        return self._transition(
            registry_candidate_id,
            CandidateLifecycleState.INVALIDATED,
            reason_code,
            event_timestamp,
        )

    def discover_ready_candidates(
        self,
        evaluated_at: datetime,
        normalized_filters: tuple[tuple[str, str], ...] = (),
    ) -> tuple[OfficialPredictionCandidateVersion, ...]:
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("Registry discovery timestamp must be timezone-aware.")
        evaluated_at = evaluated_at.astimezone(timezone.utc)
        clauses = [
            "e.event_type = 'READY'",
            "v.bankroll_scope = 'OFFICIAL'",
            "v.destination_scope = 'OFFICIAL'",
            "v.kickoff_timestamp > ?",
            "NOT EXISTS (SELECT 1 FROM official_prediction_candidate_lifecycle_events newer "
            "WHERE newer.registry_candidate_id = e.registry_candidate_id "
            "AND newer.event_sequence > e.event_sequence)",
        ]
        values: list[object] = [evaluated_at.isoformat()]
        seen: set[str] = set()
        for key, value in normalized_filters:
            if key not in self._FILTERS or key in seen:
                raise ValueError("Unsupported or duplicate registry discovery filter.")
            seen.add(key)
            clauses.append(f"v.{self._FILTERS[key]} = ?")
            values.append(value)
        try:
            rows = self._connection.execute(
                f"""
                SELECT v.*
                FROM official_prediction_candidate_versions v
                JOIN official_prediction_candidate_lifecycle_events e
                  ON e.registry_candidate_id = v.registry_candidate_id
                WHERE {' AND '.join(clauses)}
                ORDER BY v.kickoff_timestamp,
                         v.prediction_creation_timestamp,
                         v.prediction_id,
                         v.candidate_version,
                         v.registry_candidate_id
                """,
                tuple(values),
            ).fetchall()
            return tuple(_candidate_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise CandidateRegistryPersistenceError(
                "READY candidate discovery failed."
            ) from exc

    def lifecycle_history(
        self,
        registry_candidate_id: str,
    ) -> tuple[CandidateLifecycleEvent, ...]:
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM official_prediction_candidate_lifecycle_events
                WHERE registry_candidate_id = ?
                ORDER BY event_sequence, event_id
                """,
                (registry_candidate_id,),
            ).fetchall()
            return tuple(_event_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise CandidateRegistryPersistenceError(
                "Lifecycle history lookup failed."
            ) from exc

    def current_state(
        self,
        registry_candidate_id: str,
    ) -> CandidateLifecycleState | None:
        row = self._connection.execute(
            """
            SELECT event_type
            FROM official_prediction_candidate_lifecycle_events
            WHERE registry_candidate_id = ?
            ORDER BY event_sequence DESC, event_id DESC
            LIMIT 1
            """,
            (registry_candidate_id,),
        ).fetchone()
        return CandidateLifecycleState(row[0]) if row is not None else None

    def _transition(
        self,
        registry_candidate_id: str,
        target: CandidateLifecycleState,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleEvent:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            candidate = self._candidate_by_id(registry_candidate_id)
            if candidate is None:
                raise CandidateRegistryConflictError("Candidate is missing.")
            latest = self._latest_event(registry_candidate_id)
            if latest is None or latest.event_type is not CandidateLifecycleState.READY:
                raise CandidateRegistryConflictError(
                    "Only an active READY candidate can transition."
                )
            if event_timestamp < latest.event_timestamp:
                raise CandidateRegistryConflictError(
                    "Lifecycle timestamp cannot precede existing history."
                )
            event = self._make_event(
                candidate,
                target,
                reason_code,
                event_timestamp,
                previous_candidate_id=None,
                event_sequence=latest.event_sequence + 1,
            )
            self._insert_event(event)
            self._connection.commit()
        except CandidateRegistryConflictError:
            _rollback_safely(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback_safely(self._connection)
            raise CandidateRegistryPersistenceError(
                "Candidate lifecycle transition failed."
            ) from exc
        return self._event(event.event_id)

    def _insert_candidate(self, value: OfficialPredictionCandidateVersion) -> None:
        item = value.prepared
        market = item.market_identity
        self._connection.execute(
            """
            INSERT INTO official_prediction_candidate_versions (
                registry_candidate_id, logical_identity_fingerprint,
                content_fingerprint, candidate_version, prediction_id,
                match_id, source_event_id, competition_id,
                competition_display_name, competition_normalized_name,
                home_team_id, home_team_display_name, home_team_normalized_name,
                away_team_id, away_team_display_name, away_team_normalized_name,
                kickoff_timestamp, prediction_creation_timestamp, model_version,
                normalized_market, normalized_selection, market_line,
                raw_model_probability, supplied_expected_value, decimal_odds,
                odds_timestamp, odds_source_id, core_match_data_timestamp,
                lineup_status, lineup_data_timestamp,
                injury_suspension_status, injury_suspension_data_timestamp,
                confidence_level, supporting_data_status, market_availability,
                reasoning_snapshot, source_data_version, bankroll_scope,
                destination_scope, lifecycle_state_at_creation,
                registration_timestamp, normalized_snapshot,
                provenance_snapshot, candidate_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?)
            """,
            (
                value.registry_candidate_id,
                item.logical_identity_fingerprint,
                item.content_fingerprint,
                value.candidate_version,
                item.prediction_id,
                item.match_id,
                item.source_event_id,
                item.competition_id,
                item.competition_name,
                item.normalized_competition_name,
                item.home_team_id,
                item.home_team_name,
                item.normalized_home_team_name,
                item.away_team_id,
                item.away_team_name,
                item.normalized_away_team_name,
                item.kickoff_timestamp.isoformat(),
                item.prediction_creation_timestamp.isoformat(),
                item.model_version,
                market.market.value,
                market.selection,
                _optional_decimal(market.market_line),
                canonical_decimal(item.raw_model_probability),
                canonical_decimal(item.supplied_expected_value),
                canonical_decimal(item.decimal_odds),
                item.odds_timestamp.isoformat(),
                item.odds_source_id,
                item.core_match_data_timestamp.isoformat(),
                item.lineup_status.value,
                _optional_timestamp(item.lineup_data_timestamp),
                item.injury_suspension_status.value,
                _optional_timestamp(item.injury_suspension_data_timestamp),
                item.confidence_level.value,
                item.supporting_data_status.value,
                item.market_availability.value,
                _reasoning_json(item.public_reasoning_facts),
                item.source_data_version,
                item.bankroll_scope.value,
                item.destination_scope.value,
                value.lifecycle_state_at_creation.value,
                item.registration_timestamp.isoformat(),
                _json([list(pair) for pair in item.normalized_snapshot]),
                _json([list(pair) for pair in item.provenance]),
                _candidate_json(value),
            ),
        )

    def _insert_event(self, event: CandidateLifecycleEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO official_prediction_candidate_lifecycle_events (
                event_id, registry_candidate_id, event_sequence, event_type,
                reason_code, previous_candidate_id, event_timestamp,
                event_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.registry_candidate_id,
                event.event_sequence,
                event.event_type.value,
                event.reason_code,
                event.previous_candidate_id,
                event.event_timestamp.isoformat(),
                _json([list(pair) for pair in event.event_snapshot]),
            ),
        )

    def _active(
        self,
        logical_identity_fingerprint: str,
    ) -> OfficialPredictionCandidateVersion | None:
        rows = self._connection.execute(
            """
            SELECT v.*
            FROM official_prediction_candidate_versions v
            JOIN official_prediction_candidate_lifecycle_events e
              ON e.registry_candidate_id = v.registry_candidate_id
            WHERE v.logical_identity_fingerprint = ?
              AND e.event_type = 'READY'
              AND NOT EXISTS (
                  SELECT 1
                  FROM official_prediction_candidate_lifecycle_events newer
                  WHERE newer.registry_candidate_id = e.registry_candidate_id
                    AND newer.event_sequence > e.event_sequence
              )
            ORDER BY v.candidate_version DESC, v.registry_candidate_id DESC
            """,
            (logical_identity_fingerprint,),
        ).fetchall()
        if len(rows) > 1:
            raise CandidateRegistryConflictError(
                "Multiple active READY versions violate registry history."
            )
        return _candidate_from_row(rows[0]) if rows else None

    def _by_content(
        self,
        content_fingerprint: str,
    ) -> OfficialPredictionCandidateVersion | None:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_candidate_versions
            WHERE content_fingerprint = ?
            """,
            (content_fingerprint,),
        ).fetchone()
        return _candidate_from_row(row) if row is not None else None

    def _candidate_by_id(
        self,
        registry_candidate_id: str,
    ) -> OfficialPredictionCandidateVersion | None:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_candidate_versions
            WHERE registry_candidate_id = ?
            """,
            (registry_candidate_id,),
        ).fetchone()
        return _candidate_from_row(row) if row is not None else None

    def _next_sequence(self, registry_candidate_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT COALESCE(MAX(event_sequence), 0)
            FROM official_prediction_candidate_lifecycle_events
            WHERE registry_candidate_id = ?
            """,
            (registry_candidate_id,),
        ).fetchone()
        return int(row[0]) + 1

    def _latest_event(self, registry_candidate_id: str) -> CandidateLifecycleEvent | None:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_candidate_lifecycle_events
            WHERE registry_candidate_id = ?
            ORDER BY event_sequence DESC, event_id DESC
            LIMIT 1
            """,
            (registry_candidate_id,),
        ).fetchone()
        return _event_from_row(row) if row is not None else None

    def _event(self, event_id: str) -> CandidateLifecycleEvent:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_candidate_lifecycle_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            raise CandidateRegistryPersistenceError("Stored lifecycle event is missing.")
        return _event_from_row(row)

    @staticmethod
    def _make_event(
        candidate: OfficialPredictionCandidateVersion,
        event_type: CandidateLifecycleState,
        reason_code: str,
        event_timestamp: datetime,
        *,
        previous_candidate_id: str | None,
        event_sequence: int,
    ) -> CandidateLifecycleEvent:
        material = (
            f"official-candidate-lifecycle-v1|{candidate.registry_candidate_id}|"
            f"{event_sequence}|{event_type.value}|{reason_code}|"
            f"{event_timestamp.isoformat()}|{previous_candidate_id or 'none'}"
        )
        event_id = "official-candidate-event-" + hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()
        snapshot = tuple(sorted({
            "candidate_version": str(candidate.candidate_version),
            "content_fingerprint": candidate.content_fingerprint,
            "event_type": event_type.value,
            "logical_identity_fingerprint": candidate.logical_identity_fingerprint,
            "previous_candidate_id": previous_candidate_id or "null",
            "reason_code": reason_code,
        }.items()))
        return CandidateLifecycleEvent(
            event_id,
            candidate.registry_candidate_id,
            event_sequence,
            event_type,
            reason_code,
            previous_candidate_id,
            event_timestamp,
            snapshot,
        )


def _candidate_id(candidate: PreparedOfficialPredictionCandidate, version: int) -> str:
    return (
        "official-registry-candidate-"
        f"{candidate.logical_identity_fingerprint[:16]}-v{version:06d}-"
        f"{candidate.content_fingerprint[:16]}"
    )


def _candidate_from_row(row: sqlite3.Row) -> OfficialPredictionCandidateVersion:
    market = OfficialCandidateMarketIdentity(
        OfficialCandidateMarket(row["normalized_market"]),
        row["normalized_selection"],
        Decimal(row["market_line"]) if row["market_line"] is not None else None,
    )
    prepared = PreparedOfficialPredictionCandidate(
        logical_identity_fingerprint=row["logical_identity_fingerprint"],
        content_fingerprint=row["content_fingerprint"],
        source_event_id=row["source_event_id"],
        prediction_id=row["prediction_id"],
        match_id=row["match_id"],
        competition_id=row["competition_id"],
        competition_name=row["competition_display_name"],
        normalized_competition_name=row["competition_normalized_name"],
        home_team_id=row["home_team_id"],
        home_team_name=row["home_team_display_name"],
        normalized_home_team_name=row["home_team_normalized_name"],
        away_team_id=row["away_team_id"],
        away_team_name=row["away_team_display_name"],
        normalized_away_team_name=row["away_team_normalized_name"],
        kickoff_timestamp=datetime.fromisoformat(row["kickoff_timestamp"]),
        prediction_creation_timestamp=datetime.fromisoformat(
            row["prediction_creation_timestamp"]
        ),
        model_version=row["model_version"],
        market_identity=market,
        raw_model_probability=Decimal(row["raw_model_probability"]),
        supplied_expected_value=Decimal(row["supplied_expected_value"]),
        decimal_odds=Decimal(row["decimal_odds"]),
        odds_timestamp=datetime.fromisoformat(row["odds_timestamp"]),
        odds_source_id=row["odds_source_id"],
        core_match_data_timestamp=datetime.fromisoformat(
            row["core_match_data_timestamp"]
        ),
        lineup_status=LineupStatus(row["lineup_status"]),
        lineup_data_timestamp=_datetime(row["lineup_data_timestamp"]),
        injury_suspension_status=FactStatus(row["injury_suspension_status"]),
        injury_suspension_data_timestamp=_datetime(
            row["injury_suspension_data_timestamp"]
        ),
        confidence_level=ConfidenceLevel(row["confidence_level"]),
        public_reasoning_facts=_reasoning_from_json(row["reasoning_snapshot"]),
        source_data_version=row["source_data_version"],
        supporting_data_status=FactStatus(row["supporting_data_status"]),
        market_availability=MarketAvailability(row["market_availability"]),
        bankroll_scope=RiskProductScope(row["bankroll_scope"]),
        destination_scope=RiskProductScope(row["destination_scope"]),
        registration_timestamp=datetime.fromisoformat(row["registration_timestamp"]),
        normalized_snapshot=tuple(
            (item[0], item[1]) for item in json.loads(row["normalized_snapshot"])
        ),
        provenance=tuple(
            (item[0], item[1])
            for item in json.loads(
                row["provenance_snapshot"]
                if "provenance_snapshot" in row.keys()
                else "[]"
            )
        ),
    )
    return OfficialPredictionCandidateVersion(
        row["registry_candidate_id"],
        row["candidate_version"],
        prepared,
        CandidateLifecycleState(row["lifecycle_state_at_creation"]),
    )


def _event_from_row(row: sqlite3.Row) -> CandidateLifecycleEvent:
    return CandidateLifecycleEvent(
        event_id=row["event_id"],
        registry_candidate_id=row["registry_candidate_id"],
        event_sequence=row["event_sequence"],
        event_type=CandidateLifecycleState(row["event_type"]),
        reason_code=row["reason_code"],
        previous_candidate_id=row["previous_candidate_id"],
        event_timestamp=datetime.fromisoformat(row["event_timestamp"]),
        event_snapshot=tuple(
            (item[0], item[1]) for item in json.loads(row["event_snapshot"])
        ),
    )


def _reasoning_json(values: tuple[OfficialPredictionReasoningFact, ...]) -> str:
    return _json([
        {
            "fact_type": item.fact_type.value,
            "source_reference": item.source_reference,
            "text": item.text,
        }
        for item in values
    ])


def _reasoning_from_json(value: str) -> tuple[OfficialPredictionReasoningFact, ...]:
    return tuple(
        OfficialPredictionReasoningFact(
            ReasoningFactType(item["fact_type"]),
            item["text"],
            item["source_reference"],
        )
        for item in json.loads(value)
    )


def _candidate_json(value: OfficialPredictionCandidateVersion) -> str:
    item = value.prepared
    return _json({
        "away_team_display_name": item.away_team_name,
        "away_team_id": item.away_team_id,
        "away_team_normalized_name": item.normalized_away_team_name,
        "bankroll_scope": item.bankroll_scope.value,
        "candidate_version": value.candidate_version,
        "competition_display_name": item.competition_name,
        "competition_id": item.competition_id,
        "competition_normalized_name": item.normalized_competition_name,
        "confidence_level": item.confidence_level.value,
        "content_fingerprint": item.content_fingerprint,
        "core_match_data_timestamp": item.core_match_data_timestamp.isoformat(),
        "decimal_odds": canonical_decimal(item.decimal_odds),
        "destination_scope": item.destination_scope.value,
        "home_team_display_name": item.home_team_name,
        "home_team_id": item.home_team_id,
        "home_team_normalized_name": item.normalized_home_team_name,
        "injury_suspension_data_timestamp": _optional_timestamp(
            item.injury_suspension_data_timestamp
        ),
        "injury_suspension_status": item.injury_suspension_status.value,
        "kickoff_timestamp": item.kickoff_timestamp.isoformat(),
        "lineup_data_timestamp": _optional_timestamp(item.lineup_data_timestamp),
        "lineup_status": item.lineup_status.value,
        "logical_identity_fingerprint": item.logical_identity_fingerprint,
        "market": item.market_identity.market.value,
        "market_availability": item.market_availability.value,
        "market_line": _optional_decimal(item.market_identity.market_line),
        "match_id": item.match_id,
        "model_version": item.model_version,
        "normalized_snapshot": [list(pair) for pair in item.normalized_snapshot],
        "odds_source_id": item.odds_source_id,
        "odds_timestamp": item.odds_timestamp.isoformat(),
        "prediction_id": item.prediction_id,
        "prediction_creation_timestamp": (
            item.prediction_creation_timestamp.isoformat()
        ),
        "provenance": [list(pair) for pair in item.provenance],
        "public_reasoning_facts": [
            {
                "fact_type": fact.fact_type.value,
                "source_reference": fact.source_reference,
                "text": fact.text,
            }
            for fact in item.public_reasoning_facts
        ],
        "raw_model_probability": canonical_decimal(item.raw_model_probability),
        "registry_candidate_id": value.registry_candidate_id,
        "registration_timestamp": item.registration_timestamp.isoformat(),
        "selection": item.market_identity.selection,
        "source_data_version": item.source_data_version,
        "source_event_id": item.source_event_id,
        "supplied_expected_value": canonical_decimal(
            item.supplied_expected_value
        ),
        "supporting_data_status": item.supporting_data_status.value,
    })


def _optional_decimal(value: Decimal | None) -> str | None:
    return canonical_decimal(value) if value is not None else None


def _optional_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _locked(error: BaseException | None) -> bool:
    return isinstance(error, sqlite3.OperationalError) and "locked" in str(error).lower()


def _rollback_safely(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.DatabaseError:
        pass
