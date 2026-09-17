import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.database import Database, MigrationManager

from .models import (
    ClosingOddsRecord,
    ClosingSelectionPath,
    OddsMarket,
    OddsObservation,
    OddsReliability,
    OddsSelection,
    OddsSource,
    OddsSourceType,
)


class OddsRepository(Protocol):
    def save_source(self, source: OddsSource) -> None: ...
    def get_source(self, source_name: str) -> OddsSource | None: ...
    def insert_observation(self, observation: OddsObservation) -> bool: ...


class SQLiteOddsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._connection = database.connection
        MigrationManager(self._connection).migrate()

    def save_source(self, source: OddsSource) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO odds_sources (
                    source_id, source_name, source_type, priority,
                    reliability_status, commission_applies,
                    default_commission, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_type = excluded.source_type,
                    priority = excluded.priority,
                    reliability_status = excluded.reliability_status,
                    commission_applies = excluded.commission_applies,
                    default_commission = excluded.default_commission,
                    enabled = excluded.enabled
                """,
                (
                    source.source_id,
                    source.source_name,
                    source.source_type.value,
                    source.priority,
                    source.reliability.value,
                    int(source.commission_applies),
                    _text(source.default_commission),
                    int(source.enabled),
                ),
            )

    def get_source(self, source_name: str) -> OddsSource | None:
        row = self._connection.execute(
            """
            SELECT * FROM odds_sources
            WHERE lower(source_name) = lower(?) OR source_id = ?
            """,
            (source_name, source_name),
        ).fetchone()
        return self._source(row) if row is not None else None

    def sources(self) -> tuple[OddsSource, ...]:
        rows = self._connection.execute(
            "SELECT * FROM odds_sources ORDER BY priority, source_id"
        )
        return tuple(self._source(row) for row in rows)

    def insert_observation(self, observation: OddsObservation) -> bool:
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO odds_observations (
                        observation_id, fixture_id, competition, kickoff_time,
                        observed_at, source_name, source_type,
                        bookmaker_or_exchange, market, selection_id,
                        selection_name, selection_line, decimal_odds,
                        available_limit, currency, is_exchange,
                        commission_rate, raw_provider_reference, created_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    self._observation_values(observation),
                )
            return cursor.rowcount == 1
        except sqlite3.DatabaseError:
            raise

    def get_observation(self, observation_id: str) -> OddsObservation | None:
        row = self._connection.execute(
            "SELECT * FROM odds_observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        return self._observation(row) if row is not None else None

    def observations(
        self,
        *,
        fixture_id: str | None = None,
        market: OddsMarket | None = None,
        selection_id: str | None = None,
        source_name: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[OddsObservation, ...]:
        clauses: list[str] = []
        values: list[object] = []
        for clause, value in (
            ("fixture_id = ?", fixture_id),
            ("market = ?", market.value if market is not None else None),
            ("selection_id = ?", selection_id),
            ("source_name = ?", source_name),
            ("observed_at >= ?", start_at.isoformat() if start_at else None),
            ("observed_at <= ?", end_at.isoformat() if end_at else None),
        ):
            if value is not None:
                clauses.append(clause)
                values.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"""
            SELECT * FROM odds_observations
            {where}
            ORDER BY observed_at, source_name, observation_id
            """,
            tuple(values),
        )
        return tuple(self._observation(row) for row in rows)

    def latest_before(
        self,
        fixture_id: str,
        market: OddsMarket,
        selection_id: str,
        cutoff: datetime,
        source_name: str | None = None,
    ) -> OddsObservation | None:
        source_clause = "AND source_name = ?" if source_name else ""
        values: tuple[object, ...] = (
            fixture_id,
            market.value,
            selection_id,
            cutoff.isoformat(),
            *((source_name,) if source_name else ()),
        )
        row = self._connection.execute(
            f"""
            SELECT * FROM odds_observations
            WHERE fixture_id = ? AND market = ? AND selection_id = ?
              AND observed_at < ? {source_clause}
            ORDER BY observed_at DESC, source_name, observation_id
            LIMIT 1
            """,
            values,
        ).fetchone()
        return self._observation(row) if row is not None else None

    def opening(
        self,
        fixture_id: str,
        market: OddsMarket,
        selection_id: str,
        source_name: str | None = None,
    ) -> OddsObservation | None:
        source_clause = "AND source_name = ?" if source_name else ""
        values: tuple[object, ...] = (
            fixture_id,
            market.value,
            selection_id,
            *((source_name,) if source_name else ()),
        )
        row = self._connection.execute(
            f"""
            SELECT * FROM odds_observations
            WHERE fixture_id = ? AND market = ? AND selection_id = ?
              {source_clause}
            ORDER BY observed_at, source_name, observation_id
            LIMIT 1
            """,
            values,
        ).fetchone()
        return self._observation(row) if row is not None else None

    def save_closing(self, record: ClosingOddsRecord) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO closing_odds (
                    closing_id, fixture_id, market, selection_id,
                    selection_name, selection_line, kickoff_time, selected_at,
                    closing_observed_at, decimal_odds, source_name, source_type,
                    selection_path, source_count, cutoff, observation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    record.closing_id,
                    record.fixture_id,
                    record.market.value,
                    record.selection.selection_id,
                    record.selection.name,
                    _text(record.selection.line),
                    record.kickoff_time.isoformat(),
                    record.selected_at.isoformat(),
                    record.closing_observed_at.isoformat(),
                    str(record.decimal_odds),
                    record.source_name,
                    record.source_type.value,
                    record.selection_path.value,
                    record.source_count,
                    record.cutoff.isoformat(),
                    record.observation_id,
                ),
            )
        return cursor.rowcount == 1

    def get_closing(
        self,
        fixture_id: str,
        market: OddsMarket,
        selection_id: str,
    ) -> ClosingOddsRecord | None:
        row = self._connection.execute(
            """
            SELECT * FROM closing_odds
            WHERE fixture_id = ? AND market = ? AND selection_id = ?
            """,
            (fixture_id, market.value, selection_id),
        ).fetchone()
        return self._closing(row) if row is not None else None

    @staticmethod
    def _source(row: sqlite3.Row) -> OddsSource:
        return OddsSource(
            source_id=row["source_id"],
            source_name=row["source_name"],
            source_type=OddsSourceType(row["source_type"]),
            priority=row["priority"],
            reliability=OddsReliability(row["reliability_status"]),
            commission_applies=bool(row["commission_applies"]),
            default_commission=_decimal(row["default_commission"]),
            enabled=bool(row["enabled"]),
        )

    @staticmethod
    def _observation_values(observation: OddsObservation) -> tuple[object, ...]:
        return (
            observation.observation_id,
            observation.fixture_id,
            observation.competition,
            observation.kickoff_time.isoformat(),
            observation.observed_at.isoformat(),
            observation.source_name,
            observation.source_type.value,
            observation.bookmaker_or_exchange,
            observation.market.value,
            observation.selection.selection_id,
            observation.selection.name,
            _text(observation.selection.line),
            str(observation.decimal_odds),
            _text(observation.available_limit),
            observation.currency,
            int(observation.is_exchange),
            _text(observation.commission_rate),
            observation.raw_provider_reference,
            observation.created_at.isoformat(),
        )

    @staticmethod
    def _observation(row: sqlite3.Row) -> OddsObservation:
        return OddsObservation(
            observation_id=row["observation_id"],
            fixture_id=row["fixture_id"],
            competition=row["competition"],
            kickoff_time=datetime.fromisoformat(row["kickoff_time"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            source_name=row["source_name"],
            source_type=OddsSourceType(row["source_type"]),
            bookmaker_or_exchange=row["bookmaker_or_exchange"],
            market=OddsMarket(row["market"]),
            selection=OddsSelection(
                row["selection_id"],
                row["selection_name"],
                _decimal(row["selection_line"]),
            ),
            decimal_odds=Decimal(row["decimal_odds"]),
            available_limit=_decimal(row["available_limit"]),
            currency=row["currency"],
            is_exchange=bool(row["is_exchange"]),
            commission_rate=_decimal(row["commission_rate"]),
            raw_provider_reference=row["raw_provider_reference"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _closing(row: sqlite3.Row) -> ClosingOddsRecord:
        return ClosingOddsRecord(
            closing_id=row["closing_id"],
            fixture_id=row["fixture_id"],
            market=OddsMarket(row["market"]),
            selection=OddsSelection(
                row["selection_id"],
                row["selection_name"],
                _decimal(row["selection_line"]),
            ),
            kickoff_time=datetime.fromisoformat(row["kickoff_time"]),
            selected_at=datetime.fromisoformat(row["selected_at"]),
            closing_observed_at=datetime.fromisoformat(row["closing_observed_at"]),
            decimal_odds=Decimal(row["decimal_odds"]),
            source_name=row["source_name"],
            source_type=OddsSourceType(row["source_type"]),
            selection_path=ClosingSelectionPath(row["selection_path"]),
            source_count=row["source_count"],
            cutoff=datetime.fromisoformat(row["cutoff"]),
            observation_id=row["observation_id"],
        )


def _decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
