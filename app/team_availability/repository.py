import sqlite3
from datetime import datetime
from decimal import Decimal

from app.database import Database, MigrationManager

from .models import (
    AvailabilityReason,
    AvailabilityReliability,
    AvailabilitySource,
    FixtureTeamSide,
    LineupObservation,
    LineupPlayer,
    LineupStatus,
    LineupType,
    PlayerAvailabilityObservation,
    PlayerAvailabilityStatus,
    PlayerIdentity,
    TeamIdentity,
)


class SQLiteTeamAvailabilityRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._connection = database.connection
        MigrationManager(self._connection).migrate()

    def save_source(self, source: AvailabilitySource) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO availability_sources (
                    source_id, source_name, priority, reliability_status, enabled
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    priority=excluded.priority,
                    reliability_status=excluded.reliability_status,
                    enabled=excluded.enabled
                """,
                (
                    source.source_id,
                    source.source_name,
                    source.priority,
                    source.reliability.value,
                    int(source.enabled),
                ),
            )

    def get_source(self, value: str) -> AvailabilitySource | None:
        row = self._connection.execute(
            """
            SELECT * FROM availability_sources
            WHERE source_id = ? OR lower(source_name) = lower(?)
            """,
            (value, value),
        ).fetchone()
        return self._source(row) if row else None

    def insert_player(self, item: PlayerAvailabilityObservation) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO player_availability_observations (
                    observation_id, fixture_id, competition, team_id, team_name,
                    player_id, player_name, player_identity_key,
                    fixture_team_side, availability_status, reason,
                    provider_reason_text, observed_at, source_name,
                    source_reference, expected_return_at, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    item.observation_id,
                    item.fixture_id,
                    item.competition,
                    item.team.team_id,
                    item.team.team_name,
                    item.player.player_id,
                    item.player.player_name,
                    item.player.identity_key,
                    item.fixture_team_side.value,
                    item.availability_status.value,
                    item.reason.value,
                    item.provider_reason_text,
                    item.observed_at.isoformat(),
                    item.source_name,
                    item.source_reference,
                    _dt(item.expected_return_at),
                    _decimal(item.confidence),
                    item.created_at.isoformat(),
                ),
            )
        return cursor.rowcount == 1

    def insert_lineup(self, item: LineupObservation) -> bool:
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO lineup_observations (
                        lineup_observation_id, fixture_id, competition,
                        team_id, team_name, fixture_team_side, lineup_status,
                        lineup_type, observed_at, source_name, source_reference,
                        formation, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        item.lineup_observation_id,
                        item.fixture_id,
                        item.competition,
                        item.team.team_id,
                        item.team.team_name,
                        item.fixture_team_side.value,
                        item.lineup_status.value,
                        item.lineup_type.value,
                        item.observed_at.isoformat(),
                        item.source_name,
                        item.source_reference,
                        item.formation,
                        item.created_at.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    return False
                self._connection.executemany(
                    """
                    INSERT INTO lineup_players (
                        lineup_observation_id, player_identity_key, player_id,
                        player_name, role, position, shirt_number, is_starting,
                        is_captain, is_goalkeeper, source_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(
                        (
                            item.lineup_observation_id,
                            player.player.identity_key,
                            player.player.player_id,
                            player.player.player_name,
                            player.role,
                            player.position,
                            player.shirt_number,
                            int(player.is_starting),
                            (
                                None
                                if player.is_captain is None
                                else int(player.is_captain)
                            ),
                            int(player.is_goalkeeper),
                            player.source_order,
                        )
                        for player in item.players
                    ),
                )
            return True
        except sqlite3.DatabaseError:
            raise

    def player_observations(
        self,
        fixture_id: str,
        team_id: str,
        *,
        cutoff: datetime | None = None,
        player_key: str | None = None,
    ) -> tuple[PlayerAvailabilityObservation, ...]:
        clauses = ["fixture_id = ?", "team_id = ?"]
        values: list[object] = [fixture_id, team_id]
        if cutoff is not None:
            clauses.append("observed_at <= ?")
            values.append(cutoff.isoformat())
        if player_key is not None:
            clauses.append("player_identity_key = ?")
            values.append(player_key)
        rows = self._connection.execute(
            f"""
            SELECT * FROM player_availability_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at, source_name, observation_id
            """,
            tuple(values),
        )
        return tuple(self._player(row) for row in rows)

    def lineup_observations(
        self,
        fixture_id: str,
        team_id: str,
        *,
        cutoff: datetime | None = None,
        status: LineupStatus | None = None,
    ) -> tuple[LineupObservation, ...]:
        clauses = ["fixture_id = ?", "team_id = ?"]
        values: list[object] = [fixture_id, team_id]
        if cutoff is not None:
            clauses.append("observed_at <= ?")
            values.append(cutoff.isoformat())
        if status is not None:
            clauses.append("lineup_status = ?")
            values.append(status.value)
        rows = self._connection.execute(
            f"""
            SELECT * FROM lineup_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at, source_name, lineup_observation_id
            """,
            tuple(values),
        )
        return tuple(self._lineup(row) for row in rows)

    def latest_player_before(
        self,
        fixture_id: str,
        team_id: str,
        player_key: str,
        cutoff: datetime,
    ) -> tuple[PlayerAvailabilityObservation, ...]:
        observations = self.player_observations(
            fixture_id,
            team_id,
            cutoff=cutoff,
            player_key=player_key,
        )
        if not observations:
            return ()
        latest_at = observations[-1].observed_at
        return tuple(item for item in observations if item.observed_at == latest_at)

    def latest_lineup_before(
        self,
        fixture_id: str,
        team_id: str,
        cutoff: datetime,
    ) -> LineupObservation | None:
        values = self.lineup_observations(fixture_id, team_id, cutoff=cutoff)
        return values[-1] if values else None

    def _lineup(self, row: sqlite3.Row) -> LineupObservation:
        players = self._connection.execute(
            """
            SELECT * FROM lineup_players
            WHERE lineup_observation_id = ?
            ORDER BY source_order, player_identity_key
            """,
            (row["lineup_observation_id"],),
        )
        return LineupObservation(
            lineup_observation_id=row["lineup_observation_id"],
            fixture_id=row["fixture_id"],
            competition=row["competition"],
            team=TeamIdentity(row["team_id"], row["team_name"]),
            fixture_team_side=FixtureTeamSide(row["fixture_team_side"]),
            lineup_status=LineupStatus(row["lineup_status"]),
            lineup_type=LineupType(row["lineup_type"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            source_name=row["source_name"],
            source_reference=row["source_reference"],
            formation=row["formation"],
            players=tuple(self._lineup_player(item) for item in players),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _player(row: sqlite3.Row) -> PlayerAvailabilityObservation:
        return PlayerAvailabilityObservation(
            observation_id=row["observation_id"],
            fixture_id=row["fixture_id"],
            competition=row["competition"],
            team=TeamIdentity(row["team_id"], row["team_name"]),
            player=PlayerIdentity(row["player_id"], row["player_name"]),
            fixture_team_side=FixtureTeamSide(row["fixture_team_side"]),
            availability_status=PlayerAvailabilityStatus(
                row["availability_status"]
            ),
            reason=AvailabilityReason(row["reason"]),
            provider_reason_text=row["provider_reason_text"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            source_name=row["source_name"],
            source_reference=row["source_reference"],
            expected_return_at=(
                datetime.fromisoformat(row["expected_return_at"])
                if row["expected_return_at"]
                else None
            ),
            confidence=(
                Decimal(row["confidence"]) if row["confidence"] else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _lineup_player(row: sqlite3.Row) -> LineupPlayer:
        return LineupPlayer(
            player=PlayerIdentity(row["player_id"], row["player_name"]),
            role=row["role"],
            position=row["position"],
            shirt_number=row["shirt_number"],
            is_starting=bool(row["is_starting"]),
            is_captain=(
                None if row["is_captain"] is None else bool(row["is_captain"])
            ),
            is_goalkeeper=bool(row["is_goalkeeper"]),
            source_order=row["source_order"],
        )

    @staticmethod
    def _source(row: sqlite3.Row) -> AvailabilitySource:
        return AvailabilitySource(
            source_id=row["source_id"],
            source_name=row["source_name"],
            priority=row["priority"],
            reliability=AvailabilityReliability(row["reliability_status"]),
            enabled=bool(row["enabled"]),
        )


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
